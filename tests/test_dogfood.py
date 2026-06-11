from __future__ import annotations

import importlib.util
from pathlib import Path

from framework_cli.dogfood import (
    ALL_BATTERIES,
    BASELINE,
    BATTERY_JOBS,
    DogfoodConfig,
    RunResult,
    classify_jobs,
    classify_review_checks,
    parse_checks,
    parse_jobs,
    render_scorecard,
)


# ---------------------------------------------------------------------------
# Task 1: configs + expected-jobs
# ---------------------------------------------------------------------------


def test_baseline_expected_jobs_are_the_always_on_set():
    assert BASELINE.expected_jobs() == {
        "integrity",
        "lint",
        "security",
        "test",
        "build",
        "contract",
        "review-plan",
        "review-aggregate",
    }


def test_baseline_has_no_batteries():
    assert BASELINE.batteries == ()


def test_all_batteries_is_maximal_and_adds_conditional_jobs():
    # Resolved maximal set includes the conditional-job-bearing batteries.
    assert "react" in ALL_BATTERIES.batteries
    assert "consumers" in ALL_BATTERIES.batteries
    # react -> frontend job, consumers -> contracts job.
    assert {"frontend", "contracts"} <= ALL_BATTERIES.expected_jobs()


def test_config_without_conditional_batteries_omits_those_jobs():
    cfg = DogfoodConfig(name="x", batteries=("workers",))
    assert "frontend" not in cfg.expected_jobs()
    assert "contracts" not in cfg.expected_jobs()


def test_docs_battery_expects_a_docs_ci_job():
    assert BATTERY_JOBS.get("docs") == "docs"
    cfg = DogfoodConfig(name="docs", batteries=("docs",))
    assert "docs" in cfg.expected_jobs()


# ---------------------------------------------------------------------------
# Task 2: parse + classify workflow jobs (surface 1)
# ---------------------------------------------------------------------------

_BASELINE_GREEN = {
    "jobs": [
        {"name": "integrity", "conclusion": "success", "url": "u/integrity"},
        {"name": "lint", "conclusion": "success", "url": "u/lint"},
        {"name": "security", "conclusion": "success", "url": "u/security"},
        {"name": "test", "conclusion": "success", "url": "u/test"},
        {"name": "build", "conclusion": "success", "url": "u/build"},
        {"name": "contract", "conclusion": "success", "url": "u/contract"},
        {"name": "review-plan", "conclusion": "success", "url": "u/rp"},
        {"name": "review (security)", "conclusion": "success", "url": "u/rs"},
        {"name": "review (architecture)", "conclusion": "success", "url": "u/ra"},
        {"name": "review-aggregate", "conclusion": "success", "url": "u/agg"},
    ]
}


def test_classify_jobs_all_green_passes():
    v = classify_jobs(parse_jobs(_BASELINE_GREEN), BASELINE)
    assert v.ok
    assert v.failures == []


def test_classify_jobs_flags_a_failed_job_with_url():
    payload = {"jobs": [dict(j) for j in _BASELINE_GREEN["jobs"]]}
    payload["jobs"][1]["conclusion"] = "failure"  # lint
    v = classify_jobs(parse_jobs(payload), BASELINE)
    assert not v.ok
    assert any("lint" in f and "failure" in f and "u/lint" in f for f in v.failures)


def test_classify_jobs_flags_a_missing_expected_job():
    payload = {"jobs": [j for j in _BASELINE_GREEN["jobs"] if j["name"] != "build"]}
    v = classify_jobs(parse_jobs(payload), BASELINE)
    assert not v.ok
    assert any("build" in f and "missing" in f for f in v.failures)


def test_classify_jobs_flags_empty_review_matrix():
    payload = {
        "jobs": [
            j for j in _BASELINE_GREEN["jobs"] if not j["name"].startswith("review (")
        ]
    }
    v = classify_jobs(parse_jobs(payload), BASELINE)
    assert not v.ok
    assert any("matrix" in f.lower() for f in v.failures)


# ---------------------------------------------------------------------------
# Task 3: classify review Check Runs (surface 2)
# ---------------------------------------------------------------------------

