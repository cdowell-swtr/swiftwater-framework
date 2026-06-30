"""FWK133 execution gate — the encrypted backup + restore-drill actually round-trips.

Full-tier (docker) acceptance. Renders a project, brings up its data stores under an isolated
compose project, seeds a marker, runs `infra/backup/backup.sh` (dump -> age-encrypt -> $BACKUP_DEST),
then `infra/backup/restore_drill.sh` (decrypt latest -> throwaway battery-correct image -> verify).
Proves the WHOLE chain incl. decryption and the battery-correct restore image. Skips cleanly without
docker/age. Registered as a documented fast-tier exception in tests/test_test_tiers.py.
"""

import os
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
_FILES = ["-f", "infra/compose/base.yml", "-f", "infra/compose/dev.yml"]


def _tools_available() -> bool:
    if not all(shutil.which(t) for t in ("docker", "age", "age-keygen", "uv")):
        return False
    return (
        subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode
        == 0
    )


pytestmark = pytest.mark.skipif(
    not _tools_available(), reason="needs docker + age + uv"
)


def _sh(cmd, cwd, env, check=True):
    return subprocess.run(
        cmd,
        cwd=cwd,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=check,
    )


def _keypair(tmp_path: Path):
    ident = tmp_path / "id.txt"
    kg = _sh(["age-keygen", "-o", str(ident)], cwd=tmp_path, env={})
    pub = next(
        line.split(":", 1)[1].strip()
        for line in (kg.stderr + kg.stdout).splitlines()
        if "public key" in line.lower()
    )
    return ident, pub


def _env(tmp_path: Path, ident: Path, pub: str, name: str) -> dict:
    return {
        "BACKUP_DEST": str(tmp_path / "backups"),
        "BACKUP_PUBKEY": pub,
        "BACKUP_IDENTITY": str(ident),
        # (postgres/mongo don't need the dev UID/GID app-user mapping; UID is a bash-readonly var.)
        # Same project name for the test's `up` AND backup.sh's internal compose.sh `exec`.
        "COMPOSE_PROJECT_NAME": name,
        "STACK_INSTANCE": name,
        "POSTGRES_HOST_PORT": "0",  # ephemeral; the drill execs in-container, no host port needed
        "MONGO_HOST_PORT": "0",
        "TMPDIR": "/var/tmp",
    }


def _drill(dest: Path, env: dict, services: list[str], seed_sql: str):
    """up data stores -> seed -> backup.sh -> restore_drill.sh; always tears down. Returns the drill run."""
    try:
        _sh(
            [
                "docker",
                "compose",
                *_FILES,
                "--profile",
                "lite",
                "up",
                "-d",
                "--wait",
                "--build",
                *services,
            ],
            cwd=dest,
            env=env,
        )
        _sh(
            [
                "docker",
                "compose",
                *_FILES,
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "app",
                "-d",
                "app",
                "-c",
                seed_sql,
            ],
            cwd=dest,
            env=env,
        )
        _sh(["./infra/backup/backup.sh"], cwd=dest, env=env)
        return _sh(["./infra/backup/restore_drill.sh"], cwd=dest, env=env, check=False)
    finally:
        _sh(
            ["docker", "compose", *_FILES, "--profile", "lite", "down", "-v"],
            cwd=dest,
            env=env,
            check=False,
        )


# A marker table the dump must carry through encrypt -> decrypt -> restore; the drill asserts
# alembic_version has exactly one row.
_BASE_SEED = (
    "CREATE TABLE alembic_version(version_num varchar primary key); "
    "INSERT INTO alembic_version VALUES ('drill-marker');"
)


def test_baseline_backup_drill_round_trips(tmp_path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": []})
    ident, pub = _keypair(tmp_path)
    env = _env(tmp_path, ident, pub, f"bkdrill{os.getpid()}")
    drill = _drill(dest, env, ["postgres"], _BASE_SEED)
    dumps = list((tmp_path / "backups").glob("demo-postgres-*.dump.age"))
    assert dumps, "no encrypted dump produced"
    assert drill.returncode == 0, f"drill failed:\n{drill.stdout}\n{drill.stderr}"
    assert "restore-drill OK" in drill.stdout


# Postgres-extension data must restore into the BATTERY-CORRECT (built) image — the drill running
# against vanilla postgres:17 would false-green pgvector and always-fail timescale/age (the Task 5
# Critical). Seeding the extensions makes the dump carry their objects through the drill.
_EXT_SEED = (
    "CREATE EXTENSION IF NOT EXISTS age; "
    "CREATE EXTENSION IF NOT EXISTS timescaledb; "
    "CREATE EXTENSION IF NOT EXISTS vector; "
    "CREATE TABLE alembic_version(version_num varchar primary key); "
    "INSERT INTO alembic_version VALUES ('drill-marker');"
)


def test_all_data_batteries_backup_drill_round_trips(tmp_path):
    dest = tmp_path / "demo"
    render_project(
        dest, {**DATA, "batteries": ["mongodb", "age", "timescaledb", "pgvector"]}
    )
    ident, pub = _keypair(tmp_path)
    env = _env(tmp_path, ident, pub, f"bkall{os.getpid()}")
    drill = _drill(dest, env, ["postgres", "mongo"], _EXT_SEED)
    pg_dumps = list((tmp_path / "backups").glob("demo-postgres-*.dump.age"))
    mongo_dumps = list((tmp_path / "backups").glob("demo-mongo-*.archive.gz.age"))
    assert pg_dumps, "no encrypted postgres dump produced"
    assert mongo_dumps, "no encrypted mongo dump produced (mongodump path)"
    # The drill builds + restores into the extension-loaded image; vanilla would have failed here.
    assert drill.returncode == 0, (
        f"extension drill failed:\n{drill.stdout}\n{drill.stderr}"
    )
    assert "restore-drill OK" in drill.stdout
