from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from framework_cli.review.evals import (
    DEFAULT_THRESHOLDS,
    AgentScore,
    Thresholds,
    flags,
    score_agent,
)
from framework_cli.review.findings import Finding
from framework_cli.review.registry import get_agent

# Per-million-token prices, USD — approximate per Anthropic pricing (2026-05).
# Intended for relative ranking and order-of-magnitude estimates, not invoicing.
_PRICES: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.50,
        "cache_creation": 18.75,
    },
    "claude-opus-4-7": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.50,
        "cache_creation": 18.75,
    },
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_creation": 3.75,
    },
    "claude-haiku-4-5-20251001": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.10,
        "cache_creation": 1.25,
    },
}
_FALLBACK_PRICE = _PRICES["claude-sonnet-4-6"]


@dataclass(frozen=True)
class Record:
    agent: str
    kind: str
    case: str
    repeat: int
    seeded_file: str | None
    findings: list[dict[str, Any]]
    usage: dict[str, int]
    latency_ms: int | None
    stop_reason: str | None
    raw_text: str
    turns: int
    tool_calls: list[dict[str, Any]]


_REQUIRED = ("agent", "kind", "case", "repeat", "findings")


def load_records(root: Path) -> list[Record]:
    """Load all per-call JSON records under `root`. Skips files missing required keys."""
    records: list[Record] = []
    for f in sorted(root.rglob("*.json")):
        try:
            d = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not all(k in d for k in _REQUIRED):
            continue
        records.append(
            Record(
                agent=d["agent"],
                kind=d["kind"],
                case=d["case"],
                repeat=int(d["repeat"]),
                seeded_file=d.get("seeded_file"),
                findings=list(d.get("findings", [])),
                usage=dict(d.get("usage", {})),
                latency_ms=d.get("latency_ms"),
                stop_reason=d.get("stop_reason"),
                raw_text=d.get("raw_text", ""),
                turns=int(d.get("turns", 1)),
                tool_calls=list(d.get("tool_calls", [])),
            )
        )
    return records


def _findings(rec: Record) -> list[Finding]:
    return [
        Finding(
            path=f["path"],
            line=int(f["line"]),
            severity=f["severity"],
            message=f["message"],
            suggestion=f.get("suggestion"),
        )
        for f in rec.findings
    ]


def scorecard(
    records: list[Record], thresholds: dict[str, Thresholds]
) -> list[AgentScore]:
    """Re-derive recall/fp per agent from records by re-running `flags()` per call."""
    by_agent: dict[str, list[Record]] = {}
    for r in records:
        by_agent.setdefault(r.agent, []).append(r)
    out: list[AgentScore] = []
    for agent in sorted(by_agent):
        try:
            spec = get_agent(agent)
        except KeyError:
            continue
        bad_by_case: dict[str, list[int]] = {}
        good_by_case: dict[str, list[int]] = {}
        for r in by_agent[agent]:
            f = _findings(r)
            blocked = (
                flags(f, spec, file=r.seeded_file)
                if r.kind == "bad"
                else flags(f, spec)
            )
            bucket = bad_by_case if r.kind == "bad" else good_by_case
            bucket.setdefault(r.case, []).append(1 if blocked else 0)
        bad_rates = [sum(hits) / len(hits) for hits in bad_by_case.values()]
        good_rates = [sum(hits) / len(hits) for hits in good_by_case.values()]
        thr = thresholds.get(agent, DEFAULT_THRESHOLDS)
        out.append(score_agent(agent, bad_rates, good_rates, thr))
    return out


