from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from framework_cli.review.findings import Finding


def write_findings(
    path: Path, agent: str, conclusion: str, findings: list[Finding]
) -> None:
    """Write this agent's result as the lossless JSON the aggregator consumes.

    Called at every terminal path of `framework review` so a skipped/neutral agent still
    produces a file (conclusion set, empty findings) and the aggregator sees the full set.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent": agent,
        "conclusion": conclusion,
        "findings": [asdict(f) for f in findings],
    }
    path.write_text(json.dumps(payload, indent=2))


SUMMARY_MARKER = "<!-- framework-review-summary -->"

# Severity ordering for grouping + counts display (highest first).
_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

# Known related-domain agent pairs: when both flag an overlapping file, that co-occurrence is
# itself worth surfacing. Uses the registry's full agent names.
_RELATED_PAIRS: set[frozenset[str]] = {
    frozenset({"review-data-lineage", "review-privacy"}),
    frozenset({"review-data-lineage", "review-compliance"}),
    frozenset({"review-performance", "review-data-integrity"}),
}


@dataclass(frozen=True)
class AggregateResult:
    overall: str  # "pass" | "fail"
    severity_counts: dict[str, int]
    relationships: list[str]
    markdown: str


def aggregate(results: list[dict]) -> AggregateResult:
    """Combine per-agent results (parsed findings JSONs) into one summary. Pure, no I/O."""
    overall = (
        "fail" if any(r.get("conclusion") == "failure" for r in results) else "pass"
    )

    severity_counts: dict[str, int] = {}
    by_path: dict[str, set[str]] = {}
    all_findings: list[tuple[str, dict]] = []  # (agent, finding) in input order
    for r in results:
        agent = r.get("agent", "?")
        for f in r.get("findings", []):
            sev = f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            by_path.setdefault(f["path"], set()).add(agent)
            all_findings.append((agent, f))

    paths = sorted(by_path)
    sorted_pairs = sorted(tuple(sorted(p)) for p in _RELATED_PAIRS)
    relationships: list[str] = []
    for path in paths:  # (a) same file flagged by >= 2 distinct agents
        agents = by_path[path]
        if len(agents) >= 2:
            relationships.append(
                f"Multiple agents flagged `{path}`: {', '.join(sorted(agents))}"
            )
    for path in (
        paths
    ):  # (b) known related-domain pairs co-occurring on a file (deterministic order)
        agents = by_path[path]
        for a, b in sorted_pairs:
            if {a, b} <= agents:
                relationships.append(
                    f"`{a}` + `{b}` both flagged `{path}` — related concern."
                )

    markdown = _render_markdown(
        overall, severity_counts, relationships, all_findings, paths
    )
    return AggregateResult(overall, severity_counts, relationships, markdown)


def load_results(directory: Path) -> list[dict]:
    """Read every `*.json` in `directory`, tolerating a missing/malformed file (skip it)."""
    results: list[dict] = []
    for p in sorted(directory.glob("*.json")):
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            results.append(data)
    return results


def _render_markdown(
    overall: str,
    severity_counts: dict[str, int],
    relationships: list[str],
    all_findings: list[tuple[str, dict]],
    files: list[str],
) -> str:
    icon = "✅" if overall == "pass" else "❌"
    total = sum(severity_counts.values())
    counts = ", ".join(
        f"{severity_counts[s]} {s}" for s in _SEVERITY_ORDER if severity_counts.get(s)
    )
    lines = [
        SUMMARY_MARKER,
        f"## {icon} Review summary — {overall.upper()}",
        "",
        f"{total} finding(s)" + (f" ({counts})" if counts else "") + ".",
        "",
    ]
    for sev in _SEVERITY_ORDER:
        group = [(a, f) for (a, f) in all_findings if f.get("severity") == sev]
        if not group:
            continue
        lines.append(f"### {sev}")
        lines.extend(
            f"- {agent} · `{f['path']}:{f['line']}` · {f['message']}"
            for agent, f in group
        )
        lines.append("")
    lines.append("### Cross-agent relationships")
    lines.extend([f"- {r}" for r in relationships] or ["- none"])
    lines.append("")
    lines.append("### Affected files")
    lines.extend([f"- `{p}`" for p in files] or ["- none"])
    return "\n".join(lines)
