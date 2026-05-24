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
    assert runner.invoke(app, ["integrity", "--allow-drift", "alembic.ini"]).exit_code == 0
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
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
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

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(cli_mod, "_review_run", lambda diff, spec: [Finding("a.py", 1, "high", "bad")])
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 1
    assert "failure" in result.output


def test_review_low_finding_exits_0(monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(cli_mod, "_review_run", lambda diff, spec: [Finding("a.py", 1, "low", "m")])
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 0
    assert "neutral" in result.output


def test_review_infra_error_is_neutral_exit_0(monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def _boom():
        raise RuntimeError("API down")

    monkeypatch.setattr(cli_mod, "_review_diff", _boom)
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 0
    assert "neutral" in result.output or "could not run" in result.output


def test_review_agents_lists_pr_and_push(monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    pr = _json.loads(runner.invoke(app, ["review-agents", "--event", "pull_request"]).output)
    push = _json.loads(runner.invoke(app, ["review-agents", "--event", "push"]).output)
    assert "security" in pr and "documentation" in pr
    assert set(push) == {"security", "data-integrity", "data-lineage", "observability"}


def test_review_dependency_skips_when_no_dep_files(monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
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

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "+++ b/pyproject.toml\n")
    monkeypatch.setattr(cli_mod, "_review_run", lambda diff, spec: [Finding("pyproject.toml", 1, "low", "m")])
    result = runner.invoke(app, ["review", "dependency"])
    assert result.exit_code == 0  # advisory → neutral, never blocks
    assert "neutral" in result.output


def test_review_findings_out_writes_on_normal_path(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(cli_mod, "_review_run", lambda diff, spec: [Finding("a.py", 3, "low", "m")])

    out = tmp_path / "findings" / "security.json"
    result = runner.invoke(app, ["review", "security", "--findings-out", str(out)])
    assert result.exit_code == 0, result.output
    data = _json.loads(out.read_text())
    assert data["agent"] == "review-security"
    assert data["conclusion"] == "neutral"  # low finding → below "high" threshold → neutral
    assert data["findings"] == [
        {"path": "a.py", "line": 3, "severity": "low", "message": "m", "suggestion": None}
    ]


def test_review_findings_out_on_infra_error(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
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
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
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
    d = tmp_path / agent / kind
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.diff").write_text(diff)
    if seeded_file is not None:
        (d / f"{slug}.expect.json").write_text(_json.dumps({"file": seeded_file}))


def test_eval_skips_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["eval", "security"])
    assert result.exit_code == 0
    assert "skipped" in result.output


def test_eval_require_key_fails_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["eval", "security", "--require-key"])
    assert result.exit_code == 1
    assert "required" in result.output


def test_eval_passes_when_agent_catches_bad_and_clean_on_good(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "bad", "b2", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    # catch the bad diffs (a high finding on a.py); stay clean on the good diff (marked "# clean")
    monkeypatch.setattr(
        cli_mod,
        "_eval_run",
        lambda diff, spec: [] if "clean" in diff else [Finding("a.py", 1, "high", "danger")],
    )
    result = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output


def test_eval_fails_when_agent_misses(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "bad", "b2", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "_eval_run", lambda diff, spec: [])  # never catches anything
    result = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_eval_no_fixtures_skipped_unless_required(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)]).exit_code == 0
    r = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path), "--require-fixtures"])
    assert r.exit_code == 1
    assert "no fixtures" in r.output


def test_eval_repeat_zero_is_rejected(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    result = runner.invoke(app, ["eval", "security", "--repeat", "0"])
    assert result.exit_code == 2
    assert "--repeat must be >= 1" in result.output


def test_eval_unknown_agent_errors(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    result = runner.invoke(app, ["eval", "nonsense-agent"])
    assert result.exit_code == 1
    assert "unknown review agent" in result.output


def test_new_with_webhooks_passes_integrity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App", "--with", "webhooks"]).exit_code == 0
    monkeypatch.chdir(tmp_path / "my-app")
    result = runner.invoke(app, ["integrity", "--ci"])
    assert result.exit_code == 0, result.output  # battery-active .env.example checksum matches


def test_new_with_websockets_battery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "My App", "--with", "websockets"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "my-app" / "src" / "my_app" / "routes" / "websockets.py").is_file()


def test_new_without_battery_has_no_websockets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    assert not (tmp_path / "my-app" / "src" / "my_app" / "routes" / "websockets.py").exists()


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

    def fake_upskill(proj, vcs_ref=None, with_batteries=None):
        captured["with_batteries"] = with_batteries
        return True

    monkeypatch.setattr(cli_mod, "upskill_project", fake_upskill)

    from framework_cli import batteries as bat

    bat._BATTERIES["_x"] = bat.BatterySpec("_x", "x")
    try:
        result = runner.invoke(app, ["upskill", str(project), "--with", "_x"])
    finally:
        del bat._BATTERIES["_x"]
    assert result.exit_code == 0, result.output
    assert captured["with_batteries"] == ["_x", "websockets"]  # union, sorted


def test_restore_env_example_preserves_webhooks_secret(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App", "--with", "webhooks"]).exit_code == 0
    project = tmp_path / "my-app"
    env = project / ".env.example"
    env.write_text(env.read_text().replace("APP_WEBHOOK_SIGNING_SECRET=", "APP_WEBHOOK_SIGNING_SECRET=tampered"))
    monkeypatch.chdir(project)
    assert runner.invoke(app, ["restore", ".env.example"]).exit_code == 0, "restore failed"
    # restore re-renders WITH the recorded batteries -> the secret line is back, integrity green
    assert "APP_WEBHOOK_SIGNING_SECRET=" in (project / ".env.example").read_text()
    assert runner.invoke(app, ["integrity", "--ci"]).exit_code == 0


def test_eval_repeat_averages_rates(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

    calls = {"n": 0}

    def flaky(diff, spec):
        if "clean" in diff:
            return []
        calls["n"] += 1
        # catch on the first run, miss on the second → recall 0.5 over 2 repeats
        return [Finding("a.py", 1, "high", "danger")] if calls["n"] == 1 else []

    monkeypatch.setattr(cli_mod, "_eval_run", flaky)
    result = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path), "--repeat", "2"])
    assert "recall 0.50" in result.output  # 1 hit / 2 repeats on the single bad fixture
