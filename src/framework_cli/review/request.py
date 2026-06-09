from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework_cli.review.context import Bundle
from framework_cli.review.decisions import render_decisions_block
from framework_cli.review.registry import AgentSpec


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
    system.append({"type": "text", "text": spec.prompt})
    return ReviewRequest(
        model=spec.model,
        system=system,
        user_message=_BUNDLE_USER,
        tools=None,
        root=root,
        max_turns=1,
    )
