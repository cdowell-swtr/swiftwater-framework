"""LLM error hierarchy — independent of the framework's internal review backend."""

from __future__ import annotations


class LLMError(Exception):
    """Any failure invoking the LLM provider through the LLM runtime."""


class LLMExhausted(LLMError):
    """The provider rejected the call for rate-limit / quota reasons (retry later)."""
