import json as _json
from pathlib import Path

from typer.testing import CliRunner

from framework_cli.cli import app
from framework_cli.integrity.manifest import Manifest

runner = CliRunner()


def test_new_creates_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "My App"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "my-app" / "pyproject.toml").is_file()
    assert (tmp_path / "my-app" / "src" / "my_app" / "main.py").is_file()
    assert (tmp_path / "my-app" / ".copier-answers.yml").is_file()


def test_new_rejects_existing_directory(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "my-app").mkdir()
    result = runner.invoke(app, ["new", "My App"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_new_writes_a_verifiable_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "My App"])
    assert result.exit_code == 0, result.output
    lock = tmp_path / "my-app" / ".framework" / "integrity.lock"
    assert lock.is_file()
    manifest = Manifest.loads(lock.read_text())
    # The rendered ci.yml is locked and recorded with a checksum.
    ci = next(e for e in manifest.entries if e.path == ".github/workflows/ci.yml")
    assert ci.cls == "locked" and ci.sha256


def test_integrity_passes_on_a_fresh_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    monkeypatch.chdir(tmp_path / "my-app")
    result = runner.invoke(app, ["integrity", "--ci"])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_integrity_fails_when_a_locked_file_is_altered(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["new", "My App"])
    project = tmp_path / "my-app"
    (project / "alembic.ini").write_text("tampered\n")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["integrity", "--ci"])
    assert result.exit_code == 1
    assert "alembic.ini" in result.output


def test_integrity_allow_drift_then_passes(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["new", "My App"])
    project = tmp_path / "my-app"
    (project / "alembic.ini").write_text("tampered\n")
    monkeypatch.chdir(project)
    assert (
        runner.invoke(app, ["integrity", "--allow-drift", "alembic.ini"]).exit_code == 0
    )
    assert runner.invoke(app, ["integrity", "--ci"]).exit_code == 0


def test_restore_command_fixes_a_tampered_file(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["new", "My App"])
    project = tmp_path / "my-app"
    (project / "alembic.ini").write_text("tampered\n")
    monkeypatch.chdir(project)
    assert runner.invoke(app, ["restore", "alembic.ini"]).exit_code == 0
    assert runner.invoke(app, ["integrity", "--ci"]).exit_code == 0


def test_new_records_portable_source(tmp_path: Path, monkeypatch):
    from framework_cli.source import REPO_GH

    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    answers = (tmp_path / "my-app" / ".copier-answers.yml").read_text()
    assert f"_src_path: {REPO_GH}" in answers
    assert "_commit: v" in answers
    assert "/src/framework_cli/template" not in answers


def test_check_runs_and_reports():
    # In the test env the default remote is unreachable, so latest_release returns None;
    # the command must still exit 0 with a message (no crash).
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0
    assert "framework check" in result.output


def test_upskill_command_rejects_non_directory(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["upskill", "nope"])
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_review_skips_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 0
    assert "skipped" in result.output


def test_review_unknown_agent_errors(monkeypatch):
    result = runner.invoke(app, ["review", "nope"])
    assert result.exit_code == 1
    assert "unknown review agent" in result.output


