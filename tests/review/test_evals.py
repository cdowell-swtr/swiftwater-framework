import json
from pathlib import Path

_FIXTURES_ROOT = Path(__file__).parent.parent / "eval" / "fixtures"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_load_fixtures_discovers_bad_and_good(tmp_path):
    from framework_cli.review.evals import load_fixtures

    # bad case: has fixture.yaml + change.patch + expect.json
    bad_case = tmp_path / "security" / "bad" / "sqli"
    bad_case.mkdir(parents=True)
    (bad_case / "fixture.yaml").write_text("batteries: []\n")
    (bad_case / "change.patch").write_text("+++ b/app.py\n")
    (bad_case / "expect.json").write_text(json.dumps({"file": "app.py"}))

    # good case: has fixture.yaml + change.patch, no expect.json
    good_case = tmp_path / "security" / "good" / "ok"
    good_case.mkdir(parents=True)
    (good_case / "fixture.yaml").write_text("batteries: []\n")
    (good_case / "change.patch").write_text("+++ b/app.py\n")

    fx = load_fixtures(tmp_path)
    assert [(f.agent, f.kind, f.name, f.seeded_file) for f in fx] == [
        ("security", "bad", "sqli", "app.py"),
        ("security", "good", "ok", None),
    ]


def test_load_fixtures_skips_bad_without_valid_sidecar(tmp_path):
    from framework_cli.review.evals import load_fixtures

    # bad case: missing expect.json — should be skipped
    no_sidecar = tmp_path / "security" / "bad" / "no-sidecar"
    no_sidecar.mkdir(parents=True)
    (no_sidecar / "fixture.yaml").write_text("batteries: []\n")
    (no_sidecar / "change.patch").write_text("+++ b/app.py\n")

    # bad case: malformed expect.json — should be skipped
    bad_json = tmp_path / "security" / "bad" / "bad-json"
    bad_json.mkdir(parents=True)
    (bad_json / "fixture.yaml").write_text("batteries: []\n")
    (bad_json / "change.patch").write_text("+++ b/app.py\n")
    (bad_json / "expect.json").write_text("{ not json")

    # good case: must survive regardless
    good_case = tmp_path / "security" / "good" / "ok"
    good_case.mkdir(parents=True)
    (good_case / "fixture.yaml").write_text("batteries: []\n")
    (good_case / "change.patch").write_text("+++ b/app.py\n")

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
    assert (
        flags([Finding("z.py", 9, "critical", "x")], spec) is True
    )  # good-fixture block check


def test_default_thresholds():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS

    assert DEFAULT_THRESHOLDS.recall_min == 0.67 and DEFAULT_THRESHOLDS.fp_max == 0.34


def test_load_thresholds_overrides_and_missing(tmp_path):
    from framework_cli.review.evals import Thresholds, load_thresholds

    assert load_thresholds(tmp_path / "nope.yaml") == {}
    (tmp_path / "thresholds.yaml").write_text(
        "security: {recall_min: 0.5, fp_max: 0.5}\n"
    )
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

    (tmp_path / "thresholds.yaml").write_text(
        "security: {recall_min: 0.5}\n"
    )  # missing fp_max
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
        assert bad >= 1, f"{a}: needs >= 1 bad fixture, has {bad}"
        assert good >= 1, f"{a}: needs >= 1 good fixture, has {good}"


def test_contracts_has_full_fixture_set():
    from pathlib import Path

    from framework_cli.review.evals import load_fixtures

    fx = [
        f for f in load_fixtures(Path("tests/eval/fixtures")) if f.agent == "contracts"
    ]
    kinds = sorted({f.kind for f in fx})
    assert kinds == ["bad", "good"], kinds
    assert sum(1 for f in fx if f.kind == "bad") >= 2
    assert any(f.kind == "good" for f in fx)


