import json as _json

import pytest

import framework_cli.review.backend as backend_mod
from framework_cli.review.backend import (
    ApiBackend,
    BackendExhausted,
    Message,
    SubagentBackend,
    TextBlock,
    ToolUseBlock,
    Usage,
    _anthropic_messages,
    _normalize_content,
)


def test_message_exposes_sdk_shape():
    msg = Message(
        content=[TextBlock(text="hello")],
        usage=Usage(input_tokens=3, output_tokens=5),
        stop_reason="end_turn",
    )
    assert msg.content[0].type == "text"
    assert msg.content[0].text == "hello"
    assert msg.usage.input_tokens == 3
    assert msg.stop_reason == "end_turn"


def test_tool_use_block_shape():
    b = ToolUseBlock(id="t1", name="read_file", input={"path": "a.py"})
    assert b.type == "tool_use"
    assert b.id == "t1"
    assert b.name == "read_file"
    assert b.input == {"path": "a.py"}


# ---- LiteLLM helper tests ----


def test_anthropic_messages_normalizes_and_prefixes(monkeypatch):
    """_anthropic_messages prefixes the model, calls _litellm_anthropic_messages,
    and normalizes the dict-shaped response into a Message."""
    captured: dict = {}

    def fake_litellm(
        *, model, max_tokens, system, messages, tools, api_key, num_retries
    ):
        captured["model"] = model
        captured["api_key"] = api_key
        captured["num_retries"] = num_retries
        return {
            "id": "msg_01",
            "type": "message",
            "role": "assistant",
            "model": model,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 2,
                "output_tokens": 7,
                "cache_read_input_tokens": 9,
                "total_tokens": 18,
            },
            "content": [{"type": "text", "text": "[]"}],
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(backend_mod, "_litellm_anthropic_messages", fake_litellm)

    msg = _anthropic_messages(
        model_prefix="anthropic/",
        model="claude-sonnet-4-6",
        max_tokens=10,
        system=[{"type": "text", "text": "S"}],
        messages=[{"role": "user", "content": "go"}],
        tools=None,
        api_key="k",
        num_retries=8,
    )

    assert captured["model"] == "anthropic/claude-sonnet-4-6"
    assert captured["api_key"] == "k"
    assert captured["num_retries"] == 8
    assert len(msg.content) == 1
    assert msg.content[0].type == "text"
    assert msg.content[0].text == "[]"
    assert msg.usage.cache_read_input_tokens == 9
    assert msg.stop_reason == "end_turn"


def test_normalize_content_handles_dict_tool_use():
    """_normalize_content accepts dict-shaped tool_use blocks (LiteLLM response shape)."""
    blocks = _normalize_content(
        [
            {
                "type": "tool_use",
                "id": "t1",
                "name": "read_file",
                "input": {"path": "a.py"},
            }
        ]
    )
    assert len(blocks) == 1
    b = blocks[0]
    assert isinstance(b, ToolUseBlock)
    assert b.id == "t1"
    assert b.name == "read_file"
    assert b.input == {"path": "a.py"}


# ---- ApiBackend tests ----


def test_api_backend_calls_litellm_anthropic(monkeypatch):
    """ApiBackend.messages.create routes to _anthropic_messages with anthropic/ prefix."""
    captured: dict = {}

    def fake_litellm(
        *, model, max_tokens, system, messages, tools, api_key, num_retries
    ):
        captured["model"] = model
        captured["api_key"] = api_key
        captured["num_retries"] = num_retries
        return {
            "content": [{"type": "text", "text": "[]"}],
            "usage": {"input_tokens": 1, "output_tokens": 2},
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(backend_mod, "_litellm_anthropic_messages", fake_litellm)

    b = ApiBackend(api_key="mykey", num_retries=3)
    msg = b.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=10,
        system=[{"type": "text", "text": "S"}],
        messages=[{"role": "user", "content": "go"}],
    )
    assert captured["model"] == "anthropic/claude-sonnet-4-6"
    assert captured["api_key"] == "mykey"
    assert captured["num_retries"] == 3
    assert msg.content[0].text == "[]"
    assert msg.stop_reason == "end_turn"


def test_api_backend_maps_rate_limit_to_exhausted(monkeypatch):
    """ApiBackend.messages.create wraps litellm.RateLimitError as BackendExhausted."""
    import litellm

    def boom(**kwargs):
        raise litellm.RateLimitError(
            "429", llm_provider="anthropic", model="claude-sonnet-4-6"
        )

    monkeypatch.setattr(backend_mod, "_litellm_anthropic_messages", boom)

    with pytest.raises(BackendExhausted):
        ApiBackend(api_key="k").messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1,
            system=[],
            messages=[],
        )


# ---- SubagentBackend tests ----


def _exhaustion_runner(argv, *, input_text):
    """Fake runner returning a claude -p 429/session-limit payload."""
    return _json.dumps(
        {
            "is_error": True,
            "api_error_status": 429,
            "result": "You've hit your session limit · resets 11:30am (PT)",
        }
    )


def test_subagent_maps_wrapped_exhaustion_to_backend_exhausted():
    """SubagentBackend raises BackendExhausted (with reset_hint) when the claude -p
    runner returns a session-limit error.  The cause chain is:
    ClaudeExhausted (handler) → litellm.APIConnectionError (wrapper) → BackendExhausted."""
    backend = SubagentBackend(runner=_exhaustion_runner)
    with pytest.raises(BackendExhausted) as ei:
        backend.messages.create(
            model="m",
            max_tokens=10,
            system=[{"type": "text", "text": "S"}],
            messages=[{"role": "user", "content": "go"}],
        )
    assert ei.value.reset_hint is not None and "11:30" in ei.value.reset_hint


def test_subagent_backend_routes_via_claude_cli_prefix(monkeypatch):
    """SubagentBackend.messages.create routes to _anthropic_messages with claude-cli/ prefix."""
    captured: dict = {}

    def fake_litellm(
        *, model, max_tokens, system, messages, tools, api_key, num_retries
    ):
        captured["model"] = model
        return {
            "content": [{"type": "text", "text": "[]"}],
            "usage": {"input_tokens": 1, "output_tokens": 2},
            "stop_reason": "end_turn",
        }

    monkeypatch.setattr(backend_mod, "_litellm_anthropic_messages", fake_litellm)

    # runner is never called when _litellm_anthropic_messages is mocked
    backend = SubagentBackend(runner=None)
    backend.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        system=[{"type": "text", "text": "S"}],
        messages=[{"role": "user", "content": "go"}],
    )
    assert captured["model"].startswith("claude-cli/"), captured["model"]
    assert "claude-haiku-4-5-20251001" in captured["model"]