def test_review_blocking_finding_exits_1(monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(
        cli_mod,
        "_review_run",
        lambda diff, spec, force_agentic=False: [Finding("a.py", 1, "high", "bad")],
    )
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 1
    assert "failure" in result.output


def test_review_low_finding_exits_0(monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(
        cli_mod,
        "_review_run",
        lambda diff, spec, force_agentic=False: [Finding("a.py", 1, "low", "m")],
    )
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 0
    assert "neutral" in result.output


def test_review_infra_error_is_neutral_exit_0(monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def _boom():
        raise RuntimeError("API down")

    monkeypatch.setattr(cli_mod, "_review_diff", _boom)
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 0
    assert "neutral" in result.output or "could not run" in result.output


def test_review_agents_lists_pr_and_push(monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    pr = _json.loads(
        runner.invoke(app, ["review-agents", "--event", "pull_request"]).output
    )
    push = _json.loads(runner.invoke(app, ["review-agents", "--event", "push"]).output)
    assert "security" in pr and "documentation" in pr
    assert set(push) == {"security", "data-integrity", "data-lineage", "observability"}


def test_review_dependency_skips_when_no_dep_files(monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "+++ b/src/app/main.py\n")

    def _should_not_run(diff, spec):
        raise AssertionError("LLM must not run when not triggered")

    monkeypatch.setattr(cli_mod, "_review_run", _should_not_run)
    result = runner.invoke(app, ["review", "dependency"])
    assert result.exit_code == 0
    assert "not triggered" in result.output


def test_review_dependency_runs_when_dep_file_changed(monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "+++ b/pyproject.toml\n")
    monkeypatch.setattr(
        cli_mod,
        "_review_run",
        lambda diff, spec, force_agentic=False: [
            Finding("pyproject.toml", 1, "low", "m")
        ],
    )
    result = runner.invoke(app, ["review", "dependency"])
    assert result.exit_code == 0  # advisory → neutral, never blocks
    assert "neutral" in result.output


def test_review_findings_out_writes_on_normal_path(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(
        cli_mod,
        "_review_run",
        lambda diff, spec, force_agentic=False: [Finding("a.py", 3, "low", "m")],
    )

    out = tmp_path / "findings" / "security.json"
    result = runner.invoke(app, ["review", "security", "--findings-out", str(out)])
    assert result.exit_code == 0, result.output
    data = _json.loads(out.read_text())
    assert data["agent"] == "review-security"
    assert (
        data["conclusion"] == "neutral"
    )  # low finding → below "high" threshold → neutral
    assert data["findings"] == [
        {
            "path": "a.py",
            "line": 3,
            "severity": "low",
            "message": "m",
            "suggestion": None,
        }
    ]


def test_review_findings_out_on_infra_error(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def _boom():
        raise RuntimeError("API down")

    monkeypatch.setattr(cli_mod, "_review_diff", _boom)
    out = tmp_path / "findings" / "security.json"
    result = runner.invoke(app, ["review", "security", "--findings-out", str(out)])
    assert result.exit_code == 0, result.output
    data = _json.loads(out.read_text())
    assert data["agent"] == "review-security"
    assert data["conclusion"] == "neutral" and data["findings"] == []


def test_review_findings_out_on_skip_path(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    out = tmp_path / "findings" / "security.json"
    result = runner.invoke(app, ["review", "security", "--findings-out", str(out)])
    assert result.exit_code == 0, result.output
    data = _json.loads(out.read_text())
    assert data["conclusion"] == "neutral" and data["findings"] == []


def test_review_aggregate_prints_when_no_pr(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_PR_NUMBER", raising=False)
    (tmp_path / "review-security.json").write_text(
        '{"agent": "review-security", "conclusion": "failure", '
        '"findings": [{"path": "a.py", "line": 1, "severity": "high", "message": "danger"}]}'
    )
    result = runner.invoke(app, ["review-aggregate", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Review summary" in result.output and "FAIL" in result.output


def test_review_aggregate_posts_when_pr_present(tmp_path, monkeypatch):
    import framework_cli.review.comment as comment_mod

    posted = {}
    monkeypatch.setattr(
        comment_mod,
        "post_sticky_comment",
        lambda md, *, repo, pr, token: posted.update(pr=pr, repo=repo, token=token),
    )
    monkeypatch.setenv("GITHUB_PR_NUMBER", "12")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    (tmp_path / "review-a.json").write_text(
        '{"agent": "review-a", "conclusion": "success", "findings": []}'
    )
    result = runner.invoke(app, ["review-aggregate", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert posted == {"pr": "12", "repo": "o/r", "token": "t"}


# ---------------------------------------------------------------------------
# eval command
# ---------------------------------------------------------------------------


def _make_fixture(tmp_path, agent, kind, slug, diff, seeded_file=None):
    case = tmp_path / agent / kind / slug
    case.mkdir(parents=True, exist_ok=True)
    (case / "fixture.yaml").write_text("batteries: []\n")
    (case / "change.patch").write_text(diff)
    if seeded_file is not None:
        (case / "expect.json").write_text(_json.dumps({"file": seeded_file}))


def test_eval_skips_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_EVAL_API_KEY", raising=False)
    result = runner.invoke(app, ["eval", "security"])
    assert result.exit_code == 0
    assert "skipped" in result.output


def test_eval_require_key_fails_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_EVAL_API_KEY", raising=False)
    result = runner.invoke(app, ["eval", "security", "--require-key"])
    assert result.exit_code == 1
    assert "required" in result.output


def _fake_realize_cached(fx, cache, base_dir):
    """Hermetic stand-in for realize_cached: skips rendering, returns patch as diff."""
    from pathlib import Path

    return Path(base_dir), fx.patch


def test_eval_passes_when_agent_catches_bad_and_clean_on_good(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "bad", "b2", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)
    # catch the bad diffs (a high finding on a.py); stay clean on the good diff (marked "# clean")
    monkeypatch.setattr(
        cli_mod,
        "_eval_run",
        lambda diff, root, spec, **kw: (
            [] if "clean" in diff else [Finding("a.py", 1, "high", "danger")]
        ),
    )
    result = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output


def test_eval_fails_when_agent_misses(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "bad", "b2", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)
    monkeypatch.setattr(
        cli_mod, "_eval_run", lambda diff, root, spec, **kw: []
    )  # never catches anything
    result = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_eval_findings_out_writes_per_call_json(tmp_path, monkeypatch):
    """--findings-out persists each (agent, fixture, repeat)'s findings as JSON
    so the fp-cluster and partial-recall agents can be diagnosed without re-running."""
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)
    monkeypatch.setattr(
        cli_mod,
        "_eval_run",
        lambda diff, root, spec, **kw: (
            []
            if "clean" in diff
            else [Finding("a.py", 7, "high", "hardcoded secret", "use env var")]
        ),
    )
    out = tmp_path / "findings"
    result = runner.invoke(
        app,
        [
            "eval",
            "security",
            "--fixtures",
            str(tmp_path),
            "--findings-out",
            str(out),
            "--repeat",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output

    bad = out / "security" / "bad" / "b1__r0.json"
    good = out / "security" / "good" / "g1__r1.json"
    assert bad.exists() and good.exists()
    bad_obj = _json.loads(bad.read_text())
    assert bad_obj["agent"] == "security"
    assert bad_obj["kind"] == "bad"
    assert bad_obj["case"] == "b1"
    assert bad_obj["repeat"] == 0
    assert bad_obj["seeded_file"] == "a.py"
    assert bad_obj["findings"] == [
        {
            "path": "a.py",
            "line": 7,
            "severity": "high",
            "message": "hardcoded secret",
            "suggestion": "use env var",
        }
    ]
    assert _json.loads(good.read_text())["findings"] == []


def _write_record(
    dir, agent, kind, case, repeat, *, findings, usage=None, turns=1, tool_calls=None
):
    path = dir / agent / kind
    path.mkdir(parents=True, exist_ok=True)
    seeded = "a.py" if kind == "bad" else None
    payload = {
        "agent": agent,
        "kind": kind,
        "case": case,
        "repeat": repeat,
        "seeded_file": seeded,
        "findings": findings,
        "usage": usage
        or {
            "input_tokens": 1000,
            "output_tokens": 50,
            "cache_read_input_tokens": 800,
            "cache_creation_input_tokens": 0,
        },
        "latency_ms": 500,
        "stop_reason": "end_turn",
        "raw_text": _json.dumps(findings),
        "turns": turns,
        "tool_calls": tool_calls or [],
    }
    (path / f"{case}__r{repeat}.json").write_text(_json.dumps(payload))


def test_eval_analyze_produces_scorecard_cost_diagnosis_and_thresholds(tmp_path):
    """eval-analyze loads --findings-out records and emits scorecard + cost + fp-diagnosis +
    threshold proposal — the diagnostic surface the re-run needs."""
    d = tmp_path / "f"
    # security: 1 bad caught, 1 good clean → recall 1.0, fp 0.0 → PASS
    _write_record(
        d,
        "security",
        "bad",
        "b1",
        0,
        findings=[
            {
                "path": "a.py",
                "line": 1,
                "severity": "high",
                "message": "danger",
                "suggestion": None,
            }
        ],
    )
    _write_record(d, "security", "good", "g1", 0, findings=[])
    # compliance: 1 bad caught, 1 good with a high finding → recall 1.0, fp 1.0 → FAIL (fp)
    _write_record(
        d,
        "compliance",
        "bad",
        "b1",
        0,
        findings=[
            {
                "path": "a.py",
                "line": 1,
                "severity": "high",
                "message": "policy",
                "suggestion": None,
            }
        ],
    )
    _write_record(
        d,
        "compliance",
        "good",
        "g1",
        0,
        findings=[
            {
                "path": "src/demo/main.py",
                "line": 14,
                "severity": "high",
                "message": "no rate limit",
                "suggestion": None,
            }
        ],
    )
    # architecture: agentic, with a tool-call log
    _write_record(
        d,
        "architecture",
        "bad",
        "b1",
        0,
        findings=[
            {
                "path": "a.py",
                "line": 1,
                "severity": "high",
                "message": "x",
                "suggestion": None,
            }
        ],
        turns=4,
        tool_calls=[
            {"turn": 1, "tool": "grep", "input": {"pattern": "Item"}},
            {
                "turn": 2,
                "tool": "read_file",
                "input": {"path": "src/demo/db/repository.py"},
            },
        ],
    )

    result = runner.invoke(app, ["eval-analyze", str(d)])
    # exit 1 because compliance FAILs its fp threshold (gate semantics)
    assert result.exit_code == 1, result.output
    out = result.output
    # Scorecard
    assert "## Scorecard" in out
    assert "review-security" in out and "PASS" in out
    assert "review-compliance" in out and "fp 1.00" in out
    # Cost report (numbers will be tiny; check the section + agent names)
    assert "## Cost by agent" in out
    assert "claude-sonnet-4-6" in out
    # FP diagnosis surfaces the good-fixture finding
    assert "## FP diagnosis" in out
    assert "no rate limit" in out
    # Agentic behavior surfaces the tool calls
    assert "## Agentic behavior" in out
    assert "review-architecture" in out
    assert "grep" in out and "read_file" in out
    # Threshold proposal has margin
    assert "## Proposed thresholds.yaml" in out
    assert "recall_min:" in out and "fp_max:" in out


def test_eval_analyze_propose_thresholds_applies_margin():
    """propose_thresholds: recall_min = recall - margin (floored at 0), fp_max = fp + margin (capped at 1)."""
    from framework_cli.review.analyze import propose_thresholds
    from framework_cli.review.evals import AgentScore

    scores = [
        AgentScore(
            "security",
            recall=1.00,
            fp_rate=0.00,
            bad_total=1,
            good_total=1,
            passed=True,
            reason="",
        ),
        AgentScore(
            "compliance",
            recall=1.00,
            fp_rate=1.00,
            bad_total=1,
            good_total=1,
            passed=False,
            reason="fp 1.00 > 0.34",
        ),
        AgentScore(
            "contracts",
            recall=0.62,
            fp_rate=0.00,
            bad_total=1,
            good_total=1,
            passed=False,
            reason="recall 0.62 < 0.67",
        ),
    ]
    out = propose_thresholds(scores, margin=0.10)
    assert out["security"]["recall_min"] == 0.90
    assert out["security"]["fp_max"] == 0.10
    assert out["compliance"]["fp_max"] == 1.00  # capped at 1.0
    assert out["contracts"]["recall_min"] == 0.52


def test_eval_findings_out_includes_instrumentation(tmp_path, monkeypatch):
    """The per-call JSON also carries usage/latency/stop_reason/turns/tool_calls/raw_text
    so the re-run produces a single record sufficient for calibration AND diagnosis."""
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)

    def _fake_run(diff, root, spec, *, report=None):
        # the bundle/agentic runners populate `report`; mimic that contract here
        if report is not None:
            report["usage"] = {
                "input_tokens": 1234,
                "output_tokens": 56,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 0,
            }
            report["latency_ms"] = 789
            report["stop_reason"] = "end_turn"
            report["raw_text"] = "[]" if "clean" in diff else '[{"path":"a.py"}]'
            report["turns"] = 1
            report["tool_calls"] = []
        return [] if "clean" in diff else [Finding("a.py", 7, "high", "x", None)]

    monkeypatch.setattr(cli_mod, "_eval_run", _fake_run)
    out = tmp_path / "findings"
    result = runner.invoke(
        app,
        ["eval", "security", "--fixtures", str(tmp_path), "--findings-out", str(out)],
    )
    assert result.exit_code == 0, result.output
    bad_obj = _json.loads((out / "security" / "bad" / "b1__r0.json").read_text())
    assert bad_obj["usage"]["input_tokens"] == 1234
    assert bad_obj["usage"]["cache_read_input_tokens"] == 1000
    assert bad_obj["latency_ms"] == 789
    assert bad_obj["stop_reason"] == "end_turn"
    assert bad_obj["raw_text"] == '[{"path":"a.py"}]'
    assert bad_obj["turns"] == 1
    assert bad_obj["tool_calls"] == []


def test_eval_aborts_loudly_on_api_error(tmp_path, monkeypatch):
    """An API/credit/rate-limit failure is NOT a non-detection: the eval must abort
    loudly (so a contaminated scorecard is impossible), not silently score 0."""
    import anthropic
    import httpx

    import framework_cli.cli as cli_mod

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)

    def _credit_wall(diff, root, spec, **kw):
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        raise anthropic.APIError("credit balance is too low", req, body=None)

    monkeypatch.setattr(cli_mod, "_eval_run", _credit_wall)
    result = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)])
    assert result.exit_code == 3, result.output
    assert "ABORTED" in result.output
    assert "review-security" in result.output


def test_eval_no_fixtures_skipped_unless_required(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    assert (
        runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)]).exit_code
        == 0
    )
    r = runner.invoke(
        app, ["eval", "security", "--fixtures", str(tmp_path), "--require-fixtures"]
    )
    assert r.exit_code == 1
    assert "no fixtures" in r.output


def test_eval_repeat_zero_is_rejected(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    result = runner.invoke(app, ["eval", "security", "--repeat", "0"])
    assert result.exit_code == 2
    assert "--repeat must be >= 1" in result.output


def test_eval_unknown_agent_errors(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    result = runner.invoke(app, ["eval", "nonsense-agent"])
    assert result.exit_code == 1
    assert "unknown review agent" in result.output


def test_new_with_webhooks_passes_integrity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App", "--with", "webhooks"]).exit_code == 0
    monkeypatch.chdir(tmp_path / "my-app")
    result = runner.invoke(app, ["integrity", "--ci"])
    assert result.exit_code == 0, (
        result.output
    )  # battery-active .env.example checksum matches


def test_new_with_websockets_battery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "My App", "--with", "websockets"])
    assert result.exit_code == 0, result.output
    assert (
        tmp_path / "my-app" / "src" / "my_app" / "routes" / "websockets.py"
    ).is_file()


def test_new_without_battery_has_no_websockets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    assert not (
        tmp_path / "my-app" / "src" / "my_app" / "routes" / "websockets.py"
    ).exists()


def test_new_rejects_unknown_battery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "My App", "--with", "bogus"])
    assert result.exit_code == 1
    assert "unknown battery" in result.output


def test_new_records_batteries_in_answers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App", "--with", "websockets"]).exit_code == 0
    from framework_cli.source import read_batteries

    assert read_batteries(tmp_path / "my-app") == ["websockets"]


def test_read_batteries_empty_when_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    from framework_cli.source import read_batteries

    assert read_batteries(tmp_path / "my-app") == []


def test_upskill_with_unions_batteries(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App", "--with", "websockets"]).exit_code == 0
    project = tmp_path / "my-app"

    captured = {}

    def fake_upskill(proj, vcs_ref=None, with_batteries=None, alert_channels=None):
        captured["with_batteries"] = with_batteries
        return True

    monkeypatch.setattr(cli_mod, "upskill_project", fake_upskill)

    from framework_cli import batteries as bat

    bat._BATTERIES["_x"] = bat.BatterySpec("_x", "x", obs="rides-existing")
    try:
        result = runner.invoke(app, ["upskill", str(project), "--with", "_x"])
    finally:
        del bat._BATTERIES["_x"]
    assert result.exit_code == 0, result.output
    assert captured["with_batteries"] == ["_x", "websockets"]  # union, sorted


def test_upskill_alerts_flag_passes_parsed_channels(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    project = tmp_path / "my-app"

    captured = {}

    def fake_upskill(proj, vcs_ref=None, with_batteries=None, alert_channels=None):
        captured["alert_channels"] = alert_channels
        return True

    monkeypatch.setattr(cli_mod, "upskill_project", fake_upskill)
    result = runner.invoke(app, ["upskill", str(project), "--alerts", "slack,email"])
    assert result.exit_code == 0, result.output
    assert captured["alert_channels"] == ["slack", "email"]


def test_upskill_bad_alert_channel_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    project = tmp_path / "my-app"
    result = runner.invoke(app, ["upskill", str(project), "--alerts", "sms"])
    assert result.exit_code == 1
    assert "unknown alert channel" in result.output


def test_restore_env_example_preserves_webhooks_secret(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App", "--with", "webhooks"]).exit_code == 0
    project = tmp_path / "my-app"
    env = project / ".env.example"
    env.write_text(
        env.read_text().replace(
            "APP_WEBHOOK_SIGNING_SECRET=", "APP_WEBHOOK_SIGNING_SECRET=tampered"
        )
    )
    monkeypatch.chdir(project)
    assert runner.invoke(app, ["restore", ".env.example"]).exit_code == 0, (
        "restore failed"
    )
    # restore re-renders WITH the recorded batteries -> the secret line is back, integrity green
    assert "APP_WEBHOOK_SIGNING_SECRET=" in (project / ".env.example").read_text()
    assert runner.invoke(app, ["integrity", "--ci"]).exit_code == 0


def test_eval_repeat_averages_rates(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")
    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)

    calls = {"n": 0}

    def flaky(diff, root, spec, **kw):
        if "clean" in diff:
            return []
        calls["n"] += 1
        # catch on the first run, miss on the second → recall 0.5 over 2 repeats
        return [Finding("a.py", 1, "high", "danger")] if calls["n"] == 1 else []

    monkeypatch.setattr(cli_mod, "_eval_run", flaky)
    result = runner.invoke(
        app, ["eval", "security", "--fixtures", str(tmp_path), "--repeat", "2"]
    )
    assert "recall 0.50" in result.output  # 1 hit / 2 repeats on the single bad fixture


def test_downskill_command_removes_battery(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod

    (tmp_path / "proj").mkdir()
    captured = {}
    monkeypatch.setattr(
        cli_mod,
        "downskill_project",
        lambda project, battery, *, force=False: (
            captured.update(b=battery, f=force) or True
        ),
    )
    result = runner.invoke(app, ["downskill", str(tmp_path / "proj"), "webhooks"])
    assert result.exit_code == 0, result.output
    assert captured == {"b": "webhooks", "f": False}


def test_downskill_command_refusal_exits_1(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.downskill import DownskillError

    (tmp_path / "proj").mkdir()

    def boom(project, battery, *, force=False):
        raise DownskillError(
            "battery 'webhooks' appears in use by: src/x.py. Re-run with --force..."
        )

    monkeypatch.setattr(cli_mod, "downskill_project", boom)
    result = runner.invoke(app, ["downskill", str(tmp_path / "proj"), "webhooks"])
    assert result.exit_code == 1
    assert "in use" in result.output


# ---------------------------------------------------------------------------
# wizard wiring: --alerts flag + alert_channels recorded
# ---------------------------------------------------------------------------


def test_new_records_alert_channels_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # non-TTY in tests → no prompts, defaults
    result = runner.invoke(app, ["new", "Demo"])
    assert result.exit_code == 0, result.output
    answers = (tmp_path / "demo" / ".copier-answers.yml").read_text()
    assert "alert_channels:" in answers and "- webhook" in answers


def test_new_alerts_flag_sets_channels(tmp_path, monkeypatch):
    import yaml

    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "Demo", "--alerts", "slack,pagerduty"])
    assert result.exit_code == 0, result.output
    answers = (tmp_path / "demo" / ".copier-answers.yml").read_text()
    # parse rather than substring-match so an unrelated key containing "webhook" can't fool us
    assert yaml.safe_load(answers)["alert_channels"] == ["slack", "pagerduty"]


def test_new_with_flag_still_resolves_batteries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "Demo", "--with", "graphql"])
    assert result.exit_code == 0, result.output
    answers = (tmp_path / "demo" / ".copier-answers.yml").read_text()
    assert "- graphql" in answers


def test_new_bad_alert_channel_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "Demo", "--alerts", "sms"])
    assert result.exit_code == 1
    assert "unknown alert channel" in result.output


def test_dev_combos_emits_matrix_json():
    result = runner.invoke(app, ["dev-combos", "--strategy", "representative"])
    assert result.exit_code == 0, result.output
    combos = _json.loads(result.output)
    assert isinstance(combos, list)
    names = [c["name"] for c in combos]
    assert names[0] == "baseline" and "full" in names
    full = next(c for c in combos if c["name"] == "full")
    assert full["alerts_flag"] == "--alerts webhook,slack,email,pagerduty"
    assert all(
        {"name", "batteries", "with_flags", "has_react"} <= set(c) for c in combos
    )


def test_dev_combos_broad_is_seeded():
    a = runner.invoke(app, ["dev-combos", "--strategy", "broad", "--seed", "4"])
    b = runner.invoke(app, ["dev-combos", "--strategy", "broad", "--seed", "4"])
    assert a.exit_code == 0 and a.output == b.output


def test_dev_combos_rejects_unknown_strategy():
    result = runner.invoke(app, ["dev-combos", "--strategy", "nope"])
    assert result.exit_code == 1
    assert "unknown strategy" in result.output


def test_review_reads_runtime_key_not_shared_or_eval(monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.cli import app
    from typer.testing import CliRunner

    runner = CliRunner()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_EVAL_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(
        cli_mod, "_review_run", lambda diff, spec, force_agentic=False: []
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert runner.invoke(app, ["review", "security"]).exit_code == 0
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    res = runner.invoke(app, ["review", "security"])
    assert res.exit_code == 0 and "skipped" in res.stdout.lower()


def test_eval_reads_eval_key_not_runtime(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from framework_cli.cli import app

    runner = CliRunner()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_EVAL_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")  # wrong scope for eval
    result = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)])
    assert result.exit_code == 0 and "skipped" in result.stdout.lower()


def test_drift_check_flags_disallowed_tools(tmp_path):
    """drift_check returns one record per call that used tools outside the local whitelist."""
    from framework_cli.review.analyze import Record, drift_check

    records = [
        Record(
            agent="architecture",
            kind="bad",
            case="b1",
            repeat=0,
            seeded_file=None,
            findings=[],
            usage={},
            latency_ms=None,
            stop_reason=None,
            raw_text="",
            turns=3,
            tool_calls=[
                {"turn": 1, "tool": "Read", "input": {"path": "x"}},
                {"turn": 2, "tool": "Bash", "input": {"command": "ls"}},
                {"turn": 3, "tool": "WebFetch", "input": {"url": "..."}},
            ],
        ),
        Record(
            agent="security",
            kind="bad",
            case="b1",
            repeat=0,
            seeded_file=None,
            findings=[],
            usage={},
            latency_ms=None,
            stop_reason=None,
            raw_text="",
            turns=1,
            tool_calls=[],
        ),
    ]
    drifts = drift_check(records)
    assert len(drifts) == 1
    assert drifts[0]["agent"] == "architecture"
    assert set(drifts[0]["disallowed_tools"]) == {"Bash", "WebFetch"}
    assert drifts[0]["counts"] == {"Bash": 1, "WebFetch": 1}


def test_eval_analyze_strict_exits_2_on_drift(tmp_path):
    """eval-analyze --strict exits 2 when any drift is detected."""
    d = tmp_path / "f"
    _write_record(
        d,
        "architecture",
        "bad",
        "b1",
        0,
        findings=[],
        turns=2,
        tool_calls=[{"turn": 1, "tool": "Bash", "input": {"command": "ls"}}],
    )
    result = runner.invoke(app, ["eval-analyze", str(d), "--strict"])
    assert result.exit_code == 2, result.output
    assert "Drift" in result.output or "drift" in result.output


def test_eval_analyze_strict_exits_0_without_drift(tmp_path):
    """eval-analyze --strict exits 0 when no drift is detected (only Read/Grep/Glob used)."""
    d = tmp_path / "f"
    _write_record(
        d,
        "architecture",
        "bad",
        "b1",
        0,
        findings=[],
        turns=2,
        tool_calls=[{"turn": 1, "tool": "Read", "input": {"path": "x"}}],
    )
    result = runner.invoke(app, ["eval-analyze", str(d), "--strict"])
    assert result.exit_code == 0, result.output


def test_eval_analyze_renders_drift_section(tmp_path):
    """The analyze report includes a ## Drift check section listing offending calls."""
    d = tmp_path / "f"
    _write_record(
        d,
        "architecture",
        "bad",
        "b1",
        0,
        findings=[],
        turns=2,
        tool_calls=[{"turn": 1, "tool": "Bash", "input": {"command": "ls"}}],
    )
    result = runner.invoke(app, ["eval-analyze", str(d)])
    assert result.exit_code == 1, (
        result.output
    )  # FAIL on agent's score, not exit code 2
    assert "## Drift check" in result.output
    assert "architecture" in result.output
    assert "Bash" in result.output


def test_load_records_tolerates_missing_audit_dimensions(tmp_path):
    """Records without kind/case/repeat (audit shape) load with sensible defaults."""
    from framework_cli.review.analyze import load_records

    d = tmp_path / "f"
    (d / "security").mkdir(parents=True)
    # Audit-shape record: just agent + findings + telemetry, no kind/case/repeat.
    (d / "security" / "security.json").write_text(
        _json.dumps(
            {
                "agent": "security",
                "findings": [
                    {"path": "a.py", "line": 1, "severity": "high", "message": "x"}
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                "latency_ms": 200,
                "stop_reason": "end_turn",
                "raw_text": "[]",
                "turns": 1,
                "tool_calls": [],
            }
        )
    )
    records = load_records(d)
    assert len(records) == 1
    r = records[0]
    assert r.agent == "security"
    assert r.kind == "current"  # default for audit
    assert r.case == "security"  # default = agent name
    assert r.repeat == 0


def test_eval_analyze_handles_audit_records_gracefully(tmp_path):
    """eval-analyze on an audit-shape dir produces useful output without crashing
    on the absent fixture dimensions (no recall/fp diagnosis sections)."""
    d = tmp_path / "f"
    (d / "security").mkdir(parents=True)
    (d / "security" / "security.json").write_text(
        _json.dumps(
            {
                "agent": "security",
                "findings": [
                    {"path": "a.py", "line": 1, "severity": "high", "message": "x"}
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                "latency_ms": 200,
                "stop_reason": "end_turn",
                "raw_text": "[]",
                "turns": 1,
                "tool_calls": [],
            }
        )
    )
    result = runner.invoke(app, ["eval-analyze", str(d)])
    assert result.exit_code in (0, 1), result.output  # 1 if score FAIL, 0 if PASS
    assert "review-security" in result.output
    assert "## Drift check" in result.output


def test_eval_prepare_tune_outputs_work_items_for_single_agent(tmp_path, monkeypatch):
    """eval-prepare --mode tune --agent security outputs a JSON list of work items
    with diff + system_blocks + user_message + subagent_type + model per (agent,fixture,repeat)."""
    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    import framework_cli.cli as cli_mod

    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)

    result = runner.invoke(
        app,
        [
            "eval-prepare",
            "--mode",
            "tune",
            "--agent",
            "security",
            "--fixtures",
            str(tmp_path),
            "--repeat",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["mode"] == "tune"
    assert data["agents_set"] == ["security"]
    # 2 fixtures × 2 repeats = 4 items
    assert len(data["work_items"]) == 4
    item = data["work_items"][0]
    assert item["agent"] == "security"
    assert item["kind"] in ("bad", "good")
    assert item["case"] in ("b1", "g1")
    assert item["repeat_idx"] in (0, 1)
    assert item["subagent_type"] == "general-purpose"  # security is bundle tier
    assert item["model"] == "claude-sonnet-4-6"
    assert "system_blocks" in item and len(item["system_blocks"]) >= 2
    assert "user_message" in item
    assert "diff" in item
    assert item["tools_allowed"] is None  # bundle: no tools


def test_eval_prepare_tune_uses_explore_for_agentic_agents(tmp_path, monkeypatch):
    """Agentic-tier agents (e.g., architecture) get subagent_type='Explore' + tools_allowed."""
    _make_fixture(tmp_path, "architecture", "bad", "b1", "+++ b/a.py\n", "a.py")

    import framework_cli.cli as cli_mod

    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)

    result = runner.invoke(
        app,
        [
            "eval-prepare",
            "--mode",
            "tune",
            "--agent",
            "architecture",
            "--fixtures",
            str(tmp_path),
            "--repeat",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    item = data["work_items"][0]
    assert item["subagent_type"] == "Explore"
    assert item["model"] == "claude-opus-4-8"
    assert item["tools_allowed"] == ["Read", "Grep", "Glob"]
    assert "root_dir" in item  # agentic items carry the rendered root for tool access


def test_eval_prepare_audit_detects_framework_target(tmp_path, monkeypatch):
    """eval-prepare --mode audit auto-detects 'framework' target when run from the framework repo
    (presence of src/framework_cli/ + pyproject.toml [project].name='framework-cli')."""
    import framework_cli.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff content")
    result = runner.invoke(app, ["eval-prepare", "--mode", "audit"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["mode"] == "audit"
    assert data["target"] == "framework"
    # FRAMEWORK_AGENTS: architecture, security, dependency, test-quality, documentation, application-logic
    assert set(data["agents_set"]) >= {"security", "architecture"}
    assert len(data["work_items"]) == len(data["agents_set"])
    item = data["work_items"][0]
    assert item["kind"] == "current"
    assert item["repeat_idx"] == 0


def test_eval_prepare_audit_explicit_target_override(tmp_path, monkeypatch):
    """--target flag forces the target regardless of cwd signals."""
    import framework_cli.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    result = runner.invoke(
        app, ["eval-prepare", "--mode", "audit", "--target", "framework"]
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["target"] == "framework"


def test_eval_prepare_audit_tolerates_pyproject_formatting_variations(
    tmp_path, monkeypatch
):
    """Whitespace and quote variations in pyproject.toml should still detect framework target."""
    import framework_cli.cli as cli_mod

    # Simulate a different-cwd pyproject with whitespace variation
    fake_repo = tmp_path / "fake"
    (fake_repo / "src" / "framework_cli").mkdir(parents=True)
    (fake_repo / "pyproject.toml").write_text(
        "[project]\n"
        'name   =    "framework-cli"\n'  # extra whitespace, quote variation
        'version = "0.1.0"\n'
    )
    monkeypatch.chdir(fake_repo)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    result = runner.invoke(app, ["eval-prepare", "--mode", "audit"])
    # Even with the whitespace, framework auto-detection should fire.
    # If it doesn't (project-target also missing — no .copier-answers.yml),
    # this would error with "Could not auto-detect target".
    # We just need to confirm the framework path was matched, not the error path.
    assert result.exit_code == 0, result.output
    import json as _j

    data = _j.loads(result.output)
    assert data["target"] == "framework"


def test_eval_finalize_writes_records_runs_analyze_writes_meta(tmp_path):
    """eval-finalize: given workflow results, writes per-call JSON records and a scorecard."""
    out = tmp_path / "scorecard"
    out.mkdir()

    # Simulated workflow result: list of per-call records.
    results = [
        {
            "agent": "security",
            "kind": "bad",
            "case": "b1",
            "repeat_idx": 0,
            "seeded_file": "a.py",
            "findings": [
                {
                    "path": "a.py",
                    "line": 1,
                    "severity": "high",
                    "message": "x",
                    "suggestion": None,
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 10,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            "latency_ms": 200,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
        {
            "agent": "security",
            "kind": "good",
            "case": "g1",
            "repeat_idx": 0,
            "seeded_file": None,
            "findings": [],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 5,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            "latency_ms": 150,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
    ]
    results_file = tmp_path / "results.json"
    results_file.write_text(
        _json.dumps({"results": results, "meta": {"slug": "test", "repeat": 1}})
    )

    result = runner.invoke(
        app,
        [
            "eval-finalize",
            "--mode",
            "tune",
            "--results",
            str(results_file),
            "--out-dir",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    # Per-call records written under findings/
    assert (out / "findings" / "security" / "bad" / "b1__r0.json").is_file()
    assert (out / "findings" / "security" / "good" / "g1__r0.json").is_file()
    # Scorecard generated
    assert (out / "scorecard.md").is_file()
    sc = (out / "scorecard.md").read_text()
    assert "review-security" in sc
    # Thresholds proposal extracted
    assert (out / "thresholds.proposal.yaml").is_file()
    # Apply.md generated
    assert (out / "apply.md").is_file()
    # Meta.json with run metadata
    assert (out / "meta.json").is_file()
    meta = _json.loads((out / "meta.json").read_text())
    assert meta["slug"] == "test"
    assert meta["mode"] == "tune"


def test_eval_finalize_audit_mode_writes_audit_report(tmp_path):
    """In audit mode, eval-finalize writes findings/<agent>.json and audit-report.md."""
    out = tmp_path / "audit"
    out.mkdir()
    results = [
        {
            "agent": "security",
            "findings": [],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 5,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            "latency_ms": 150,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
    ]
    results_file = tmp_path / "results.json"
    results_file.write_text(
        _json.dumps({"results": results, "meta": {"target": "framework"}})
    )

    result = runner.invoke(
        app,
        [
            "eval-finalize",
            "--mode",
            "audit",
            "--results",
            str(results_file),
            "--out-dir",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (out / "findings" / "security.json").is_file()
    assert (out / "audit-report.md").is_file()
