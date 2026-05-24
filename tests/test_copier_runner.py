import json
from pathlib import Path

import yaml

from framework_cli.copier_runner import render_project

DATA = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def test_render_creates_expected_files(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    assert (dest / "pyproject.toml").is_file()
    assert (dest / "Taskfile.yml").is_file()
    assert (dest / ".copier-answers.yml").is_file()
    assert (dest / "src" / "demo" / "main.py").is_file()
    assert (dest / "src" / "demo" / "routes" / "health.py").is_file()
    assert (dest / "tests" / "functional" / "test_health.py").is_file()


def test_render_substitutes_package_name(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    main_py = (dest / "src" / "demo" / "main.py").read_text()
    assert "from demo.routes import include_routers" in main_py


def test_render_includes_coverage_config(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pytest-cov" in pyproject
    assert "[tool.coverage.run]" in pyproject

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:cov" in taskfile


def test_render_includes_precommit_config(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    cfg = dest / ".pre-commit-config.yaml"
    assert cfg.is_file()
    text = cfg.read_text()
    assert "ruff" in text
    assert "mypy" in text
    assert "gitleaks" in text
    # pins the hook id the no-Docker precommit acceptance test SKIPs (DB suite needs Docker)
    assert "coverage-threshold" in text

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pre-commit" in pyproject


def test_render_includes_claude_md(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    claude = dest / "CLAUDE.md"
    assert claude.is_file()
    text = claude.read_text()
    assert "<!-- FRAMEWORK:BEGIN -->" in text
    assert "<!-- FRAMEWORK:END -->" in text
    assert "Demo" in text
    assert "write the failing test first" in text.lower()


def test_render_readme_documents_gates(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    readme = (dest / "README.md").read_text()
    assert "Quality gates" in readme
    assert "task test:cov" in readme


def test_render_includes_claude_hooks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    settings = dest / ".claude" / "settings.json"
    assert settings.is_file()
    data = json.loads(settings.read_text())
    matchers = [group["matcher"] for group in data["hooks"]["PostToolUse"]]
    assert any("Edit" in m and "Write" in m for m in matchers)

    hook = dest / ".claude" / "hooks" / "lint_changed.py"
    assert hook.is_file()
    assert "tool_input" in hook.read_text()


def test_render_docs_mention_editor_hook(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "editor hook" in (dest / "CLAUDE.md").read_text().lower()
    assert ".claude/settings.json" in (dest / "README.md").read_text()


def test_render_includes_runtime_modules(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert (dest / "src" / "demo" / "config" / "settings.py").is_file()
    assert (dest / "src" / "demo" / "observability" / "metrics.py").is_file()
    assert (dest / "src" / "demo" / "observability" / "slo.py").is_file()
    assert (dest / "src" / "demo" / "logging_config.py").is_file()
    assert (dest / "src" / "demo" / "middleware" / "observability.py").is_file()
    health = (dest / "src" / "demo" / "routes" / "health.py").read_text()
    assert "build_health_report" in health


def test_render_includes_dockerfile_multistage(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    dockerfile = dest / "infra" / "docker" / "Dockerfile"
    assert dockerfile.is_file()
    text = dockerfile.read_text()
    # multi-stage: a builder stage and a runtime stage
    assert text.count("FROM ") >= 2
    assert " AS builder" in text
    assert "uv sync" in text
    # a .dockerignore at the build-context root keeps the host .venv out of the image
    assert ".venv" in (dest / ".dockerignore").read_text()


def test_render_compose_structure(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    base = yaml.safe_load((dest / "infra" / "compose" / "base.yml").read_text())
    app = base["services"]["app"]
    assert app["environment"]["TZ"] == "UTC"
    assert "healthcheck" in app
    assert "/heartbeat" in " ".join(app["healthcheck"]["test"])
    labels = "\n".join(app["labels"])
    assert "traefik.enable=true" in labels
    assert "demo.localhost" in labels

    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    assert "dev" in dev["services"]["app"]["profiles"]
    assert any("8000" in str(p) for p in dev["services"]["app"]["ports"])
    traefik = dev["services"]["traefik"]
    assert traefik["depends_on"]["app"]["condition"] == "service_healthy"
    assert any(p for p in traefik["ports"] if "443" in str(p))

    test = yaml.safe_load((dest / "infra" / "compose" / "test.yml").read_text())
    assert test["services"]["app"]["environment"]["APP_ENVIRONMENT"] == "test"
    assert "test" in test["services"]["app"]["profiles"]


def test_render_env_services_and_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    env = (dest / ".env.example").read_text()
    assert "APP_ENVIRONMENT=" in env
    assert "APP_SLO_REQUEST_LATENCY_P99_MS=" in env

    services = (dest / "SERVICES.md").read_text()
    assert "demo.localhost" in services      # external HTTPS host
    assert "app:8000" in services             # internal docker address

    taskfile = (dest / "Taskfile.yml").read_text()
    for task in ("dev:", "dev:lite:", "dev:reset:", "certs:", "test:stack:"):
        assert task in taskfile


def test_render_traefik_and_certs_gitignored(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    static = yaml.safe_load((dest / "infra" / "traefik" / "traefik.yml").read_text())
    assert "websecure" in static["entryPoints"]
    assert static["providers"]["docker"]["exposedByDefault"] is False

    tls = yaml.safe_load((dest / "infra" / "traefik" / "dynamic" / "tls.yml").read_text())
    certs = tls["tls"]["certificates"][0]
    assert certs["certFile"].endswith(".pem")

    assert (dest / "infra" / "traefik" / "certs" / ".gitkeep").is_file()
    gitignore = (dest / ".gitignore").read_text()
    assert "infra/traefik/certs/*.pem" in gitignore


def test_render_observability_services_in_dev(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    svcs = dev["services"]
    for name in ("prometheus", "grafana", "alertmanager"):
        assert name in svcs
        assert svcs[name]["profiles"] == ["dev"]  # not in `lite`
    assert svcs["prometheus"]["depends_on"]["app"]["condition"] == "service_healthy"
    assert any("3000" in str(p) for p in svcs["grafana"]["ports"])
    assert any("9090" in str(p) for p in svcs["prometheus"]["ports"])


def test_render_docs_mention_observability(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "grafana:3000" in (dest / "SERVICES.md").read_text()
    assert "task observability:gen" in (dest / "README.md").read_text()


def test_render_observability_config(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    obs = dest / "infra" / "observability"

    prom = yaml.safe_load((obs / "prometheus" / "prometheus.yml").read_text())
    jobs = {s["job_name"] for s in prom["scrape_configs"]}
    assert "app" in jobs
    app_job = next(s for s in prom["scrape_configs"] if s["job_name"] == "app")
    assert "app:8000" in app_job["static_configs"][0]["targets"]
    assert "/etc/prometheus/alerts/*.yml" in prom["rule_files"]
    assert "alertmanager:9093" in prom["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]

    ds = yaml.safe_load(
        (obs / "grafana" / "provisioning" / "datasources" / "prometheus.yml").read_text()
    )
    assert ds["datasources"][0]["uid"] == "prometheus"
    assert ds["datasources"][0]["url"] == "http://prometheus:9090"

    prov = yaml.safe_load(
        (obs / "grafana" / "provisioning" / "dashboards" / "provider.yml").read_text()
    )
    assert prov["providers"][0]["options"]["path"] == "/var/lib/grafana/dashboards"

    am = yaml.safe_load((obs / "alertmanager" / "alertmanager.yml").read_text())
    assert "route" in am and "receivers" in am


def test_render_loki_promtail(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    obs = dest / "infra" / "observability"

    loki = yaml.safe_load((obs / "loki" / "loki-config.yml").read_text())
    assert loki["auth_enabled"] is False
    assert loki["server"]["http_listen_port"] == 3100

    pt = yaml.safe_load((obs / "promtail" / "promtail-config.yml").read_text())
    assert pt["clients"][0]["url"] == "http://loki:3100/loki/api/v1/push"
    sc = pt["scrape_configs"][0]
    assert any("docker_sd_configs" == k for k in sc)
    stages = sc["pipeline_stages"]
    json_stage = next(s["json"] for s in stages if "json" in s)
    assert "level" in json_stage["expressions"]
    assert "correlation_id" in json_stage["expressions"]

    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    for name in ("loki", "promtail"):
        assert dev["services"][name]["profiles"] == ["dev"]
    assert any("3100" in str(p) for p in dev["services"]["loki"]["ports"])
    vols = " ".join(dev["services"]["promtail"]["volumes"])
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in vols
    assert "loki" in dev["services"]["promtail"]["depends_on"]


def test_render_grafana_loki_datasource(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ds = yaml.safe_load(
        (dest / "infra" / "observability" / "grafana" / "provisioning" / "datasources" / "loki.yml").read_text()
    )
    d = ds["datasources"][0]
    assert d["uid"] == "loki"
    assert d["type"] == "loki"
    assert d["url"] == "http://loki:3100"


def test_render_docs_mention_logs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "loki:3100" in (dest / "SERVICES.md").read_text()
    assert '{service="app"}' in (dest / "README.md").read_text()


def test_render_tempo_datasource_and_loki_link(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ds_dir = dest / "infra" / "observability" / "grafana" / "provisioning" / "datasources"

    tempo = yaml.safe_load((ds_dir / "tempo.yml").read_text())["datasources"][0]
    assert tempo["uid"] == "tempo"
    assert tempo["type"] == "tempo"
    assert tempo["url"] == "http://tempo:3200"

    loki = yaml.safe_load((ds_dir / "loki.yml").read_text())["datasources"][0]
    df = loki["jsonData"]["derivedFields"][0]
    assert df["name"] == "trace_id"
    assert df["datasourceUid"] == "tempo"
    # the regex must match the ACTUAL structlog JSON line (JSONRenderer puts a space
    # after the colon), not merely contain "trace_id" — guards the Loki->Tempo link.
    import re

    sample = json.dumps({"event": "request", "trace_id": "0af7651916cd43dd8448eb211c80319c"})
    m = re.search(df["matcherRegex"], sample)
    assert m and m.group(1) == "0af7651916cd43dd8448eb211c80319c"


def test_render_docs_mention_traces(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "tempo:3200" in (dest / "SERVICES.md").read_text()
    assert "OpenTelemetry" in (dest / "README.md").read_text()


def test_render_pyproject_database_deps(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    pyproject = (dest / "pyproject.toml").read_text()
    assert "sqlalchemy" in pyproject
    assert "alembic" in pyproject
    assert "psycopg" in pyproject
    assert "testcontainers" in pyproject  # dev dep for real-PG tests


def test_render_settings_has_database_url(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    settings = (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "database_url" in settings
    assert "postgresql+psycopg://" in settings


def test_render_includes_db_core(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    db = dest / "src" / "demo" / "db"
    assert (db / "base.py").is_file()
    engine = (db / "engine.py").read_text()
    assert "def get_session" in engine
    assert "build_engine" in engine


def test_render_conftest_uses_real_postgres(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    conftest = (dest / "tests" / "conftest.py").read_text()
    assert "PostgresContainer" in conftest
    assert "db_session" in conftest
    assert "pytest.fail" in conftest  # forcing function: DB tests fail (not skip) w/o Docker


def test_render_tempo_otel_collector(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    obs = dest / "infra" / "observability"

    tempo = yaml.safe_load((obs / "tempo" / "tempo.yml").read_text())
    assert "otlp" in tempo["distributor"]["receivers"]
    assert tempo["storage"]["trace"]["backend"] == "local"

    col = yaml.safe_load((obs / "otel" / "otel-collector.yml").read_text())
    assert "otlp" in col["receivers"]
    assert col["exporters"]["otlp/tempo"]["endpoint"] == "tempo:4317"
    assert col["service"]["pipelines"]["traces"]["exporters"] == ["otlp/tempo"]

    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    for name in ("tempo", "otel-collector"):
        assert dev["services"][name]["profiles"] == ["dev"]
    app_env = dev["services"]["app"]["environment"]
    assert app_env["APP_OTEL_ENABLED"] == "true"
    assert app_env["APP_OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-collector:4317"


def test_render_includes_db_model_and_repository(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    models = (dest / "src" / "demo" / "db" / "models.py").read_text()
    assert "class Item" in models
    assert '__tablename__ = "items"' in models
    repo = (dest / "src" / "demo" / "db" / "repository.py").read_text()
    assert "def list_items" in repo
    assert "def create_item" in repo


def test_render_includes_seed(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    seed_mod = (dest / "src" / "demo" / "db" / "seed.py").read_text()
    assert "def seed" in seed_mod
    data = json.loads((dest / "seeds" / "items.json").read_text())
    assert isinstance(data, list) and data and "name" in data[0]
    cli = (dest / "scripts" / "seed.py").read_text()
    assert "from demo.db.seed import seed" in cli


def test_render_includes_alembic(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ini = (dest / "alembic.ini").read_text()
    assert "script_location = migrations" in ini
    env = (dest / "migrations" / "env.py").read_text()
    assert "from demo.db.base import Base" in env
    assert "get_settings().database_url" in env
    assert (dest / "migrations" / "script.py.mako").is_file()
    initial = (dest / "migrations" / "versions" / "0001_initial.py").read_text()
    assert "create_table" in initial and '"items"' in initial


def test_render_wires_items_route(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    items = (dest / "src" / "demo" / "routes" / "items.py").read_text()
    assert '@router.get("/items"' in items
    main = (dest / "src" / "demo" / "main.py").read_text()
    # items router is now wired via autodiscovery, not explicit include_router
    assert "include_routers(app)" in main


def test_render_includes_resilience_scaffold(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    src = dest / "src" / "demo"

    assert (src / "middleware" / "errors.py").is_file()
    assert (src / "resilience" / "retry.py").is_file()
    assert (src / "resilience" / "circuit_breaker.py").is_file()
    assert (src / "observability" / "recoverability.py").is_file()

    errors = (src / "middleware" / "errors.py").read_text()
    assert "application/problem+json" in errors

    main = (src / "main.py").read_text()
    assert "register_exception_handlers" in main
    assert "lifespan" in main

    pyproject = (dest / "pyproject.toml").read_text()
    assert "tenacity" in pyproject
    assert "pybreaker" in pyproject

    claude = (dest / "CLAUDE.md").read_text()
    assert "RFC 7807" in claude


def test_render_dockerfile_entrypoint(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    entry = (dest / "scripts" / "entrypoint.sh").read_text()
    assert "alembic upgrade head" in entry
    assert "scripts/seed.py" in entry
    assert 'exec "$@"' in entry
    dockerfile = (dest / "infra" / "docker" / "Dockerfile").read_text()
    assert "entrypoint.sh" in dockerfile
    assert "ENTRYPOINT" in dockerfile
    assert "uvicorn" in dockerfile and "CMD" in dockerfile


def test_render_postgres_in_dev_and_lite(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    pg = dev["services"]["postgres"]
    assert pg["profiles"] == ["dev", "lite"]   # present in dev AND lite, not test
    assert "pg_isready" in " ".join(pg["healthcheck"]["test"])
    app = dev["services"]["app"]
    assert app["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert "postgres:5432" in app["environment"]["APP_DATABASE_URL"]
    assert "pgdata" in dev["volumes"]


def test_render_postgres_test_profile(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    test = yaml.safe_load((dest / "infra" / "compose" / "test.yml").read_text())
    pg = test["services"]["postgres-test"]
    assert pg["profiles"] == ["test"]
    assert "tmpfs" in pg  # ephemeral: reset between runs
    app = test["services"]["app"]
    assert "postgres-test:5432" in app["environment"]["APP_DATABASE_URL"]
    assert app["depends_on"]["postgres-test"]["condition"] == "service_healthy"


def test_render_db_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "db:migrate:" in taskfile
    assert "db:seed:" in taskfile
    assert "alembic upgrade head" in taskfile
    assert "scripts/seed.py" in taskfile


def test_render_database_docs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    env = (dest / ".env.example").read_text()
    assert "APP_DATABASE_URL=" in env
    services = (dest / "SERVICES.md").read_text()
    assert "postgres:5432" in services
    readme = (dest / "README.md").read_text()
    assert "task db:migrate" in readme
    assert "PostgreSQL" in readme
    assert "/items" in readme


def test_render_coverage_script_and_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    script = dest / "scripts" / "coverage.sh"
    assert script.is_file()
    text = script.read_text()
    assert "coverage run --context=" in text
    assert "--fail-under=" in text

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:unit:" in taskfile

    precommit = (dest / ".pre-commit-config.yaml").read_text()
    assert "scripts/coverage.sh 70 unit functional" in precommit


def test_render_dependency_security(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pip-audit" in pyproject

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "audit:" in taskfile

    dependabot = dest / ".github" / "dependabot.yml"
    assert dependabot.is_file()
    cfg = yaml.safe_load(dependabot.read_text())
    ecosystems = {u["package-ecosystem"] for u in cfg["updates"]}
    assert {"uv", "github-actions"} <= ecosystems


def test_render_workflow_and_shell_linters(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    precommit = (dest / ".pre-commit-config.yaml").read_text()
    assert "actionlint" in precommit
    assert "shellcheck" in precommit

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "actionlint" in taskfile
    assert "shellcheck" in taskfile


def test_render_smoke_suite(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    assert (dest / "tests" / "smoke" / "test_smoke.py").is_file()
    smoke = (dest / "tests" / "smoke" / "test_smoke.py").read_text()
    assert "SMOKE_TARGET" in smoke
    assert "/heartbeat" in smoke and "/health" in smoke

    pyproject = (dest / "pyproject.toml").read_text()
    assert '"tests/unit", "tests/functional", "tests/e2e"' in pyproject

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:smoke:" in taskfile


def test_render_sniff_suite(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sniff = (dest / "tests" / "sniff" / "test_sniff.py")
    assert sniff.is_file()
    text = sniff.read_text()
    assert "SNIFF_TARGET" in text
    assert "/items" in text

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:sniff:" in taskfile


def test_render_load_test(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    load_js = (dest / "tests" / "non_functional" / "load.js")
    assert load_js.is_file()
    js = load_js.read_text()
    assert "thresholds" in js
    assert "http_req_duration" in js  # k6 maps this to the p99 SLO

    script = (dest / "scripts" / "load.sh")
    assert script.is_file()
    assert "grafana/k6" in script.read_text()

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:load:" in taskfile


def test_render_e2e_is_target_aware(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    conftest = (dest / "tests" / "conftest.py").read_text()
    assert "api_client" in conftest
    assert "E2E_TARGET" in conftest
    assert "e2e_client" not in conftest  # the in-process-only fixture is gone

    e2e = (dest / "tests" / "e2e" / "test_items_e2e.py").read_text()
    assert "api_client" in e2e


def test_render_deploy_strategy_seam(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    strategy = (dest / "infra" / "deploy" / "strategy.sh")
    assert strategy.is_file()
    text = strategy.read_text()
    for op in ("deploy", "endpoints", "await-healthy", "rollback", "releases", "teardown"):
        assert op in text, f"strategy.sh missing operation {op}"
    # opinionated skeleton: config validated; target hooks fail loudly; rollback reverses migrations
    assert "require_var" in text
    assert "_todo" in text
    assert "downgrade" in text and "__target_migrate" in text  # migration-aware rollback

    assert (dest / "infra" / "deploy" / "notify.sh").is_file()
    readme = (dest / "infra" / "deploy" / "README.md").read_text()
    assert "deploy strategy" in readme.lower()
    assert "rollback" in readme
    assert "expand/contract" in readme  # prescribed migration discipline


def test_render_staging_prod_compose(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    for env in ("staging", "prod"):
        path = dest / "infra" / "compose" / f"{env}.yml"
        assert path.is_file(), f"{env}.yml missing"
        compose = yaml.safe_load(path.read_text())
        app = compose["services"]["app"]
        assert "build" not in app, f"{env} must run the pushed image, not build"
        assert "${APP_IMAGE" in app["image"]
        assert app["environment"]["APP_ENVIRONMENT"] == env
        assert app["restart"] == "unless-stopped"
        assert compose["services"]["postgres"]["restart"] == "unless-stopped"


def test_render_includes_ci_pipeline(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    wf = dest / ".github" / "workflows" / "ci.yml"
    assert wf.is_file()
    ci = yaml.safe_load(wf.read_text())

    # NB: PyYAML parses the workflow `on:` key as the boolean True.
    assert True in ci or "on" in ci
    jobs = ci["jobs"]
    # the spec §14 ordering, with integrity (Plan 6) + review (Plan 7) as seam jobs
    for job in ("integrity", "lint", "test", "build", "contract", "security", "review"):
        assert job in jobs, f"ci.yml missing the {job} job"
    assert jobs["lint"]["needs"] == "integrity"
    assert jobs["review"]["needs"] == ["test", "contract", "review-plan"]

    # the test job runs the combined 85% gate via the shared script
    test_run = " ".join(str(s.get("run", "")) for s in jobs["test"]["steps"])
    assert "scripts/coverage.sh 85 unit functional e2e" in test_run

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "ci:" in taskfile
    assert "push:" in taskfile


def test_render_deploy_prod_workflow(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    wf = dest / ".github" / "workflows" / "deploy-prod.yml"
    assert wf.is_file()
    ci = yaml.safe_load(wf.read_text())

    # manual approval gate via a protected GitHub Environment, and a tag trigger
    assert ci["jobs"]["deploy-prod"]["environment"] == "production"
    triggers = ci[True] if True in ci else ci["on"]  # PyYAML parses `on:` as True
    assert "workflow_dispatch" in triggers

    steps = " ".join(str(s.get("run", "")) for s in ci["jobs"]["deploy-prod"]["steps"])
    assert "strategy.sh deploy" in steps and "strategy.sh rollback" in steps
    # prod sniff is read-only; no E2E/load writes against prod
    assert "tests/smoke" in steps and "tests/sniff" in steps
    assert "tests/e2e" not in steps


def test_render_migration_guard(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    guard = (dest / "scripts" / "check_migrations.py")
    assert guard.is_file()
    assert "downgrade" in guard.read_text()

    precommit = (dest / ".pre-commit-config.yaml").read_text()
    assert "migrations-reversible" in precommit

    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "check_migrations.py" in ci

    # the backward-compatibility (contract-direction) guard + the opt-in marker
    assert "_contract_problem" in guard.read_text()
    assert "deploy: contract" in guard.read_text()


def test_render_deploy_docs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    deploy_md = (dest / "DEPLOY.md")
    assert deploy_md.is_file()
    text = deploy_md.read_text()
    assert "Demo" in text  # {{ project_name }} interpolated
    assert "infra/deploy/strategy.sh" in text

    assert "## Deploy" in (dest / "README.md").read_text()
    claude = (dest / "CLAUDE.md").read_text()
    assert "deploy" in claude.lower()
    assert "reversible" in claude.lower()  # the strengthened migration convention


def test_render_deploy_staging_workflow(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    wf = dest / ".github" / "workflows" / "deploy-staging.yml"
    assert wf.is_file()
    text = wf.read_text()
    # GitHub expressions are preserved verbatim (plain .yml, no Jinja) — NOT escaped/emptied.
    assert "${{ github.repository }}" in text
    assert "ghcr.io" in text and "docker push" in text

    ci = yaml.safe_load(text)
    jobs = ci["jobs"]
    assert "build-push" in jobs and "deploy-staging" in jobs
    deploy_steps = " ".join(str(s.get("run", "")) for s in jobs["deploy-staging"]["steps"])
    for op in ("strategy.sh deploy", "strategy.sh rollback", "strategy.sh endpoints"):
        assert op in deploy_steps, f"deploy-staging missing {op}"
    assert "tests/smoke" in deploy_steps and "tests/sniff" in deploy_steps
    assert "tests/e2e" in deploy_steps and "scripts/load.sh" in deploy_steps


def test_render_entrypoint_gates_migrations(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    entry = (dest / "scripts" / "entrypoint.sh").read_text()
    assert "APP_RUN_MIGRATIONS" in entry
    assert "alembic upgrade head" in entry
    assert 'exec "$@"' in entry


def test_render_migration_docs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    claude = (dest / "CLAUDE.md").read_text()
    assert "backward-compatible" in claude.lower()

    deploy_readme = (dest / "infra" / "deploy" / "README.md").read_text()
    assert "deploy: contract" in deploy_readme
    assert "APP_RUN_MIGRATIONS" in deploy_readme


def test_hybrid_files_render_with_markers(tmp_path: Path):
    from framework_cli.integrity.sections import section_content

    dest = tmp_path / "proj"
    render_project(
        dest,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    for rel in ("CLAUDE.md", ".env.example", "Taskfile.yml"):
        text = (dest / rel).read_text()
        assert section_content(text) is not None, f"{rel} has no FRAMEWORK section"


def test_taskfile_wires_integrity(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(
        dest,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "\n  integrity:\n" in taskfile
    assert "command -v framework" in taskfile


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "framework_cli").is_dir():
            return parent
    raise RuntimeError("repo root not found")


def test_ci_activates_integrity_step(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(
        dest,
        {"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"},
    )
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "framework integrity --ci" in ci
    assert "uv tool install" in ci and "_commit" in ci


def test_ci_review_job_runs_framework_review(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(
        dest,
        {"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"},
    )
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "framework review " in ci
    assert "uv tool install" in ci and "_commit" in ci
    assert "ANTHROPIC_API_KEY" in ci


def test_ci_review_matrix(tmp_path: Path):
    import yaml

    dest = tmp_path / "proj"
    render_project(
        dest,
        {"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"},
    )
    text = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "framework review-agents" in text
    assert "fromJSON(needs.review-plan.outputs.agents)" in text
    doc = yaml.safe_load(text)
    assert "review-plan" in doc["jobs"] and "review" in doc["jobs"]
    assert doc["jobs"]["review"]["needs"] == ["test", "contract", "review-plan"]


def test_render_ci_review_aggregation(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ci = yaml.safe_load((dest / ".github" / "workflows" / "ci.yml").read_text())
    jobs = ci["jobs"]

    # the review matrix job writes per-agent findings and uploads them even on a blocking failure
    review_steps = jobs["review"]["steps"]
    runs = " ".join(str(s.get("run", "")) for s in review_steps)
    assert "--findings-out" in runs
    upload = next(s for s in review_steps if "upload-artifact" in str(s.get("uses", "")))
    assert upload["if"] == "always()"
    assert "review-findings-" in upload["with"]["name"]

    # a review-aggregate job consolidates them into the single PR comment
    assert "review-aggregate" in jobs
    agg = jobs["review-aggregate"]
    assert agg["needs"] == "review"
    assert agg["if"] == "always()"
    assert " ".join(str(s.get("run", "")) for s in agg["steps"]).find("framework review-aggregate") != -1
    download = next(s for s in agg["steps"] if "download-artifact" in str(s.get("uses", "")))
    assert download["with"]["pattern"] == "review-findings-*"
    assert download["with"]["merge-multiple"] is True
    assert download["with"]["path"] == "all-findings"
    assert "all-findings" in " ".join(str(s.get("run", "")) for s in agg["steps"])


def test_render_routes_use_autodiscovery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    init = (dest / "src" / "demo" / "routes" / "__init__.py").read_text()
    assert "include_routers" in init and "iter_modules" in init
    main = (dest / "src" / "demo" / "main.py").read_text()
    assert "include_routers(app)" in main
    assert "include_router(health.router)" not in main
    assert "include_router(items.router)" not in main


def test_render_without_battery_has_no_websockets(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)  # DATA has no "batteries" -> defaults to []
    assert not (dest / "src" / "demo" / "routes" / "websockets.py").exists()
    assert not (dest / "src" / "demo" / "websockets").exists()


def test_render_with_websockets_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    assert (dest / "src" / "demo" / "routes" / "websockets.py").is_file()
    assert (dest / "src" / "demo" / "websockets" / "connection_manager.py").is_file()
    assert (dest / "tests" / "functional" / "test_websockets.py").is_file()
    assert "router" in (dest / "src" / "demo" / "routes" / "websockets.py").read_text()


def test_render_without_webhooks_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert not (dest / "src" / "demo" / "routes" / "webhooks.py").exists()
    assert not (dest / "src" / "demo" / "webhooks").exists()


def test_render_with_webhooks_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    pkg = dest / "src" / "demo" / "webhooks"
    assert (dest / "src" / "demo" / "routes" / "webhooks.py").is_file()
    assert (pkg / "signature.py").is_file() and (pkg / "inbox.py").is_file()
    assert (pkg / "models.py").is_file() and (pkg / "handler.py").is_file()
    assert (dest / "tests" / "functional" / "test_webhooks.py").is_file()
    assert "router" in (dest / "src" / "demo" / "routes" / "webhooks.py").read_text()


def test_render_webhooks_secret_in_env_managed_section(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    env = (dest / ".env.example").read_text()
    begin, end = env.index("# FRAMEWORK:BEGIN"), env.index("# FRAMEWORK:END")
    assert "APP_WEBHOOK_SIGNING_SECRET=" in env[begin:end]  # inside the managed section
    settings = (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "webhook_signing_secret" in settings
    assert (dest / "migrations" / "versions" / "0002_webhook_events.py").is_file()


def test_render_no_webhooks_secret_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "WEBHOOK_SIGNING_SECRET" not in (dest / ".env.example").read_text()
    assert "webhook_signing_secret" not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert not (dest / "migrations" / "versions" / "0002_webhook_events.py").exists()


def test_render_with_workers_battery_adds_celery_dep(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    assert "celery[redis]" in (dest / "pyproject.toml").read_text()


def test_render_without_workers_battery_has_no_celery_dep(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "celery[redis]" not in (dest / "pyproject.toml").read_text()


def test_render_workers_creates_tasks_package(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    pkg = dest / "src" / DATA["package_name"]
    assert (pkg / "tasks" / "app.py").exists()
    assert (pkg / "tasks" / "__init__.py").exists()
    text = (pkg / "tasks" / "app.py").read_text()
    assert "{{" not in text  # template fully rendered
    assert DATA["package_name"] in text


def test_render_no_tasks_package_without_workers(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert not (dest / "src" / DATA["package_name"] / "tasks").exists()


def test_render_workers_migration_chains_off_initial(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    mig = (dest / "migrations" / "versions" / "0003_dead_letter.py").read_text()
    assert 'revision = "0003"' in mig
    assert 'down_revision = "0001"' in mig


def test_render_workers_migration_chains_off_webhooks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks", "workers"]})
    mig = (dest / "migrations" / "versions" / "0003_dead_letter.py").read_text()
    assert 'down_revision = "0002"' in mig


def test_render_no_workers_migration_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "migrations" / "versions" / "0003_dead_letter.py").exists()


def test_render_env_py_no_workers_import_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert "tasks import dead_letter" not in (dest / "migrations" / "env.py").read_text()


def test_render_env_py_imports_dead_letter_with_workers(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    env_py = (dest / "migrations" / "env.py").read_text()
    assert f"from {DATA['package_name']}.tasks import dead_letter" in env_py


def test_render_workers_functional_test_present(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    assert (dest / "tests" / "functional" / "test_workers_functional.py").exists()


def test_render_no_workers_functional_test_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert not (dest / "tests" / "functional" / "test_workers_functional.py").exists()


def test_render_workers_creates_base_task(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    assert (dest / "src" / DATA["package_name"] / "tasks" / "base.py").exists()


def test_render_workers_creates_task_modules(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    base = dest / "src" / DATA["package_name"] / "tasks"
    for name in ("liveness.py", "tasks.py", "schedule.py"):
        assert (base / name).exists(), f"expected {name} in tasks/"
    # Rendered files contain package_name (not raw Jinja tags)
    liveness_text = (base / "liveness.py").read_text()
    assert "{{ " not in liveness_text, "liveness.py still has unrendered Jinja"
    assert "demo:worker:heartbeat" in liveness_text
    schedule_text = (base / "schedule.py").read_text()
    assert "{{ " not in schedule_text, "schedule.py still has unrendered Jinja"
    assert "demo.tasks.tasks.heartbeat" in schedule_text


def test_root_copier_yml_renders_template_without_leaking_config(tmp_path: Path):
    import shutil
    import yaml
    from copier import run_copy

    root = _repo_root()
    cfg = yaml.safe_load((root / "copier.yml").read_text())
    assert cfg["_subdirectory"] == "src/framework_cli/template"

    # Render from a NON-git copy of {root copier.yml + the template subdir} so Copier uses the
    # working-tree files (not a committed git ref). The output must NOT contain copier.yml.
    src = tmp_path / "src"
    (src / "src" / "framework_cli").mkdir(parents=True)
    shutil.copy(root / "copier.yml", src / "copier.yml")
    shutil.copytree(
        root / "src" / "framework_cli" / "template",
        src / "src" / "framework_cli" / "template",
    )
    dest = tmp_path / "out"
    run_copy(
        str(src),
        str(dest),
        data={"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"},
        defaults=True,
        overwrite=True,
        quiet=True,
    )
    assert not (dest / "copier.yml").exists(), "subdir copier.yml leaked into the rendered project"
    assert (dest / "pyproject.toml").is_file()
    assert (dest / ".copier-answers.yml").is_file()
