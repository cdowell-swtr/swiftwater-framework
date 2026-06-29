"""Wire the audit stages through the checkpointed orchestrator and emit a vetted
changelist. Sequence: brief→audit (Stage 1, per target) → reconcile (Stage 2, one call) →
refute (Stage 3, per proposed edit) → vetted changelist persisted to out_dir."""

from __future__ import annotations

import hashlib
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
from framework_cli.review.checkpoint import tree_signature
from framework_cli.review.registry import agent_names, get_agent

_PROVENANCE = "audit-provenance.json"


class CheckpointProvenanceError(RuntimeError):
    """Raised when --resume meets a checkpoint produced against different inputs
    (code/agent-prompts/roster, the audited targets, skeptic count, or baseline) —
    a stale checkpoint must not silently bind to the wrong inputs (FWK47)."""

    def __init__(self, changed: list[str]) -> None:
        self.changed = changed
        super().__init__(
            "reviewer-audit checkpoint is stale — inputs changed: "
            + (", ".join(changed) or "(fingerprint differs)")
        )


def _baseline_digest(baseline_dir: Path | None) -> str:
    """A content hash of the evidence baseline dir (gitignored → invisible to the
    tree signature), so a changed baseline invalidates a resume. '' when absent."""
    if baseline_dir is None or not baseline_dir.exists():
        return ""
    h = hashlib.sha256()
    for p in sorted(baseline_dir.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(baseline_dir)).encode("utf-8", "replace"))
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def _targets_digest(targets: list[str]) -> str:
    """A content hash of each audited agent's resolved spec (prompt + bar + activation).
    Built-in agent prompts are tracked (caught by tree_signature), but a project-local
    reviewer's prompt is UNTRACKED — hashing the resolved spec closes that FWK47 gap
    for the FWK48 BYO path regardless of git-tracking (FWK121)."""
    h = hashlib.sha256()
    for name in sorted(targets):
        h.update(name.encode("utf-8", "replace"))
        h.update(b"\0")
        try:
            spec = get_agent(name)
        except KeyError:
            h.update(b"?\0")
            continue
        h.update(spec.prompt.encode("utf-8", "replace"))
        h.update(b"\0")
        h.update(f"{spec.block_threshold}\0{spec.active_when}\0".encode())
    return h.hexdigest()


def _audit_provenance(
    root: Path,
    targets: list[str],
    baseline_dir: Path | None,
    skeptics: int,
    fixtures_root: Path | None = None,
) -> dict[str, str]:
    """The fingerprint a resume must match. tree_signature(root) captures committed/
    tracked code; the rest captures the runtime inputs the tree doesn't reflect:
    targets, skeptics, the baseline content, the fixtures dir (path AND content, so an
    in-place edit to a same-path fixture is caught), and the resolved agent specs (so an
    untracked project-reviewer prompt change is caught) — FWK47/118/121."""
    sha, dirty = tree_signature(root)
    parts = {
        "git_sha": sha,
        "dirty_hash": dirty,
        "targets": ",".join(sorted(targets)),
        "skeptics": str(skeptics),
        "baseline": _baseline_digest(baseline_dir),
        "fixtures_root": str(fixtures_root) if fixtures_root else "",
        "fixtures_content": _baseline_digest(fixtures_root),
        "agent_specs": _targets_digest(targets),
    }
    digest = hashlib.sha256(
        json.dumps(parts, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return {"fingerprint": digest, **parts}


def _provenance_drift(prior: dict[str, str], current: dict[str, str]) -> list[str]:
    """Human-readable names of the input fields that changed (git_sha+dirty_hash
    collapse to 'code'; the two fixtures fields collapse to 'fixtures'; agent_specs
    reports as 'prompts')."""
    changed = []
    if (prior.get("git_sha"), prior.get("dirty_hash")) != (
        current.get("git_sha"),
        current.get("dirty_hash"),
    ):
        changed.append("code")
    for field, label in (
        ("targets", "targets"),
        ("skeptics", "skeptics"),
        ("baseline", "baseline"),
        ("fixtures_root", "fixtures"),
        ("fixtures_content", "fixtures"),
        ("agent_specs", "prompts"),
    ):
        if prior.get(field) != current.get(field) and label not in changed:
            changed.append(label)
    return changed


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
    fixtures_root: Path | None = None,
) -> Changelist:
    out_dir.mkdir(parents=True, exist_ok=True)

    # FWK47 — checkpoint-provenance guard. Stamp the inputs a fresh run was produced
    # against; on resume, refuse a checkpoint whose inputs no longer match (a stale
    # checkpoint silently binding to the wrong inputs is the failure class here).
    prov_path = out_dir / _PROVENANCE
    current = _audit_provenance(root, targets, baseline_dir, skeptics, fixtures_root)
    if resume and prov_path.exists():
        prior = json.loads(prov_path.read_text())
        if prior.get("fingerprint") != current["fingerprint"]:
            raise CheckpointProvenanceError(_provenance_drift(prior, current))
    elif resume:
        # A legacy checkpoint with no provenance file can't be verified — proceed,
        # but say so rather than silently trusting possibly-stale inputs.
        log(
            f"reviewer-audit: resuming a checkpoint with no provenance stamp ({prov_path.name} "
            "absent) — cannot verify inputs match; re-stamping from the current run"
        )
    prov_path.write_text(json.dumps(current, indent=2, sort_keys=True))

    roster = {n: get_agent(n).block_threshold for n in agent_names()}

    # Stage 1 — audit fan-out (per target), checkpointed.
    log(f"Stage 1: auditing {len(targets)} agent(s)")

    def _audit(target: str) -> dict[str, Any]:
        brief = build_audit_brief(
            target, root=root, baseline_dir=baseline_dir, fixtures_root=fixtures_root
        )
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
