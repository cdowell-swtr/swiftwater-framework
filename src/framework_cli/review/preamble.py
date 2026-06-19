"""Compose the shared reviewer preamble (rubric + output contract) per agent.

The rubric body is single-sourced in `rubric.md`; the only per-agent variation in
the shared blocks is the allowed severity enum, derived from `block_threshold`
(advisory → low|info) with an optional `AgentSpec.severity_enum` override. Composed
with the agent's domain block at prompt-build time (see `request.py`)."""

from __future__ import annotations

from importlib.resources import files

from framework_cli.review.registry import AgentSpec

_RUBRIC = (files("framework_cli.review") / "rubric.md").read_text()

_ADVISORY_NOTE = (
    "\n**You are an ADVISORY agent** (registry `block_threshold` is `None`): cap every "
    "finding at the severities in your output contract and NEVER emit high/medium unless "
    "your contract lists them. You surface observations by design; an info/low finding on "
    "otherwise-clean code is not a false positive for you."
)

_OUTPUT_CONTRACT = (
    "\n## Output\n"
    "Return **JSON ONLY** — a single JSON array, no prose, no code fences. Each element:\n"
    '`{{"path": "<file path from the diff>", "line": <integer>, '
    '"severity": "{enum}", "message": "<what is wrong and why it matters>", '
    '"suggestion": "<concrete fix, optional>"}}`. '
    "Every element MUST include a `severity` field. Output exactly `[]` when there are no findings.\n"
)


def severity_enum_for(spec: AgentSpec) -> str:
    if spec.severity_enum is not None:
        return "|".join(spec.severity_enum)
    if spec.block_threshold is None:
        return "low|info"
    return "high|medium|low|info"


def build_preamble(spec: AgentSpec) -> str:
    parts = [_RUBRIC.rstrip()]
    if spec.block_threshold is None:
        parts.append(_ADVISORY_NOTE)
    parts.append(_OUTPUT_CONTRACT.format(enum=severity_enum_for(spec)))
    return "\n".join(parts)
