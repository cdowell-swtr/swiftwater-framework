"""check_migrations scans BOTH alembic chains (app + control). Framework-level: loads the
template script via importlib and exercises it with temp migration dirs."""

import importlib.util
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src/framework_cli/template/scripts/check_migrations.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("check_migrations", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_GOOD = "def upgrade():\n    op.add_column('t', c)\n\n\ndef downgrade():\n    op.drop_column('t', 'c')\n"
_BAD = "def upgrade():\n    op.drop_table('t')\n\n\ndef downgrade():\n    op.create_table('t')\n"
_BAD_MARKED = "# deploy: contract\n" + _BAD


def _write(d: Path, name: str, body: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body)


def test_clean_app_chain_passes(tmp_path):
    mod = _load()
    _write(tmp_path / "app", "0001.py", _GOOD)
    assert mod.main([tmp_path / "app"]) == 0


def test_destructive_unmarked_control_migration_fails(tmp_path):
    mod = _load()
    _write(tmp_path / "app", "0001.py", _GOOD)
    _write(tmp_path / "control", "c0001.py", _BAD)
    assert mod.main([tmp_path / "app", tmp_path / "control"]) == 1


def test_contract_marked_control_migration_passes(tmp_path):
    mod = _load()
    _write(tmp_path / "control", "c0001.py", _BAD_MARKED)
    assert mod.main([tmp_path / "control"]) == 0


def test_absent_dir_is_skipped(tmp_path):
    mod = _load()
    _write(tmp_path / "app", "0001.py", _GOOD)
    assert mod.main([tmp_path / "app", tmp_path / "does_not_exist"]) == 0
