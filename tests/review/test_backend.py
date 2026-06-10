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
    _join_system,
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
        captured["input_text"] = input_text
        # Capture system file content while the temp file is still present
        try:
            idx = argv.index("--system-prompt-file")
            with open(argv[idx + 1]) as fh:
                captured["sys_file_content"] = fh.read()
        except (ValueError, IndexError, OSError):
            captured["sys_file_content"] = None
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
    # System content goes via --system-prompt-file (not inline --system-prompt)
    assert "--system-prompt-file" in argv
    assert "--system-prompt" not in argv
    sys_content = captured["sys_file_content"]
    assert sys_content is not None and "SYS-A" in sys_content and "SYS-B" in sys_content
    assert "--exclude-dynamic-system-prompt-sections" in argv
    assert "-p" in argv or "--print" in argv
    assert "--output-format" in argv and "json" in argv
    assert "--model" in argv and "claude-haiku-4-5-20251001" in argv
    assert "--disallowed-tools" in argv
    # Prompt passed via stdin, not as argv positional
    assert captured["input_text"] == "Return your findings as a JSON array only."
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


def test_subagent_session_limit_429_raises_exhausted_with_reset_hint():
    # The real `claude -p` 429 payload that crashed the Plan 21 baseline sweep:
    # "session limit" was NOT in _EXHAUSTION_MARKERS, so it raised RuntimeError
    # instead of BackendExhausted. Regression guard + reset-hint extraction.
    def runner(argv, *, input_text):
        return _json.dumps(
            {
                "is_error": True,
                "api_error_status": 429,
                "result": "You've hit your session limit · resets 11:30am (America/Los_Angeles)",
            }
        )

    backend = SubagentBackend(runner=runner)
    with pytest.raises(BackendExhausted) as ei:
        backend.messages.create(
            model="m",
            max_tokens=10,
            system=[{"type": "text", "text": "S"}],
            messages=[{"role": "user", "content": "go"}],
            tools=None,
        )
    assert ei.value.reset_hint and "11:30" in ei.value.reset_hint


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
    captured: dict = {}

    def runner(argv, *, input_text):
        captured["argv"] = argv
        captured["input_text"] = input_text
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
    # Prompt is passed via stdin; the transcript (which includes available tools) arrives
    # as input_text, not as an argv positional after -p
    assert captured["input_text"] is not None
    assert "--system-prompt-file" in captured["argv"]
    assert "--system-prompt" not in captured["argv"]


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


# ---- MAX_ARG_STRLEN guard: system content must go via --system-prompt-file ----

_MAX_ARG_STRLEN = 131072  # Linux per-argument limit (~128 KB)


def test_subagent_large_system_goes_via_file_not_argv():
    """When system content exceeds MAX_ARG_STRLEN, it must NOT appear as an argv element.
    Instead --system-prompt-file <path> must be used and the rendered prompt passed via
    stdin (input_text), not as a positional argv element after -p."""
    captured: dict = {}

    def capturing_runner(argv: list, *, input_text: str | None) -> str:
        captured["argv"] = list(argv)
        captured["input_text"] = input_text
        # Read the temp file content before it is cleaned up (still open during the call)
        sys_file_path: str | None = None
        try:
            idx = argv.index("--system-prompt-file")
            sys_file_path = argv[idx + 1]
        except (ValueError, IndexError):
            pass
        if sys_file_path is not None:
            try:
                with open(sys_file_path) as fh:
                    captured["sys_file_content"] = fh.read()
            except OSError:
                captured["sys_file_content"] = None
        return _json.dumps(
            {
                "is_error": False,
                "stop_reason": "end_turn",
                "result": "[]",
                "usage": {},
            }
        )

    large_sys = "x" * 200_000  # well over MAX_ARG_STRLEN (128 KB)
    system = [{"type": "text", "text": large_sys}]
    user_prompt = "Review the diff."

    backend = SubagentBackend(runner=capturing_runner)
    backend.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        tools=None,
    )

    argv = captured["argv"]

    # (a) No single argv element exceeds MAX_ARG_STRLEN
    for elem in argv:
        assert len(elem) <= _MAX_ARG_STRLEN, (
            f"argv element of length {len(elem)} exceeds MAX_ARG_STRLEN: {elem[:60]!r}..."
        )

    # (b) --system-prompt-file is present; its file content equals _join_system(system)
    assert "--system-prompt-file" in argv, "expected --system-prompt-file in argv"
    assert "--system-prompt" not in argv, "--system-prompt (inline) must NOT be in argv"
    assert captured.get("sys_file_content") == _join_system(system), (
        "temp file content must equal _join_system(system)"
    )

    # (c) Rendered prompt was passed via stdin (input_text), not as an argv positional
    assert captured["input_text"] == user_prompt, (
        "prompt must be passed via stdin (input_text), not as argv positional"
    )

    # (d) The large system string is not present anywhere in argv
    assert large_sys not in argv, "large system content must NOT appear as argv element"

    # (e) Essential flags still present
    assert "--exclude-dynamic-system-prompt-sections" in argv
    assert "--output-format" in argv
    assert "json" in argv
    assert "--model" in argv
    assert "claude-haiku-4-5-20251001" in argv
    assert "--disallowed-tools" in argv
