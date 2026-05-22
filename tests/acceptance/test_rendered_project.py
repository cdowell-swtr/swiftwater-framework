import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from framework_cli.copier_runner import render_project

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
