"""Agent error hierarchy — independent of the framework's internal review backend."""

from __future__ import annotations


class AgentError(Exception):
    """Any failure invoking the LLM provider through the agent runtime."""


class AgentExhausted(AgentError):
    """The provider rejected the call for rate-limit / quota reasons (retry later)."""
