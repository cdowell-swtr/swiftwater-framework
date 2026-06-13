"""Parity tests: both ApiBackend and SubagentBackend must produce identical findings.

The engine + normalisation are now SHARED (both route through _anthropic_messages),
so parity is proven by mocking _litellm_anthropic_messages and confirming:
  1. Both backends call through with the correct provider prefix.
  2. Both produce identical Finding lists.
"""

import framework_cli.review.backend as backend_mod
from framework_cli.review.agentic import run_agent_agentic
from framework_cli.review.backend import ApiBackend, SubagentBackend
from framework_cli.review.context import Bundle
from framework_cli.review.registry import get_agent
from framework_cli.review.runner import run_agent

_FINDINGS = '[{"path":"a.py","line":3,"severity":"high","message":"boom"}]'


def _make_fake_litellm(calls: list, result_text: str):
    """Return a fake _litellm_anthropic_messages that records model and returns result_text."""

    def fake(*, model, max_tokens, system, messages, tools, api_key, num_retries):
        calls.append(model)
        return {
            "content": [{"type": "text", "text": result_text}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }

    return fake


def test_bundle_findings_identical_across_backends(monkeypatch) -> None:
    """Both backends produce the same findings for a bundle (single-turn) agent."""
    bundle, spec = Bundle(diff="DIFF"), get_agent("security")

    api_calls: list = []
    monkeypatch.setattr(
        backend_mod,
        "_litellm_anthropic_messages",
        _make_fake_litellm(api_calls, _FINDINGS),
    )
    f_api = run_agent(bundle, spec, ApiBackend(api_key="x"))

    sub_calls: list = []
    monkeypatch.setattr(
        backend_mod,
        "_litellm_anthropic_messages",
        _make_fake_litellm(sub_calls, _FINDINGS),
    )
    f_sub = run_agent(bundle, spec, SubagentBackend())

    assert f_api == f_sub
    assert f_api[0].message == "boom" and f_api[0].severity == "high"

    # Verify provider prefix routing
    assert any(m.startswith("anthropic/") for m in api_calls)
    assert any(m.startswith("claude-cli/") for m in sub_calls)


def test_empty_findings_identical_across_backends(monkeypatch) -> None:
    bundle, spec = Bundle(diff="DIFF"), get_agent("security")

    monkeypatch.setattr(
        backend_mod, "_litellm_anthropic_messages", _make_fake_litellm([], "[]")
    )
    f_api = run_agent(bundle, spec, ApiBackend(api_key="x"))

    monkeypatch.setattr(
        backend_mod, "_litellm_anthropic_messages", _make_fake_litellm([], "[]")
    )
    f_sub = run_agent(bundle, spec, SubagentBackend())

    assert f_api == f_sub == []


_MULTI = (
    '[{"path":"a.py","line":1,"severity":"high","message":"one"},'
    '{"path":"b.py","line":2,"severity":"low","message":"two"}]'
)


def test_multi_findings_identical_across_backends(monkeypatch) -> None:
    bundle, spec = Bundle(diff="DIFF"), get_agent("security")

    monkeypatch.setattr(
        backend_mod, "_litellm_anthropic_messages", _make_fake_litellm([], _MULTI)
    )
    f_api = run_agent(bundle, spec, ApiBackend(api_key="x"))

    monkeypatch.setattr(
        backend_mod, "_litellm_anthropic_messages", _make_fake_litellm([], _MULTI)
    )
    f_sub = run_agent(bundle, spec, SubagentBackend())

    assert f_api == f_sub
    assert len(f_api) == 2 and f_api[1].message == "two"


def test_agentic_findings_identical_across_backends(monkeypatch, tmp_path) -> None:
    """Both backends produce the same findings for an agentic agent (tool use + findings)."""
    (tmp_path / "a.py").write_text("x = 1\n")
    spec = get_agent("architecture")  # agentic tier

    _TOOL_USE = {
        "content": [
            {
                "type": "tool_use",
                "id": "t1",
                "name": "read_file",
                "input": {"path": "a.py"},
            }
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "stop_reason": "tool_use",
    }
    _FINDINGS_RESP = {
        "content": [{"type": "text", "text": _FINDINGS}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "stop_reason": "end_turn",
    }

    def make_scripted(responses: list):
        """Return a fake that pops responses from the list."""
        remaining = list(responses)

        def fake(*, model, max_tokens, system, messages, tools, api_key, num_retries):
            return remaining.pop(0)

        return fake

    # API backend: tool_use then findings
    monkeypatch.setattr(
        backend_mod,
        "_litellm_anthropic_messages",
        make_scripted([_TOOL_USE, _FINDINGS_RESP]),
    )
    f_api = run_agent_agentic(
        "DIFF", tmp_path, spec, ApiBackend(api_key="x"), max_turns=12
    )

    # SubagentBackend: same script
    monkeypatch.setattr(
        backend_mod,
        "_litellm_anthropic_messages",
        make_scripted([_TOOL_USE, _FINDINGS_RESP]),
    )
    f_sub = run_agent_agentic("DIFF", tmp_path, spec, SubagentBackend(), max_turns=12)

    assert f_api == f_sub
    assert f_api[0].message == "boom"
