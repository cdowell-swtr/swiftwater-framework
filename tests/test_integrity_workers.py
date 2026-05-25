"""Integration tests: workers battery integrity and downskill.

Test 1: `framework new --with workers` produces a project whose `framework integrity`
        is GREEN — the conditionally-rendered LOCKED files (infra/compose/dev.yml,
        infra/observability/prometheus/prometheus.yml) are checksummed at their
        battery-active content and verify clean.

Test 2: `framework downskill workers` reverts LOCKED files, de-injects HYBRID managed
        sections, removes owned files (tasks package, alerts, dashboard), preserves the
        0003_dead_letter.py migration, and leaves integrity GREEN (manifest regenerated).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from framework_cli.cli import app
from framework_cli.downskill import remove_battery
from framework_cli.integrity.checker import check
from framework_cli.source import read_batteries


_RUNNER = CliRunner()


def _new_workers_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Invoke `framework new My App --with workers` and return the project root."""
    monkeypatch.chdir(tmp_path)
    result = _RUNNER.invoke(app, ["new", "My App", "--with", "workers"])
    assert result.exit_code == 0, f"framework new failed:\n{result.output}"
    return tmp_path / "my-app"


def _git_commit(project: Path) -> None:
    """Initialise a git repo and commit everything (required for downskill)."""
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


# ---------------------------------------------------------------------------
# Test 1: new --with workers → integrity GREEN
# ---------------------------------------------------------------------------


def test_new_with_workers_integrity_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A freshly rendered workers project passes integrity checks with no findings."""
    project = _new_workers_project(tmp_path, monkeypatch)

    # ci=True: skip the gitignored .env existence check (matches production CI behaviour
    # and how test_restore.py exercises this path).
    findings = check(project, ci=True)

    assert findings == [], (
        "Integrity check should be clean for a fresh --with workers project.\n"
        "Findings:\n" + "\n".join(f"  {f.path}: {f.problem}" for f in findings)
    )


# ---------------------------------------------------------------------------
# Test 2: downskill workers → reverts everything, preserves migration, integrity GREEN
# ---------------------------------------------------------------------------


def test_downskill_workers_reverts_locked_files_preserves_migration_integrity_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """downskill workers: owned files gone, LOCKED files reverted, HYBRID sections
    de-injected, migration preserved, battery list cleared, integrity GREEN."""
    project = _new_workers_project(tmp_path, monkeypatch)
    _git_commit(project)

    # No --force needed: although framework-gated shared files mention the battery name
    # ("# Celery workers" in settings.py, report["workers"] in health.py), usage_references
    # byte-identical-excludes files that match the framework's with-battery render, so a
    # pristine scaffold downskills cleanly. (Only builder-MODIFIED references would refuse.)
    report = remove_battery(project, "workers", force=False)

    pkg = "my_app"

    # --- owned files removed ---
    assert not (project / "src" / pkg / "tasks").exists(), (
        "tasks/ package dir should be removed after downskill"
    )
    assert not (
        project
        / "infra"
        / "observability"
        / "prometheus"
        / "alerts"
        / "workers_alerts.yml"
    ).exists()
    assert not (
        project / "infra" / "observability" / "grafana" / "dashboards" / "workers.json"
    ).exists()
    assert not (
        project / "tests" / "functional" / "test_workers_functional.py"
    ).exists()
    assert not (project / "tests" / "unit" / "test_workers_unit.py").exists()

    # --- migration PRESERVED (battery owns it, but it mutates the DB schema) ---
    assert (project / "migrations" / "versions" / "0003_dead_letter.py").is_file(), (
        "0003_dead_letter.py migration must be preserved after downskill"
    )
    assert any("0003_dead_letter" in p for p in report.preserved), (
        "RemovalReport.preserved should mention 0003_dead_letter"
    )
    assert any("migration" in w for w in report.warnings), (
        "RemovalReport.warnings should carry the migration-preserved advisory"
    )

    # --- LOCKED files reverted ---
    dev_yml = (project / "infra" / "compose" / "dev.yml").read_text()
    assert "celery-exporter" not in dev_yml, (
        "celery-exporter service must be absent from dev.yml after downskill"
    )
    assert "image: redis:" not in dev_yml, (
        "redis service must be absent from dev.yml after downskill"
    )

    prom_yml = (
        project / "infra" / "observability" / "prometheus" / "prometheus.yml"
    ).read_text()
    assert "celery-exporter" not in prom_yml, (
        "celery-exporter scrape target must be absent from prometheus.yml after downskill"
    )
    assert "job_name: celery" not in prom_yml, (
        "celery scrape job must be absent from prometheus.yml after downskill"
    )

    # --- HYBRID managed sections de-injected ---
    env_example = (project / ".env.example").read_text()
    assert "APP_CELERY_BROKER_URL" not in env_example, (
        "APP_CELERY_BROKER_URL must be removed from .env.example managed section"
    )
    assert "APP_REDIS_URL" not in env_example, (
        "APP_REDIS_URL must be removed from .env.example managed section"
    )

    taskfile = (project / "Taskfile.yml").read_text()
    assert "worker:" not in taskfile, (
        "worker: task must be removed from Taskfile.yml managed section"
    )

    # --- battery list cleared ---
    assert read_batteries(project) == [], "Battery list must be empty after downskill"

    # --- integrity GREEN after downskill (manifest regenerated) ---
    # ci=True: skip the gitignored .env existence check (matches production CI behaviour).
    findings = check(project, ci=True)
    assert findings == [], (
        "Integrity check should be clean after downskill.\n"
        "Findings:\n" + "\n".join(f"  {f.path}: {f.problem}" for f in findings)
    )
