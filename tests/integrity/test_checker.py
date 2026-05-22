from pathlib import Path

from framework_cli.integrity.checker import check, record_drift
from framework_cli.integrity.classes import LOCKED_TRACKED
from framework_cli.integrity.generate import write_manifest


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    for rel in LOCKED_TRACKED:
        f = proj / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"content of {rel}\n")
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
