from pathlib import Path

from framework_cli.copier_runner import render_project
from framework_cli.integrity.checker import check
from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.restore import restore_file


def _new_project(tmp_path: Path) -> Path:
    dest = tmp_path / "demo"
    render_project(
        dest,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    write_manifest(dest, installed_framework_version())
    return dest


def test_restore_recovers_an_altered_locked_file(tmp_path: Path):
    proj = _new_project(tmp_path)
    target = proj / "alembic.ini"
    canonical = target.read_text()
    target.write_text("tampered\n")
    assert any(f.path == "alembic.ini" and f.fatal for f in check(proj))

    restore_file(proj, "alembic.ini")

    assert target.read_text() == canonical
    assert check(proj, ci=True) == []


def test_restore_rejects_unmanaged_file(tmp_path: Path):
    proj = _new_project(tmp_path)
    try:
        restore_file(proj, "src/demo/main.py")
    except ValueError as exc:
        assert "not a restorable" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for an unmanaged path")


def test_restore_outside_a_framework_project_is_a_clear_error(tmp_path: Path):
    # No manifest, no answers file — a bare directory.
    try:
        restore_file(tmp_path, "alembic.ini")
    except ValueError as exc:
        assert "not a framework project" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError outside a framework project")
