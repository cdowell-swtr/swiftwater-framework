"""The LLM audit stages. Each builds a system prompt from a script-authored brief and
dispatches ONE structured call through the backend seam (backend.messages.create).
Stage 1 (audit) here; Stage 2 (reconcile) + Stage 3 (refute) added in Phase 2.

All stages run on Opus (AGENTIC_MODEL) — these are agentic judgments."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from framework_cli.review.audit.brief import AuditBrief
from framework_cli.review.audit.changelist import Changelist, ProposedEdit, Verdict
from framework_cli.review.registry import AGENTIC_MODEL, agent_names

# Prose context (never re-parsed); a generous, intentionally-lossy cut so a huge
# baseline can't blow the prompt budget.
_BASELINE_CHAR_BUDGET = 20_000
# Stage calls share one token ceiling so audit/reconcile/refute stay consistent.
_MAX_TOKENS = 8000
# reconcile produces a full consolidated changelist — larger than a single audit report.
_RECONCILE_MAX_TOKENS = 16000
# Cap on serialised per-agent reports fed into the reconcile prompt.
_REPORTS_CHAR_BUDGET = 60_000

_AUDIT_SYSTEM = """You are a reviewer-prompt AUDITOR. You audit ONE framework review agent's
prompt for severity-bar calibration, scope discipline, hallucination resistance,
stricter-than-codebase and internal-consistency violations, and fixture validity.

The agent under audit, its composed prompt (shared rubric + its domain block):
<<<PROMPT
{prompt}
PROMPT>>>

The FULL reviewer roster's block_thresholds — your CONSISTENCY baseline (this agent's bar
must be consistent with how the rest of the roster grades the same severity class):
{roster}

Its golden fixtures (good = must stay clean; bad = must be caught) and expectations:
{fixtures}

Its baseline eval findings (evidence — reason FROM these AND beyond them; --repeat variance
exposes flakiness, not ground truth):
{baseline}

Return JSON ONLY — an object:
{{"agent": "<name>", "severity_issues": [..], "scope_creep": [..],
  "fixture_verdicts": {{"<kind>/<case>": "clean|unambiguous|dirty|ambiguous"}},
  "proposed_block_threshold": <one of "critical","high","medium","low","info", or JSON null for advisory>,
  "edits": [{{"target": "domain_prompt|fixture|block_threshold|rubric",
             "rationale": "..", "before": "..", "after": "..", "path": "<optional>"}}]}}
No prose, no code fences."""


def _canonical_agent(name: str) -> str | None:
    """Map a model-emitted agent id to its registry key, or None if unresolvable.

    Strips a leading 'review-' (the AgentSpec.name form) and validates against the
    roster of known registry keys.
    """
    known = set(agent_names())
    candidate = name[len("review-") :] if name.startswith("review-") else name
    return candidate if candidate in known else None


def _extract_json(text: str) -> Any:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t).rstrip("`").rstrip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # Tolerate leading/trailing prose around a single object/array — the most
        # common terse-model slip. Fall back to the outermost {...} or [...] span.
        for open_c, close_c in (("{", "}"), ("[", "]")):
            i, j = t.find(open_c), t.rfind(close_c)
            if 0 <= i < j:
                return json.loads(t[i : j + 1])
        raise


def _fmt_fixtures(brief: AuditBrief) -> str:
    return (
        "\n".join(
            f"[{f.kind}/{f.case}] expect={f.expect}\n{f.patch}" for f in brief.fixtures
        )
        or "(no fixtures)"
    )


def audit_agent(brief: AuditBrief, backend: Any) -> dict[str, Any]:
    system = _AUDIT_SYSTEM.format(
        prompt=brief.composed_prompt,
        roster=json.dumps(brief.roster_bars, indent=2, sort_keys=True),
        fixtures=_fmt_fixtures(brief),
        baseline=json.dumps(brief.baseline_findings, indent=2)[:_BASELINE_CHAR_BUDGET]
        or "(none)",
    )
    msg = backend.messages.create(
        model=AGENTIC_MODEL,
        max_tokens=_MAX_TOKENS,
        system=[{"type": "text", "text": system}],
        messages=[
            {"role": "user", "content": "Audit this agent. Return the JSON object."}
        ],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    report = _extract_json(text)
    report.setdefault("agent", brief.target)
    report.setdefault("edits", [])
    # Normalize a stringified "null"/"none" threshold to the canonical None (advisory).
    bt = report.get("proposed_block_threshold")
    if isinstance(bt, str) and bt.strip().lower() in ("null", "none", ""):
        report["proposed_block_threshold"] = None
    return report


# ---------------------------------------------------------------------------
# Stage 2 — cross-agent reconciliation
# ---------------------------------------------------------------------------

_RECONCILE_SYSTEM = """You are the reviewer-roster RECONCILER. You receive every per-agent
audit report and the full roster's block_thresholds. Produce ONE consolidated changelist
that (a) reconciles the severity bar ACROSS agents — the same defect class must not be HIGH
for one agent and LOW for another; (b) enforces one-owner-per-class scope boundaries;
(c) proposes refinements to the SHARED rubric (preamble_edits) when a fix belongs in the
common block rather than one agent.

