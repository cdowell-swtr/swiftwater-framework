from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework_cli.review.context import Bundle
from framework_cli.review.decisions import Decision, render_decisions_block
from framework_cli.review.registry import AgentSpec, composed_prompt


@dataclass(frozen=True)
class ReviewRequest:
    """The dispatch-agnostic review request: identical for paid and free backends."""

    model: str
    system: list[dict[str, Any]]
    user_message: str
    tools: list[dict[str, Any]] | None
    root: Path
    max_turns: int


_BUNDLE_USER = "Return your findings as a JSON array only."


def build_review_request(
    bundle: Bundle, spec: AgentSpec, *, root: Path
) -> ReviewRequest:
    system: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Review this unified diff:\n\n{bundle.diff}",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if bundle.context_files:
        joined = "\n\n".join(
            f"=== {path} ===\n{content}" for path, content in bundle.context_files
        )
        note = "\n\n[context truncated to fit the budget]" if bundle.truncated else ""
        system.append(
            {
                "type": "text",
                "text": f"Relevant repository files for context:\n\n{joined}{note}",
                "cache_control": {"type": "ephemeral"},
            }
        )
    block = render_decisions_block(list(bundle.decisions))
    if block is not None:
        system.append(
            {"type": "text", "text": block, "cache_control": {"type": "ephemeral"}}
        )
    system.append({"type": "text", "text": composed_prompt(spec)})
    return ReviewRequest(
        model=spec.model,
        system=system,
        user_message=_BUNDLE_USER,
        tools=None,
        root=root,
        max_turns=1,
    )


_AGENTIC_USER = (
    "Review the change shown in the diff. Use the read_file, grep, and glob tools to "
    "explore the surrounding repository as needed. When done, reply with ONLY a JSON "
    "array of findings (no tools)."
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file by its path relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "grep",
        "description": "Search file contents with a Python regex. Optional path_glob limits the search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path_glob": {"type": "string"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "glob",
        "description": "List files matching a glob pattern (e.g. 'src/**/*.py') relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    },
]


def build_agentic_request(
    diff: str,
    spec: AgentSpec,
    *,
    root: Path,
    decisions: tuple[Decision, ...] = (),
    max_turns: int,
) -> ReviewRequest:
    system: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Review this unified diff:\n\n{diff}",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    block = render_decisions_block(list(decisions))
    if block is not None:
        system.append(
            {"type": "text", "text": block, "cache_control": {"type": "ephemeral"}}
        )
    system.append({"type": "text", "text": composed_prompt(spec)})
    return ReviewRequest(
        model=spec.model,
        system=system,
        user_message=_AGENTIC_USER,
        tools=TOOL_SCHEMAS,
        root=root,
        max_turns=max_turns,
    )
