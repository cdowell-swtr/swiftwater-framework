# tests/test_backup_completeness.py
from pathlib import Path

import pytest
import yaml

from framework_cli.batteries import battery_names, get_battery
from framework_cli.copier_runner import render_project

_BASE = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}
_COMPOSE = Path("infra/compose")
# Every overlay that can declare a named volume.
_OVERLAYS = (
    "base.yml",
    "dev.yml",
    "services.yml",
    "prod.yml",
    "staging.yml",
    "test.yml",
    "observability.yml",
)
_BACKUP = Path("infra/backup/backup.sh")
# obs telemetry volumes are base + retention-bounded (not SoT); declared rebuildable by convention.
_BASE_REBUILDABLE = {"promdata", "lokidata", "tempodata"}


def _named_volumes(root: Path) -> set[str]:
    vols: set[str] = set()
    for f in _OVERLAYS:
        p = root / _COMPOSE / f
        if not p.is_file():
            continue
        data = yaml.safe_load(p.read_text()) or {}
        vols |= set((data.get("volumes") or {}).keys())
    return vols


def _backup_stores(root: Path) -> set[str]:
    """Parse the `# BACKUP-STORES: postgres mongo` manifest line from backup.sh."""
    p = root / _BACKUP
    if not p.is_file():
        return set()
    for line in p.read_text().splitlines():
        if line.strip().startswith("# BACKUP-STORES:"):
            return set(line.split(":", 1)[1].split())
    return set()


@pytest.fixture(scope="module")
def baseline(tmp_path_factory) -> Path:
    dest = tmp_path_factory.mktemp("bk-base") / "demo"
    render_project(dest, {**_BASE, "batteries": []})
    return dest


@pytest.mark.parametrize("name", battery_names())
def test_battery_data_matches_rendered_volumes(
    name: str, baseline: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "demo"
    render_project(dest, {**_BASE, "batteries": [name]})
    new_volumes = _named_volumes(dest) - _named_volumes(baseline)
    data = get_battery(name).data
    stores = _backup_stores(dest)

    if data == "none":
        assert not new_volumes, (
            f"{name}: a 'none' battery must add no named volume; got {new_volumes}"
        )
    elif data == "rebuildable":
        assert new_volumes, (
            f"{name}: a 'rebuildable' battery must add the volume it declares"
        )
        for v in new_volumes:
            store = v.removesuffix("data")
            assert store not in stores, (
                f"{name}: rebuildable volume {v!r} must NOT be in BACKUP-STORES"
            )
    elif data == "store":
        assert new_volumes, f"{name}: a 'store' battery must add a named volume"
        if (dest / _BACKUP).is_file():  # hardened in Task 3 once backup.sh exists
            for v in new_volumes:
                store = v.removesuffix("data")
                assert store in stores, (
                    f"{name}: store volume {v!r} not dumped in infra/backup/backup.sh"
                )
    elif data == "postgres-extension":
        assert not new_volumes, (
            f"{name}: a 'postgres-extension' battery shares pgdata, adds no volume"
        )
        dev = (dest / _COMPOSE / "dev.yml").read_text()
        assert "postgres.Dockerfile" in dev, (
            f"{name}: a 'postgres-extension' battery must build the extension postgres image "
            "(so restore is extension-correct)"
        )


def test_no_unclassified_volume_in_baseline(baseline: Path) -> None:
    """Every base named volume is either pgdata (core backup) or a known rebuildable telemetry store."""
    vols = _named_volumes(baseline)
    assert "pgdata" in vols, "base scaffold must declare the pgdata volume"
    unclassified = vols - {"pgdata"} - _BASE_REBUILDABLE
    assert not unclassified, (
        f"base render has unclassified durable volume(s): {unclassified}"
    )


@pytest.mark.skipif(
    True, reason="activated by Task 3 (backup.sh)"
)  # Task 3 deletes this marker
def test_base_postgres_is_core_backed_up(baseline: Path) -> None:
    backup = baseline / _BACKUP
    assert backup.is_file(), (
        "core backup script infra/backup/backup.sh must render in the base scaffold"
    )
    text = backup.read_text()
    assert "pg_dump" in text, "core backup must pg_dump the base postgres"
    assert "postgres" in _backup_stores(baseline), (
        "BACKUP-STORES must list postgres in the base render"
    )
