import json

from framework_cli.review.findings import Finding


def test_write_findings_round_trips(tmp_path):
    from framework_cli.review.aggregate import write_findings

    out = tmp_path / "sub" / "review-x.json"  # parent dir does not exist yet
    write_findings(
        out, "review-x", "failure", [Finding("a.py", 1, "high", "boom", "fix")]
    )

    assert json.loads(out.read_text()) == {
        "agent": "review-x",
        "conclusion": "failure",
        "findings": [
            {
                "path": "a.py",
                "line": 1,
                "severity": "high",
                "message": "boom",
                "suggestion": "fix",
            }
        ],
    }


def test_write_findings_empty_list(tmp_path):
    from framework_cli.review.aggregate import write_findings

    out = tmp_path / "review-y.json"
    write_findings(out, "review-y", "neutral", [])
    assert json.loads(out.read_text()) == {
        "agent": "review-y",
        "conclusion": "neutral",
        "findings": [],
    }


def _result(agent, conclusion, findings):
    return {"agent": agent, "conclusion": conclusion, "findings": findings}


def _f(path, line, sev, msg):
    return {"path": path, "line": line, "severity": sev, "message": msg}


def test_overall_fails_if_any_agent_failed():
    from framework_cli.review.aggregate import aggregate

    r = aggregate(
        [
            _result("review-security", "failure", [_f("a.py", 1, "high", "x")]),
            _result("review-test-quality", "success", []),
        ]
    )
    assert r.overall == "fail"


def test_overall_passes_when_no_failure():
    from framework_cli.review.aggregate import aggregate

    r = aggregate([_result("review-security", "neutral", [_f("a.py", 1, "low", "x")])])
    assert r.overall == "pass"


def test_severity_counts_across_agents():
    from framework_cli.review.aggregate import aggregate

    r = aggregate(
        [
            _result(
                "review-a",
                "neutral",
                [_f("a.py", 1, "low", "x"), _f("b.py", 2, "high", "y")],
            ),
            _result("review-b", "neutral", [_f("c.py", 3, "low", "z")]),
        ]
    )
    assert r.severity_counts == {"low": 2, "high": 1}


def test_same_file_flagged_by_two_agents_is_a_relationship():
    from framework_cli.review.aggregate import aggregate

    r = aggregate(
        [
            _result("review-security", "neutral", [_f("a.py", 1, "low", "x")]),
            _result("review-architecture", "neutral", [_f("a.py", 9, "low", "y")]),
        ]
    )
    assert any("Multiple agents flagged `a.py`" in s for s in r.relationships)


def test_related_domain_pair_is_a_relationship():
    from framework_cli.review.aggregate import aggregate

    r = aggregate(
        [
            _result("review-data-lineage", "neutral", [_f("p.py", 1, "low", "x")]),
            _result("review-privacy", "neutral", [_f("p.py", 2, "low", "y")]),
        ]
    )
    assert any("related concern" in s for s in r.relationships)


def test_no_relationships_when_files_disjoint():
    from framework_cli.review.aggregate import aggregate

    r = aggregate(
        [
            _result("review-security", "neutral", [_f("a.py", 1, "low", "x")]),
            _result("review-privacy", "neutral", [_f("b.py", 2, "low", "y")]),
        ]
    )
    assert r.relationships == []


def test_markdown_has_header_groups_relationships_files_and_marker():
    from framework_cli.review.aggregate import SUMMARY_MARKER, aggregate

    md = aggregate(
        [_result("review-security", "failure", [_f("a.py", 1, "high", "danger")])]
    ).markdown
    assert SUMMARY_MARKER in md
    assert "Review summary" in md and "FAIL" in md
    assert "high" in md and "danger" in md and "review-security" in md
    assert "Cross-agent relationships" in md
    assert "Affected files" in md and "a.py" in md


def test_two_related_pairs_on_same_path_are_ordered_and_additive():
    from framework_cli.review.aggregate import aggregate

    # lineage+privacy AND lineage+compliance both match p.py; same-file rule also fires.
    r = aggregate(
        [
            _result("review-data-lineage", "neutral", [_f("p.py", 1, "low", "x")]),
            _result("review-privacy", "neutral", [_f("p.py", 2, "low", "y")]),
            _result("review-compliance", "neutral", [_f("p.py", 3, "low", "z")]),
        ]
    )
    related = [s for s in r.relationships if "related concern" in s]
    assert related == [
        "`review-compliance` + `review-data-lineage` both flagged `p.py` — related concern.",
        "`review-data-lineage` + `review-privacy` both flagged `p.py` — related concern.",
    ]
    # additive: the same-file rule also produced an entry for the 3 agents on p.py
    assert any("Multiple agents flagged `p.py`" in s for s in r.relationships)


def test_markdown_with_zero_findings_renders_sensibly():
    from framework_cli.review.aggregate import aggregate

    md = aggregate([_result("review-security", "success", [])]).markdown
    assert "0 finding(s)" in md
    assert (
        "- none" in md
    )  # both the relationships and affected-files sections fall back


def test_load_results_reads_json_and_skips_malformed(tmp_path):
    from framework_cli.review.aggregate import load_results

    (tmp_path / "review-a.json").write_text(
        '{"agent": "review-a", "conclusion": "success", "findings": []}'
    )
    (tmp_path / "review-b.json").write_text("{ not valid json")
    (tmp_path / "ignore.txt").write_text("not json at all")

    results = load_results(tmp_path)
    assert len(results) == 1 and results[0]["agent"] == "review-a"


def test_load_results_missing_directory_is_empty(tmp_path):
    from framework_cli.review.aggregate import load_results

    assert load_results(tmp_path / "does-not-exist") == []
