import json
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


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_passes_its_own_tests(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(["uv", "run", "pytest", "-q"], cwd=dest)
    assert result.returncode == 0, "the generated project's test suite did not pass"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_coverage_gate_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(["uv", "run", "task", "test:cov"], cwd=dest)
    if result.returncode == 127 or shutil.which("task") is None:
        result = subprocess.run(
            ["uv", "run", "pytest", "--cov", "--cov-fail-under=70", "-q"], cwd=dest
        )
    assert result.returncode == 0, "coverage gate did not pass in the generated project"


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
    # A freshly generated project must make a clean first commit: every hook the
    # framework installs must pass on the scaffolded files (no hook rewrites them).
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(["uv", "run", "pre-commit", "run", "--all-files"], cwd=dest)
    assert result.returncode == 0, "pre-commit hooks did not pass cleanly on a fresh project"


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


def _docker_available() -> bool:
    if shutil.which("uv") is None or shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info"], capture_output=True, timeout=10
    )
    return result.returncode == 0


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
