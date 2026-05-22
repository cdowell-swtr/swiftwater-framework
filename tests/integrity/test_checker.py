from pathlib import Path

from framework_cli.integrity.checker import check, record_drift
from framework_cli.integrity.classes import HYBRID_TRACKED, LOCKED_TRACKED
from framework_cli.integrity.generate import write_manifest

_HYBRID_STUB = "# FRAMEWORK:BEGIN\nstub content\n# FRAMEWORK:END\n"


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    for rel in LOCKED_TRACKED:
        f = proj / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"content of {rel}\n")
    for rel in HYBRID_TRACKED:
        f = proj / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(_HYBRID_STUB)
    (proj / ".gitignore").write_text(".env\ninfra/traefik/certs/*.pem\n")
    (proj / ".env").write_text("APP_ENVIRONMENT=dev\n")
    write_manifest(proj, "0.1.0")
    return proj


def test_clean_project_has_no_findings(tmp_path: Path):
    assert check(_project(tmp_path)) == []


def test_altered_locked_file_is_a_fatal_finding(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / "alembic.ini").write_text("hacked\n")
    findings = check(proj)
    assert any(f.path == "alembic.ini" and f.fatal for f in findings)


def test_missing_locked_file_is_fatal(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / "alembic.ini").unlink()
    findings = check(proj)
    assert any(f.path == "alembic.ini" and f.fatal for f in findings)


def test_tampered_manifest_is_fatal(tmp_path: Path):
    proj = _project(tmp_path)
    lock = proj / ".framework" / "integrity.lock"
    lock.write_text(lock.read_text().replace('"0.1.0"', '"9.9.9"'))
    findings = check(proj)
    assert len(findings) == 1 and findings[0].fatal
    assert "self-checksum" in findings[0].problem


def test_missing_gitignored_file_is_a_warning_local_only(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / ".env").unlink()
    # Local: a non-fatal warning.
    local = check(proj, ci=False)
    assert any(f.path == ".env" and not f.fatal for f in local)
    # CI: gitignored existence checks are skipped entirely.
    assert all(f.path != ".env" for f in check(proj, ci=True))


def test_drift_recorded_file_is_skipped(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / "alembic.ini").write_text("builder's intentional change\n")
    record_drift(proj, ["alembic.ini"])
    assert all(f.path != "alembic.ini" for f in check(proj))


def _hybrid_project(tmp_path: Path) -> Path:
    from framework_cli.integrity.manifest import Entry, Manifest
    from framework_cli.integrity.sections import section_sha256

    proj = tmp_path / "hyb"
    (proj / ".framework").mkdir(parents=True)
    claude = proj / "CLAUDE.md"
    claude.write_text(
        "# Title\n<!-- FRAMEWORK:BEGIN -->\nmanaged line\n<!-- FRAMEWORK:END -->\n"
        "## Notes\nbuilder text\n"
    )
    manifest = Manifest(
        framework_version="0.1.0",
        entries=[
            Entry("CLAUDE.md", "hybrid", "tracked", sha256=section_sha256(claude.read_text()))
        ],
    )
    (proj / ".framework" / "integrity.lock").write_text(manifest.dumps())
    return proj


def test_hybrid_clean_has_no_findings(tmp_path: Path):
    assert check(_hybrid_project(tmp_path)) == []


def test_hybrid_edit_outside_the_block_is_clean(tmp_path: Path):
    proj = _hybrid_project(tmp_path)
    claude = proj / "CLAUDE.md"
    claude.write_text(claude.read_text() + "\nmore builder notes\n")
    assert check(proj) == []


def test_hybrid_edit_inside_the_block_is_fatal(tmp_path: Path):
    proj = _hybrid_project(tmp_path)
    claude = proj / "CLAUDE.md"
    claude.write_text(claude.read_text().replace("managed line", "managed LINE"))
    findings = check(proj)
    assert any(f.path == "CLAUDE.md" and f.fatal for f in findings)


def test_hybrid_damaged_markers_are_fatal(tmp_path: Path):
    proj = _hybrid_project(tmp_path)
    (proj / "CLAUDE.md").write_text("markers deleted\n")
    findings = check(proj)
    assert any(f.path == "CLAUDE.md" and f.fatal and "markers" in f.problem for f in findings)