def cost_report(
    records: list[Record], model_map: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Sum usage tokens × per-model prices into per-agent cost slots."""
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        model = model_map.get(r.agent)
        if not model:
            continue
        price = _PRICES.get(model, _FALLBACK_PRICE)
        u = r.usage
        cost = (
            u.get("input_tokens", 0) * price["input"]
            + u.get("output_tokens", 0) * price["output"]
            + u.get("cache_read_input_tokens", 0) * price["cache_read"]
            + u.get("cache_creation_input_tokens", 0) * price["cache_creation"]
        ) / 1_000_000
        slot = out.setdefault(
            r.agent,
            {
                "model": model,
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cost": 0.0,
            },
        )
        slot["calls"] += 1
        slot["input_tokens"] += u.get("input_tokens", 0)
        slot["output_tokens"] += u.get("output_tokens", 0)
        slot["cache_read_input_tokens"] += u.get("cache_read_input_tokens", 0)
        slot["cost"] += cost
    return out


def recall_diagnosis(records: list[Record]) -> dict[str, list[dict[str, Any]]]:
    """For each bad record: did it catch the seeded defect, and what else did it flag?"""
    out: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if r.kind != "bad":
            continue
        seeded_hits = [f for f in r.findings if f.get("path") == r.seeded_file]
        other = [f for f in r.findings if f.get("path") != r.seeded_file]
        out.setdefault(r.agent, []).append(
            {
                "case": r.case,
                "repeat": r.repeat,
                "seeded_file": r.seeded_file,
                "caught": bool(seeded_hits),
                "seeded_hits": seeded_hits,
                "other_findings": other,
            }
        )
    return out


def fp_diagnosis(records: list[Record]) -> dict[str, list[dict[str, Any]]]:
    """For each good record that flagged something: the actual findings (= the fp surface)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if r.kind != "good" or not r.findings:
            continue
        out.setdefault(r.agent, []).append(
            {"case": r.case, "repeat": r.repeat, "findings": r.findings}
        )
    return out


def agentic_behavior(
    records: list[Record], max_turns: int = 12
) -> dict[str, dict[str, Any]]:
    """For agentic agents (resolved via the registry): turns + tool-call histogram."""
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        try:
            spec = get_agent(r.agent)
        except KeyError:
            continue
        if getattr(spec.context, "strategy", "") != "agentic":
            continue
        slot = out.setdefault(
            r.agent,
            {
                "calls": 0,
                "turn_counts": [],
                "tool_counter": Counter(),
                "path_counter": Counter(),
                "max_turns_hits": 0,
            },
        )
        slot["calls"] += 1
        slot["turn_counts"].append(r.turns)
        for tc in r.tool_calls:
            slot["tool_counter"][tc.get("tool", "?")] += 1
            inp = tc.get("input", {}) or {}
            for v in (inp.get("path"), inp.get("path_glob"), inp.get("pattern")):
                if isinstance(v, str):
                    slot["path_counter"][v] += 1
        if r.turns >= max_turns:
            slot["max_turns_hits"] += 1
    return out


def propose_thresholds(
    scores: list[AgentScore], *, margin: float = 0.10
) -> dict[str, dict[str, float]]:
    """Suggest thresholds with margin: recall_min = recall - margin, fp_max = fp + margin."""
    out: dict[str, dict[str, float]] = {}
    for s in scores:
        out[s.agent] = {
            "recall_min": round(max(0.0, s.recall - margin), 2),
            "fp_max": round(min(1.0, s.fp_rate + margin), 2),
            "_observed_recall": round(s.recall, 2),
            "_observed_fp": round(s.fp_rate, 2),
        }
    return out


def render_markdown(
    records: list[Record],
    scores: list[AgentScore],
    costs: dict[str, dict[str, Any]],
    recall_diag: dict[str, list[dict[str, Any]]],
    fp_diag: dict[str, list[dict[str, Any]]],
    agentic: dict[str, dict[str, Any]],
    proposed: dict[str, dict[str, float]],
) -> str:
    """Render the full analyze report as Markdown."""
    lines: list[str] = []
    lines.append("# Eval scorecard")
    lines.append("")
    bad = sum(1 for r in records if r.kind == "bad")
    good = sum(1 for r in records if r.kind == "good")
    agents = {r.agent for r in records}
    total_cost = sum(slot["cost"] for slot in costs.values())
    lines.append("## Summary")
    lines.append(f"- Agents: {len(agents)}")
    lines.append(f"- Calls: {len(records)} (bad: {bad}, good: {good})")
    lines.append(f"- Total cost (est., USD): ${total_cost:.2f}")
    lines.append("")
    lines.append("## Scorecard")
    lines.append("| Agent | Recall | FP | Status |")
    lines.append("|---|---|---|---|")
    for s in scores:
        status = "PASS" if s.passed else f"FAIL ({s.reason})"
        lines.append(
            f"| review-{s.agent} | {s.recall:.2f} | {s.fp_rate:.2f} | {status} |"
        )
    lines.append("")
    lines.append("## Cost by agent")
    lines.append(
        "| Agent | Model | Calls | In tok | Out tok | Cache reads | Est. cost |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for agent in sorted(costs):
        c = costs[agent]
        lines.append(
            f"| review-{agent} | {c['model']} | {c['calls']} | "
            f"{c['input_tokens']} | {c['output_tokens']} | "
            f"{c['cache_read_input_tokens']} | ${c['cost']:.2f} |"
        )
    lines.append("")
    lines.append("## Recall diagnosis (per bad case)")
    if not recall_diag:
        lines.append("_(no bad records)_")
    for agent in sorted(recall_diag):
        lines.append(f"### review-{agent}")
        for e in recall_diag[agent]:
            mark = "[caught]" if e["caught"] else "[MISSED]"
            lines.append(
                f"- {mark} `{e['case']}` r{e['repeat']} — "
                f"seeded=`{e['seeded_file']}`, other_findings={len(e['other_findings'])}"
            )
            for f in e["other_findings"][:5]:
                lines.append(
                    f"  - other: `{f.get('path')}:{f.get('line')}` "
                    f"{f.get('severity')} — {f.get('message')}"
                )
        lines.append("")
    lines.append("## FP diagnosis (findings on good fixtures)")
    if not fp_diag:
        lines.append("_(no fp findings — all good fixtures clean)_")
    for agent in sorted(fp_diag):
        lines.append(f"### review-{agent}")
        for e in fp_diag[agent]:
            lines.append(
                f"- `{e['case']}` r{e['repeat']} → {len(e['findings'])} findings:"
            )
            for f in e["findings"][:5]:
                lines.append(
                    f"  - `{f.get('path')}:{f.get('line')}` "
                    f"{f.get('severity')} — {f.get('message')}"
                )
        lines.append("")
    lines.append("## Agentic behavior")
    if not agentic:
        lines.append("_(no agentic records)_")
    for agent in sorted(agentic):
        a = agentic[agent]
        avg_turns = mean(a["turn_counts"]) if a["turn_counts"] else 0.0
        tools = ", ".join(f"{t}×{n}" for t, n in a["tool_counter"].most_common(5))
        paths = ", ".join(f"`{p}`×{n}" for p, n in a["path_counter"].most_common(5))
        lines.append(f"### review-{agent}")
        lines.append(
            f"- Calls: {a['calls']}, avg turns: {avg_turns:.1f}, "
            f"max-cap hits: {a['max_turns_hits']}"
        )
        if tools:
            lines.append(f"- Tools: {tools}")
        if paths:
            lines.append(f"- Top paths/patterns: {paths}")
        lines.append("")
    lines.append("## Proposed thresholds.yaml")
    lines.append("```yaml")
    for agent in sorted(proposed):
        t = proposed[agent]
        lines.append(f"{agent}:")
        lines.append(
            f"  recall_min: {t['recall_min']:.2f}  # observed {t['_observed_recall']:.2f}"
        )
        lines.append(f"  fp_max: {t['fp_max']:.2f}  # observed {t['_observed_fp']:.2f}")
    lines.append("```")
    return "\n".join(lines) + "\n"
