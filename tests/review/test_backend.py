import json as _json

import pytest

from framework_cli.review.backend import (
    ApiBackend,
    BackendExhausted,
    Message,
    SubagentBackend,
    TextBlock,
    ToolUseBlock,
    Usage,
)


class _SDKBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _SDKMessage:
    def __init__(self):
        self.content = [_SDKBlock("[]")]
        self.usage = type(
            "U",
            (),
            {
                "input_tokens": 1,
                "output_tokens": 2,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        )()
        self.stop_reason = "end_turn"


class _SDKMessages:
    def __init__(self):
        self.last = None

    def create(self, **kwargs):
        self.last = kwargs
        return _SDKMessage()


class _SDKClient:
    def __init__(self):
        self.messages = _SDKMessages()


def test_api_backend_passes_through_sdk_and_normalizes_usage():
    sdk = _SDKClient()
    backend = ApiBackend(sdk)
    msg = backend.messages.create(model="m", max_tokens=10, system=[], messages=[])
    assert msg.content[0].text == "[]"
    assert msg.usage.input_tokens == 1
    assert msg.stop_reason == "end_turn"
    assert sdk.messages.last["model"] == "m"


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


def _fake_runner(captured):
    def run(argv, *, input_text):
        captured["argv"] = argv
        return _json.dumps(
            {
                "subtype": "success",
                "is_error": False,
                "num_turns": 1,
                "stop_reason": "end_turn",
                "result": '```json\n[{"path":"a.py","line":1,"severity":"high","message":"x"}]\n```',
                "usage": {"input_tokens": 7, "output_tokens": 11},
            }
        )

    return run


def test_subagent_backend_bundle_single_turn():
    captured = {}
    backend = SubagentBackend(runner=_fake_runner(captured))
    msg = backend.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=[{"type": "text", "text": "SYS-A"}, {"type": "text", "text": "SYS-B"}],
        messages=[
            {"role": "user", "content": "Return your findings as a JSON array only."}
        ],
        tools=None,
    )
    argv = captured["argv"]
    assert "--system-prompt" in argv
    sysidx = argv.index("--system-prompt") + 1
    assert "SYS-A" in argv[sysidx] and "SYS-B" in argv[sysidx]
    assert "--exclude-dynamic-system-prompt-sections" in argv
    assert "-p" in argv or "--print" in argv
    assert "--output-format" in argv and "json" in argv
    assert "--model" in argv and "claude-haiku-4-5-20251001" in argv
    assert "--disallowed-tools" in argv
    assert len(msg.content) == 1 and msg.content[0].type == "text"
    assert '"path":"a.py"' in msg.content[0].text
    assert msg.usage.output_tokens == 11
    assert msg.stop_reason == "end_turn"


def test_subagent_is_error_with_exhaustion_marker_raises_exhausted():
    def runner(argv, *, input_text):
        return _json.dumps(
            {"is_error": True, "result": "Claude usage limit reached. Try later."}
        )

    backend = SubagentBackend(runner=runner)
    with pytest.raises(BackendExhausted):
        backend.messages.create(
            model="m",
            max_tokens=10,
            system=[{"type": "text", "text": "S"}],
            messages=[{"role": "user", "content": "go"}],
            tools=None,
        )


def test_subagent_is_error_without_marker_raises_runtime():
    def runner(argv, *, input_text):
        return _json.dumps({"is_error": True, "result": "some other failure"})

    backend = SubagentBackend(runner=runner)
    with pytest.raises(RuntimeError):
        backend.messages.create(
            model="m",
            max_tokens=10,
            system=[{"type": "text", "text": "S"}],
            messages=[{"role": "user", "content": "go"}],
            tools=None,
        )


