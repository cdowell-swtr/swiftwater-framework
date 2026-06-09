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


def _normalize_content(raw: Any) -> list[TextBlock | ToolUseBlock]:
    out: list[TextBlock | ToolUseBlock] = []
    for b in raw or []:
        btype = getattr(b, "type", None)
        if btype == "text":
            out.append(TextBlock(text=getattr(b, "text", "") or ""))
        elif btype == "tool_use":
            out.append(
                ToolUseBlock(
                    id=getattr(b, "id", ""),
                    name=getattr(b, "name", ""),
                    input=dict(getattr(b, "input", {}) or {}),
                )
            )
    return out


def _normalize_usage(raw: Any) -> Usage:
    return Usage(
        input_tokens=getattr(raw, "input_tokens", 0) or 0,
        output_tokens=getattr(raw, "output_tokens", 0) or 0,
        cache_read_input_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
    )


class _ApiMessages:
    def __init__(self, sdk: Any) -> None:
        self._sdk = sdk

    def create(self, **kwargs: Any) -> Message:
        resp = self._sdk.messages.create(**kwargs)
        return Message(
            content=_normalize_content(getattr(resp, "content", [])),
            usage=_normalize_usage(getattr(resp, "usage", None)),
            stop_reason=getattr(resp, "stop_reason", None),
        )


class ApiBackend:
    """The paid backend: the Anthropic SDK client, normalized to `Message`."""

    def __init__(self, sdk_client: Any) -> None:
        self.messages = _ApiMessages(sdk_client)
