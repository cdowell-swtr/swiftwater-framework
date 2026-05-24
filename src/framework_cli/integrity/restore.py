from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

import yaml

from framework_cli.copier_runner import render_project
from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.manifest import Manifest
from framework_cli.integrity.sections import section_sha256, section_span

_LOCK_REL = ".framework/integrity.lock"
_ANSWERS_REL = ".copier-answers.yml"


def _answers(project: Path) -> dict[str, object]:
    answers = project / _ANSWERS_REL
    if not answers.is_file():
        raise ValueError(
            f"{_ANSWERS_REL} is missing — cannot determine which template version to restore from"
        )
    data = yaml.safe_load(answers.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _restore_section(target: Path, canonical: Path) -> None:
    """Replace target's FRAMEWORK:BEGIN/END span with canonical's, preserving outside content."""
    target_text = target.read_text()
    t_span = section_span(target_text)
    if t_span is None:
        raise ValueError(
            f"{target.name}: managed-section markers are missing or damaged — "
            "fix the FRAMEWORK:BEGIN/END markers or re-scaffold"
        )
    canonical_text = canonical.read_text()
    c_span = section_span(canonical_text)
    if c_span is None:  # the bundled template should always be marked
        raise ValueError(f"{target.name}: canonical template is missing its markers")
    t_lines = target_text.splitlines()
    c_lines = canonical_text.splitlines()
    # Line-based splice (LF). Safe for the hybrid file set: text files are LF-normalized via
    # the locked `.gitattributes` (eol=lf), and the framework sections are ASCII.
    new_lines = (
        t_lines[: t_span[0]] + c_lines[c_span[0] : c_span[1] + 1] + t_lines[t_span[1] + 1 :]
    )
    trailing = "\n" if target_text.endswith("\n") else ""
    target.write_text("\n".join(new_lines) + trailing)


def restore_file(project: Path, rel: str) -> None:
    """Re-render `rel` from the bundled template and overwrite the project's copy.

    6a restores locked (full-file) entries to the installed framework version.
    """
    lock = project / _LOCK_REL
    if not lock.is_file():
        raise ValueError(
            "not a framework project (no .framework/integrity.lock) — run from a project root"
        )
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
        if entry.cls == "hybrid":
            _restore_section(project / rel, canonical)
        else:
            (project / rel).write_bytes(canonical.read_bytes())

    if entry.cls == "hybrid":
        new_sha = section_sha256((project / rel).read_text())
    else:
        new_sha = sha256_file(project / rel)
    manifest.entries = [
        replace(e, sha256=new_sha, drift=False) if e.path == rel else e
        for e in manifest.entries
    ]
    lock.write_text(manifest.dumps())
