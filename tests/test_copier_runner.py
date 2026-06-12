import http.server
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
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
    assert "demo.localhost" in services  # external HTTPS host
    assert "app:8000" in services  # internal docker address

    taskfile = (dest / "Taskfile.yml").read_text()
    for task in ("dev:", "dev:lite:", "dev:reset:", "certs:", "test:stack:"):
        assert task in taskfile


def test_render_traefik_and_certs_gitignored(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    static = yaml.safe_load((dest / "infra" / "traefik" / "traefik.yml").read_text())
    assert "websecure" in static["entryPoints"]
    assert static["providers"]["docker"]["exposedByDefault"] is False

    tls = yaml.safe_load(
        (dest / "infra" / "traefik" / "dynamic" / "tls.yml").read_text()
    )
    certs = tls["tls"]["certificates"][0]
    assert certs["certFile"].endswith(".pem")

    assert (dest / "infra" / "traefik" / "certs" / ".gitkeep").is_file()
    gitignore = (dest / ".gitignore").read_text()
    assert "infra/traefik/certs/*.pem" in gitignore


def test_render_observability_services_in_overlay(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    # Core obs stack is now in the observability.yml overlay, not dev.yml.
    overlay = yaml.safe_load(
        (dest / "infra" / "compose" / "observability.yml").read_text()
    )
    svcs = overlay["services"]
    for name in ("prometheus", "grafana", "alertmanager"):
        assert name in svcs
        # The overlay has NO profiles — it runs whenever merged
        assert "profiles" not in svcs[name]
    assert svcs["prometheus"]["depends_on"]["app"]["condition"] == "service_healthy"
    assert any("3000" in str(p) for p in svcs["grafana"]["ports"])
    assert any("9090" in str(p) for p in svcs["prometheus"]["ports"])
    # dev.yml has a grafana profile override (anonymous auth) but not the full service:
    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    assert "grafana" in dev["services"]
    assert dev["services"]["grafana"]["profiles"] == ["dev"]
    assert "GF_AUTH_ANONYMOUS_ENABLED" in str(dev["services"]["grafana"]["environment"])
    # prometheus/alertmanager are NOT in dev.yml (moved to overlay):
    assert "prometheus" not in dev["services"]
    assert "alertmanager" not in dev["services"]


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
    assert (
        "alertmanager:9093"
        in prom["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    )

    ds = yaml.safe_load(
        (
            obs / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
        ).read_text()
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

    # loki/promtail are now defined in the observability.yml overlay (no profiles — no gating):
    overlay = yaml.safe_load(
        (dest / "infra" / "compose" / "observability.yml").read_text()
    )
    for name in ("loki", "promtail"):
        assert name in overlay["services"]
        assert "profiles" not in overlay["services"][name]
    assert any("3100" in str(p) for p in overlay["services"]["loki"]["ports"])
    vols = " ".join(overlay["services"]["promtail"]["volumes"])
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in vols
    assert "loki" in overlay["services"]["promtail"]["depends_on"]


def test_render_grafana_loki_datasource(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ds = yaml.safe_load(
        (
            dest
            / "infra"
            / "observability"
            / "grafana"
            / "provisioning"
            / "datasources"
            / "loki.yml"
        ).read_text()
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
    ds_dir = (
        dest / "infra" / "observability" / "grafana" / "provisioning" / "datasources"
    )

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

    sample = json.dumps(
        {"event": "request", "trace_id": "0af7651916cd43dd8448eb211c80319c"}
    )
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
    assert (
        "pytest.fail" in conftest
    )  # forcing function: DB tests fail (not skip) w/o Docker


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

    # tempo/otel-collector are now in the observability.yml overlay (no profiles):
    overlay = yaml.safe_load(
        (dest / "infra" / "compose" / "observability.yml").read_text()
    )
    for name in ("tempo", "otel-collector"):
        assert name in overlay["services"]
        assert "profiles" not in overlay["services"][name]
    # The overlay carries the OTEL app fragment (deep-merged onto app):
    overlay_app_env = overlay["services"]["app"]["environment"]
    assert overlay_app_env["APP_OTEL_ENABLED"] == "true"
    assert (
        overlay_app_env["APP_OTEL_EXPORTER_OTLP_ENDPOINT"]
        == "http://otel-collector:4317"
    )
    # dev.yml app still has these too (harmless redundancy — overlay + dev both set them):
    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
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


def test_seed_script_reads_as_an_owned_example(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    cli = (dest / "scripts" / "seed.py").read_text()
    assert "compose your domain seeding here" in cli
    assert "db.seed" in cli  # still points at the reusable helper


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
    assert pg["profiles"] == ["dev", "lite"]  # present in dev AND lite, not test
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
    # Dependabot manages app deps (uv) only. GitHub Actions are framework-owned:
    # pinned + APPROVED_ACTIONS-gated and living in integrity-locked workflow files,
    # so a github-actions bump PR is born red (drift + unapproved version). Excluded
    # by design; action freshness is the framework's job (propagated via upgrade).
    assert "uv" in ecosystems
    assert "github-actions" not in ecosystems


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

    sniff = dest / "tests" / "sniff" / "test_sniff.py"
    assert sniff.is_file()
    text = sniff.read_text()
    assert "SNIFF_TARGET" in text
    assert "/items" in text

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:sniff:" in taskfile


def test_render_load_test(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    load_js = dest / "tests" / "non_functional" / "load.js"
    assert load_js.is_file()
    js = load_js.read_text()
    assert "thresholds" in js
    assert "http_req_duration" in js  # k6 maps this to the p99 SLO

    script = dest / "scripts" / "load.sh"
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

    strategy = dest / "infra" / "deploy" / "strategy.sh"
    assert strategy.is_file()
    text = strategy.read_text()
    for op in (
        "deploy",
        "endpoints",
        "await-healthy",
        "rollback",
        "releases",
        "teardown",
    ):
        assert op in text, f"strategy.sh missing operation {op}"
    # opinionated skeleton: config validated; target hooks fail loudly; rollback reverses migrations
    assert "require_var" in text
    assert "_todo" in text
    assert (
        "downgrade" in text and "__target_migrate" in text
    )  # migration-aware rollback

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

    guard = dest / "scripts" / "check_migrations.py"
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

    deploy_md = dest / "DEPLOY.md"
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
    deploy_steps = " ".join(
        str(s.get("run", "")) for s in jobs["deploy-staging"]["steps"]
    )
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
    for rel in ("CLAUDE.md", ".env.example", "Taskfile.yml", ".pre-commit-config.yaml"):
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
        if (parent / "pyproject.toml").is_file() and (
            parent / "src" / "framework_cli"
        ).is_dir():
            return parent
    raise RuntimeError("repo root not found")


def test_ci_activates_integrity_step(tmp_path: Path):
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
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "framework integrity --ci" in ci
    assert "uv tool install" in ci and "_commit" in ci


def test_ci_review_job_runs_framework_review(tmp_path: Path):
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
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "framework review " in ci
    assert "uv tool install" in ci and "_commit" in ci
    assert "ANTHROPIC_RUNTIME_API_KEY" in ci
    assert "secrets.ANTHROPIC_DEMO_CI_RUNTIME" in ci
    assert "ANTHROPIC_API_KEY" not in ci


def test_ci_review_matrix(tmp_path: Path):
    import yaml

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
    upload = next(
        s for s in review_steps if "upload-artifact" in str(s.get("uses", ""))
    )
    assert upload["if"] == "always()"
    assert "review-findings-" in upload["with"]["name"]

    # a review-aggregate job consolidates them into the single PR comment
    assert "review-aggregate" in jobs
    agg = jobs["review-aggregate"]
    assert agg["needs"] == "review"
    assert agg["if"] == "always()"
    assert (
        " ".join(str(s.get("run", "")) for s in agg["steps"]).find(
            "framework review-aggregate"
        )
        != -1
    )
    download = next(
        s for s in agg["steps"] if "download-artifact" in str(s.get("uses", ""))
    )
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


def test_render_frontend_obs_artifacts(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    alerts = dest / "infra/observability/prometheus/alerts/frontend_alerts.yml"
    dash = dest / "infra/observability/grafana/dashboards/frontend.json"
    assert alerts.is_file()
    assert "FrontendLCPDegraded" in alerts.read_text()
    assert dash.is_file()
    assert '"uid": "frontend"' in dash.read_text()
    # in-process surface: no new scrape job
    prom = (dest / "infra/observability/prometheus/prometheus.yml").read_text()
    assert "job_name: frontend" not in prom


def test_render_without_react_has_no_frontend_obs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert not (
        dest / "infra/observability/prometheus/alerts/frontend_alerts.yml"
    ).exists()
    assert not (dest / "infra/observability/grafana/dashboards/frontend.json").exists()


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
    assert (
        "webhook_signing_secret"
        not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    )
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


def test_render_no_workers_migration_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "migrations" / "versions" / "0003_dead_letter.py").exists()


def test_render_env_py_no_workers_import_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert (
        "tasks import dead_letter" not in (dest / "migrations" / "env.py").read_text()
    )


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


def test_render_workers_settings_fields(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    s = (dest / "src" / DATA["package_name"] / "config" / "settings.py").read_text()
    assert "celery_broker_url" in s and "redis_url" in s


def test_render_workers_env_lines_in_managed_section(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    env = (dest / ".env.example").read_text()
    begin = env.index("FRAMEWORK:BEGIN")
    end = env.index("FRAMEWORK:END")
    assert "APP_CELERY_BROKER_URL" in env[begin:end]


def test_render_no_celery_env_without_workers(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert "APP_CELERY_BROKER_URL" not in (dest / ".env.example").read_text()


def test_render_workers_taskfile_has_worker_task(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    tf = (dest / "Taskfile.yml").read_text()
    begin = tf.index("FRAMEWORK:BEGIN")
    end = tf.index("FRAMEWORK:END")
    assert "worker:" in tf[begin:end]


def test_render_taskfile_unchanged_without_workers(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert "worker:" not in (dest / "Taskfile.yml").read_text()


def test_render_workers_taskfile_valid_yaml(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    tf_text = (dest / "Taskfile.yml").read_text()
    parsed = yaml.safe_load(tf_text)
    assert parsed is not None
    assert "worker" in parsed["tasks"]
    assert "beat" in parsed["tasks"]


def test_render_workers_settings_valid_python(tmp_path: Path):
    import ast

    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    settings_text = (
        dest / "src" / DATA["package_name"] / "config" / "settings.py"
    ).read_text()
    ast.parse(settings_text)  # raises SyntaxError if invalid


def test_render_health_has_dlq_gauge_with_workers(tmp_path: Path):
    import ast

    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    h = (dest / "src" / DATA["package_name"] / "routes" / "health.py").read_text()
    assert "render_dlq_metrics" in h and "per-instance" in h
    ast.parse(h)  # must be valid Python after rendering


def test_render_health_clean_without_workers(tmp_path: Path):
    import ast

    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    h = (dest / "src" / DATA["package_name"] / "routes" / "health.py").read_text()
    assert "render_dlq_metrics" not in h
    assert "per-instance" in h  # the SLO comment is unconditional
    ast.parse(h)  # must be valid Python even without the workers block


def test_render_workers_compose_services(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    import yaml as _yaml

    dev = _yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    # celery-exporter relocated to observability.yml (runs in prod too)
    for svc in ("redis", "worker", "beat"):
        assert svc in dev["services"]
    assert "celery-exporter" not in dev["services"]
    assert "redisdata" in dev["volumes"]
    obs = _yaml.safe_load(
        (dest / "infra" / "compose" / "observability.yml").read_text()
    )
    assert "celery-exporter" in obs["services"]


def test_render_compose_byte_identical_without_workers(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    # no workers services leaked
    assert "redis:" not in dev and "celery-exporter:" not in dev
    # dev.yml service set: core obs moved to overlay; dev keeps app/postgres/traefik + grafana override
    parsed = yaml.safe_load(dev)
    svcs = set(parsed["services"].keys())
    expected = {
        "app",
        "postgres",
        "traefik",
        "grafana",  # dev-only anonymous override (partial service definition)
    }
    assert svcs == expected, f"unexpected services in dev.yml: {svcs ^ expected}"
    # volumes: only pgdata, no redisdata
    assert set(parsed["volumes"].keys()) == {"pgdata"}
    # core obs stack is in the overlay, not dev.yml:
    overlay = yaml.safe_load(
        (dest / "infra" / "compose" / "observability.yml").read_text()
    )
    for svc in (
        "prometheus",
        "grafana",
        "alertmanager",
        "loki",
        "promtail",
        "tempo",
        "otel-collector",
    ):
        assert svc in overlay["services"]


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
        data={
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
        defaults=True,
        overwrite=True,
        quiet=True,
    )
    assert not (dest / "copier.yml").exists(), (
        "subdir copier.yml leaked into the rendered project"
    )
    assert (dest / "pyproject.toml").is_file()
    assert (dest / ".copier-answers.yml").is_file()


def test_render_workers_prometheus_scrape(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    prom = (
        dest / "infra" / "observability" / "prometheus" / "prometheus.yml"
    ).read_text()
    assert "celery-exporter" in prom
    import yaml as _yaml

    parsed = _yaml.safe_load(prom)
    assert any(j["job_name"] == "celery" for j in parsed["scrape_configs"])


def test_render_prometheus_unchanged_without_workers(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    prom = (
        dest / "infra" / "observability" / "prometheus" / "prometheus.yml"
    ).read_text()
    assert "celery-exporter" not in prom
    assert "job_name: app" in prom and "job_name: prometheus" in prom


def test_render_workers_alerts_and_dashboard(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    alerts = (
        dest
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "workers_alerts.yml"
    )
    dash = dest / "infra" / "observability" / "grafana" / "dashboards" / "workers.json"
    assert alerts.exists() and dash.exists()
    import json as _json
    import yaml as _yaml

    _yaml.safe_load(alerts.read_text())  # valid YAML
    assert "{{ $value }}" in alerts.read_text()  # Prometheus templating preserved
    _json.loads(dash.read_text())  # valid JSON


def test_render_no_workers_alerts_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (
        dest
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "workers_alerts.yml"
    ).exists()
    assert not (
        dest / "infra" / "observability" / "grafana" / "dashboards" / "workers.json"
    ).exists()


def test_render_webhooks_alone_handler_is_inline(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    h = (dest / "src" / DATA["package_name"] / "webhooks" / "handler.py").read_text()
    assert "process_async" not in h
    assert "get_logger().info" in h


def test_render_webhooks_plus_workers_handler_enqueues(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks", "workers"]})
    h = (dest / "src" / DATA["package_name"] / "webhooks" / "handler.py").read_text()
    assert "process_async.delay" in h
    assert "get_logger" not in h


def _assert_ruff_format_clean(dest: Path) -> None:
    """Assert that `uv run ruff format --check` passes on a rendered project directory.

    Uses the framework's own ruff (a deterministic proxy for the project's ruff; both
    resolve ruff>=0.8 from the same lockfile version). If the framework ruff ever diverges
    from the project ruff, the Docker precommit test (`test_rendered_project_precommit_runs_clean`)
    is the authoritative gate. This check is a fast hermetic guard that catches gated-block
    whitespace regressions without Docker.
    """
    src_dir = dest / "src"
    tests_dir = dest / "tests"
    migrations_dir = dest / "migrations"
    result = subprocess.run(
        [
            "uv",
            "run",
            "ruff",
            "format",
            "--check",
            str(src_dir),
            str(tests_dir),
            str(migrations_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"ruff format --check found files to reformat in {dest}:\n{result.stdout}{result.stderr}"
    )


def test_render_workers_battery_is_ruff_format_clean(tmp_path: Path):
    """Hermetic guard: workers-only render must be ruff-format-clean without Docker."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    _assert_ruff_format_clean(dest)


def test_render_webhooks_workers_battery_is_ruff_format_clean(tmp_path: Path):
    """Hermetic guard: webhooks+workers render must be ruff-format-clean without Docker."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks", "workers"]})
    _assert_ruff_format_clean(dest)


def test_render_redis_battery_is_ruff_format_clean(tmp_path: Path):
    """Hermetic guard: redis-only render must be ruff-format-clean without Docker."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["redis"]})
    _assert_ruff_format_clean(dest)


def test_render_workers_redis_battery_is_ruff_format_clean(tmp_path: Path):
    """Hermetic guard: workers+redis render (shared redis service + both /health blocks)
    must be ruff-format-clean without Docker."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers", "redis"]})
    _assert_ruff_format_clean(dest)


def test_render_workers_redis_health_alias_distinct(tmp_path: Path):
    """workers + redis both touch /health: workers does `import redis as _redis`, so the redis
    cache ping must use a DISTINCT alias — else the generated project's mypy gate fails [no-redef]."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers", "redis"]})
    health = (dest / "src" / "demo" / "routes" / "health.py").read_text()
    assert "get_redis as _get_redis" in health  # distinct alias for the cache ping
    assert (
        "get_redis as _redis" not in health
    )  # must not collide with workers' `import redis as _redis`


def test_render_webhooks_battery_is_ruff_format_clean(tmp_path: Path):
    """Hermetic guard: webhooks-only render must be ruff-format-clean without Docker."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    _assert_ruff_format_clean(dest)


def test_render_websockets_battery_is_ruff_format_clean(tmp_path: Path):
    """Hermetic guard: websockets-only render must be ruff-format-clean without Docker."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    _assert_ruff_format_clean(dest)


def test_render_webhooks_metrics_module(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    assert (dest / "src" / DATA["package_name"] / "webhooks" / "metrics.py").exists()
    assert (dest / "tests" / "unit" / "test_webhooks_unit.py").exists()


def test_render_no_webhooks_metrics_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (
        dest / "src" / DATA["package_name"] / "webhooks" / "metrics.py"
    ).exists()


def test_render_webhooks_route_records_metrics(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    route = (dest / "src" / DATA["package_name"] / "routes" / "webhooks.py").read_text()
    assert "webhook_metrics.record" in route
    health = (dest / "src" / DATA["package_name"] / "routes" / "health.py").read_text()
    assert "webhook_metrics.render_prometheus" in health


def test_render_health_clean_without_webhooks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    health = (dest / "src" / DATA["package_name"] / "routes" / "health.py").read_text()
    assert "webhook_metrics" not in health


def test_render_webhooks_alerts_and_dashboard(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    alerts = (
        dest
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "webhooks_alerts.yml"
    )
    dash = dest / "infra" / "observability" / "grafana" / "dashboards" / "webhooks.json"
    assert alerts.exists() and dash.exists()
    import json as _json
    import yaml as _yaml

    parsed = _yaml.safe_load(alerts.read_text())
    assert parsed["groups"][0]["name"] == "webhooks"
    _json.loads(dash.read_text())  # valid JSON


def test_render_no_webhooks_alerts_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (
        dest
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "webhooks_alerts.yml"
    ).exists()
    assert not (
        dest / "infra" / "observability" / "grafana" / "dashboards" / "webhooks.json"
    ).exists()


def test_render_websockets_metrics_module(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    assert (dest / "src" / DATA["package_name"] / "websockets" / "metrics.py").exists()
    assert (dest / "tests" / "unit" / "test_websockets_unit.py").exists()


def test_render_no_websockets_metrics_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (
        dest / "src" / DATA["package_name"] / "websockets" / "metrics.py"
    ).exists()


def test_render_websockets_emits_metrics(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    mgr = (
        dest / "src" / DATA["package_name"] / "websockets" / "connection_manager.py"
    ).read_text()
    assert "ws_metrics.connection_opened" in mgr
    assert "ws_metrics.connection_closed" in mgr
    assert "ws_metrics.message_sent" in mgr
    route = (
        dest / "src" / DATA["package_name"] / "routes" / "websockets.py"
    ).read_text()
    assert "ws_metrics.message_received" in route
    health = (dest / "src" / DATA["package_name"] / "routes" / "health.py").read_text()
    assert "ws_metrics.render_prometheus" in health


def test_render_health_clean_without_websockets(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    health = (dest / "src" / DATA["package_name"] / "routes" / "health.py").read_text()
    assert "ws_metrics" not in health


def test_render_websockets_alerts_and_dashboard(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    alerts = (
        dest
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "websockets_alerts.yml"
    )
    dash = (
        dest / "infra" / "observability" / "grafana" / "dashboards" / "websockets.json"
    )
    assert alerts.exists() and dash.exists()
    import yaml as _yaml
    import json as _json

    parsed = _yaml.safe_load(alerts.read_text())
    assert parsed["groups"][0]["name"] == "websockets"
    assert len(parsed["groups"][0]["rules"]) == 2
    _json.loads(dash.read_text())  # valid JSON


def test_render_no_websockets_alerts_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (
        dest
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "websockets_alerts.yml"
    ).exists()
    assert not (
        dest / "infra" / "observability" / "grafana" / "dashboards" / "websockets.json"
    ).exists()


def test_render_with_graphql_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    pkg = dest / "src" / "demo"
    assert (pkg / "graphql" / "schema.py").is_file()
    assert (pkg / "graphql" / "context.py").is_file()
    assert (pkg / "routes" / "graphql.py").is_file()
    assert (dest / "tests" / "functional" / "test_graphql.py").is_file()
    route = (pkg / "routes" / "graphql.py").read_text()
    assert "GraphQLRouter" in route and 'prefix="/graphql"' in route


def test_render_without_graphql_has_none(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "src" / "demo" / "graphql").exists()
    assert not (dest / "src" / "demo" / "routes" / "graphql.py").exists()


def test_render_graphql_settings_and_dep(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    settings = (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "graphql_ide_enabled" in settings and "resolved_graphql_ide" in settings
    assert "strawberry-graphql[fastapi]" in (dest / "pyproject.toml").read_text()


def test_render_graphql_settings_clean_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert (
        "graphql_ide_enabled"
        not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    )
    assert "strawberry-graphql" not in (dest / "pyproject.toml").read_text()


def test_render_graphql_battery_is_ruff_format_clean(tmp_path: Path):
    """Hermetic guard: graphql-only render must be ruff-format-clean without Docker."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    _assert_ruff_format_clean(dest)


def test_render_graphql_metrics_module(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    assert (dest / "src" / "demo" / "graphql" / "metrics.py").exists()
    assert (dest / "src" / "demo" / "graphql" / "extension.py").exists()
    assert (dest / "tests" / "unit" / "test_graphql_metrics.py").exists()
    schema = (dest / "src" / "demo" / "graphql" / "schema.py").read_text()
    assert "MetricsExtension" in schema
    health = (dest / "src" / "demo" / "routes" / "health.py").read_text()
    assert "gql_metrics.render_prometheus" in health


def test_render_health_clean_without_graphql(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert (
        "gql_metrics"
        not in (dest / "src" / "demo" / "routes" / "health.py").read_text()
    )


def test_render_graphql_alerts_and_dashboard(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    alerts = (
        dest
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "graphql_alerts.yml"
    )
    dash = dest / "infra" / "observability" / "grafana" / "dashboards" / "graphql.json"
    assert alerts.exists() and dash.exists()
    parsed = yaml.safe_load(alerts.read_text())
    assert parsed["groups"][0]["name"] == "graphql"
    json.loads(dash.read_text())  # valid JSON


def test_render_no_graphql_alerts_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (
        dest
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "graphql_alerts.yml"
    ).exists()
    assert not (
        dest / "infra" / "observability" / "grafana" / "dashboards" / "graphql.json"
    ).exists()


def test_render_graphql_export_script(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    script = dest / "scripts" / "export-graphql-schema.sh"
    assert script.is_file()
    assert "schema.graphql" in script.read_text()
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "export-graphql-schema.sh" in ci and "find_breaking_changes" in ci


def test_render_ci_clean_without_graphql(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "graphql" not in ci and "export-graphql-schema" not in ci


def test_render_workers_migration_down_revision(tmp_path: Path):
    d1 = tmp_path / "w"
    render_project(d1, {**DATA, "batteries": ["workers"]})
    mig = next((d1 / "migrations" / "versions").glob("0003_*.py")).read_text()
    assert 'down_revision = "0001"' in mig

    d2 = tmp_path / "wh"
    render_project(d2, {**DATA, "batteries": ["webhooks", "workers"]})
    mig2 = next((d2 / "migrations" / "versions").glob("0003_*.py")).read_text()
    assert 'down_revision = "0002"' in mig2


def test_render_with_pgvector_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["pgvector"]})
    pkg = dest / "src" / "demo"
    assert (pkg / "vectors" / "models.py").is_file()
    assert (pkg / "vectors" / "repository.py").is_file()
    mig = next((dest / "migrations" / "versions").glob("0004_*.py")).read_text()
    assert "CREATE EXTENSION" in mig and "vector" in mig
    assert 'down_revision = "0001"' in mig  # pgvector alone chains to baseline
    assert "pgvector" in (dest / "pyproject.toml").read_text()
    conftest = (dest / "tests" / "conftest.py").read_text()
    # pgvector now builds a custom Postgres image via DockerImage (not a prebuilt pull)
    assert "DockerImage" in conftest
    assert "postgres.Dockerfile" in conftest
    assert "pgvector/pgvector" not in conftest  # prebuilt image no longer used
    assert (
        "vectors" in (dest / "migrations" / "env.py").read_text()
    )  # gated model import


def test_render_without_pgvector_clean(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "src" / "demo" / "vectors").exists()
    assert "pgvector" not in (dest / "pyproject.toml").read_text()
    conftest = (dest / "tests" / "conftest.py").read_text()
    assert "pgvector/pgvector" not in conftest
    assert (
        "DockerImage" not in conftest
    )  # custom build only present with extension battery


def test_render_pgvector_battery_is_ruff_format_clean(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["pgvector"]})
    _assert_ruff_format_clean(dest)


def test_render_with_mongodb_core(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})
    pkg = dest / "src" / "demo"
    assert (pkg / "mongo" / "client.py").is_file() and (
        pkg / "mongo" / "repository.py"
    ).is_file()
    assert (dest / "tests" / "functional" / "test_mongo.py").is_file()
    assert "pymongo" in (dest / "pyproject.toml").read_text()
    assert "mongo_url" in (pkg / "config" / "settings.py").read_text()
    assert "mongo" in (pkg / "routes" / "health.py").read_text()


def test_render_mongodb_core_clean_without(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "src" / "demo" / "mongo").exists()
    assert "pymongo" not in (dest / "pyproject.toml").read_text()
    assert (
        "mongo_url"
        not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    )


def test_render_mongodb_is_ruff_format_clean(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})
    _assert_ruff_format_clean(dest)


def test_render_mongodb_service_and_obs(tmp_path: Path):
    import json as _j

    import yaml as _y

    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    # mongodb-exporter relocated to observability.yml (runs in prod too)
    assert "mongo:7" in dev
    assert "mongodb-exporter" not in dev
    obs = (dest / "infra" / "compose" / "observability.yml").read_text()
    assert "mongodb-exporter" in obs
    prom = (
        dest / "infra" / "observability" / "prometheus" / "prometheus.yml"
    ).read_text()
    assert "mongodb-exporter" in prom
    assert "APP_MONGO_URL" in (dest / ".env.example").read_text()
    alerts = (
        dest
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "mongodb_alerts.yml"
    )
    dash = dest / "infra" / "observability" / "grafana" / "dashboards" / "mongodb.json"
    assert alerts.exists() and dash.exists()
    assert _y.safe_load(alerts.read_text())["groups"][0]["name"] == "mongodb"
    assert _j.loads(dash.read_text())["uid"] == "mongodb"


def test_render_dev_yml_clean_without_mongodb(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert "mongo" not in (dest / "infra" / "compose" / "dev.yml").read_text()
    assert (
        "mongodb"
        not in (
            dest / "infra" / "observability" / "prometheus" / "prometheus.yml"
        ).read_text()
    )


def test_render_observability_overlay(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(
        dest, {**DATA}
    )  # baseline — the overlay is always-on (not battery-gated)
    overlay = dest / "infra" / "compose" / "observability.yml"
    assert overlay.exists()
    text = overlay.read_text()
    for svc in (
        "prometheus:",
        "grafana:",
        "alertmanager:",
        "loki:",
        "promtail:",
        "tempo:",
        "otel-collector:",
        "postgres-exporter:",
    ):
        assert svc in text
    # prod-safe grafana in the overlay (no anonymous), admin password from env:
    assert (
        "GF_SECURITY_ADMIN_PASSWORD" in text and "GF_AUTH_ANONYMOUS_ENABLED" not in text
    )


def test_render_dev_yml_core_obs_removed(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    dev_text = (dest / "infra" / "compose" / "dev.yml").read_text()
    dev = yaml.safe_load(dev_text)
    # core obs moved to the overlay — dev.yml no longer defines them as services:
    for svc in (
        "prometheus",
        "loki",
        "tempo",
        "otel-collector",
        "promtail",
        "alertmanager",
    ):
        assert svc not in dev["services"], f"{svc} should not be a service in dev.yml"
    # dev keeps a grafana override re-enabling anonymous auth for local convenience:
    assert "GF_AUTH_ANONYMOUS_ENABLED" in dev_text
    assert "grafana" in dev["services"]
    # app + postgres + traefik stay:
    assert "traefik" in dev["services"] and "postgres" in dev["services"]


def test_render_postgres_obs(tmp_path: Path):
    import json as _j

    import yaml as _y

    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # baseline — postgres is always-on
    prom = (
        dest / "infra" / "observability" / "prometheus" / "prometheus.yml"
    ).read_text()
    assert "job_name: postgres" in prom
    alerts = (
        dest
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "postgres_alerts.yml"
    )
    dash = dest / "infra" / "observability" / "grafana" / "dashboards" / "postgres.json"
    assert alerts.exists() and dash.exists()
    assert _y.safe_load(alerts.read_text())["groups"][0]["name"] == "postgres"
    assert _j.loads(dash.read_text())["uid"] == "postgres"


def test_render_merge_wiring(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    tf = (dest / "Taskfile.yml").read_text()
    assert "-f infra/compose/observability.yml" in tf
    lite_line = next(ln for ln in tf.splitlines() if "--profile lite" in ln)
    assert "observability.yml" not in lite_line  # dev:lite opts out
    env = (dest / ".env.example").read_text()
    assert "APP_ALERT_WEBHOOK_URL" in env and "GRAFANA_ADMIN_PASSWORD" in env
    strat = (dest / "infra" / "deploy" / "strategy.sh").read_text()
    assert "observability.yml" in strat  # place-image guidance references the overlay


def test_render_alertmanager_webhook(tmp_path: Path):
    import yaml as _y

    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    am = (
        dest / "infra" / "observability" / "alertmanager" / "alertmanager.yml"
    ).read_text()
    assert "null" not in am  # no longer the null receiver
    assert "webhook_configs" in am and "url_file" in am
    cfg = _y.safe_load(am)
    assert cfg["route"]["receiver"] != "null"


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker required for compose config"
)
def test_prod_plus_overlay_merges_with_obs_stack(tmp_path: Path) -> None:
    """Docker compose config merge-validation: proves the obs overlay wiring is correct.

    Three scenarios:
    1. prod + overlay → valid topology including obs stack + app + postgres; grafana auth-required.
    2. dev:lite (base + dev, no overlay) → NO obs services.
    3. dev (base + overlay + dev) → grafana anonymous (dev override wins via merge order).
    """
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    comp = dest / "infra" / "compose"
    base_env = {**os.environ, "APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x"}

    # --- Scenario 1: prod + overlay → full obs stack, auth-required grafana ---

    r = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(comp / "prod.yml"),
            "-f",
            str(comp / "observability.yml"),
            "config",
        ],
        capture_output=True,
        text=True,
        env=base_env,
    )
    assert r.returncode == 0, f"prod + overlay compose config failed:\n{r.stderr}"
    for svc in (
        "prometheus",
        "grafana",
        "alertmanager",
        "postgres-exporter",
        "app",
        "postgres",
    ):
        assert svc in r.stdout, f"service '{svc}' missing from prod+overlay config"
    # prod grafana must NOT have anonymous auth (the overlay is prod-safe):
    assert "GF_AUTH_ANONYMOUS_ENABLED" not in r.stdout, (
        "prod grafana must not have GF_AUTH_ANONYMOUS_ENABLED — the overlay is prod-safe"
    )

    # --- Scenario 2: dev:lite (base + dev, no overlay) → no obs services ---
    r2 = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(comp / "base.yml"),
            "-f",
            str(comp / "dev.yml"),
            "--profile",
            "lite",
            "config",
        ],
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    assert r2.returncode == 0, f"dev:lite compose config failed:\n{r2.stderr}"
    assert "prometheus" not in r2.stdout, (
        "dev:lite must not include prometheus — the overlay was not merged"
    )

    # --- Scenario 3: dev (base + overlay + dev) → grafana is anonymous (dev override wins) ---
    r3 = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(comp / "base.yml"),
            "-f",
            str(comp / "observability.yml"),
            "-f",
            str(comp / "dev.yml"),
            "--profile",
            "dev",
            "config",
        ],
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    assert r3.returncode == 0, f"dev compose config failed:\n{r3.stderr}"
    assert "GF_AUTH_ANONYMOUS_ENABLED" in r3.stdout, (
        "dev grafana must have GF_AUTH_ANONYMOUS_ENABLED — dev.yml override must win over the overlay"
    )


def test_render_services_overlay_workers(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    svc = (dest / "infra" / "compose" / "services.yml").read_text()
    import yaml as _y

    cfg = _y.safe_load(svc)
    assert (
        "redis" in cfg["services"]
        and "worker" in cfg["services"]
        and "beat" in cfg["services"]
    )
    assert "${APP_IMAGE" in svc and 'APP_RUN_MIGRATIONS: "false"' in svc
    assert "celery" in svc and "redisdata" in cfg["volumes"]


def test_render_services_overlay_mongodb(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})
    cfg = __import__("yaml").safe_load(
        (dest / "infra" / "compose" / "services.yml").read_text()
    )
    assert "mongo" in cfg["services"] and "mongodata" in cfg["volumes"]


def test_render_services_overlay_empty_is_valid(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # no battery → valid YAML no-op (comment only)
    svc = (dest / "infra" / "compose" / "services.yml").read_text()
    parsed = __import__("yaml").safe_load(svc)  # must not raise
    assert not (parsed or {}).get("services")  # no battery services


def test_render_exporters_in_observability_overlay(tmp_path: Path):
    for batteries, exporter in (
        (["workers"], "celery-exporter"),
        (["mongodb"], "mongodb-exporter"),
    ):
        dest = tmp_path / ("e_" + exporter)
        render_project(dest, {**DATA, "batteries": batteries})
        obs = (dest / "infra" / "compose" / "observability.yml").read_text()
        dev = (dest / "infra" / "compose" / "dev.yml").read_text()
        assert exporter in obs, f"{exporter} should be in observability.yml"
        assert exporter not in dev, f"{exporter} should be gone from dev.yml"


def test_render_services_deploy_guidance(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    strat = (dest / "infra" / "deploy" / "strategy.sh").read_text()
    assert "services.yml" in strat  # place-image guidance merges the services overlay
    readme = (dest / "infra" / "deploy" / "README.md").read_text()
    assert "services.yml" in readme and "managed" in readme.lower()


def test_dev_and_services_images_match(tmp_path: Path):
    """Image-drift guard: dev.yml and services.yml must pin the same image tags."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb", "workers"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    svc = (dest / "infra" / "compose" / "services.yml").read_text()
    for image in ("mongo:7", "redis:7-alpine"):
        assert image in dev and image in svc, (
            f"{image} drifted between dev.yml and services.yml"
        )


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker required for compose config"
)
def test_prod_plus_services_plus_obs_merges(tmp_path: Path):
    """Docker compose config merge-validation: proves prod+services+obs wiring is correct.

    Asserts the headline SVC-PROD property: prod.yml + services.yml + observability.yml
    produces a valid topology with worker/beat on the promoted image (APP_RUN_MIGRATIONS=false),
    mongo/redis, app/postgres, and both battery exporters. dev:lite remains clean (no workers).
    """
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb", "workers"]})
    comp = dest / "infra" / "compose"
    env = {**os.environ, "APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x"}
    r = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(comp / "prod.yml"),
            "-f",
            str(comp / "services.yml"),
            "-f",
            str(comp / "observability.yml"),
            "config",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    for svc in (
        "worker",
        "beat",
        "redis",
        "mongo",
        "app",
        "postgres",
        "mongodb-exporter",
        "celery-exporter",
        "prometheus",
    ):
        assert svc in r.stdout, f"{svc} missing from prod+services+obs merge"
    # worker/beat run the promoted image with APP_RUN_MIGRATIONS=false
    assert "APP_RUN_MIGRATIONS" in r.stdout and "demo:ci" in r.stdout

    # dev:lite (no overlays) still has its data stores + NO worker/beat/exporters:
    r2 = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(comp / "base.yml"),
            "-f",
            str(comp / "dev.yml"),
            "--profile",
            "lite",
            "config",
        ],
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    assert r2.returncode == 0 and "redis" in r2.stdout and "worker" not in r2.stdout


def test_timescaledb_migration_ordering():
    from framework_cli.migrations import migration_down_revisions

    assert migration_down_revisions(["timescaledb"]) == {"timescaledb": "0001"}
    assert migration_down_revisions(["pgvector", "timescaledb"]) == {
        "pgvector": "0001",
        "timescaledb": "0004",
    }


def test_render_timescaledb_battery(tmp_path):
    dest = tmp_path / "ts"
    render_project(dest, {**DATA, "batteries": ["timescaledb"]})
    assert (dest / "src" / "demo" / "timeseries" / "repository.py").exists()
    mig = (dest / "migrations" / "versions" / "0005_readings.py").read_text()
    assert "create_hypertable" in mig
    assert 'down_revision = "0001"' in mig
    df = (dest / "infra" / "docker" / "postgres.Dockerfile").read_text()
    # timescaledb is COPYed from the pinned -ha image (no packagecloud apt) — Plan 15
    assert "COPY --from=timescale/timescaledb-ha:pg17.10-ts2.27.1" in df
    assert "packagecloud.io" not in df  # the flaky apt source is gone
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "shared_preload_libraries=timescaledb" in dev
    # prod + staging carry the same shared_preload_libraries command (regression guard)
    assert (
        "shared_preload_libraries=timescaledb"
        in (dest / "infra" / "compose" / "prod.yml").read_text()
    )
    assert (
        "shared_preload_libraries=timescaledb"
        in (dest / "infra" / "compose" / "staging.yml").read_text()
    )
    assert "timeseries import models" in (dest / "migrations" / "env.py").read_text()


def test_uses_postgres_extension_render_switches_postgres_image(tmp_path):
    """With pgvector, dev/test Postgres build the custom Dockerfile; baseline stays postgres:17."""
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "infra" / "docker" / "postgres.Dockerfile").exists()
    assert "image: postgres:17" in (base / "infra" / "compose" / "dev.yml").read_text()
    assert "image: postgres:17" in (base / "infra" / "compose" / "test.yml").read_text()

    ext = tmp_path / "ext"
    render_project(ext, {**DATA, "batteries": ["pgvector"]})
    dockerfile = ext / "infra" / "docker" / "postgres.Dockerfile"
    assert dockerfile.exists()
    assert "postgresql-17-pgvector" in dockerfile.read_text()
    dev = (ext / "infra" / "compose" / "dev.yml").read_text()
    assert "dockerfile: infra/docker/postgres.Dockerfile" in dev
    assert "image: postgres:17" not in dev
    test = (ext / "infra" / "compose" / "test.yml").read_text()
    assert "dockerfile: infra/docker/postgres.Dockerfile" in test
    assert "image: postgres:17" not in test


def test_prod_staging_postgres_image_switches_for_extensions(tmp_path):
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert "image: postgres:17" in (base / "infra" / "compose" / "prod.yml").read_text()
    assert (
        "image: postgres:17" in (base / "infra" / "compose" / "staging.yml").read_text()
    )

    ext = tmp_path / "ext"
    render_project(ext, {**DATA, "batteries": ["pgvector"]})
    prod = (ext / "infra" / "compose" / "prod.yml").read_text()
    assert "${POSTGRES_IMAGE" in prod and "image: postgres:17" not in prod
    staging = (ext / "infra" / "compose" / "staging.yml").read_text()
    assert "${POSTGRES_IMAGE" in staging and "image: postgres:17" not in staging


def test_age_migration_ordering():
    from framework_cli.migrations import migration_down_revisions

    assert migration_down_revisions(["age"]) == {"age": "0001"}
    assert migration_down_revisions(["timescaledb", "age"]) == {
        "timescaledb": "0001",
        "age": "0005",
    }
    assert migration_down_revisions(["pgvector", "timescaledb", "age"]) == {
        "pgvector": "0001",
        "timescaledb": "0004",
        "age": "0005",
    }


def test_render_age_battery_foundation(tmp_path):
    dest = tmp_path / "age"
    render_project(dest, {**DATA, "batteries": ["age"]})
    df = (dest / "infra" / "docker" / "postgres.Dockerfile").read_text()
    assert "apache/age:release_PG17_1.6.0" in df and "age.so" in df
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "shared_preload_libraries=age" in dev
    mig = (dest / "migrations" / "versions" / "0006_graph.py").read_text()
    assert "create_graph" in mig and 'down_revision = "0001"' in mig
    # combined preload list when timescaledb + age
    both = tmp_path / "both"
    render_project(both, {**DATA, "batteries": ["timescaledb", "age"]})
    assert (
        "shared_preload_libraries=timescaledb,age"
        in (both / "infra" / "compose" / "dev.yml").read_text()
    )


def test_render_age_graph_package(tmp_path):
    dest = tmp_path / "age"
    render_project(dest, {**DATA, "batteries": ["age"]})
    assert (dest / "src" / "demo" / "graph" / "repository.py").exists()
    assert (dest / "tests" / "functional" / "test_graph.py").exists()
    repo = (dest / "src" / "demo" / "graph" / "repository.py").read_text()
    assert "cypher(" in repo and "app_graph" in repo
    # the relationship-type colon must stay escaped (\:) or text() misreads :KNOWS as a bind param
    assert r"\:" in repo, "colon-escape missing — relate() would raise on :KNOWS"
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "src" / "demo" / "graph").exists()


# ---------------------------------------------------------------------------
# T6: integrity across slice-2 battery combos + migration chain + preload
# coverage + downskill (age / timescaledb)
# ---------------------------------------------------------------------------


def _git_init_commit(project: Path) -> None:
    """Initialise a git repo and commit everything (required for remove_battery)."""
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(project),
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.email=test@test",
            "-c",
            "user.name=Test",
            "commit",
            "-qm",
            "scaffold",
        ],
        check=True,
    )


@pytest.mark.parametrize(
    "batteries",
    [
        [],
        ["pgvector"],
        ["timescaledb"],
        ["age"],
        ["pgvector", "timescaledb"],
        ["timescaledb", "age"],
        ["pgvector", "age"],
        ["pgvector", "timescaledb", "age"],
        ["webhooks", "workers", "pgvector", "timescaledb", "age"],
        ["workers", "mongodb", "age", "timescaledb"],
    ],
)
def test_integrity_green_for_slice2_combos(tmp_path, batteries):
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": batteries})
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []


def test_full_migration_chain_ordering():
    from framework_cli.migrations import migration_down_revisions

    assert migration_down_revisions(
        ["webhooks", "workers", "pgvector", "timescaledb", "age"]
    ) == {
        "webhooks": "0001",
        "workers": "0002",
        "pgvector": "0003",
        "timescaledb": "0004",
        "age": "0005",
    }


def test_preload_join_in_all_compose_files(tmp_path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["timescaledb", "age"]})
    for f in ["dev.yml", "test.yml", "prod.yml", "staging.yml"]:
        text = (dest / "infra" / "compose" / f).read_text()
        assert "shared_preload_libraries=timescaledb,age" in text, (
            f"{f} is missing the joined preload 'shared_preload_libraries=timescaledb,age'"
        )
    # conftest builds the testcontainer with the same joined preload — assigned to a
    # `preload` var + interpolated, so the with_command line is a constant length and
    # stays ruff-format-stable across preload combos (see conftest.py.jinja).
    conftest = (dest / "tests" / "conftest.py").read_text()
    assert 'preload = "timescaledb,age"' in conftest, (
        "tests/conftest.py is missing the joined preload 'timescaledb,age'"
    )
    assert "shared_preload_libraries={preload}" in conftest, (
        "tests/conftest.py is missing the shared_preload_libraries command"
    )


def test_downskill_age_no_force(tmp_path):
    from framework_cli.downskill import remove_battery
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["age"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "age", force=False)
    assert not (dest / "src" / "demo" / "graph").exists()
    # migrations preserved (8a-2 rule)
    assert (dest / "migrations" / "versions" / "0006_graph.py").exists()
    assert check(dest, ci=True) == []


def test_downskill_timescaledb_no_force(tmp_path):
    from framework_cli.downskill import remove_battery
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["timescaledb"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "timescaledb", force=False)
    assert not (dest / "src" / "demo" / "timeseries").exists()
    # preserved (8a-2 rule)
    assert (dest / "migrations" / "versions" / "0005_readings.py").exists()
    assert check(dest, ci=True) == []


def test_redis_service_shared_by_workers_or_redis(tmp_path):
    for bats, want_redis, want_worker in [
        ([], False, False),
        (["redis"], True, False),
        (["workers"], True, True),
        (["workers", "redis"], True, True),
    ]:
        d = tmp_path / ("_".join(bats) or "base")
        render_project(d, {**DATA, "batteries": bats})
        dev = (d / "infra" / "compose" / "dev.yml").read_text()
        assert dev.count("\n  redis:\n") == (1 if want_redis else 0), (
            bats,
            "redis svc count",
        )
        assert ("\n  worker:\n" in dev) == want_worker, (bats, "worker presence")
        settings = (d / "src" / "demo" / "config" / "settings.py").read_text()
        assert settings.count("redis_url:") == (1 if want_redis else 0), (
            bats,
            "redis_url count",
        )


def test_render_redis_cache_package(tmp_path):
    dest = tmp_path / "r"
    render_project(dest, {**DATA, "batteries": ["redis"]})
    assert (dest / "src" / "demo" / "cache" / "client.py").exists()
    repo = (dest / "src" / "demo" / "cache" / "repository.py").read_text()
    assert "cache_set" in repo and "cache_get" in repo and "cache_delete" in repo
    health = (dest / "src" / "demo" / "routes" / "health.py").read_text()
    assert "redis" in health and "ping" in health
    pyproject = (dest / "pyproject.toml").read_text()
    assert "redis>=5" in pyproject and "testcontainers[redis]" in pyproject
    assert (dest / "tests" / "functional" / "test_cache.py").exists()
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "src" / "demo" / "cache").exists()


def test_render_redis_observability(tmp_path):
    for bats in (["redis"], ["workers"], ["workers", "redis"]):
        d = tmp_path / "_".join(bats)
        render_project(d, {**DATA, "batteries": bats})
        obs = (d / "infra" / "compose" / "observability.yml").read_text()
        assert obs.count("\n  redis-exporter:\n") == 1, (bats, "one redis-exporter")
        prom = (
            d / "infra" / "observability" / "prometheus" / "prometheus.yml"
        ).read_text()
        assert "job_name: redis" in prom
        assert (
            d / "infra" / "observability" / "prometheus" / "alerts" / "redis_alerts.yml"
        ).exists()
        assert (
            d / "infra" / "observability" / "grafana" / "dashboards" / "redis.json"
        ).exists()
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert (
        "redis-exporter"
        not in (base / "infra" / "compose" / "observability.yml").read_text()
    )
    assert (
        "job_name: redis"
        not in (
            base / "infra" / "observability" / "prometheus" / "prometheus.yml"
        ).read_text()
    )


# ---------------------------------------------------------------------------
# T4: integrity across redis battery combos + downskill (shared-infra retained)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "batteries",
    [
        [],
        ["redis"],
        ["workers"],
        ["workers", "redis"],
        ["workers", "redis", "mongodb", "pgvector"],
    ],
)
def test_integrity_green_for_redis_combos(tmp_path, batteries):
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": batteries})
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []


def test_downskill_redis_alone_no_force(tmp_path):
    from framework_cli.downskill import remove_battery
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["redis"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "redis", force=False)
    assert not (dest / "src" / "demo" / "cache").exists()
    assert "\n  redis:\n" not in (dest / "infra" / "compose" / "dev.yml").read_text()
    assert (
        "redis_url:"
        not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    )
    assert check(dest, ci=True) == []


def test_downskill_redis_keeps_shared_infra_when_workers_remains(tmp_path):
    from framework_cli.downskill import remove_battery
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["workers", "redis"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "redis", force=False)
    assert not (dest / "src" / "demo" / "cache").exists()  # cache package gone
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "\n  redis:\n" in dev  # redis service STAYS (workers needs it)
    assert (
        "redis_url:" in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    )
    assert (
        "redis-exporter"
        in (dest / "infra" / "compose" / "observability.yml").read_text()
    )
    assert check(dest, ci=True) == []


def test_render_react_frontend_scaffold(tmp_path):
    dest = tmp_path / "r"
    render_project(dest, {**DATA, "batteries": ["react"]})
    fe = dest / "frontend"
    assert (fe / "package.json").exists()
    assert (fe / "vite.config.ts").exists()
    assert (fe / "src" / "Items.tsx").exists()
    assert (fe / "src" / "Items.test.tsx").exists()
    assert (fe / "e2e" / "items.spec.ts").exists()
    pkg = (fe / "package.json").read_text()
    assert "vite" in pkg and "vitest" in pkg and "@axe-core/playwright" in pkg
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "frontend").exists()


def test_render_react_serving_wiring(tmp_path):
    dest = tmp_path / "r"
    render_project(dest, {**DATA, "batteries": ["react"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "\n  frontend:\n" in dev and "node:" in dev
    dockerfile = (dest / "infra" / "docker" / "Dockerfile").read_text()
    assert "frontend-build" in dockerfile and "npm run build" in dockerfile
    main = (dest / "src" / "demo" / "main.py").read_text()
    assert "StaticFiles" in main and "frontend/dist" in main
    assert "frontend/dist" in (dest / ".gitignore").read_text()
    # host node_modules must be kept out of the docker build context (else COPY frontend/ clobbers npm ci)
    assert "frontend/node_modules" in (dest / ".dockerignore").read_text()
    # baseline: none of it
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert "frontend" not in (base / "infra" / "compose" / "dev.yml").read_text()
    assert "StaticFiles" not in (base / "src" / "demo" / "main.py").read_text()
    assert (
        "frontend-build" not in (base / "infra" / "docker" / "Dockerfile").read_text()
    )


def test_render_react_ci_job(tmp_path):
    import yaml

    dest = tmp_path / "r"
    render_project(dest, {**DATA, "batteries": ["react"]})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "frontend:" in ci and "setup-node" in ci and "vitest" in ci.lower()
    yaml.safe_load(ci)  # valid YAML
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert "setup-node" not in (base / ".github" / "workflows" / "ci.yml").read_text()


# ---------------------------------------------------------------------------
# T6: integrity across react battery combos + downskill
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "batteries",
    [[], ["react"], ["react", "graphql"], ["react", "workers", "redis"]],
)
def test_integrity_green_for_react_combos(tmp_path, batteries):
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": batteries})
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []


def test_downskill_react_no_force(tmp_path):
    from framework_cli.downskill import remove_battery
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["react"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "react", force=False)
    assert not (dest / "frontend").exists()
    assert "StaticFiles" not in (dest / "src" / "demo" / "main.py").read_text()
    assert "setup-node" not in (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "\n  frontend:\n" not in (dest / "infra" / "compose" / "dev.yml").read_text()
    assert check(dest, ci=True) == []


def test_render_consumers_foundation(tmp_path):
    dest = tmp_path / "c"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    assert (dest / "src" / "demo" / "clients" / "inventory.py").exists()
    assert (
        "inventory_url"
        in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    )
    pyproject = (dest / "pyproject.toml").read_text()
    assert "pact-python" in pyproject and "httpx" in pyproject
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "src" / "demo" / "clients").exists()
    assert (
        "inventory_url"
        not in (base / "src" / "demo" / "config" / "settings.py").read_text()
    )


def test_render_consumers_consumer_test(tmp_path):
    dest = tmp_path / "c"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    t = (dest / "tests" / "functional" / "test_consumer_inventory.py").read_text()
    assert "from pact import Pact" in t and "get_stock" in t and "pact.serve()" in t
    assert "pacts/" in (dest / ".gitignore").read_text()
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "tests" / "functional" / "test_consumer_inventory.py").exists()


def test_render_consumers_provider(tmp_path):
    dest = tmp_path / "c"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    pact_file = dest / "pacts" / "examplewebapp-app.json"
    assert pact_file.exists()
    doc = json.loads(pact_file.read_text())
    assert doc["provider"]["name"] == "app"
    t = (dest / "tests" / "contract" / "test_provider_pact.py").read_text()
    assert "from pact import Verifier" in t and "add_transport" in t
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "pacts").exists()
    assert not (base / "tests" / "contract").exists()


def test_render_consumers_ci_and_broker(tmp_path):
    dest = tmp_path / "c"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "test_provider_pact" in ci or "contract:pact" in ci
    yaml.safe_load(ci)
    assert (dest / "scripts" / "pact-publish.sh").exists()
    assert "PACT_BROKER_URL" in (dest / "scripts" / "pact-publish.sh").read_text()
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert (
        "test_provider_pact"
        not in (base / ".github" / "workflows" / "ci.yml").read_text()
    )


# ---------------------------------------------------------------------------
# Consumers: integrity combos + downskill
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "batteries",
    [[], ["consumers"], ["consumers", "graphql"], ["consumers", "workers"]],
)
def test_integrity_green_for_consumers_combos(tmp_path, batteries):
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": batteries})
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []


def test_downskill_consumers_no_force(tmp_path):
    from framework_cli.downskill import remove_battery
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "consumers", force=False)
    assert not (dest / "src" / "demo" / "clients").exists()
    assert not (dest / "tests" / "contract").exists()
    assert not (dest / "pacts").exists()
    assert (
        "inventory_url"
        not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    )
    assert (
        "test_provider_pact"
        not in (dest / ".github" / "workflows" / "ci.yml").read_text()
    )
    assert check(dest, ci=True) == []


# ---------------------------------------------------------------------------
# Alertmanager: conditional receivers per alert_channels
# ---------------------------------------------------------------------------

ALERTMANAGER_DEFAULT = """\
route:
  receiver: "default"
  group_by: ["alertname"]
  group_wait: 10s
  group_interval: 1m
  repeat_interval: 1h

receivers:
  - name: "default"
    webhook_configs:
      # The URL is read from a mounted file (the APP_ALERT_WEBHOOK_URL secret, materialized on
      # deploy at /etc/alertmanager/webhook_url). When the file is absent (e.g. local dev),
      # alertmanager still loads this config; notifications simply no-op until it exists.
      - url_file: /etc/alertmanager/webhook_url
        send_resolved: true
"""


def test_alertmanager_byte_identical_for_default_webhook(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # alert_channels defaults to ["webhook"]
    rendered = (dest / "infra/observability/alertmanager/alertmanager.yml").read_text()
    assert rendered == ALERTMANAGER_DEFAULT


def test_alertmanager_renders_slack_and_pagerduty(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["slack", "pagerduty"]})
    text = (dest / "infra/observability/alertmanager/alertmanager.yml").read_text()
    assert (
        "slack_configs:" in text
        and "api_url_file: /etc/alertmanager/slack_api_url" in text
    )
    assert (
        "pagerduty_configs:" in text
        and "routing_key_file: /etc/alertmanager/pagerduty_routing_key" in text
    )
    assert "webhook_configs:" not in text  # webhook not selected
    parsed = yaml.safe_load(text)
    assert parsed["receivers"][0]["name"] == "default"


def test_alertmanager_renders_email(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["email"]})
    text = (dest / "infra/observability/alertmanager/alertmanager.yml").read_text()
    assert "email_configs:" in text
    assert "auth_password_file: /etc/alertmanager/smtp_auth_password" in text
    assert yaml.safe_load(text)["receivers"][0]["name"] == "default"


# ---------------------------------------------------------------------------
# .env.example managed section: per-channel alert secret vars
# ---------------------------------------------------------------------------


def test_env_example_default_has_only_webhook_secret(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    env = (dest / ".env.example").read_text()
    assert "APP_ALERT_WEBHOOK_URL=" in env
    assert "APP_ALERT_SLACK_API_URL" not in env
    assert "APP_ALERT_PAGERDUTY_ROUTING_KEY" not in env
    assert "APP_ALERT_SMTP_" not in env


def test_env_example_adds_selected_channel_secrets(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["slack", "email", "pagerduty"]})
    env = (dest / ".env.example").read_text()
    assert "APP_ALERT_SLACK_API_URL=" in env
    assert "APP_ALERT_PAGERDUTY_ROUTING_KEY=" in env
    for v in ("SMARTHOST", "FROM", "TO", "AUTH_USERNAME", "AUTH_PASSWORD"):
        assert f"APP_ALERT_SMTP_{v}=" in env
    # webhook not selected → its var absent
    assert "APP_ALERT_WEBHOOK_URL=" not in env


# ---------------------------------------------------------------------------
# Alert-secrets deploy precondition (Task 7)
# ---------------------------------------------------------------------------


def _run_precondition(dest: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(dest / "infra/deploy/check_alert_secrets.sh")],
        env={"PATH": os.environ["PATH"], **env},
        capture_output=True,
        text=True,
    )


def test_alert_precondition_fails_when_secret_missing(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["slack"]})
    result = _run_precondition(dest, {})  # APP_ALERT_SLACK_API_URL unset
    assert result.returncode == 1
    assert "APP_ALERT_SLACK_API_URL" in result.stderr


def test_alert_precondition_passes_when_secret_present(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["slack"]})
    result = _run_precondition(
        dest, {"APP_ALERT_SLACK_API_URL": "https://hooks.example/x"}
    )
    assert result.returncode == 0, result.stderr


def test_alert_precondition_default_checks_webhook(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert _run_precondition(dest, {}).returncode == 1  # webhook url missing
    assert (
        _run_precondition(dest, {"APP_ALERT_WEBHOOK_URL": "https://x"}).returncode == 0
    )


def test_alert_precondition_email_reports_all_missing_secrets(tmp_path: Path):
    # email is the multi-secret channel: with only some set, ALL missing ones must be named
    # (accumulate-then-exit, not fail-on-first).
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["email"]})
    result = _run_precondition(
        dest,
        {"APP_ALERT_SMTP_SMARTHOST": "smtp:587", "APP_ALERT_SMTP_FROM": "a@x"},
    )
    assert result.returncode == 1
    assert "APP_ALERT_SMTP_TO" in result.stderr
    assert "APP_ALERT_SMTP_AUTH_PASSWORD" in result.stderr


# ---------------------------------------------------------------------------
# Always-on meta-alert: AlertmanagerNotificationsFailing
# ---------------------------------------------------------------------------


def test_alertmanager_meta_alert_present_always(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # no batteries, default channels
    rule = dest / "infra/observability/prometheus/alerts/alertmanager_alerts.yml"
    assert rule.is_file()
    parsed = yaml.safe_load(rule.read_text())
    names = {r["alert"] for g in parsed["groups"] for r in g["rules"]}
    assert "AlertmanagerNotificationsFailing" in names
    assert "alertmanager_notifications_failed_total" in rule.read_text()


# ---------------------------------------------------------------------------
# #3 Advisory alert delivery smoke
# ---------------------------------------------------------------------------


class _FakeAM(http.server.BaseHTTPRequestHandler):
    failed_total = 0.0  # set per test

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):  # /api/v2/alerts
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):  # /metrics
        body = (
            'alertmanager_notifications_failed_total{integration="webhook"} '
            f"{self.failed_total}\n"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)


def _serve_fake_am(failed_total: float):
    _FakeAM.failed_total = failed_total
    srv = http.server.HTTPServer(("127.0.0.1", 0), _FakeAM)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _run_smoke(dest: Path, am_url: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(dest / "infra/deploy/alert_smoke.sh")],
        env={"PATH": os.environ["PATH"], "ALERTMANAGER_URL": am_url, "SMOKE_WAIT": "1"},
        capture_output=True,
        text=True,
    )


def test_alert_smoke_reports_failure_but_exits_zero(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    srv = _serve_fake_am(failed_total=3.0)  # non-zero failures present
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        result = _run_smoke(dest, url)
    finally:
        srv.shutdown()
    assert result.returncode == 0  # advisory — never fails the deploy
    assert "delivery" in (result.stdout + result.stderr).lower()


def test_alert_smoke_clean_when_no_failures(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    srv = _serve_fake_am(failed_total=0.0)
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        result = _run_smoke(dest, url)
    finally:
        srv.shutdown()
    assert result.returncode == 0
    assert "ok" in (result.stdout + result.stderr).lower()


def test_alert_smoke_advisory_when_alertmanager_unreachable(tmp_path: Path):
    # The common CI case: Alertmanager not reachable from the runner → skip, still exit 0.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    result = _run_smoke(dest, "http://127.0.0.1:1")  # port 1 → connection refused
    assert result.returncode == 0
    assert "could not reach" in (result.stdout + result.stderr).lower()


def test_integrity_green_across_alert_channel_combos(tmp_path: Path):
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    for i, channels in enumerate(
        [
            ["webhook"],
            ["slack"],
            ["email", "pagerduty"],
            ["webhook", "slack", "email", "pagerduty"],
        ]
    ):
        dest = tmp_path / f"demo{i}"
        render_project(dest, {**DATA, "alert_channels": channels})
        write_manifest(dest, installed_framework_version())
        findings = check(dest, ci=True)
        assert not [f for f in findings if f.fatal], (channels, findings)


def test_dev_app_runs_as_host_uid(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    dev = (dest / "infra/compose/dev.yml").read_text()
    parsed = yaml.safe_load(dev)
    assert parsed["services"]["app"]["user"] == "${UID:-1000}:${GID:-1000}"


def test_taskfile_dev_plumbs_uid_gid(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    tf = yaml.safe_load((dest / "Taskfile.yml").read_text())
    for task in ("dev", "dev:lite"):
        env = tf["tasks"][task]["env"]
        assert env["UID"] == {"sh": "id -u"}
        assert env["GID"] == {"sh": "id -g"}


def test_secrets_doc_renders_with_convention(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    secrets = (dest / "SECRETS.md").read_text()
    # the two-tier naming convention + the project's secrets are documented
    assert "ANTHROPIC_RUNTIME_API_KEY" in secrets
    assert "GITLEAKS_LICENSE" in secrets
    assert "provider console" in secrets.lower()
    # project/package name interpolates (DATA → project_name="Demo", package_name="demo")
    assert "demo" in secrets.lower()
    # the `{{ package_name | upper }}` filter inside a markdown table cell renders correctly
    assert "ANTHROPIC_DEMO_CI_RUNTIME" in secrets


def test_app_host_compose_renders_app_only(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(dest, DATA)
    compose = dest / "infra/compose/app-host.yml"
    assert compose.exists(), "app-host.yml was not rendered"
    text = compose.read_text()
    # app-only: the app service on image:${APP_IMAGE}, migrations OFF, no postgres service.
    assert "image: ${APP_IMAGE" in text
    assert 'APP_RUN_MIGRATIONS: "false"' in text
    assert "postgres:" not in text, "app-host.yml must not define a Postgres service"
    assert "traefik" not in text.lower(), (
        "app hosts serve plain HTTP behind the builder's LB"
    )


def test_deploy_readme_documents_compose_ssh_target(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(dest, DATA)
    readme = (dest / "infra/deploy/README.md").read_text()
    assert "DEPLOY_TARGET=compose-ssh" in readme
    assert "DEPLOY_HOSTS" in readme
    assert "load balancer" in readme.lower()


def test_deploy_workflows_pass_through_deploy_target(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(dest, DATA)
    for wf in (
        ".github/workflows/deploy-staging.yml",
        ".github/workflows/deploy-prod.yml",
    ):
        text = (dest / wf).read_text()
        assert "DEPLOY_TARGET" in text, f"{wf} does not pass through DEPLOY_TARGET"


def test_contract_job_self_seeds_openapi_when_untracked(tmp_path: Path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": []})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    # tracked-vs-untracked branch + the tracked guard
    assert "git ls-files --error-unmatch openapi.json" in ci
    assert "openapi_tracked=true" in ci and "openapi_tracked=false" in ci
    # oasdiff is gated on tracked-ness (won't 404 on base for a never-committed spec)
    assert "steps.spec.outputs.openapi_tracked == 'true'" in ci


def test_contract_job_self_seeds_graphql_schema_when_untracked(tmp_path: Path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "git ls-files --error-unmatch schema.graphql" in ci
    assert "steps.gqlspec.outputs.schema_tracked == 'true'" in ci


def test_timescaledb_copies_from_prebuilt_image_no_packagecloud(tmp_path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["timescaledb"]})
    df = (dest / "infra" / "docker" / "postgres.Dockerfile").read_text()
    assert (
        "COPY --from=timescale/timescaledb-ha:pg17" in df
    )  # timescaledb COPY'd from prebuilt
    assert "packagecloud.io" not in df  # the flaky apt is gone
    assert "FROM postgres:17" in df  # base unchanged (COPY, not a swap)


def test_non_timescaledb_extension_keeps_postgres_base(tmp_path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["pgvector"]})
    df = (dest / "infra" / "docker" / "postgres.Dockerfile").read_text()
    assert "FROM postgres:17" in df  # unchanged for non-timescaledb
    assert "timescaledb-ha" not in df
    assert "postgresql-17-pgvector" in df  # pgvector PGDG apt retained


def test_age_copy_present_on_both_bases(tmp_path):
    for bats in (["age"], ["timescaledb", "age"]):
        dest = tmp_path / ("p_" + "_".join(bats))
        render_project(dest, {**DATA, "batteries": bats})
        df = (dest / "infra" / "docker" / "postgres.Dockerfile").read_text()
        assert "apache/age:release_PG17_1.6.0" in df


def test_oasdiff_gated_on_base_spec_existence(tmp_path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": []})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "base_has_openapi=true" in ci and "base_has_openapi=false" in ci
    assert "curl -sfI" in ci  # probes the base branch's openapi.json over HTTP
    assert "steps.spec.outputs.base_has_openapi == 'true'" in ci  # oasdiff gated on it


def test_rendered_project_uses_in_process_review(tmp_path: Path):
    """The rendered project ships the in-process review gate, not the dead JS/prepare path."""
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    # the dead Workflow JS is gone from the rendered project
    assert not (dest / ".claude" / "workflows" / "reviewers-audit.js").exists()
    assert not (dest / ".claude" / "workflows" / "reviewers-gate.js").exists()

    # the rendered gate hook invokes `framework gate` (in-process), not gate-prepare
    hook = (dest / ".claude" / "hooks" / "reviewers-gate-check.sh").read_text()
    assert "framework gate" in hook
    assert "gate-prepare" not in hook


def test_render_docs_battery_adds_docs_dependency_group(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    pyproject = (dest / "pyproject.toml").read_text()
    assert "mkdocs-material" in pyproject
    assert "mike" in pyproject
    assert "mkdocs-render-swagger-plugin" in pyproject
    assert "mkdocstrings[python]" in pyproject


def test_render_without_docs_battery_has_no_docs_deps(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    pyproject = (dest / "pyproject.toml").read_text()
    assert "mkdocs" not in pyproject
    assert "mike" not in pyproject


def test_render_docs_battery_creates_mkdocs_site(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    assert (dest / "mkdocs.yml").is_file()
    assert (dest / "documentation" / "index.md").is_file()
    assert (dest / "documentation" / "architecture.md").is_file()
    assert (dest / "documentation" / "api" / "rest.md").is_file()
    assert (dest / "documentation" / "api" / "python.md").is_file()
    assert (dest / "documentation" / "see-also.md").is_file()

    mkdocs = (dest / "mkdocs.yml").read_text()
    assert "material" in mkdocs
    assert "provider: mike" in mkdocs
    assert "mkdocstrings" in mkdocs
    assert "render_swagger" in mkdocs
    assert "Demo" in mkdocs  # title interpolated from project_name

    assert "::: demo" in (dest / "documentation" / "api" / "python.md").read_text()
    assert (
        "!!swagger openapi.json!!"
        in (dest / "documentation" / "api" / "rest.md").read_text()
    )


def test_render_without_docs_battery_has_no_mkdocs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert not (dest / "mkdocs.yml").exists()
    assert not (dest / "documentation").exists()


def test_render_docs_battery_adds_taskfile_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "docs:serve" in taskfile
    assert "docs:build" in taskfile
    assert "docs:deploy" in taskfile
    assert "mike serve" in taskfile
    assert "mkdocs build --strict" in taskfile
    # docs:build must run inside the `ci` task so the render-matrix (`task ci`) exercises it.
    ci_section = taskfile.split("ci:", 1)[1].split("push:", 1)[0]
    assert "docs:build" in ci_section


def test_render_without_docs_battery_has_no_docs_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "docs:serve" not in (dest / "Taskfile.yml").read_text()


def test_render_docs_battery_adds_ci_docs_job(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    ci = yaml.safe_load((dest / ".github" / "workflows" / "ci.yml").read_text())
    assert "docs" in ci["jobs"], "the docs battery must add a `docs` job to ci.yml"
    steps = ci["jobs"]["docs"]["steps"]
    flat = " ".join(str(s.get("run", "")) for s in steps)
    assert "mkdocs build --strict" in flat


def test_render_without_docs_battery_has_no_ci_docs_job(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ci = yaml.safe_load((dest / ".github" / "workflows" / "ci.yml").read_text())
    assert "docs" not in ci["jobs"]


def test_render_docs_battery_adds_publish_workflow(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    path = dest / ".github" / "workflows" / "docs.yml"
    assert path.is_file(), "the docs battery must ship a docs.yml publish workflow"
    wf = yaml.safe_load(path.read_text())
    # PyYAML parses the bare `on:` key as boolean True — assert on that key.
    triggers = wf[True]
    assert "tags" in triggers["push"], "publish must be tag-triggered"
    body = path.read_text()
    assert "mike deploy" in body
    assert "contents: write" in body  # needed to push the gh-pages branch


def test_render_without_docs_battery_has_no_publish_workflow(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert not (dest / ".github" / "workflows" / "docs.yml").exists()


def test_doctor_script_checks_expected_host_tools(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)  # baseline: no react battery
    doctor = (dest / "scripts" / "doctor.sh").read_text()
    for probe in (
        "command -v docker",
        "docker compose version",
        "docker buildx version",
        "command -v mkcert",
        "command -v uv",
        "command -v git",
    ):
        assert probe in doctor, f"doctor.sh missing probe: {probe}"
    assert "command -v node" not in doctor  # node only with the react battery


def test_doctor_script_checks_node_only_with_react(tmp_path: Path):
    dest = tmp_path / "demo_react"
    render_project(dest, {**DATA, "batteries": ["react"]})
    doctor = (dest / "scripts" / "doctor.sh").read_text()
    assert "command -v node" in doctor
    assert "command -v npm" in doctor


def test_doctor_script_is_locked():
    from framework_cli.integrity.classes import LOCKED_TRACKED

    assert "scripts/doctor.sh" in LOCKED_TRACKED


def test_traefik_image_supports_modern_docker_api(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    m = re.search(r"image:\s*traefik:v3\.(\d+)", dev)
    assert m, "traefik image pin not found in dev.yml"
    # v3.6+ added Docker API auto-negotiation; Docker Engine 27+ (min API 1.44) rejects
    # Traefik <=v3.5's hardcoded API 1.24. See 2026-06-12 lock-taxonomy-and-doctor design.
    assert int(m.group(1)) >= 6, f"traefik must be >= v3.6 (found v3.{m.group(1)})"


def test_doctor_task_present_and_not_in_ci(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "\n  doctor:" in taskfile
    assert "bash scripts/doctor.sh" in taskfile
    # doctor is advisory — it must NOT be wired into `task ci` (CI has no mkcert).
    ci_block = taskfile.split("\n  ci:")[1].split("\n  push:")[0]
    assert "doctor" not in ci_block


def test_host_tool_guards_point_at_doctor(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    taskfile = (dest / "Taskfile.yml").read_text()
    # The lazy precondition messages cross-reference the canonical preflight (certs + the
    # three docker guards: dev / dev:lite / dev:reset).
    assert taskfile.count("Run `task doctor`") >= 4


def test_readme_points_at_doctor_for_prerequisites(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    readme = (dest / "README.md").read_text()
    assert "task doctor" in readme
    assert "Prerequisites" in readme
