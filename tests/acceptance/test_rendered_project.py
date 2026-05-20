import shutil
import subprocess
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
