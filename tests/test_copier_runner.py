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
    assert "from demo.routes import health" in main_py


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
    assert "items" in main
    assert "include_router(items.router)" in main


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