def test_subagent_non_json_output_raises_runtime():
    def runner(argv, *, input_text):
        return "this is not json"

    backend = SubagentBackend(runner=runner)
    with pytest.raises(RuntimeError):
        backend.messages.create(
            model="m",
            max_tokens=10,
            system=[{"type": "text", "text": "S"}],
            messages=[{"role": "user", "content": "go"}],
            tools=None,
        )


def test_subagent_agentic_tool_turn_decodes_to_tool_use():
    captured = {}

    def runner(argv, *, input_text):
        captured["argv"] = argv
        return _json.dumps(
            {
                "is_error": False,
                "stop_reason": "end_turn",
                "result": '{"tool_calls":[{"name":"read_file","input":{"path":"a.py"}}]}',
                "usage": {"input_tokens": 4, "output_tokens": 6},
            }
        )

    backend = SubagentBackend(runner=runner)
    msg = backend.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        system=[{"type": "text", "text": "SYS"}],
        messages=[{"role": "user", "content": "Review the diff."}],
        tools=[{"name": "read_file"}],
    )
    assert len(msg.content) == 1 and msg.content[0].type == "tool_use"
    assert msg.content[0].name == "read_file"
    assert msg.content[0].input == {"path": "a.py"}
    pidx = captured["argv"].index("-p") + 1
    assert "tool_calls" in captured["argv"][pidx]


def test_subagent_agentic_final_array_is_text():
    def runner(argv, *, input_text):
        return _json.dumps(
            {
                "is_error": False,
                "stop_reason": "end_turn",
                "result": '[{"path":"a.py","line":2,"severity":"low","message":"m"}]',
                "usage": {},
            }
        )

    backend = SubagentBackend(runner=runner)
    msg = backend.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        system=[{"type": "text", "text": "SYS"}],
        messages=[{"role": "user", "content": "Review the diff."}],
        tools=[{"name": "read_file"}],
    )
    assert len(msg.content) == 1 and msg.content[0].type == "text"
    assert '"severity":"low"' in msg.content[0].text


def test_subagent_agentic_tool_turn_with_prose_decodes():
    def runner(argv, *, input_text):
        return _json.dumps(
            {
                "is_error": False,
                "stop_reason": "end_turn",
                "result": 'Let me read that file:\n{"tool_calls":[{"name":"read_file","input":{"path":"a.py"}}]}',
                "usage": {},
            }
        )

    backend = SubagentBackend(runner=runner)
    msg = backend.messages.create(
        model="m",
        max_tokens=10,
        system=[{"type": "text", "text": "S"}],
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "read_file"}],
    )
    assert len(msg.content) == 1 and msg.content[0].type == "tool_use"
    assert msg.content[0].name == "read_file"


def test_subagent_agentic_fenced_tool_turn_decodes():
    def runner(argv, *, input_text):
        return _json.dumps(
            {
                "is_error": False,
                "stop_reason": "end_turn",
                "result": '```json\n{"tool_calls":[{"name":"grep","input":{"pattern":"x"}}]}\n```',
                "usage": {},
            }
        )

    backend = SubagentBackend(runner=runner)
    msg = backend.messages.create(
        model="m",
        max_tokens=10,
        system=[{"type": "text", "text": "S"}],
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "grep"}],
    )
    assert len(msg.content) == 1 and msg.content[0].type == "tool_use"
    assert msg.content[0].name == "grep"


def test_subagent_agentic_findings_array_with_prose_is_text():
    # A findings array (even prose-wrapped) must NOT be misread as tools.
    def runner(argv, *, input_text):
        return _json.dumps(
            {
                "is_error": False,
                "stop_reason": "end_turn",
                "result": 'Here are my findings: [{"path":"a.py","line":1,"severity":"low","message":"m"}]',
                "usage": {},
            }
        )

    backend = SubagentBackend(runner=runner)
    msg = backend.messages.create(
        model="m",
        max_tokens=10,
        system=[{"type": "text", "text": "S"}],
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "read_file"}],
    )
    assert len(msg.content) == 1 and msg.content[0].type == "text"
