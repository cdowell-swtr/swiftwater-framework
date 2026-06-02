"""Accepted design-decision records the review agents read (spec 2026-06-01).

A decision lives as one markdown file with YAML frontmatter under
docs/superpowers/decisions/. The code keys ONLY on an active allowlist; every other
status (the open "no longer stands" family + typos) is inactive, fail-closed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

_log = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"accepted", "deferred"})


@dataclass(frozen=True)
class Decision:
    id: str
    status: str
    agents: tuple[str, ...]
    concern: str
    premise: str
    body: str
    source: str  # filename, for reporting


def _decisions_dir(root: Path) -> Path:
    return Path(root) / "docs" / "superpowers" / "decisions"


def _parse(path: Path) -> Decision:
    text = path.read_text()
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path.name}: malformed frontmatter (missing closing '---')")
    _, fm, body = parts
    meta = yaml.safe_load(fm) or {}
    premise = str(meta.get("premise", "")).strip()
    if not premise:
        raise ValueError(f"{path.name}: decision is missing a non-empty `premise`")
    agents = meta.get("agents") or []
    return Decision(
        id=str(meta["id"]),
        status=str(meta.get("status", "")),
        agents=tuple(str(a) for a in agents),
        concern=str(meta.get("concern", "")),
        premise=premise,
        body=body.strip(),
        source=path.name,
    )


def load_decisions(decisions_dir: Path) -> list[Decision]:
    """Parse every *.md decision in `decisions_dir` (any status). Raises on a bad record."""
    d = Path(decisions_dir)
    if not d.is_dir():
        return []
    return [_parse(p) for p in sorted(d.glob("*.md"))]


def _safe_load(root: Path) -> list[Decision]:
    """Load decisions for a LIVE review path, degrading to [] on any error (fail-open).

    A malformed/half-edited decision file must never crash the gate or a review run. The
    strict, raising path is `load_decisions` (used for explicit validation/tests)."""
    try:
        return load_decisions(_decisions_dir(root))
    except Exception as exc:
        _log.warning("decisions load failed at %s: %s", _decisions_dir(root), exc)
        return []


def relevant_decisions(agent: str, root: Path) -> list[Decision]:
    """Active (accepted/deferred) decisions whose `agents` includes `agent` (short name).

    Fail-open: a bad decisions file degrades to no decisions (logged), never breaks review."""
    return [
        dec
        for dec in _safe_load(root)
        if dec.status in ACTIVE_STATUSES and agent in dec.agents
    ]


def active_decision_ids(root: Path) -> set[str]:
    """Ids of all active decisions (for the verdict integrity guard). Fail-open (see _safe_load)."""
    return {dec.id for dec in _safe_load(root) if dec.status in ACTIVE_STATUSES}


_PROTOCOL = (
    "Accepted Decisions (design choices already made and accepted for THIS repo).\n"
    "For each finding you would raise, consult these:\n"
    "- If it matches a decision's concern AND the decision's `premise` still holds given the "
    'code -> still emit the finding, but add `acknowledged: "<id>"`.\n'
    "- If it matches but the premise NO LONGER holds -> emit a normal finding with "
    '`stale: "<id>"` and say which premise clause broke.\n'
    "- Otherwise emit the finding normally.\n"
)


def render_decisions_block(decisions: list[Decision]) -> str | None:
    """Render the protocol preamble + records as one text block, or None if no decisions."""
    if not decisions:
        return None
    records = "\n\n".join(
        f"[{d.id}] (agents: {', '.join(d.agents)})\n"
        f"  concern: {d.concern}\n"
        f"  premise (must hold, else STALE): {d.premise}\n"
        f"  rationale: {d.body}"
        for d in decisions
    )
    return f"{_PROTOCOL}\n{records}"
