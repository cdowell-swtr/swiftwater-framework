from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

import yaml

from framework_cli.copier_runner import render_project
from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.manifest import Manifest

_LOCK_REL = ".framework/integrity.lock"
_ANSWERS_REL = ".copier-answers.yml"


def _answers(project: Path) -> dict[str, str]:
    data = yaml.safe_load((project / _ANSWERS_REL).read_text())
    return {k: str(v) for k, v in data.items() if not k.startswith("_")}


def restore_file(project: Path, rel: str) -> None:
    """Re-render `rel` from the bundled template and overwrite the project's copy.

    6a restores locked (full-file) entries to the installed framework version.
    """
    lock = project / _LOCK_REL
    manifest = Manifest.loads(lock.read_text())
    entry = next((e for e in manifest.entries if e.path == rel), None)
    if entry is None or entry.tier != "tracked":
        raise ValueError(f"{rel} is not a restorable framework file")

    with tempfile.TemporaryDirectory() as tmp:
        canonical_root = Path(tmp) / "render"
        render_project(canonical_root, _answers(project))
        canonical = canonical_root / rel
        if not canonical.is_file():
            raise ValueError(f"{rel} was not produced by the canonical template")
        (project / rel).write_bytes(canonical.read_bytes())

    manifest.entries = [
        replace(e, sha256=sha256_file(project / rel), drift=False)
        if e.path == rel
        else e
        for e in manifest.entries
    ]
    lock.write_text(manifest.dumps())
