"""Deterministic ordering of battery-contributed alembic migrations.

Each migration-adding battery has a FIXED numeric revision id (by canonical position) and a
`down_revision` computed as the nearest PRESENT predecessor in the canonical order (else the
baseline 0001). Revision ids are opaque alembic labels, so "gaps" (0001 -> 0003 when webhooks
is absent) are harmless and no renaming is needed.
"""

from __future__ import annotations

from collections.abc import Sequence

# Canonical order of migration-adding batteries (others add no alembic migration).
MIGRATION_ORDER: tuple[str, ...] = (
    "webhooks",
    "workers",
    "pgvector",
    "timescaledb",
    "age",
)
# Fixed revision id per battery (baseline is 0001).
REVISIONS: dict[str, str] = {
    "webhooks": "0002",
    "workers": "0003",
    "pgvector": "0004",
    "timescaledb": "0005",
    "age": "0006",
}

if set(MIGRATION_ORDER) != set(REVISIONS):  # pragma: no cover - authoring guard
    raise RuntimeError(
        "MIGRATION_ORDER and REVISIONS must list the same batteries "
        "(a new migration-adding battery must be added to both)"
    )


def migration_down_revisions(batteries: Sequence[str]) -> dict[str, str]:
    """Map each present migration-adding battery to its down_revision (nearest present
    predecessor in canonical order, else '0001')."""
    present = [b for b in MIGRATION_ORDER if b in batteries]
    out: dict[str, str] = {}
    prev = "0001"
    for b in present:
        out[b] = prev
        prev = REVISIONS[b]
    return out


def migration_context(batteries: Sequence[str]) -> dict[str, str]:
    """Copier context vars `down_revision_<battery>` for each present migration battery."""
    return {
        f"down_revision_{b}": rev
        for b, rev in migration_down_revisions(batteries).items()
    }
