from pathlib import Path

from framework_cli.copier_runner import render_project
from framework_cli.integrity.checker import check
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.integrity.restore import restore_file
from framework_cli.integrity.sections import section_content, section_span


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


def test_restore_hybrid_fixes_block_and_preserves_builder_content(tmp_path: Path):
    proj = _new_project(tmp_path)
    claude = proj / "CLAUDE.md"
    original = claude.read_text()
    begin, _ = section_span(original)  # type: ignore[misc]
    lines = original.splitlines()
    lines[begin + 1] = lines[begin + 1] + "  TAMPER"  # edit the first in-block line
    claude.write_text("\n".join(lines) + "\nMY BUILDER NOTE\n")  # + content outside the block

    assert any(f.path == "CLAUDE.md" and f.fatal for f in check(proj, ci=True))

    restore_file(proj, "CLAUDE.md")

    restored = claude.read_text()
    assert "TAMPER" not in (section_content(restored) or "")  # block restored
    assert "MY BUILDER NOTE" in restored  # builder content outside the block preserved
    assert check(proj, ci=True) == []


def test_restore_hybrid_errors_when_markers_destroyed(tmp_path: Path):
    proj = _new_project(tmp_path)
    (proj / "CLAUDE.md").write_text("the builder deleted the markers\n")
    try:
        restore_file(proj, "CLAUDE.md")
    except ValueError as exc:
        assert "markers" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError when markers are destroyed")
