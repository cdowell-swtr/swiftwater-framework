"""Swappable model backends behind a `messages.create`-shaped seam.

`run_agent` / `run_agent_agentic` call `backend.messages.create(...)` and read
`.content` / `.usage` / `.stop_reason` — the same surface the Anthropic SDK
returns. Both `ApiBackend` and `SubagentBackend` route through LiteLLM via
`_anthropic_messages`, so the review loops are byte-identical across paid and
free — normalisation is shared, not duplicated.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Literal

# litellm schedules a fire-and-forget async success-logging coroutine; under the
# `asyncio.run` we drive `anthropic_messages` with, the loop closes before that
# coroutine is awaited, so the GC later emits a benign "coroutine
# '...async_success_handler' was never awaited" RuntimeWarning. We consume no litellm
# callbacks, so the dropped telemetry is harmless — suppress just that one warning.
# A persistent filter (not a context manager) is required because the warning fires
# at GC time, after any call-scoped `catch_warnings` block has exited.
warnings.filterwarnings(
    "ignore",
    message=r"coroutine '.*async_success_handler' was never awaited",
    category=RuntimeWarning,
)


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


def _block_get(b: Any, key: str, default: Any = None) -> Any:
    """Read a field from a block that may be a dict or an object."""
    return b.get(key, default) if isinstance(b, dict) else getattr(b, key, default)


def _normalize_content(raw: Any) -> list[TextBlock | ToolUseBlock]:
    out: list[TextBlock | ToolUseBlock] = []
    for b in raw or []:
        btype = _block_get(b, "type")
        if btype == "text":
            out.append(TextBlock(text=_block_get(b, "text", "") or ""))
        elif btype == "tool_use":
            out.append(
                ToolUseBlock(
                    id=_block_get(b, "id", "") or "",
                    name=_block_get(b, "name", "") or "",
                    input=dict(_block_get(b, "input", {}) or {}),
                )
            )
    return out


def _normalize_usage(raw: Any) -> Usage:
    if isinstance(raw, dict):
        return Usage(
            input_tokens=raw.get("input_tokens", 0) or 0,
            output_tokens=raw.get("output_tokens", 0) or 0,
            cache_read_input_tokens=raw.get("cache_read_input_tokens", 0) or 0,
            cache_creation_input_tokens=raw.get("cache_creation_input_tokens", 0) or 0,
        )
    return Usage(
        input_tokens=getattr(raw, "input_tokens", 0) or 0,
        output_tokens=getattr(raw, "output_tokens", 0) or 0,
        cache_read_input_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
    )


def _resp_get(resp: Any, key: str, default: Any = None) -> Any:
    """Read a field from a response that may be a dict or an object."""
    return (
        resp.get(key, default)
        if isinstance(resp, dict)
        else getattr(resp, key, default)
    )


def _litellm_anthropic_messages(
    *,
    model: str,
    max_tokens: int,
    system: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    api_key: str | None,
    num_retries: int | None,
) -> Any:
    """Single call-site for litellm.anthropic_messages; async-driven via asyncio.run."""
    import asyncio

    import litellm

    kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    if tools is not None:
        kwargs["tools"] = tools
    if api_key is not None:
        kwargs["api_key"] = api_key
    if num_retries is not None:
        kwargs["num_retries"] = num_retries
    return asyncio.run(litellm.anthropic_messages(**kwargs))


def _anthropic_messages(
    *,
    model_prefix: str,
    model: str,
    max_tokens: int,
    system: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    api_key: str | None = None,
    num_retries: int | None = None,
) -> Message:
    """Call LiteLLM's anthropic_messages endpoint and normalize the response to Message."""
    raw = _litellm_anthropic_messages(
        model=model_prefix + model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        tools=tools,
        api_key=api_key,
        num_retries=num_retries,
    )
    return Message(
        content=_normalize_content(_resp_get(raw, "content", []) or []),
        usage=_normalize_usage(_resp_get(raw, "usage", None)),
        stop_reason=_resp_get(raw, "stop_reason", None),
    )


class _ApiMessages:
    def __init__(self, api_key: str | None, num_retries: int | None) -> None:
        self._api_key = api_key
        self._num_retries = num_retries

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Message:
        import litellm

        try:
            return _anthropic_messages(
                model_prefix="anthropic/",
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=tools,
                api_key=self._api_key,
                num_retries=self._num_retries,
            )
        except litellm.RateLimitError as exc:
            raise BackendExhausted(str(exc)) from exc


class ApiBackend:
    """The paid backend: routes through LiteLLM's anthropic/ provider, normalized to Message."""

    def __init__(self, api_key: str | None, num_retries: int | None = None) -> None:
        self.messages = _ApiMessages(api_key, num_retries)


class _SubagentMessages:
    def __init__(self, runner: Any | None = None) -> None:
        import litellm

        from framework_cli.review.litellm_provider import ClaudeCliLLM

        handler = ClaudeCliLLM() if runner is None else ClaudeCliLLM(runner=runner)
        existing = [
            p
            for p in (litellm.custom_provider_map or [])
            if p.get("provider") != "claude-cli"
        ]
        litellm.custom_provider_map = [
            {"provider": "claude-cli", "custom_handler": handler},
            *existing,
        ]

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Message:
        from framework_cli.review.litellm_provider import ClaudeExhausted

        try:
            return _anthropic_messages(
                model_prefix="claude-cli/",
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )
        except BackendExhausted:
            raise
        except Exception as exc:  # litellm wraps the handler's ClaudeExhausted
            cause = exc.__cause__ or exc.__context__
            if isinstance(cause, ClaudeExhausted):
                raise BackendExhausted(str(cause), reset_hint=cause.reset_hint) from exc
            raise


class SubagentBackend:
    """The free backend: routes through LiteLLM's claude-cli/ provider, normalized to Message.

    Tools are always disabled so each call is a single model turn; the agentic loop in
    `run_agent_agentic` drives tool use via a text protocol."""

    def __init__(self, runner: Any | None = None) -> None:
        self.messages = _SubagentMessages(runner)
