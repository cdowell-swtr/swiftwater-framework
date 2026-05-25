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
    findings = run_agent("--- a/a.py\n+++ b/a.py\n", get_agent("security"), client)
    assert findings == [Finding("a.py", 2, "high", "bad")]


def test_run_agent_caches_the_diff_prefix():
    client = _FakeClient("[]")
    run_agent("THE DIFF", get_agent("security"), client)
    system = client.messages.last_kwargs["system"]
    assert "THE DIFF" in system[0]["text"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert any("security" in b["text"].lower() for b in system[1:])
