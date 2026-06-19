from framework_cli.review.context import Bundle
from framework_cli.review.decisions import Decision
from framework_cli.review.findings import Finding
from framework_cli.review.registry import composed_prompt, get_agent
from framework_cli.review.runner import _max_retries, run_agent


def test_max_retries_elevated_default(monkeypatch):
    """The retry budget defaults above the SDK's 2 so a transient per-minute 429 is
    absorbed via backoff instead of hard-aborting eval / the `framework review` path."""
    monkeypatch.delenv("ANTHROPIC_MAX_RETRIES", raising=False)
    assert _max_retries() >= 6


def test_max_retries_env_override(monkeypatch):
    """ANTHROPIC_MAX_RETRIES tunes the retry budget per environment."""
    monkeypatch.setenv("ANTHROPIC_MAX_RETRIES", "3")
    assert _max_retries() == 3


def test_max_retries_invalid_falls_back_to_default(monkeypatch):
    """A non-integer ANTHROPIC_MAX_RETRIES is ignored (use the default) rather
    than crashing or being treated as 'unset' silently."""
    from framework_cli.review.runner import DEFAULT_MAX_RETRIES

    monkeypatch.setenv("ANTHROPIC_MAX_RETRIES", "eight")
    assert _max_retries() == DEFAULT_MAX_RETRIES


def test_max_retries_nonpositive_falls_back_to_default(monkeypatch):
    """0/negative would disable retries, defeating the backoff purpose — fall back
    to the default rather than honouring it."""
    from framework_cli.review.runner import DEFAULT_MAX_RETRIES

    monkeypatch.setenv("ANTHROPIC_MAX_RETRIES", "0")
    assert _max_retries() == DEFAULT_MAX_RETRIES


def test_max_retries_excessive_clamped_to_cap(monkeypatch):
    """An absurd value is clamped to MAX_RETRIES_CAP rather than backing off for
    hours and masking a sustained outage."""
    from framework_cli.review.runner import MAX_RETRIES_CAP

    monkeypatch.setenv("ANTHROPIC_MAX_RETRIES", "10000")
    assert _max_retries() == MAX_RETRIES_CAP


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
    assert system[1]["text"] == composed_prompt(get_agent("security"))


def test_bundle_with_context_inserts_cached_context_block():
    client = _FakeClient("[]")
    bundle = Bundle(diff="D", context_files=(("src/demo/x.py", "CONTENT"),))
    run_agent(bundle, get_agent("security"), client)
    system = client.messages.last_kwargs["system"]
    assert len(system) == 3  # diff + context + prompt
    assert "src/demo/x.py" in system[1]["text"]
    assert "CONTENT" in system[1]["text"]
    assert system[1]["cache_control"] == {"type": "ephemeral"}
    assert system[2]["text"] == composed_prompt(get_agent("security"))


def test_truncation_note_added_when_truncated():
    client = _FakeClient("[]")
    bundle = Bundle(diff="D", context_files=(("a.py", "x"),), truncated=True)
    run_agent(bundle, get_agent("security"), client)
    assert "truncated" in client.messages.last_kwargs["system"][1]["text"].lower()


def _make_decision() -> Decision:
    return Decision(
        id="DEC-1",
        status="accepted",
        agents=("security",),
        concern="c",
        premise="p",
        body="b",
        source="DEC-1.md",
    )


def test_run_agent_decisions_block_inserted_before_prompt():
    """A non-empty Bundle.decisions injects a decisions block immediately before the prompt."""
    client = _FakeClient("[]")
    bundle = Bundle(diff="d", decisions=(_make_decision(),))
    run_agent(bundle, get_agent("security"), client)
    system = client.messages.last_kwargs["system"]
    # diff block + decisions block + prompt block = 3
    assert len(system) == 3
    decisions_block = system[1]
    assert "DEC-1" in decisions_block["text"]
    assert "acknowledged:" in decisions_block["text"]
    assert decisions_block["cache_control"] == {"type": "ephemeral"}
    # Prompt must remain the last block
    assert system[2]["text"] == composed_prompt(get_agent("security"))


def test_run_agent_no_decisions_block_when_empty():
    """An empty Bundle.decisions leaves the system blocks byte-identical to the no-decisions path."""
    client = _FakeClient("[]")
    bundle = Bundle(diff="THE DIFF")
    run_agent(bundle, get_agent("security"), client)
    system = client.messages.last_kwargs["system"]
    # Must be exactly diff + prompt — no extra block
    assert len(system) == 2
    assert system[0]["text"].startswith("Review this unified diff:")
    assert system[1]["text"] == composed_prompt(get_agent("security"))
