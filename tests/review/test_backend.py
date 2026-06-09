from framework_cli.review.backend import TextBlock, ToolUseBlock, Usage, Message


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
