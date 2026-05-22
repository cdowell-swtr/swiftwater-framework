from pathlib import Path

import pytest

from framework_cli.integrity.classes import LOCKED_TRACKED
from framework_cli.integrity.generate import AuthoringError, build_manifest, write_manifest
from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.manifest import Manifest


def _fake_project(tmp_path: Path, *, gitignore: str = "") -> Path:
    """A minimal stand-in project containing every locked path + a .gitignore."""
    proj = tmp_path / "proj"
    for rel in LOCKED_TRACKED:
        f = proj / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"content of {rel}\n")
    (proj / ".gitignore").write_text(gitignore)
    return proj


def test_build_manifest_checksums_every_locked_file(tmp_path: Path):
    proj = _fake_project(tmp_path)
    manifest = build_manifest(proj, "0.1.0")
    locked = {e.path: e for e in manifest.entries if e.tier == "tracked"}
    assert set(locked) == set(LOCKED_TRACKED)
    sample = next(iter(LOCKED_TRACKED))
    assert locked[sample].sha256 == sha256_file(proj / sample)


def test_build_manifest_includes_gitignored_existence_tier(tmp_path: Path):
    proj = _fake_project(tmp_path)
    manifest = build_manifest(proj, "0.1.0")
    env = next(e for e in manifest.entries if e.path == ".env")
    assert env.tier == "gitignored" and env.sha256 is None


def test_authoring_error_when_a_locked_file_is_gitignored(tmp_path: Path):
    # Mark a locked path as ignored — a framework authoring bug per spec §17.
    proj = _fake_project(tmp_path, gitignore="*.yml\n")
    with pytest.raises(AuthoringError, match="matches .gitignore"):
        build_manifest(proj, "0.1.0")


def test_authoring_error_when_a_locked_file_is_missing(tmp_path: Path):
    proj = _fake_project(tmp_path)
    (proj / "alembic.ini").unlink()
    with pytest.raises(AuthoringError, match="not rendered"):
        build_manifest(proj, "0.1.0")


def test_write_manifest_creates_loadable_lock(tmp_path: Path):
    proj = _fake_project(tmp_path)
    out = write_manifest(proj, "0.1.0")
    assert out == proj / ".framework" / "integrity.lock"
    Manifest.loads(out.read_text())  # parses without error
