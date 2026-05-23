import json
from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_load_fixtures_discovers_bad_and_good(tmp_path):
    from framework_cli.review.evals import load_fixtures

    _write(tmp_path / "security" / "bad" / "sqli.diff", "+++ b/app.py\n")
    _write(tmp_path / "security" / "bad" / "sqli.expect.json", json.dumps({"file": "app.py"}))
    _write(tmp_path / "security" / "good" / "ok.diff", "+++ b/app.py\n")

    fx = load_fixtures(tmp_path)
    assert [(f.agent, f.kind, f.name, f.seeded_file) for f in fx] == [
        ("security", "bad", "sqli", "app.py"),
        ("security", "good", "ok", None),
    ]


def test_load_fixtures_skips_bad_without_valid_sidecar(tmp_path):
    from framework_cli.review.evals import load_fixtures

    _write(tmp_path / "security" / "bad" / "no-sidecar.diff", "+++ b/app.py\n")  # no .expect.json
    _write(tmp_path / "security" / "bad" / "bad-json.diff", "+++ b/app.py\n")
    _write(tmp_path / "security" / "bad" / "bad-json.expect.json", "{ not json")
    _write(tmp_path / "security" / "good" / "ok.diff", "+++ b/app.py\n")  # must survive

    fx = load_fixtures(tmp_path)
    # both bad fixtures skipped, but the good one still loads (skip-one-keep-the-rest)
    assert [(f.kind, f.name) for f in fx] == [("good", "ok")]


def test_load_fixtures_ignores_non_dir_entries(tmp_path):
    from framework_cli.review.evals import load_fixtures

    _write(tmp_path / "thresholds.yaml", "security: {recall_min: 0.5, fp_max: 0.5}\n")
    assert load_fixtures(tmp_path) == []


def _spec(threshold):
    from framework_cli.review.registry import AgentSpec

    return AgentSpec("review-x", "prompt", threshold, "always", "m")


def test_flags_blocking_finding_on_file_is_detected():
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    spec = _spec("high")
    assert flags([Finding("a.py", 1, "high", "x")], spec, file="a.py") is True


def test_flags_finding_on_other_file_is_not_detected():
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    spec = _spec("high")
    assert flags([Finding("b.py", 1, "high", "x")], spec, file="a.py") is False


def test_flags_below_threshold_is_not_a_block():
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    spec = _spec("high")
    assert flags([Finding("a.py", 1, "low", "x")], spec, file="a.py") is False


def test_flags_advisory_agent_counts_any_finding():
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    spec = _spec(None)  # advisory: never blocks in prod, so evals score on surfacing
    assert flags([Finding("a.py", 1, "low", "x")], spec, file="a.py") is True
    assert flags([], spec, file="a.py") is False


def test_flags_no_file_restriction_scans_all():
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    spec = _spec("high")
    assert flags([Finding("z.py", 9, "critical", "x")], spec) is True  # good-fixture block check