def test_fixtures_are_wellformed():
    """Structural validation of directory-format fixtures (no render required)."""
    import yaml

    from framework_cli.review.evals import load_fixtures

    fixtures = load_fixtures(_FIXTURES_ROOT)
    assert fixtures, "no fixtures discovered"
    for fx in fixtures:
        label = f"{fx.agent}/{fx.kind}/{fx.name}"
        assert fx.patch.strip(), f"{label}: empty patch"
        # fixture.yaml must parse cleanly (load_fixtures already did this; verify batteries type)
        assert isinstance(fx.batteries, tuple), f"{label}: batteries must be a tuple"
        if fx.kind == "bad":
            assert fx.seeded_file is not None, (
                f"{label}: bad fixture missing seeded_file"
            )
            assert fx.seeded_file.strip(), f"{label}: bad fixture has empty seeded_file"

    # Also validate the raw directories directly (catches malformed cases load_fixtures skips)
    for agent_dir in sorted(p for p in _FIXTURES_ROOT.glob("*") if p.is_dir()):
        for kind in ("bad", "good"):
            for case in sorted(p for p in (agent_dir / kind).glob("*") if p.is_dir()):
                spec_f = case / "fixture.yaml"
                if not spec_f.is_file():
                    # A dir without fixture.yaml is not a recognized case — skip
                    continue
                label = f"{agent_dir.name}/{kind}/{case.name}"
                patch_f = case / "change.patch"
                assert patch_f.is_file(), f"{label}: missing change.patch"
                assert patch_f.read_text().strip(), f"{label}: empty change.patch"
                spec_data = yaml.safe_load(spec_f.read_text()) or {}
                assert isinstance(spec_data, dict), (
                    f"{label}: fixture.yaml must be a mapping"
                )
                if kind == "bad":
                    expect_f = case / "expect.json"
                    assert expect_f.is_file(), f"{label}: bad case missing expect.json"
                    import json as _json

                    data = _json.loads(expect_f.read_text())
                    assert "file" in data, f"{label}: expect.json missing 'file' key"


def test_load_fixtures_discovers_rendered_directory_format(tmp_path):
    from framework_cli.review.evals import load_fixtures

    case = tmp_path / "security" / "bad" / "hardcoded"
    case.mkdir(parents=True)
    (case / "fixture.yaml").write_text("batteries: []\n")
    (case / "change.patch").write_text("--- a/x\n+++ b/x\n")
    (case / "expect.json").write_text('{"file": "src/demo/x.py"}')
    fx = load_fixtures(tmp_path)
    assert len(fx) == 1
    assert fx[0].agent == "security" and fx[0].kind == "bad"
    assert fx[0].batteries == () and fx[0].seeded_file == "src/demo/x.py"
    assert fx[0].patch.startswith("--- a/x")


# The hardcoded-secret patch touches src/demo/config/settings.py — a file that exists
# in every baseline render, so it's a safe choice for cache-reuse testing.
_HARDCODED_SECRET_PATCH = (
    _FIXTURES_ROOT / "security" / "bad" / "hardcoded-secret" / "change.patch"
).read_text()


def test_realize_cached_reuses_base_render(tmp_path):
    """realize_cached renders the base once per battery-combo and copies it per fixture."""
    from framework_cli.review.evals import Fixture, realize_cached

    base_dir = tmp_path / "bases"
    base_dir.mkdir()
    cache: dict = {}

    fx1 = Fixture(
        "security",
        "bad",
        "case1",
        (),
        _HARDCODED_SECRET_PATCH,
        "src/demo/config/settings.py",
    )
    fx2 = Fixture(
        "security",
        "bad",
        "case2",
        (),
        _HARDCODED_SECRET_PATCH,
        "src/demo/config/settings.py",
    )

    root1, diff1 = realize_cached(fx1, cache, base_dir)
    assert len(cache) == 1, "first call should populate cache with 1 entry"

    root2, diff2 = realize_cached(fx2, cache, base_dir)
    assert len(cache) == 1, (
        "second call with same batteries should reuse cache (still 1 entry)"
    )

    # Both should return non-empty diffs (the patch applied successfully)
    assert diff1.strip(), "diff1 should be non-empty"
    assert diff2.strip(), "diff2 should be non-empty"

    # The two work-trees must be distinct paths
    assert root1 != root2


def test_every_fixture_realizes():
    """Every golden fixture's change.patch must apply to a fresh render of the current
    template — the durable guard against fixture/template drift the structural checks miss.
    No backend; Copier render + `git apply` only."""
    import subprocess
    import tempfile

    from framework_cli.review.evals import load_fixtures, realize_cached

    base = Path(tempfile.mkdtemp(prefix="fixture-realize-"))
    cache: dict = {}
    failures: list[str] = []
    for fx in load_fixtures(_FIXTURES_ROOT):
        try:
            realize_cached(fx, cache, base)
        except subprocess.CalledProcessError:
            failures.append(f"{fx.agent}/{fx.kind}/{fx.name}")
    assert not failures, (
        "fixtures drifted from the template (change.patch no longer applies) — "
        f"re-anchor: {failures}"
    )
