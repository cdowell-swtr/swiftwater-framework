from framework_cli.review.engine import run_engine, EngineItem
from framework_cli.review.backend import BackendExhausted, Message, TextBlock
from framework_cli.review.registry import ContextPolicy


class _Spec:
    def __init__(self, name, strategy="diff"):
        self.name = name
        self.model = "m"
        self.context = ContextPolicy(strategy)
        self.prompt = "P"


def _backend_returning(findings_json):
    class _Msgs:
        def create(self, **kw):
            return Message(
                content=[TextBlock(text=findings_json)], stop_reason="end_turn"
            )

    return type("B", (), {"messages": _Msgs()})()


def test_engine_writes_record_per_item(tmp_path):
    items = [
        EngineItem(agent="security", diff="D", spec=_Spec("review-security")),
        EngineItem(agent="documentation", diff="D", spec=_Spec("review-documentation")),
    ]
    run = tmp_path / "run"
    result = run_engine(
        items,
        backend=_backend_returning("[]"),
        run_dir=run,
        root=tmp_path,
        git_sha="s",
        dirty_hash="h",
        backend_name="api",
    )
    assert result.completed == ["security", "documentation"]
    assert result.exhausted is False
    assert (run / "findings" / "security.json").is_file()


def test_engine_checkpoints_then_stops_on_exhaustion(tmp_path):
    calls = {"n": 0}

    class _Msgs:
        def create(self, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return Message(content=[TextBlock(text="[]")], stop_reason="end_turn")
            raise BackendExhausted("limit", reset_hint="3pm")

    backend = type("B", (), {"messages": _Msgs()})()
    items = [
        EngineItem(agent="security", diff="D", spec=_Spec("review-security")),
        EngineItem(agent="architecture", diff="D", spec=_Spec("review-architecture")),
    ]
    run = tmp_path / "run"
    result = run_engine(
        items,
        backend=backend,
        run_dir=run,
        root=tmp_path,
        git_sha="s",
        dirty_hash="h",
        backend_name="subagent",
    )
    assert result.exhausted is True and result.reset_hint == "3pm"
    assert result.completed == ["security"]
    assert "architecture" not in result.completed


def test_engine_records_item_failure_and_continues(tmp_path):
    # First item's backend raises a non-exhaustion error; the run must record a failure
    # for it AND continue to the second item (not crash the whole run).
    calls = {"n": 0}

    class _Msgs:
        def create(self, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("claude -p failed")
            return Message(content=[TextBlock(text="[]")], stop_reason="end_turn")

    backend = type("B", (), {"messages": _Msgs()})()
    items = [
        EngineItem(agent="security", diff="D", spec=_Spec("review-security")),
        EngineItem(agent="documentation", diff="D", spec=_Spec("review-documentation")),
    ]
    run = tmp_path / "run"
    result = run_engine(
        items,
        backend=backend,
        run_dir=run,
        root=tmp_path,
        git_sha="s",
        dirty_hash="h",
        backend_name="subagent",
    )
    assert result.exhausted is False
    assert result.failed == ["security"]
    assert result.completed == ["documentation"]
    # Both records are checkpointed; the failure record carries the error marker.
    assert (run / "findings" / "security.json").is_file()
    assert (run / "findings" / "documentation.json").is_file()
    import json

    sec = json.loads((run / "findings" / "security.json").read_text())
    assert sec["findings"] == [] and "error" in sec
