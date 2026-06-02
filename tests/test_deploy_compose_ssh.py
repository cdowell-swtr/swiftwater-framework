"""Fast, Docker-free tests for the compose-over-SSH deploy target wiring.

They render a project, then invoke the REAL strategy.sh to assert the DEPLOY_TARGET
source-hook behavior without any real host or Docker.
"""
import os
import stat
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


def _install_shims(dest: Path, ssh_stdout: str = "") -> Path:
    """Put fake ssh/scp/docker/curl on PATH that append their argv to shims/calls.log."""
    shims = dest / "shims"
    shims.mkdir(exist_ok=True)
    log = shims / "calls.log"
    bodies = {
        "ssh": f'echo "ssh $*" >> "{log}"\nprintf "%b" {ssh_stdout!r}\n',
        "scp": f'echo "scp $*" >> "{log}"\n',
        "docker": f'echo "docker $*" >> "{log}"\n',
        "curl": f'echo "curl $*" >> "{log}"\nprintf "%s" \'{{"status":"ok"}}\'\n',
    }
    for name, body in bodies.items():
        p = shims / name
        p.write_text("#!/usr/bin/env bash\n" + body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return shims


def _read_calls(dest: Path) -> str:
    log = dest / "shims" / "calls.log"
    return log.read_text() if log.exists() else ""


def _shim_env(dest: Path, **extra) -> dict:
    return {**os.environ, "PATH": f"{dest/'shims'}:{os.environ['PATH']}", **extra}


def test_strategy_sources_compose_ssh_target(tmp_path: Path):
    """DEPLOY_TARGET=compose-ssh sources the target so 'releases' is no longer _todo."""
    dest = _render(tmp_path)
    _install_shims(dest, ssh_stdout="")
    proc = subprocess.run(
        ["bash", "infra/deploy/strategy.sh", "releases"],
        cwd=dest,
        env=_shim_env(dest, DEPLOY_ENV="staging", DEPLOY_TARGET="compose-ssh", DEPLOY_HOSTS="h1 h2"),
        capture_output=True, text=True,
    )
    assert "is not implemented for your target" not in proc.stderr, proc.stderr
    assert proc.returncode == 0, proc.stderr


def test_deploy_migrates_once_then_rolls_each_host(tmp_path: Path):
    dest = _render(tmp_path)
    _install_shims(dest, ssh_stdout='{"status":"ok"}')
    env = _shim_env(dest, DEPLOY_ENV="prod", DEPLOY_TARGET="compose-ssh",
                    DEPLOY_HOSTS="h1 h2", DEPLOY_BASE_URL="http://lb",
                    APP_IMAGE="reg/app:v2", APP_DATABASE_URL="postgresql://shared",
                    POSTGRES_PASSWORD="x", APP_ALERT_WEBHOOK_URL="http://fake-webhook")
    proc = subprocess.run(["bash", "infra/deploy/strategy.sh", "deploy"],
                          cwd=dest, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    calls = _read_calls(dest)
    assert calls.count("alembic upgrade head") == 1, calls
    assert "h1" in calls and "h2" in calls
    assert calls.count("compose -f app-host.yml up -d") == 2, calls


def test_rollback_downgrades_once_then_rolls_old_image_without_reupgrade(tmp_path: Path):
    dest = _render(tmp_path)
    history = "reg/app:v1\tR1\nreg/app:v2\tR2\n"
    _install_shims(dest, ssh_stdout=history)
    env = _shim_env(dest, DEPLOY_ENV="prod", DEPLOY_TARGET="compose-ssh",
                    DEPLOY_HOSTS="h1 h2", DEPLOY_BASE_URL="http://lb",
                    APP_IMAGE="reg/app:v2", APP_DATABASE_URL="postgresql://shared")
    proc = subprocess.run(["bash", "infra/deploy/strategy.sh", "rollback"],
                          cwd=dest, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    calls = _read_calls(dest)
    assert "alembic downgrade R1" in calls, calls
    assert "alembic upgrade head" not in calls, calls
    assert calls.count("compose -f app-host.yml up -d") == 2, calls
