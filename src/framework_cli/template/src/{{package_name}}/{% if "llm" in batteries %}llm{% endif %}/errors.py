"""LLM error hierarchy — independent of the framework's internal review backend."""

from __future__ import annotations


class LLMError(Exception):
    """Any failure invoking the LLM provider through the LLM runtime."""


class LLMExhausted(LLMError):
    """The provider rejected the call for rate-limit / quota reasons (retry later).

    `reset_hint` is an optional human string (e.g. "resets 11:30am") surfaced by
    providers that know when capacity returns — e.g. the claude-cli subscription
    backend's ClaudeExhausted. Any cause-chain exception exposing a `reset_hint`
    attribute is treated as exhaustion by the service (duck-typed, no plugin import).
    """

    def __init__(self, message: str, *, reset_hint: str | None = None) -> None:
        super().__init__(message)
        self.reset_hint = reset_hint
