"""Wire the audit stages through the checkpointed orchestrator and emit a vetted
changelist. Sequence: brief→audit (Stage 1, per target) → reconcile (Stage 2, one call) →
refute (Stage 3, per proposed edit) → vetted changelist persisted to out_dir."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from framework_cli.review.audit.brief import build_audit_brief
from framework_cli.review.audit.changelist import (
    AgentChange,
    Changelist,
    ProposedEdit,
    Verdict,
)
from framework_cli.review.audit.orchestrator import run_stage
from framework_cli.review.audit.stages import audit_agent, reconcile, refute
from framework_cli.review.registry import agent_names, get_agent


def run_audit(
    targets: list[str],
    *,
    backend: Any,
    root: Path,
    baseline_dir: Path | None,
    out_dir: Path,
    skeptics: int = 3,
    resume: bool = False,
    log: Callable[[str], None] = lambda _msg: None,
    concurrency: int = 1,
) -> Changelist:
    out_dir.mkdir(parents=True, exist_ok=True)
    roster = {n: get_agent(n).block_threshold for n in agent_names()}

    # Stage 1 — audit fan-out (per target), checkpointed.
    log(f"Stage 1: auditing {len(targets)} agent(s)")

    def _audit(target: str) -> dict[str, Any]:
        brief = build_audit_brief(target, root=root, baseline_dir=baseline_dir)
        return audit_agent(brief, backend)

    reports = run_stage(
        targets,
        _audit,
        run_dir=out_dir / "stage1-audit",
        item_id=lambda t: t,
        resume=resume,
        label="audit",
        log=log,
        concurrency=concurrency,
    )

    # Stage 2 — cross-agent reconciliation (single call). Checkpoint its output so a
    # resume reuses the SAME changelist — otherwise re-running the non-deterministic
    # reconcile would desync the Stage-3 verdict checkpoint keys.
    log("Stage 2: reconciling")
    recon_path = out_dir / "stage2-reconcile.json"
    if resume and recon_path.exists():
        cl = Changelist.from_dict(json.loads(recon_path.read_text()))
    else:
        cl = reconcile(reports, roster, backend, log=log)
        recon_path.write_text(json.dumps(cl.to_dict(), indent=2))
    n_edits = sum(len(a.edits) for a in cl.agents) + len(cl.preamble_edits)
    log(f"Stage 2: reconcile -> {n_edits} edit(s) across {len(cl.agents)} agent(s)")

    # Stage 3 — adversarial refutation per proposed edit, checkpointed.
    flat = [(a.agent, i, e) for a in cl.agents for i, e in enumerate(a.edits)]
    flat += [("__preamble__", i, e) for i, e in enumerate(cl.preamble_edits)]
    log(f"Stage 3: refuting {len(flat)} edit(s) (x{skeptics} skeptics)")

    def _refute(item: tuple[str, int, ProposedEdit]) -> dict[str, Any]:
        agent, idx, edit = item
        v = refute(edit, agent, backend, skeptics=skeptics, log=log)
        return {
            "agent": agent,
            "idx": idx,
            "verdict": {
                "refuted": v.refuted,
                "votes": v.votes,
                "refutation": v.refutation,
                "parse_failures": v.parse_failures,
            },
        }

    verdicts = run_stage(
        flat,
        _refute,
        run_dir=out_dir / "stage3-refute",
        item_id=lambda it: f"{it[0]}__{it[1]}",
        resume=resume,
        label="refute",
        log=log,
        concurrency=concurrency,
    )
    vmap = {
        (r["agent"], r["idx"]): r["verdict"]
        for r in verdicts
        if "verdict" in r and "agent" in r and "idx" in r
    }

    def _attach(agent: str, edits: list[ProposedEdit]) -> list[ProposedEdit]:
        out = []
        for i, e in enumerate(edits):
            v = vmap.get((agent, i))
            out.append(
                ProposedEdit(
                    e.target,
                    e.rationale,
                    e.before,
                    e.after,
                    e.path,
                    Verdict(**v) if v else None,
                )
            )
        return out

    decided = Changelist(
        agents=[
            AgentChange(
                a.agent,
                a.proposed_block_threshold,
                _attach(a.agent, a.edits),
                dict(a.fixture_verdicts),
            )
            for a in cl.agents
        ],
        preamble_edits=_attach("__preamble__", cl.preamble_edits),
    )
    vetted = decided.vetted()
    (out_dir / "changelist.json").write_text(json.dumps(vetted.to_dict(), indent=2))
    (out_dir / "changelist-full.json").write_text(
        json.dumps(decided.to_dict(), indent=2)
    )
    n_v = sum(len(a.edits) for a in vetted.agents) + len(vetted.preamble_edits)
    n_all = len(flat)
    log(f"vetted {n_v}/{n_all} ({n_all - n_v} refuted) -> {out_dir}/")
    return vetted
