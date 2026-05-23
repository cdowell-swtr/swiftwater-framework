import json
from pathlib import Path

_FIXTURES_ROOT = Path(__file__).parent.parent / "eval" / "fixtures"


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


def test_default_thresholds():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS

    assert DEFAULT_THRESHOLDS.recall_min == 0.67 and DEFAULT_THRESHOLDS.fp_max == 0.34


def test_load_thresholds_overrides_and_missing(tmp_path):
    from framework_cli.review.evals import Thresholds, load_thresholds

    assert load_thresholds(tmp_path / "nope.yaml") == {}
    (tmp_path / "thresholds.yaml").write_text("security: {recall_min: 0.5, fp_max: 0.5}\n")
    got = load_thresholds(tmp_path / "thresholds.yaml")
    assert got == {"security": Thresholds(0.5, 0.5)}


def test_score_agent_passes_when_recall_high_and_fp_low():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS, score_agent

    s = score_agent("security", [1.0, 1.0, 0.0], [0.0], DEFAULT_THRESHOLDS)
    assert s.recall == 2 / 3 and s.fp_rate == 0.0 and s.passed and s.reason == ""


def test_score_agent_fails_on_low_recall():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS, score_agent

    s = score_agent("x", [1.0, 0.0, 0.0], [0.0], DEFAULT_THRESHOLDS)
    assert not s.passed and "recall" in s.reason


def test_score_agent_fails_on_high_fp():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS, score_agent

    s = score_agent("x", [1.0, 1.0], [1.0], DEFAULT_THRESHOLDS)
    assert not s.passed and "fp" in s.reason


def test_score_agent_vacuous_when_no_fixtures():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS, score_agent

    s = score_agent("x", [], [], DEFAULT_THRESHOLDS)
    assert s.recall == 1.0 and s.fp_rate == 0.0 and s.passed


def test_load_thresholds_rejects_malformed_entry(tmp_path):
    import pytest

    from framework_cli.review.evals import load_thresholds

    (tmp_path / "thresholds.yaml").write_text("security: {recall_min: 0.5}\n")  # missing fp_max
    with pytest.raises(ValueError, match="security"):
        load_thresholds(tmp_path / "thresholds.yaml")


def test_every_registered_agent_has_fixtures():
    from framework_cli.review.evals import load_fixtures
    from framework_cli.review.registry import agent_names

    counts: dict[tuple[str, str], int] = {}
    for fx in load_fixtures(_FIXTURES_ROOT):
        counts[(fx.agent, fx.kind)] = counts.get((fx.agent, fx.kind), 0) + 1
    for a in agent_names():
        bad = counts.get((a, "bad"), 0)
        good = counts.get((a, "good"), 0)
        assert bad >= 2, f"{a}: needs >= 2 bad fixtures, has {bad}"
        assert good >= 1, f"{a}: needs >= 1 good fixture, has {good}"


def test_fixtures_are_wellformed():
    from framework_cli.review.diff import changed_files
    from framework_cli.review.evals import load_fixtures

    fixtures = load_fixtures(_FIXTURES_ROOT)
    assert fixtures, "no fixtures discovered"
    for fx in fixtures:
        label = f"{fx.agent}/{fx.kind}/{fx.name}"
        assert fx.diff.strip(), f"{label}: empty diff"
        changed = changed_files(fx.diff)
        assert changed, f"{label}: diff has no '+++ b/' paths"
        if fx.kind == "bad":
            assert fx.seeded_file in changed, (
                f"{label}: seeded_file {fx.seeded_file!r} not among changed files {changed}"
            )
