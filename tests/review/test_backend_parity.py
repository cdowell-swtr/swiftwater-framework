import json

from framework_cli.review.agentic import run_agent_agentic
from framework_cli.review.backend import ApiBackend, SubagentBackend
from framework_cli.review.context import Bundle
from framework_cli.review.registry import get_agent
from framework_cli.review.runner import run_agent

_FINDINGS = '[{"path":"a.py","line":3,"severity":"high","message":"boom"}]'


class _SDKBlock:
    def __init__(self, t: str) -> None:
        self.type = "text"
        self.text = t


class _SDKMsg:
    def __init__(self, t: str) -> None:
        self.content = [_SDKBlock(t)]
        self.usage = None
        self.stop_reason = "end_turn"


class _SDKMsgs:
    def __init__(self, t: str) -> None:
        self._t = t
        self.last = None

    def create(self, **kw):  # type: ignore[no-untyped-def]
        self.last = kw
        return _SDKMsg(self._t)


class _SDK:
    def __init__(self, t: str) -> None:
        self.messages = _SDKMsgs(t)


def _sub_runner(result_text: str):  # type: ignore[no-untyped-def]
    def run(argv, *, input_text):  # type: ignore[no-untyped-def]
        return json.dumps(
            {
                "is_error": False,
                "stop_reason": "end_turn",
                "result": result_text,
                "usage": {},
            }
        )

    return run


def test_bundle_findings_identical_across_backends() -> None:
    bundle, spec = Bundle(diff="DIFF"), get_agent("security")
    f_api = run_agent(bundle, spec, ApiBackend(_SDK(_FINDINGS)))
    f_sub = run_agent(bundle, spec, SubagentBackend(runner=_sub_runner(_FINDINGS)))
    assert f_api == f_sub
    assert f_api[0].message == "boom" and f_api[0].severity == "high"


class _SDKToolUse:
    def __init__(self, i: str, n: str, inp: dict) -> None:
        self.type = "tool_use"
        self.id = i
        self.name = n
        self.input = inp


class _SDKResp:
    def __init__(self, blocks: list) -> None:
        self.content = blocks
        self.usage = None
        self.stop_reason = "end_turn"


class _ScriptedSDK:
    def __init__(self, responses: list) -> None:
        self._r = list(responses)
        self.messages = self

    def create(self, **kw):  # type: ignore[no-untyped-def]
        return self._r.pop(0)


def test_agentic_findings_identical_across_backends(tmp_path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    spec = get_agent("architecture")  # agentic tier
    api = ApiBackend(
        _ScriptedSDK(
            [
                _SDKResp([_SDKToolUse("t1", "read_file", {"path": "a.py"})]),
                _SDKResp([_SDKBlock(_FINDINGS)]),
            ]
        )
    )
    sub_results = iter(
        ['{"tool_calls":[{"name":"read_file","input":{"path":"a.py"}}]}', _FINDINGS]
    )

    def sub_runner(argv, *, input_text):  # type: ignore[no-untyped-def]
        return json.dumps(
            {
                "is_error": False,
                "stop_reason": "end_turn",
                "result": next(sub_results),
                "usage": {},
            }
        )

    f_api = run_agent_agentic("DIFF", tmp_path, spec, api, max_turns=12)
    f_sub = run_agent_agentic(
        "DIFF", tmp_path, spec, SubagentBackend(runner=sub_runner), max_turns=12
    )
    assert f_api == f_sub
    assert f_api[0].message == "boom"


def test_empty_findings_identical_across_backends():
    bundle, spec = Bundle(diff="DIFF"), get_agent("security")
    f_api = run_agent(bundle, spec, ApiBackend(_SDK("[]")))
    f_sub = run_agent(bundle, spec, SubagentBackend(runner=_sub_runner("[]")))
    assert f_api == f_sub == []


_MULTI = (
    '[{"path":"a.py","line":1,"severity":"high","message":"one"},'
    '{"path":"b.py","line":2,"severity":"low","message":"two"}]'
)


def test_multi_findings_identical_across_backends():
    bundle, spec = Bundle(diff="DIFF"), get_agent("security")
    f_api = run_agent(bundle, spec, ApiBackend(_SDK(_MULTI)))
    f_sub = run_agent(bundle, spec, SubagentBackend(runner=_sub_runner(_MULTI)))
    assert f_api == f_sub
    assert len(f_api) == 2 and f_api[1].message == "two"