All per-agent audit reports:
{reports}

Full roster block_thresholds:
{roster}

Return JSON ONLY in the Changelist shape (proposed_block_threshold is a severity
string like "high"/"medium"/… or JSON null for advisory — NOT the string "null"):
{{"agents": [{{"agent": "..", "proposed_block_threshold": <severity or null>,
   "edits": [{{"target": "domain_prompt|fixture|block_threshold", "rationale": "..",
              "before": "..", "after": "..", "path": "<optional>"}}],
   "fixture_verdicts": {{"<kind>/<case>": "clean|unambiguous|dirty|ambiguous"}}
}}],
 "preamble_edits": [{{"target": "rubric", "rationale": "..", "before": "..", "after": ".."}}]}}
No prose, no code fences."""


def reconcile(
    reports: list[dict[str, Any]],
    roster: dict[str, Any],
    backend: Any,
    *,
    log: Callable[[str], None] = lambda _msg: None,
) -> Changelist:
    system = _RECONCILE_SYSTEM.format(
        reports=json.dumps(reports, indent=2)[:_REPORTS_CHAR_BUDGET],
        roster=json.dumps(roster, indent=2, sort_keys=True),
    )
    msg = backend.messages.create(
        model=AGENTIC_MODEL,
        max_tokens=_RECONCILE_MAX_TOKENS,
        system=[{"type": "text", "text": system}],
        messages=[{"role": "user", "content": "Reconcile into one changelist."}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    parsed = _extract_json(text)
    # Normalize a stringified "null"/"none" threshold to canonical None (as Stage 1 does).
    for a in parsed.get("agents", []):
        bt = a.get("proposed_block_threshold")
        if isinstance(bt, str) and bt.strip().lower() in ("null", "none", ""):
            a["proposed_block_threshold"] = None
    # Normalize agent identifiers: strip leading 'review-' prefix and drop any that
    # still don't resolve to a known registry key (logged, never silently dropped).
    kept = []
    for a in parsed.get("agents", []):
        canon = _canonical_agent(str(a.get("agent", "")))
        if canon is None:
            log(f"reconcile: dropped change for unknown agent {a.get('agent')!r}")
            continue
        a["agent"] = canon
        kept.append(a)
    parsed["agents"] = kept
    return Changelist.from_dict(parsed)


# ---------------------------------------------------------------------------
# Stage 3 — adversarial refutation
# ---------------------------------------------------------------------------

_REFUTE_SYSTEM = """You are an adversarial SKEPTIC. Your job is to REFUTE the proposed change
to a reviewer prompt/fixture. Default to refuted=true if uncertain. Refute if the change
under-flags a defect class, loosens a bar so a `bad` fixture would slip, was tuned against a
dirty `good` fixture, or makes a bad case ambiguous.

Agent: {agent}
Proposed change ({target}): {rationale}
--- before ---
{before}
--- after ---
{after}

Return JSON ONLY: {{"refuted": true|false, "reason": "<one sentence>"}}. No prose, no fences."""


def refute(
    edit: ProposedEdit, agent: str, backend: Any, *, skeptics: int = 3
) -> Verdict:
    system = _REFUTE_SYSTEM.format(
        agent=agent,
        target=edit.target,
        rationale=edit.rationale,
        before=edit.before,
        after=edit.after,
    )
    refutals, survived = [], 0
    for _ in range(skeptics):
        msg = backend.messages.create(
            model=AGENTIC_MODEL,
            max_tokens=600,
            system=[{"type": "text", "text": system}],
            messages=[
                {"role": "user", "content": "Refute or fail to refute. JSON only."}
            ],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            verdict = _extract_json(text)
        except Exception:  # noqa: BLE001 — an unparseable skeptic counts as a refutation (default-to-refuted)
            refutals.append("unparseable skeptic response")
            continue
        if verdict.get("refuted", True):
            refutals.append(str(verdict.get("reason", "")))
        else:
            survived += 1
    refuted = survived < (
        skeptics // 2 + 1
    )  # survives only on a strict majority fail-to-refute
    return Verdict(refuted=refuted, votes=survived, refutation=" | ".join(refutals))
