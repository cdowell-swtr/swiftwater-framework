"""Fast, Docker-free tests for the compose-over-SSH deploy target wiring.

They render a project, then invoke the REAL strategy.sh to assert the DEPLOY_TARGET
source-hook behavior without any real host or Docker.
"""
import os
import subprocess
from pathlib import Path

from framework_cli.copier_runner import render_project

DATA = {"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"}


def _render(tmp_path: Path) -> Path:
    dest = tmp_path / "proj"
    render_project(dest, DATA)
    return dest


def test_strategy_unset_target_is_skeleton_todo(tmp_path: Path):
    """With DEPLOY_TARGET unset, the hooks remain _todo (exit 1 with the skeleton message)."""
    dest = _render(tmp_path)
    proc = subprocess.run(
        ["bash", "infra/deploy/strategy.sh", "releases"],
        cwd=dest, env={**os.environ, "DEPLOY_ENV": "staging"},
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "is not implemented for your target" in proc.stderr


def test_strategy_missing_target_file_errors(tmp_path: Path):
    """DEPLOY_TARGET pointing at a non-existent target file fails fast with a clear error."""
    dest = _render(tmp_path)
    proc = subprocess.run(
        ["bash", "infra/deploy/strategy.sh", "releases"],
        cwd=dest, env={**os.environ, "DEPLOY_ENV": "staging", "DEPLOY_TARGET": "does-not-exist"},
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "does not exist" in proc.stderr
