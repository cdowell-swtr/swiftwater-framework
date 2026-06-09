"""Swappable model backends behind a `messages.create`-shaped seam.

`run_agent` / `run_agent_agentic` call `backend.messages.create(...)` and read
`.content` / `.usage` / `.stop_reason` — the same surface the Anthropic SDK
returns. `ApiBackend` is the SDK; `SubagentBackend` shells out to headless
`claude -p` and adapts its JSON into these dataclasses, so the review loops are
byte-identical across paid and free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class TextBlock:
    text: str
    type: Literal["text"] = "text"


@dataclass(frozen=True)
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: Literal["tool_use"] = "tool_use"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class Message:
    content: list[TextBlock | ToolUseBlock] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None


class BackendExhausted(Exception):
    """The backend cannot continue for a reason that will not clear by retrying soon
    (e.g. the Claude subscription usage limit). Carries an optional reset hint. Used by
    Plan 20b's engine; defined here so both plans share the type."""

    def __init__(self, message: str, *, reset_hint: str | None = None) -> None:
        super().__init__(message)
        self.reset_hint = reset_hint
