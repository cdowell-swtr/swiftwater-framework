from framework_cli.review.backend import (
    TextBlock,
    ToolUseBlock,
    Usage,
    Message,
    ApiBackend,
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
