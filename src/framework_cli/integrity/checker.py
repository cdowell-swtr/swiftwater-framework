from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.manifest import Manifest
from framework_cli.integrity.sections import section_sha256

_LOCK_REL = ".framework/integrity.lock"


@dataclass(frozen=True)
class Finding:
    path: str
    problem: str
    fix: str
    fatal: bool


def _load(project: Path) -> tuple[Manifest, str] | None:
    lock = project / _LOCK_REL
    if not lock.is_file():
        return None
    text = lock.read_text()
    return Manifest.loads(text), text


def check(project: Path, ci: bool = False) -> list[Finding]:
    """Verify a project against its manifest. Returns findings (empty == intact)."""
    loaded = _load(project)
    if loaded is None:
        return [
            Finding(
                _LOCK_REL,
                "integrity manifest is missing",
                "restore it from version control, or re-scaffold",
                True,
            )
        ]
    manifest, text = loaded
    stored = json.loads(text).get("self_sha256")
    if stored != manifest.self_sha256():
        # The manifest itself was edited; its entries can no longer be trusted.
        return [
            Finding(
                _LOCK_REL,
                "manifest self-checksum mismatch (tampered)",
                "restore the manifest from version control",
                True,
            )
        ]

    findings: list[Finding] = []
    for e in manifest.entries:
        if e.drift:
            continue
        f = project / e.path
        if e.tier == "gitignored":
            if not ci and not f.exists():
                findings.append(
                    Finding(
                        e.path,
                        "framework-managed file is absent",
                        "create it (e.g. copy .env.example to .env) — local check only",
                        False,
                    )
                )
            continue
        # tracked tier (locked = full file; hybrid = the FRAMEWORK:BEGIN/END section)
        if not f.is_file():
            findings.append(
                Finding(e.path, "framework file is missing", f"framework restore {e.path}", True)
            )
            continue
        if e.cls == "hybrid":
            section_hash = section_sha256(f.read_text())
            if section_hash is None:
                findings.append(
                    Finding(
                        e.path,
                        "managed-section markers are missing or damaged",
                        f"framework restore {e.path}",
                        True,
                    )
                )
            elif section_hash != e.sha256:
                findings.append(
                    Finding(
                        e.path,
                        "framework-managed section has been altered",
                        f"framework restore {e.path}  (or `framework integrity "
                        f"--allow-drift {e.path}` to keep your change)",
                        True,
                    )
                )
        elif sha256_file(f) != e.sha256:  # cls == "locked"
            findings.append(
                Finding(
                    e.path,
                    "locked file has been altered",
                    f"framework restore {e.path}  (or `framework integrity "
                    f"--allow-drift {e.path}` to keep your change)",
                    True,
                )
            )
    return findings


def record_drift(project: Path, paths: list[str]) -> None:
    """Mark the given managed files as intentionally diverged and rewrite the manifest."""
    lock = project / _LOCK_REL
    manifest = Manifest.loads(lock.read_text())
    known = {e.path for e in manifest.entries}
    unknown = [p for p in paths if p not in known]
    if unknown:
        raise ValueError(f"not framework-managed file(s): {', '.join(unknown)}")
    wanted = set(paths)
    manifest.entries = [
        replace(e, drift=True) if e.path in wanted else e for e in manifest.entries
    ]
    lock.write_text(manifest.dumps())
