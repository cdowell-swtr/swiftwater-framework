import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from framework_cli.copier_runner import render_project
from framework_cli.downskill import remove_battery
from framework_cli.integrity.checker import check
from framework_cli.integrity.restore import restore_file

DATA = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def _docker_available() -> bool:
    if shutil.which("uv") is None or shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info"], capture_output=True, timeout=10
    )
    return result.returncode == 0


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_passes_its_own_tests(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(["uv", "run", "pytest", "-q"], cwd=dest)
    assert result.returncode == 0, "the generated project's test suite did not pass"


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_coverage_gate_passes(tmp_path: Path):
    # The fast pre-commit-equivalent gate: unit + functional, >=70%, via scripts/coverage.sh.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(["bash", "scripts/coverage.sh", "70", "unit", "functional"], cwd=dest)
    assert result.returncode == 0, "the 70% unit+functional coverage gate did not pass"


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_websockets_battery_passes(tmp_path: Path):
    # Renders a project with the websockets battery active, asserts the battery files
    # were emitted, then runs unit+functional (70% gate) to confirm the WS echo test
    # (tests/functional/test_websockets.py) is collected and passes.
    data_with_ws = {**DATA, "batteries": ["websockets"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_ws)

    # Battery files must exist in the rendered project.
    assert (dest / "src" / "demo" / "routes" / "websockets.py").exists(), \
        "routes/websockets.py was not rendered by the websockets battery"
    assert (dest / "tests" / "functional" / "test_websockets.py").exists(), \
        "tests/functional/test_websockets.py was not rendered by the websockets battery"
    assert (dest / "src" / "demo" / "websockets" / "connection_manager.py").exists(), \
        "websockets/connection_manager.py was not rendered by the websockets battery"

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Run unit + functional tiers (70% gate) — this collects test_websockets.py.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate did not pass for the websockets battery project:\n"
        + result.stdout + result.stderr
    )
    # Prove the WS functional test actually ran: the route handler reaches full coverage
    # only when test_websocket_echo_broadcast exercises it (router autodiscovery alone
    # imports routes/websockets.py on every create_app() call, yielding ~46% — so the
    # filename appearing in the coverage table is NOT sufficient proof). 100% only occurs
    # when the connect→send→broadcast→receive→disconnect path runs.
    combined_output = result.stdout + result.stderr
    ws_cov_line = next(
        (ln for ln in combined_output.splitlines() if "routes/websockets.py" in ln), ""
    )
    assert "100%" in ws_cov_line, (
        f"WS route not fully exercised; coverage line: {ws_cov_line!r}\n"
        "Expected 100% coverage of routes/websockets.py — was "
        "tests/functional/test_websockets.py collected and did it pass?\n"
        + combined_output
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_webhooks_battery_passes(tmp_path: Path):
    # Renders a project with the webhooks battery active, asserts the battery files
    # were emitted, then runs unit+functional (70% gate) to confirm the webhook tests
    # (tests/functional/test_webhooks.py) are collected and pass — exercising the
    # 0002_webhook_events migration, HMAC signature verification, and dedup logic.
    data_with_webhooks = {**DATA, "batteries": ["webhooks"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_webhooks)

    # Battery files must exist in the rendered project.
    assert (dest / "src" / "demo" / "routes" / "webhooks.py").exists(), \
        "routes/webhooks.py was not rendered by the webhooks battery"
    assert (dest / "tests" / "functional" / "test_webhooks.py").exists(), \
        "tests/functional/test_webhooks.py was not rendered by the webhooks battery"
    assert (dest / "migrations" / "versions" / "0002_webhook_events.py").exists(), \
        "migrations/versions/0002_webhook_events.py was not rendered by the webhooks battery"

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Run unit + functional tiers (70% gate) — this collects test_webhooks.py and runs
    # it against a real testcontainers Postgres (the 0002 migration provisions webhook_events).
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate did not pass for the webhooks battery project:\n"
        + result.stdout + result.stderr
    )
    # Prove the webhook functional tests actually ran: the route handler reaches full coverage
    # only when test_webhooks.py exercises the valid-sig 200 / bad-sig 401 / duplicate-dedup
    # paths (router autodiscovery imports routes/webhooks.py on every create_app() call,
    # yielding ~40% import-only — so the filename appearing is NOT sufficient proof).
    # 100% only occurs when all three test cases run against the real DB.
    combined_output = result.stdout + result.stderr
    wh_cov_line = next(
        (ln for ln in combined_output.splitlines() if "routes/webhooks.py" in ln), ""
    )
    assert "100%" in wh_cov_line, (
        f"Webhook route not fully exercised; coverage line: {wh_cov_line!r}\n"
        "Expected 100% coverage of routes/webhooks.py — was "
        "tests/functional/test_webhooks.py collected and did it pass?\n"
        + combined_output
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_workers_battery_passes(tmp_path: Path):
    # Renders a project with the workers battery active, asserts the battery files
    # were emitted, then runs unit+functional (70% gate) to confirm both workers test
    # files (tests/unit/test_workers_unit.py + tests/functional/test_workers_functional.py)
    # are collected and pass — exercising the 0003_dead_letter migration and DLQ logic.
    data_with_workers = {**DATA, "batteries": ["workers"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_workers)

    # Battery files must exist in the rendered project.
    assert (dest / "src" / "demo" / "tasks" / "app.py").exists(), \
        "tasks/app.py was not rendered by the workers battery"
    assert (dest / "tests" / "unit" / "test_workers_unit.py").exists(), \
        "tests/unit/test_workers_unit.py was not rendered by the workers battery"
    assert (dest / "tests" / "functional" / "test_workers_functional.py").exists(), \
        "tests/functional/test_workers_functional.py was not rendered by the workers battery"
    assert (dest / "migrations" / "versions" / "0003_dead_letter.py").exists(), \
        "migrations/versions/0003_dead_letter.py was not rendered by the workers battery"

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Run unit + functional tiers (70% gate) — this collects both workers test files and
    # runs the functional tests against a real testcontainers Postgres (0003 migration
    # provisions the dead_letter_tasks table). Celery runs in eager mode (autouse session
    # fixture in conftest.py), so no live broker is required.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate did not pass for the workers battery project:\n"
        + result.stdout + result.stderr
    )
    # Prove the workers functional tests actually ran (not just collected): dead_letter.py
    # reaches 100% only when test_workers_functional.py exercises record_failure / count /
    # list_recent / render_dlq_metrics + the on_failure DLQ-drain path against the real DB.
    combined_output = result.stdout + result.stderr
    dlq_cov_line = next(
        (ln for ln in combined_output.splitlines() if "tasks/dead_letter.py" in ln), ""
    )
    assert "100%" in dlq_cov_line, (
        f"DLQ repository not fully exercised; coverage line: {dlq_cov_line!r}\n"
        "Expected 100% coverage of tasks/dead_letter.py — was "
        "tests/functional/test_workers_functional.py collected and did it pass?\n"
        + combined_output
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_webhooks_and_workers_passes(tmp_path: Path):
    # Renders a project with BOTH webhooks + workers batteries, verifies the full
    # migration chain (0001 → 0002 webhook_events → 0003 dead_letter), the webhooks
    # functional tests pass with the enqueue handler (Celery eager mode), and the
    # workers functional tests pass — proving end-to-end composition.
    data_with_both = {**DATA, "batteries": ["webhooks", "workers"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_both)

    # Both battery file sets must exist.
    assert (dest / "src" / "demo" / "routes" / "webhooks.py").exists(), \
        "routes/webhooks.py was not rendered"
    assert (dest / "src" / "demo" / "tasks" / "app.py").exists(), \
        "tasks/app.py was not rendered"
    assert (dest / "migrations" / "versions" / "0002_webhook_events.py").exists(), \
        "0002_webhook_events.py was not rendered"
    assert (dest / "migrations" / "versions" / "0003_dead_letter.py").exists(), \
        "0003_dead_letter.py was not rendered"

    # Verify the handler uses process_async.delay (enqueue composition is wired).
    handler = (dest / "src" / "demo" / "webhooks" / "handler.py").read_text()
    assert "process_async.delay" in handler, \
        "handler.py does not call process_async.delay — webhooks+workers composition not wired"

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Run unit + functional tiers (70% gate) — alembic upgrade head walks 0001→0002→0003,
    # the webhooks functional tests pass (the route calls handle_event → process_async.delay,
    # which runs eagerly via the autouse session fixture), and the workers functional tests
    # pass. Coverage must reach 70% across the combined project.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate did not pass for the webhooks+workers project:\n"
        + result.stdout + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_downskill_webhooks_is_green(tmp_path: Path):
    # Renders a project WITH the webhooks battery, removes it via remove_battery, and
    # verifies that the remaining project is still green (no dangling imports break
    # alembic upgrade / pytest collection, and the 70% coverage gate still passes).
    data_with_webhooks = {**DATA, "batteries": ["webhooks"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_webhooks)

    # Sanity: battery files must exist before removal.
    assert (dest / "src" / "demo" / "routes" / "webhooks.py").exists(), \
        "routes/webhooks.py was not rendered — webhooks battery did not activate"

    # Remove the battery (no force needed — no builder code references it).
    remove_battery(dest, "webhooks")

    # Battery-owned route file must be gone.
    assert not (dest / "src" / "demo" / "routes" / "webhooks.py").exists(), \
        "routes/webhooks.py was not deleted by remove_battery"

    # Migration must be PRESERVED (remove_battery keeps migrations/).
    assert (dest / "migrations" / "versions" / "0002_webhook_events.py").exists(), \
        "0002_webhook_events.py was unexpectedly deleted — migrations should be preserved"

    # migrations/env.py must no longer reference webhooks (hybrid section stripped).
    env_py = (dest / "migrations" / "env.py").read_text()
    assert "webhooks" not in env_py, \
        "migrations/env.py still contains 'webhooks' after remove_battery"

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the post-downskill project"

    # Run unit + functional tiers (70% gate) — alembic upgrade head applies both
    # migrations (0001 + 0002); the webhook_events table goes unused but causes no errors.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate failed after downskilling webhooks:\n"
        + result.stdout + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the e2e tier runs against real Postgres",
)
def test_rendered_project_combined_coverage_gate_passes(tmp_path: Path):
    # The authoritative CI gate: unit + functional + e2e, >=85%, via scripts/coverage.sh.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "85", "unit", "functional", "e2e"], cwd=dest
    )
    assert result.returncode == 0, "the 85% combined coverage gate did not pass"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_precommit_config_is_valid(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["uv", "run", "pre-commit", "validate-config", ".pre-commit-config.yaml"],
        cwd=dest,
    )
    assert result.returncode == 0, "pre-commit config is invalid"


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("git") is None,
    reason="uv and git are required for this test",
)
def test_rendered_project_precommit_runs_clean(tmp_path: Path):
    # A freshly generated project must make a clean first pass on the NO-DOCKER hooks:
    # ruff-check / ruff-format / mypy / gitleaks / file-hygiene must pass on the
    # scaffolded files (no hook rewrites them). The `coverage-threshold` hook runs the
    # DB test suite against a real Postgres (testcontainers), so it's skipped here and
    # exercised instead by the Docker-gated coverage test.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["uv", "run", "pre-commit", "run", "--all-files"],
        cwd=dest,
        env={**os.environ, "SKIP": "coverage-threshold"},
    )
    assert result.returncode == 0, "pre-commit hooks did not pass cleanly on a fresh project"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_exports_openapi(tmp_path: Path):
    # The export needs the app importable (uv sync) but NOT a database — create_app()
    # introspects routes without connecting, so this runs without Docker.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    result = subprocess.run(["bash", "scripts/export-openapi.sh"], cwd=dest)
    assert result.returncode == 0, "export-openapi.sh failed"

    spec = json.loads((dest / "openapi.json").read_text())
    # The OpenAPI title is the service identifier (settings.service_name, which defaults to the
    # package name) — the same identifier used for structlog/OTEL, so it is lowercase.
    assert spec["info"]["title"] == DATA["package_name"]
    for path in ("/items", "/health", "/heartbeat", "/metrics"):
        assert path in spec["paths"], f"{path} missing from the exported OpenAPI spec"


def _run_hook(dest: Path, file_path: Path) -> subprocess.CompletedProcess[str]:
    payload = json.dumps(
        {"tool_name": "Write", "tool_input": {"file_path": str(file_path)}}
    )
    return subprocess.run(
        ["uv", "run", "python", ".claude/hooks/lint_changed.py"],
        cwd=dest,
        input=payload,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_lint_hook_blocks_on_bad_python(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    bad = dest / "src" / "demo" / "scratch_bad.py"
    bad.write_text("import os\n")  # unused import -> ruff F401

    result = _run_hook(dest, bad)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "F401" in (result.stdout + result.stderr)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_lint_hook_passes_clean_python(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    clean = dest / "src" / "demo" / "scratch_clean.py"
    clean.write_text("VALUE: int = 1\n")

    result = _run_hook(dest, clean)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_lint_hook_ignores_non_python(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    note = dest / "notes.txt"
    note.write_text("not python\n")

    result = _run_hook(dest, note)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv and docker are required for the live-stack test",
)
def test_rendered_project_dev_lite_stack_serves_health(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base = "infra/compose/base.yml"
    dev = "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        # app is published on 8000 in the `lite` profile (no Traefik)
        deadline = time.time() + 90
        body = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://localhost:8000/health", timeout=3) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read())
                        break
            except OSError:
                time.sleep(2)
        assert body is not None, "app did not serve /health within 90s"
        assert body["status"] in {"ok", "degraded"}
        assert "request_latency_p99_ms" in body["slos"]
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(not _docker_available(), reason="uv and docker are required for the live-stack test")
def test_rendered_project_dev_stack_prometheus_scrapes_app(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        deadline = time.time() + 120
        up_targets = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    "http://localhost:9090/api/v1/targets?state=active", timeout=3
                ) as resp:
                    data = json.loads(resp.read())
                    actives = data.get("data", {}).get("activeTargets", [])
                    app_targets = [t for t in actives if t.get("labels", {}).get("job") == "app"]
                    if app_targets and app_targets[0].get("health") == "up":
                        up_targets = app_targets
                        break
            except OSError:
                pass
            time.sleep(3)
        assert up_targets, "prometheus did not report the app target healthy within 120s"
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(not _docker_available(), reason="uv and docker are required for the live-stack test")
def test_rendered_project_app_logs_reach_loki(tmp_path: Path):
    import urllib.parse

    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        # wait for the app, then generate some log lines (each request is logged)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen("http://localhost:8000/heartbeat", timeout=3).read()
                break
            except OSError:
                time.sleep(2)
        for _ in range(5):
            try:
                urllib.request.urlopen("http://localhost:8000/heartbeat", timeout=3).read()
            except OSError:
                pass
        # poll Loki for the app's logs (ship + ingest has a lag)
        deadline = time.time() + 90
        found = False
        while time.time() < deadline and not found:
            q = urllib.parse.urlencode(
                {
                    "query": '{service="app"}',
                    "limit": "5",
                    "start": str(int((time.time() - 600) * 1e9)),
                }
            )
            try:
                with urllib.request.urlopen(
                    f"http://localhost:3100/loki/api/v1/query_range?{q}", timeout=5
                ) as resp:
                    data = json.loads(resp.read())
                    result = data.get("data", {}).get("result", [])
                    if result and any(stream.get("values") for stream in result):
                        found = True
                        break
            except OSError:
                pass
            time.sleep(3)
        assert found, "no app logs reached Loki within the timeout"
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(not _docker_available(), reason="uv and docker are required for the live-stack test")
def test_rendered_project_traces_reach_tempo(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen("http://localhost:8000/heartbeat", timeout=3).read()
                break
            except OSError:
                time.sleep(2)
        for _ in range(5):
            try:
                urllib.request.urlopen("http://localhost:8000/heartbeat", timeout=3).read()
            except OSError:
                pass
        deadline = time.time() + 120
        found = False
        while time.time() < deadline and not found:
            try:
                with urllib.request.urlopen(
                    'http://localhost:3200/api/search?q=%7Bresource.service.name%3D%22demo%22%7D&limit=1',
                    timeout=5,
                ) as resp:
                    data = json.loads(resp.read())
                    if data.get("traces"):
                        found = True
                        break
            except OSError:
                pass
            time.sleep(4)
        assert found, "no app traces reached Tempo within the timeout"
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(not _docker_available(), reason="uv and docker are required for the live-stack test")
def test_rendered_project_smoke_and_sniff_against_lite(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        # wait for /health (seeded lite app)
        deadline = time.time() + 120
        ready = False
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://localhost:8000/health", timeout=3) as r:
                    if r.status == 200:
                        ready = True
                        break
            except OSError:
                time.sleep(2)
        assert ready, "lite app did not serve /health within 120s"
        env = {**os.environ, "SMOKE_TARGET": "http://localhost:8000", "SNIFF_TARGET": "http://localhost:8000"}
        smoke = subprocess.run(["uv", "run", "pytest", "tests/smoke", "-q"], cwd=dest, env=env)
        assert smoke.returncode == 0, "smoke suite failed against the live lite stack"
        sniff = subprocess.run(["uv", "run", "pytest", "tests/sniff", "-q"], cwd=dest, env=env)
        assert sniff.returncode == 0, "sniff suite failed against the live lite stack"
        e2e = subprocess.run(
            ["uv", "run", "pytest", "tests/e2e", "-q"],
            cwd=dest, env={**os.environ, "E2E_TARGET": "http://localhost:8000"},
        )
        assert e2e.returncode == 0, "remote-mode e2e failed against the live lite stack"
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_blocks_contract_migration(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    # The scaffold's own migration is safe (reversible + expand-only) -> exit 0.
    clean = subprocess.run(["uv", "run", "python", "scripts/check_migrations.py"], cwd=dest)
    assert clean.returncode == 0, "the scaffold's 0001 migration should pass both guards"

    versions = dest / "migrations" / "versions"

    # A destructive (contract) upgrade with NO marker -> blocked (exit 1).
    bad = versions / "9999_drop.py"
    bad.write_text(
        "def upgrade():\n    op.drop_column('items', 'name')\n\n"
        "def downgrade():\n    op.add_column('items', sa.Column('name', sa.String()))\n"
    )
    blocked = subprocess.run(
        ["uv", "run", "python", "scripts/check_migrations.py"], cwd=dest, capture_output=True, text=True
    )
    assert blocked.returncode == 1, "a contract migration without the marker must be blocked"
    assert "contract" in (blocked.stdout + blocked.stderr).lower()

    # Same migration WITH the acknowledgement marker -> allowed (exit 0).
    bad.write_text(
        "# deploy: contract\n"
        "def upgrade():\n    op.drop_column('items', 'name')\n\n"
        "def downgrade():\n    op.add_column('items', sa.Column('name', sa.String()))\n"
    )
    allowed = subprocess.run(["uv", "run", "python", "scripts/check_migrations.py"], cwd=dest)
    assert allowed.returncode == 0, "the '# deploy: contract' marker must exempt the migration"

    bad.unlink()


def test_rendered_project_hybrid_section_integrity(tmp_path):
    from framework_cli.copier_runner import render_project
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version
    from framework_cli.integrity.sections import section_span

    dest = tmp_path / "hyb"
    render_project(
        dest,
        {
            "project_name": "Hyb",
            "project_slug": "hyb",
            "package_name": "hyb",
            "python_version": "3.12",
        },
    )
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []

    claude = dest / "CLAUDE.md"
    # Editing OUTSIDE the markers (the builder's area) stays clean — defines "hybrid".
    claude.write_text(claude.read_text() + "\n## My project notes\nsome builder content\n")
    assert check(dest, ci=True) == []

    # Editing INSIDE the markers is fatal.
    text = claude.read_text()
    begin, _ = section_span(text)
    lines = text.splitlines()
    lines[begin + 1] = lines[begin + 1] + "  SNEAKY"
    claude.write_text("\n".join(lines) + "\n")
    findings = check(dest, ci=True)
    assert any(f.path == "CLAUDE.md" and f.fatal for f in findings)


def test_rendered_project_integrity_verifies_tamper_and_restore(tmp_path: Path):
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "acc"
    render_project(
        dest,
        {
            "project_name": "Acc",
            "project_slug": "acc",
            "package_name": "acc",
            "python_version": "3.12",
        },
    )
    write_manifest(dest, installed_framework_version())

    # Fresh project verifies clean.
    assert check(dest, ci=True) == []

    # Tampering with a locked file is caught as fatal.
    locked = dest / ".pre-commit-config.yaml"
    locked.write_text(locked.read_text() + "\n# sneaky edit\n")
    findings = check(dest, ci=True)
    assert any(f.path == ".pre-commit-config.yaml" and f.fatal for f in findings)

    # Restore returns it to canonical and the project verifies clean again.
    restore_file(dest, ".pre-commit-config.yaml")
    assert check(dest, ci=True) == []


@pytest.mark.skipif(not _docker_available(), reason="uv and docker are required for the live-stack test")
def test_rendered_project_dev_stack_serves_seeded_items(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    # `lite` profile = app + postgres only (no Traefik/observability) — app on 8000.
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        deadline = time.time() + 120
        items = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://localhost:8000/items", timeout=3) as resp:
                    if resp.status == 200:
                        payload = json.loads(resp.read())
                        if payload:
                            items = payload
                            break
            except OSError:
                pass
            time.sleep(3)
        assert items, "no seeded items served by /items within 120s"
        assert {row["name"] for row in items} >= {"alpha", "beta"}
    finally:
        subprocess.run(down, cwd=dest)
