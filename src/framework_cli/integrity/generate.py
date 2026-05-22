from __future__ import annotations

from pathlib import Path

import pathspec

from framework_cli.integrity.classes import rules
from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.manifest import Entry, Manifest
from framework_cli.integrity.sections import section_sha256


class AuthoringError(Exception):
    """A framework authoring bug surfaced at manifest generation (not a builder error)."""


def _gitignore_spec(project: Path) -> pathspec.PathSpec:
    gi = project / ".gitignore"
    lines = gi.read_text().splitlines() if gi.is_file() else []
    return pathspec.PathSpec.from_lines("gitignore", lines)


def build_manifest(project: Path, framework_version: str) -> Manifest:
    """Build the integrity manifest for a rendered project.

    Enforces spec §17: a checksummed (tracked) file must exist and must not be
    excluded by the project's own .gitignore.
    """
    spec = _gitignore_spec(project)
    entries: list[Entry] = []
    for rule in rules():
        if rule.tier == "tracked":
            if spec.match_file(rule.path):
                raise AuthoringError(
                    f"{rule.path} is locked/tracked but matches .gitignore — a "
                    "checksummed file must be git-tracked (spec §17)."
                )
            f = project / rule.path
            if not f.is_file():
                raise AuthoringError(
                    f"{rule.path} is declared locked but was not rendered."
                )
            if rule.cls == "hybrid":
                section_hash = section_sha256(f.read_text())
                if section_hash is None:
                    raise AuthoringError(
                        f"{rule.path} is a hybrid file but has no FRAMEWORK:BEGIN/END markers."
                    )
                entries.append(Entry(rule.path, rule.cls, rule.tier, sha256=section_hash))
            else:
                entries.append(
                    Entry(rule.path, rule.cls, rule.tier, sha256=sha256_file(f))
                )
        else:  # gitignored existence tier — recorded, never checksummed
            entries.append(Entry(rule.path, rule.cls, rule.tier, sha256=None))
    return Manifest(framework_version=framework_version, entries=entries)


def write_manifest(project: Path, framework_version: str) -> Path:
    """Generate and write `.framework/integrity.lock`; return its path."""
    manifest = build_manifest(project, framework_version)
    out = project / ".framework" / "integrity.lock"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(manifest.dumps())
    return out