_CHECKS_NEUTRAL = {
    "check_runs": [
        {"name": "security", "conclusion": "neutral", "html_url": "c/sec"},
        {"name": "architecture", "conclusion": "neutral", "html_url": "c/arch"},
    ]
}


def test_review_checks_neutral_passes_without_key():
    checks = parse_checks(_CHECKS_NEUTRAL)
    v = classify_review_checks(
        checks, expected_agents=["security", "architecture"], with_key=False
    )
    assert v.ok
    assert v.failures == []


def test_review_check_failure_without_key_is_a_hard_failure():
    payload = {"check_runs": [dict(c) for c in _CHECKS_NEUTRAL["check_runs"]]}
    payload["check_runs"][0]["conclusion"] = "failure"
    v = classify_review_checks(
        parse_checks(payload),
        expected_agents=["security", "architecture"],
        with_key=False,
    )
    assert not v.ok
    assert any("security" in f and "neutral" in f for f in v.failures)


def test_missing_expected_review_check_is_a_failure():
    v = classify_review_checks(
        parse_checks(_CHECKS_NEUTRAL),
        expected_agents=["security", "architecture", "privacy"],
        with_key=False,
    )
    assert not v.ok
    assert any("privacy" in f and "missing" in f for f in v.failures)


def test_with_key_success_or_neutral_passes_and_failure_warns():
    payload = {
        "check_runs": [
            {"name": "security", "conclusion": "success", "html_url": "c/sec"},
            {"name": "architecture", "conclusion": "failure", "html_url": "c/arch"},
        ]
    }
    v = classify_review_checks(
        parse_checks(payload),
        expected_agents=["security", "architecture"],
        with_key=True,
    )
    assert v.ok  # with-key failures are warnings, not hard failures
    assert any("architecture" in w and "failure" in w for w in v.warnings)


# ---------------------------------------------------------------------------
# Task 4: scorecard rendering
# ---------------------------------------------------------------------------


def test_render_scorecard_includes_config_run_urls_and_status():
    results = [
        RunResult(
            config="baseline",
            with_key=False,
            push_run_url="https://gha/push/1",
            pr_run_url="https://gha/pr/1",
            ok=True,
            failures=[],
            warnings=[],
        ),
        RunResult(
            config="all-batteries",
            with_key=False,
            push_run_url="https://gha/push/2",
            pr_run_url="https://gha/pr/2",
            ok=True,
            failures=[],
            warnings=["review check 'privacy' ..."],
        ),
    ]
    md = render_scorecard(results, commit="v0.1.1")
    assert "v0.1.1" in md
    assert "baseline" in md and "all-batteries" in md
    assert "https://gha/push/1" in md and "https://gha/pr/2" in md
    assert "GREEN" in md  # overall verdict line


def test_render_scorecard_marks_red_when_a_run_failed():
    results = [
        RunResult(
            "baseline",
            False,
            "u1",
            "u2",
            ok=False,
            failures=["job 'test' ..."],
            warnings=[],
        ),
    ]
    md = render_scorecard(results, commit="v0.1.1")
    assert "RED" in md
    assert "job 'test'" in md


# ---------------------------------------------------------------------------
# Task 5: orchestrator wiring test
# ---------------------------------------------------------------------------


def _load_orchestrator():
    path = Path(__file__).resolve().parent.parent / "scripts" / "dogfood_e2e.py"
    spec = importlib.util.spec_from_file_location("dogfood_e2e", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_assert_run_combines_both_surfaces():
    mod = _load_orchestrator()
    jobs = {
        "jobs": [
            {"name": n, "conclusion": "success", "url": f"u/{n}"}
            for n in [
                "integrity",
                "lint",
                "security",
                "test",
                "build",
                "contract",
                "review-plan",
                "review-aggregate",
                "review (security)",
            ]
        ]
    }
    checks = {
        "check_runs": [{"name": "security", "conclusion": "neutral", "html_url": "c/s"}]
    }
    from framework_cli.dogfood import BASELINE

    verdict = mod.assert_run(
        jobs, checks, BASELINE, expected_agents=["security"], with_key=False
    )
    assert verdict.ok, verdict.failures
