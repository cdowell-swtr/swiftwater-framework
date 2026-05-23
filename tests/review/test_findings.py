import pytest

from framework_cli.review.findings import (
    Finding,
    FindingsParseError,
    parse_findings,
    severity_rank,
)

_JSON = '[{"path": "a.py", "line": 3, "severity": "high", "message": "SQL injection", "suggestion": "use params"}]'


def test_parse_plain_json():
    findings = parse_findings(_JSON)
    assert findings == [Finding("a.py", 3, "high", "SQL injection", "use params")]


def test_parse_json_in_code_fence_and_prose():
    wrapped = f"Here are my findings:\n```json\n{_JSON}\n```\nDone."
    assert parse_findings(wrapped)[0].path == "a.py"


def test_parse_empty_array():
    assert parse_findings("[]") == []


def test_parse_optional_suggestion_absent():
    findings = parse_findings('[{"path": "x", "line": 1, "severity": "low", "message": "m"}]')
    assert findings[0].suggestion is None


def test_invalid_severity_raises():
    with pytest.raises(FindingsParseError):
        parse_findings('[{"path": "x", "line": 1, "severity": "nope", "message": "m"}]')


def test_no_array_raises():
    with pytest.raises(FindingsParseError):
        parse_findings("I could not produce JSON.")


def test_severity_rank_orders_critical_above_info():
    assert severity_rank("critical") > severity_rank("high") > severity_rank("info")
