from framework_cli.review.context import Bundle
from framework_cli.review.findings import Finding
from framework_cli.review.registry import get_agent
from framework_cli.review.runner import run_agent


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Message:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, text):
        self._text = text
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _Message(self._text)


class _FakeClient:
    def __init__(self, text):
        self.messages = _FakeMessages(text)


def test_run_agent_parses_findings_from_client():
    client = _FakeClient(
        '[{"path": "a.py", "line": 2, "severity": "high", "message": "bad"}]'
    )
    findings = run_agent(
        Bundle(diff="--- a/a.py\n+++ b/a.py\n"), get_agent("security"), client
    )
    assert findings == [Finding("a.py", 2, "high", "bad")]


def test_run_agent_caches_the_diff_prefix():
    client = _FakeClient("[]")
    run_agent(Bundle(diff="THE DIFF"), get_agent("security"), client)
    system = client.messages.last_kwargs["system"]
    assert "THE DIFF" in system[0]["text"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert any("security" in b["text"].lower() for b in system[1:])


def test_diff_only_bundle_sends_two_blocks_diff_first():
    client = _FakeClient("[]")
    run_agent(Bundle(diff="THE DIFF"), get_agent("security"), client)
    system = client.messages.last_kwargs["system"]
    assert len(system) == 2  # diff + prompt; no context block
    assert system[0]["text"].startswith("Review this unified diff:")
    assert "THE DIFF" in system[0]["text"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert system[1]["text"] == get_agent("security").prompt


def test_bundle_with_context_inserts_cached_context_block():
    client = _FakeClient("[]")
    bundle = Bundle(diff="D", context_files=(("src/demo/x.py", "CONTENT"),))
    run_agent(bundle, get_agent("security"), client)
    system = client.messages.last_kwargs["system"]
    assert len(system) == 3  # diff + context + prompt
    assert "src/demo/x.py" in system[1]["text"]
    assert "CONTENT" in system[1]["text"]
    assert system[1]["cache_control"] == {"type": "ephemeral"}
    assert system[2]["text"] == get_agent("security").prompt


def test_truncation_note_added_when_truncated():
    client = _FakeClient("[]")
    bundle = Bundle(diff="D", context_files=(("a.py", "x"),), truncated=True)
    run_agent(bundle, get_agent("security"), client)
    assert "truncated" in client.messages.last_kwargs["system"][1]["text"].lower()
