import json

from framework_cli.review.findings import Finding


def test_write_findings_round_trips(tmp_path):
    from framework_cli.review.aggregate import write_findings

    out = tmp_path / "sub" / "review-x.json"  # parent dir does not exist yet
    write_findings(out, "review-x", "failure", [Finding("a.py", 1, "high", "boom", "fix")])

    assert json.loads(out.read_text()) == {
        "agent": "review-x",
        "conclusion": "failure",
        "findings": [
            {"path": "a.py", "line": 1, "severity": "high", "message": "boom", "suggestion": "fix"}
        ],
    }


def test_write_findings_empty_list(tmp_path):
    from framework_cli.review.aggregate import write_findings

    out = tmp_path / "review-y.json"
    write_findings(out, "review-y", "neutral", [])
    assert json.loads(out.read_text()) == {"agent": "review-y", "conclusion": "neutral", "findings": []}
