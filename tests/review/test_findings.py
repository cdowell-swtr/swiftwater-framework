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
    findings = parse_findings(
        '[{"path": "x", "line": 1, "severity": "low", "message": "m"}]'
    )
    assert findings[0].suggestion is None


def test_invalid_severity_raises():
    with pytest.raises(FindingsParseError):
        parse_findings('[{"path": "x", "line": 1, "severity": "nope", "message": "m"}]')


def test_no_array_raises():
    with pytest.raises(FindingsParseError):
        parse_findings("I could not produce JSON.")


def test_parse_array_with_trailing_prose_containing_brackets():
    """The agent appends an explanation after the JSON array, and that prose
    itself contains brackets (e.g. a line reference) — naive first-[..last-]
    over-spans and json.loads chokes on 'Extra data'. Extract the FIRST complete
    array and ignore the trailing content. Regression: a real contracts-agent
    response crashed the paid eval exactly this way."""
    text = _JSON + "\n\nNote: see the related check at line [42] for context."
    findings = parse_findings(text)
    assert len(findings) == 1
    assert findings[0].path == "a.py"


def test_parse_first_array_when_response_has_trailing_array():
    """A second bracketed token after the findings array must not be swept in."""
    text = _JSON + "\n\nAnd separately: [1, 2, 3]"
    findings = parse_findings(text)
    assert len(findings) == 1
    assert findings[0].path == "a.py"


def test_parse_array_when_prose_has_invalid_leading_bracket():
    """A bracket in the prose BEFORE the array that is NOT valid JSON (e.g.
    `[docs]`) is skipped — take the first bracket that decodes to a JSON list."""
    text = "See [docs]. Findings:\n" + _JSON
    findings = parse_findings(text)
    assert len(findings) == 1
    assert findings[0].path == "a.py"


def test_parse_skips_leading_numeric_array_citation():
    """A valid-JSON but non-findings array in leading prose (e.g. a `[42]` line
    citation) must NOT be returned — it isn't a list of finding objects, so skip
    it and take the real findings array."""
    text = "See line [42] for context. Findings:\n" + _JSON
    findings = parse_findings(text)
    assert len(findings) == 1
    assert findings[0].path == "a.py"


def test_parse_skips_leading_empty_array_in_prose():
    """An empty `[]` in leading prose (e.g. 'no [] params found') must NOT short-
    circuit to zero findings — prefer the first NON-EMPTY array of objects."""
    text = "Checked: no [] params found. Findings:\n" + _JSON
    findings = parse_findings(text)
    assert len(findings) == 1
    assert findings[0].path == "a.py"


def test_parse_nonnumeric_line_coerced_keeps_finding():
    """An agent sometimes puts a code snippet (not a number) in `line`. That must
    not crash or discard the finding — coerce to 0 and keep it. Regression: a
    real data-lineage response with line='item.name = payload.name' crashed the
    paid eval via int()."""
    text = (
        '[{"path": "a.py", "line": "item.name = payload.name", '
        '"severity": "high", "message": "m"}]'
    )
    findings = parse_findings(text)
    assert len(findings) == 1
    assert findings[0].path == "a.py"
    assert findings[0].line == 0


def test_parse_extracts_leading_int_from_messy_line():
    text = '[{"path": "a.py", "line": "42: see here", "severity": "low", "message": "m"}]'
    assert parse_findings(text)[0].line == 42


def test_parse_missing_required_field_raises_parse_error():
    """A structurally-broken item (missing `path`) raises FindingsParseError — not
    a raw KeyError — so the eval loop and the `framework review` path degrade
    gracefully instead of crashing."""
    text = '[{"line": 1, "severity": "high", "message": "m"}]'  # no path
    with pytest.raises(FindingsParseError):
        parse_findings(text)


def test_severity_rank_orders_critical_above_info():
    assert severity_rank("critical") > severity_rank("high") > severity_rank("info")


def test_parse_findings_reads_acknowledged_and_stale():
    text = (
        '[{"path":"a.py","line":1,"severity":"high","message":"m","acknowledged":"DEC-0001"},'
        '{"path":"b.py","line":2,"severity":"high","message":"m","stale":"DEC-0002"}]'
    )
    fs = parse_findings(text)
    assert fs[0].acknowledged == "DEC-0001" and fs[0].stale is None
    assert fs[1].stale == "DEC-0002" and fs[1].acknowledged is None


def test_parse_findings_defaults_tags_none():
    fs = parse_findings('[{"path":"a.py","line":1,"severity":"low","message":"m"}]')
    assert fs[0].acknowledged is None and fs[0].stale is None
