"""Assemble a per-target audit brief: the composed prompt under review, its fixtures
+ expectations, the baseline eval findings (the evidence), the canonical preamble, and
the FULL roster's block_thresholds (the cross-agent consistency oracle). Script-authored
and persisted by the orchestrator for auditability."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from framework_cli.review.preamble import build_preamble
from framework_cli.review.registry import agent_names, composed_prompt, get_agent


@dataclass(frozen=True)
class FixtureRef:
    kind: str  # "good" | "bad"
    case: str
    patch: str
    expect: dict[str, Any] | None


@dataclass(frozen=True)
class AuditBrief:
    target: str
    composed_prompt: str
    preamble: str
    fixtures: list[FixtureRef] = field(default_factory=list)
    baseline_findings: list[dict[str, Any]] = field(default_factory=list)
    roster_bars: dict[str, str | None] = field(default_factory=dict)


def _load_fixtures(target: str, fixtures_root: Path) -> list[FixtureRef]:
    out: list[FixtureRef] = []
    base = fixtures_root / target
    for kind in ("good", "bad"):
        kdir = base / kind
        if not kdir.is_dir():
            continue
        for case in sorted(p for p in kdir.iterdir() if p.is_dir()):
            patch_f = case / "change.patch"
            if not patch_f.exists():
                continue
            exp = case / "expect.json"
            out.append(
                FixtureRef(
                    kind=kind,
                    case=case.name,
                    patch=patch_f.read_text(),
                    expect=json.loads(exp.read_text()) if exp.exists() else None,
                )
            )
    return out


def _load_baseline(target: str, baseline_dir: Path | None) -> list[dict[str, Any]]:
    """Load per-(agent, fixture, repeat) findings written by ``framework eval --findings-out``.

    The writer (cli.py ``_write_findings``) produces a subdirectory layout::

        <findings_out>/<agent>/<kind>/<case>__r<repeat>.json

    We glob recursively under ``<baseline_dir>/<target>/`` to collect all JSON
    records for this agent regardless of kind/case/repeat ordering.
    """
    if baseline_dir is None or not baseline_dir.is_dir():
        return []
    agent_dir = baseline_dir / target
    if not agent_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for f in sorted(agent_dir.rglob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def build_audit_brief(
    target: str,
    *,
    root: Path,
    baseline_dir: Path | None,
    fixtures_root: Path | None = None,
) -> AuditBrief:
    spec = get_agent(target)
    froot = fixtures_root or (root / "tests" / "eval" / "fixtures")
    roster: dict[str, str | None] = {
        n: get_agent(n).block_threshold for n in agent_names()
    }
    return AuditBrief(
        target=target,
        composed_prompt=composed_prompt(spec),
        preamble=build_preamble(spec),
        fixtures=_load_fixtures(target, froot),
        baseline_findings=_load_baseline(target, baseline_dir),
        roster_bars=roster,
    )
