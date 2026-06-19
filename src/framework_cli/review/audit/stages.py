"""The LLM audit stages. Each builds a system prompt from a script-authored brief and
dispatches ONE structured call through the backend seam (backend.messages.create).
Stage 1 (audit) here; Stage 2 (reconcile) + Stage 3 (refute) added in Phase 2.

All stages run on Opus (AGENTIC_MODEL) — these are agentic judgments."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from framework_cli.review.audit.brief import AuditBrief
from framework_cli.review.registry import AGENTIC_MODEL

# Prose context (never re-parsed); a generous, intentionally-lossy cut so a huge
# baseline can't blow the prompt budget.
_BASELINE_CHAR_BUDGET = 20_000
# Stage calls share one token ceiling so audit/reconcile/refute stay consistent.
_MAX_TOKENS = 8000

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


def audit_agent(brief: AuditBrief, backend: Any, *, root: Path) -> dict[str, Any]:  # noqa: ARG001
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
