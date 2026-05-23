from dataclasses import replace

from framework_cli.review.checks import neutral_payload, to_check_run
from framework_cli.review.findings import Finding
from framework_cli.review.registry import get_agent

_SPEC = get_agent("security")  # block_threshold = high


def test_no_findings_is_success():
    payload = to_check_run(_SPEC, [])
    assert payload.conclusion == "success"
    assert payload.annotations == []


def test_blocking_finding_is_failure():
    payload = to_check_run(_SPEC, [Finding("a.py", 1, "high", "m")])
    assert payload.conclusion == "failure"
    assert payload.annotations[0]["path"] == "a.py"
    assert payload.annotations[0]["start_line"] == 1


def test_below_threshold_is_neutral():
    payload = to_check_run(_SPEC, [Finding("a.py", 1, "low", "m"), Finding("b.py", 2, "medium", "m")])
    assert payload.conclusion == "neutral"
    assert len(payload.annotations) == 2


def test_annotation_includes_suggestion_and_level():
    payload = to_check_run(_SPEC, [Finding("a.py", 1, "critical", "boom", "fix it")])
    ann = payload.annotations[0]
    assert ann["annotation_level"] == "failure"
    assert "fix it" in ann["message"]


def test_neutral_payload():
    payload = neutral_payload("review-security", "skipped")
    assert payload.conclusion == "neutral" and payload.annotations == []


def test_advisory_agent_never_fails():
    advisory = replace(_SPEC, block_threshold=None)
    assert to_check_run(advisory, [Finding("a.py", 1, "critical", "x")]).conclusion == "neutral"
    assert to_check_run(advisory, []).conclusion == "success"
