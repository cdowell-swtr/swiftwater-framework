"""LiteLLM interface spike for Plan 27 (FWK5), Task 1.

Resolves the two facts the docs do not:

- **S2 (routing) — the architecture gate.** Does ``litellm.anthropic_messages``
  dispatch a ``custom_provider_map`` model (``claude-cli/<model>``) to our custom
  handler, with ``cache_control`` preserved? Proven GO on litellm 1.88.1; kept as a
  permanent regression guard so a future litellm bump can't silently break routing.
- **S1 (caching) — a cost-lever confirmation, NOT a gate.** Does the ``anthropic/``
  provider via ``anthropic_messages`` actually return ``cache_read_input_tokens > 0``
  on a repeat call? Needs a live key; gated behind ``RUN_LITELLM_SPIKE=1``.

``anthropic_messages`` is async-native (returns a coroutine); ``_run`` drives it
via ``asyncio.run`` — the same shim the seam helper uses.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import litellm
import pytest
from litellm import CustomLLM, ModelResponse


def _run(awaitable_or_value: Any) -> Any:
    if asyncio.iscoroutine(awaitable_or_value):
        return asyncio.run(awaitable_or_value)
    return awaitable_or_value


def test_s2_anthropic_messages_routes_to_custom_provider() -> None:
    """anthropic_messages(model="claude-cli/...") must reach the custom handler, with
    the provider prefix stripped and cache_control preserved into the handler input."""
    seen: dict[str, Any] = {"hit": False, "model": None, "messages": None}

    class _Probe(CustomLLM):
        async def acompletion(self, *args: Any, **kwargs: Any) -> ModelResponse:  # noqa: D102
            seen["hit"] = True
            seen["model"] = kwargs.get("model") or (args[0] if args else None)
            seen["messages"] = kwargs.get("messages") or (
                args[1] if len(args) > 1 else None
            )
            mr = kwargs.get("model_response")
            if mr is not None:
                mr.choices[0].message.content = "[]"
                return mr
            return ModelResponse(
                choices=[{"message": {"role": "assistant", "content": "[]"}}]
            )

        def completion(self, *args: Any, **kwargs: Any) -> ModelResponse:  # noqa: D102
            return asyncio.run(self.acompletion(*args, **kwargs))

    saved = litellm.custom_provider_map
    litellm.custom_provider_map = [{"provider": "claude-cli", "custom_handler": _Probe()}]
    try:
        _run(
            litellm.anthropic_messages(
                model="claude-cli/claude-haiku-4-5-20251001",
                max_tokens=16,
                system=[
                    {
                        "type": "text",
                        "text": "probe-sys",
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": "go"}],
            )
        )
    finally:
        litellm.custom_provider_map = saved

    assert seen["hit"], "anthropic_messages did not route to the custom provider"
    # litellm strips the provider prefix before calling the handler.
    assert seen["model"] == "claude-haiku-4-5-20251001"
    # The system block (with cache_control) is folded into messages as a system role.
    sys_msg = next(m for m in seen["messages"] if m.get("role") == "system")
    blocks = sys_msg["content"]
    assert isinstance(blocks, list)
    assert blocks[0].get("cache_control") == {"type": "ephemeral"}


@pytest.mark.skipif(
    os.environ.get("RUN_LITELLM_SPIKE") != "1"
    or not os.environ.get("ANTHROPIC_EVAL_API_KEY"),
    reason="live S1: set RUN_LITELLM_SPIKE=1 with ANTHROPIC_EVAL_API_KEY",
)
def test_s1_api_path_caching_passthrough() -> None:
    """anthropic provider via anthropic_messages: cache_control honored, cache_read>0
    on a repeated call. Confirms the cost lever survives (not an architecture gate)."""
    key = os.environ["ANTHROPIC_EVAL_API_KEY"]
    big = "You are a strict code reviewer. " + ("context line. " * 2000)
    system = [{"type": "text", "text": big, "cache_control": {"type": "ephemeral"}}]

    def call() -> Any:
        return _run(
            litellm.anthropic_messages(
                model="anthropic/claude-haiku-4-5-20251001",
                max_tokens=32,
                system=system,
                messages=[{"role": "user", "content": "Reply with exactly: []"}],
                api_key=key,
            )
        )

    call()  # primes the cache
    second = call()
    usage = second["usage"] if isinstance(second, dict) else second.usage
    cache_read = (
        usage.get("cache_read_input_tokens")
        if isinstance(usage, dict)
        else getattr(usage, "cache_read_input_tokens", 0)
    )
    assert cache_read and cache_read > 0, f"no cache hit on repeat: {usage!r}"
