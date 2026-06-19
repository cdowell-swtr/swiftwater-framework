"""FWK7 — reverse integrity-coverage check.

Forward coverage is one-directional in `classes.py` (registered paths must render). This module
adds the reverse direction: every framework-infra file under the scanned surface roots must be
classified into exactly one category, so a new framework file cannot silently escape integrity
coverage. Scope is intentionally limited to the surface roots below; widening it is a one-line
change to `_SURFACE_ROOTS` plus its own per-file audit (see the design doc's Non-goals).
"""

from __future__ import annotations

from pathlib import Path

from framework_cli.integrity.classes import (
    BATTERY_LOCKED,
    EXEMPT,
    GITIGNORED_EXISTENCE,
    HYBRID_TRACKED,
    INTENTIONALLY_UNLOCKED,
    LOCKED_TRACKED,
)

# Extensibility seam: the framework-infra directories the reverse check polices.
_SURFACE_ROOTS: tuple[str, ...] = ("infra", "scripts", ".github/workflows")


def classified_paths() -> set[str]:
    """Every path the integrity classification accounts for, across all categories."""
    return (
        set(LOCKED_TRACKED)
        | set(HYBRID_TRACKED)
        | set(GITIGNORED_EXISTENCE)
        | set(INTENTIONALLY_UNLOCKED)
        | set(BATTERY_LOCKED)
        | set(EXEMPT)
    )


def infra_surface_files(project: Path) -> list[str]:
    """Project-root-relative posix paths of every file under the scanned surface roots."""
    found: list[str] = []
    for root in _SURFACE_ROOTS:
        base = project / root
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file():
                found.append(p.relative_to(project).as_posix())
    return found


def unclassified_infra_files(project: Path) -> list[str]:
    """Surface-root files not accounted for by any classification category (sorted)."""
    return sorted(set(infra_surface_files(project)) - classified_paths())
