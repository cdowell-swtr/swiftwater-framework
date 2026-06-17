import json as _json
from pathlib import Path

import pytest
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
        lambda diff, spec, force_agentic=False, **kw: [
            Finding("a.py", 1, "high", "bad")
        ],
    )
    result = runner.invoke(app, ["review", "security", "--backend", "api"])
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
        lambda diff, spec, force_agentic=False, **kw: [Finding("a.py", 1, "low", "m")],
    )
    result = runner.invoke(app, ["review", "security", "--backend", "api"])
    assert result.exit_code == 0
    assert "neutral" in result.output


def test_review_infra_error_is_neutral_exit_0(monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def _boom():
        raise RuntimeError("API down")

    monkeypatch.setattr(cli_mod, "_review_diff", _boom)
    result = runner.invoke(app, ["review", "security", "--backend", "api"])
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

    def _should_not_run(diff, spec, **kw):
        raise AssertionError("LLM must not run when not triggered")

    monkeypatch.setattr(cli_mod, "_review_run", _should_not_run)
    result = runner.invoke(app, ["review", "dependency", "--backend", "api"])
    assert result.exit_code == 0
    assert "not triggered" in result.output


def test_bare_upskill_is_blocked_with_a_battery_message(tmp_path):
    from typer.testing import CliRunner

    from framework_cli.cli import app

    (tmp_path / ".copier-answers.yml").write_text("batteries: []\n")
    result = CliRunner().invoke(app, ["upskill", str(tmp_path)])
    assert result.exit_code != 0
    assert "at least one `--with`" in result.output
    assert "framework upgrade" in result.output


def test_upgrade_success_prints_commit_after_instruction_last(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    from framework_cli.upgrade import UpgradeOutcome

    monkeypatch.setattr(
        cli,
        "upgrade_project",
        lambda project, to=None: UpgradeOutcome("green", "v0.3.0"),
    )
    (tmp_path / "x").mkdir()
    result = CliRunner().invoke(cli.app, ["upgrade", str(tmp_path / "x")])
    assert result.exit_code == 0
    # The commit/push instruction is the final thing the user sees.
    tail = result.output.strip().splitlines()[-1]
    assert "git" in tail and "commit" in tail and "push" in tail


def test_upgrade_already_current_is_a_noop(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    from framework_cli.upgrade import UpgradeOutcome

    monkeypatch.setattr(
        cli,
        "upgrade_project",
        lambda project, to=None: UpgradeOutcome("already-current", "v0.3.0"),
    )
    (tmp_path / "x").mkdir()
    result = CliRunner().invoke(cli.app, ["upgrade", str(tmp_path / "x")])
    assert result.exit_code == 0
    assert "up to date" in result.output


def test_upgrade_red_exits_nonzero(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    from framework_cli.upgrade import UpgradeOutcome

    monkeypatch.setattr(
        cli, "upgrade_project", lambda project, to=None: UpgradeOutcome("red", "v0.3.0")
    )
    (tmp_path / "x").mkdir()
    result = CliRunner().invoke(cli.app, ["upgrade", str(tmp_path / "x")])
    assert result.exit_code != 0
    assert "task test" in result.output or "failed" in result.output


def test_check_points_at_upgrade(monkeypatch):
    from typer.testing import CliRunner

    import framework_cli.cli as cli

    monkeypatch.setattr(cli, "installed_framework_version", lambda: "0.2.0")
    monkeypatch.setattr(cli, "latest_release", lambda: "v0.3.0")
    result = CliRunner().invoke(cli.app, ["check"])
    assert "framework upgrade" in result.output
    assert "framework upskill" not in result.output


def test_review_dependency_runs_when_dep_file_changed(monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "+++ b/pyproject.toml\n")
    monkeypatch.setattr(
        cli_mod,
        "_review_run",
        lambda diff, spec, force_agentic=False, **kw: [
            Finding("pyproject.toml", 1, "low", "m")
        ],
    )
    result = runner.invoke(app, ["review", "dependency", "--backend", "api"])
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
        lambda diff, spec, force_agentic=False, **kw: [Finding("a.py", 3, "low", "m")],
    )

    out = tmp_path / "findings" / "security.json"
    result = runner.invoke(
        app, ["review", "security", "--findings-out", str(out), "--backend", "api"]
    )
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
            "acknowledged": None,
            "stale": None,
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
    result = runner.invoke(
        app, ["review", "security", "--findings-out", str(out), "--backend", "api"]
    )
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


# ---------------------------------------------------------------------------
# R1 cost-safety tests: presence ≠ consent; no backend = skip/error
# ---------------------------------------------------------------------------


def test_eval_skip_neutral_no_intent(monkeypatch):
    """R1: key present but no intent (no --backend, no env, no config) → skip exit 0.

    Bare `framework eval` must NEVER spend when only a key is present — explicit
    intent is required (--backend, FRAMEWORK_REVIEW_BACKEND, or review.toml).
    """
    import framework_cli.cli as climod

    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "sk-x")
    monkeypatch.delenv("FRAMEWORK_REVIEW_BACKEND", raising=False)
    # Ensure no review.toml config provides intent
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": None, "reason": "no-intent", "intent": None}
        )(),
    )
    result = runner.invoke(app, ["eval", "security"])
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output
    assert "backend" in result.output


def test_eval_require_key_errors_no_backend(monkeypatch):
    """R1: --require-key with no backend resolved → exit 1, not skip."""
    import framework_cli.cli as climod

    monkeypatch.delenv("ANTHROPIC_EVAL_API_KEY", raising=False)
    monkeypatch.delenv("FRAMEWORK_REVIEW_BACKEND", raising=False)
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": None, "reason": "no-intent", "intent": None}
        )(),
    )
    result = runner.invoke(app, ["eval", "security", "--require-key"])
    assert result.exit_code == 1, result.output
    assert "required" in result.output


def test_eval_honors_env_var(tmp_path, monkeypatch):
    """FRAMEWORK_REVIEW_BACKEND=subagent is explicit intent → resolves + runs (not skip)."""
    import framework_cli.cli as climod

    monkeypatch.delenv("ANTHROPIC_EVAL_API_KEY", raising=False)
    monkeypatch.setenv("FRAMEWORK_REVIEW_BACKEND", "subagent")

    class _StubMessages:
        def create(self, **kwargs):
            from framework_cli.review.backend import Message, TextBlock, Usage

            return Message(
                content=[TextBlock(text="[]")], usage=Usage(), stop_reason="end_turn"
            )

    class _StubBackend:
        messages = _StubMessages()

    stub = _StubBackend()
    made: list = []

    def _capture_make_backend(name, key_env):
        made.append(name)
        return stub

    monkeypatch.setattr(climod, "_make_backend", _capture_make_backend)
    monkeypatch.setattr(climod, "realize_cached", _fake_realize_cached)
    # Resolve subagent via env var — stub so `claude` availability is not a concern
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": "subagent", "reason": "resolved", "intent": "subagent"}
        )(),
    )
    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    result = runner.invoke(
        app,
        ["eval", "security", "--fixtures", str(tmp_path)],
    )
    assert "skipped" not in result.output, (
        "env-var intent must not be treated as no-intent"
    )
    assert result.exit_code in (0, 1), result.output  # ran (0=PASS, 1=FAIL)
    assert made == ["subagent"]


def test_review_skip_neutral_no_intent(monkeypatch):
    """R1: review with no backend intent → skip-neutral (exit 0, neutral check posted).

    review is the CI/auto command; it must NEVER block CI when no backend is enabled.
    """
    import framework_cli.cli as climod

    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": None, "reason": "no-intent", "intent": None}
        )(),
    )
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 0, result.output
    # skip-neutral: output mentions skipped and the reason
    assert "skipped" in result.output
    assert "no-intent" in result.output


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
    result = runner.invoke(
        app, ["eval", "security", "--fixtures", str(tmp_path), "--backend", "api"]
    )
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
    result = runner.invoke(
        app, ["eval", "security", "--fixtures", str(tmp_path), "--backend", "api"]
    )
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_eval_unparseable_response_is_non_fatal(tmp_path, monkeypatch):
    """A FindingsParseError from one agent's response must NOT crash the whole
    eval run (regression: a malformed contracts response with trailing data
    crashed the paid eval). It is scored as no findings for that repeat — a miss
    on a bad fixture — and the run completes with a normal verdict, not a
    traceback. Only an openai.APIError (litellm's base) aborts (scores unreliable)."""
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import FindingsParseError

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)

    def boom(diff, root, spec, **kw):
        raise FindingsParseError("Extra data: line 1 column 17 (char 16)")

    monkeypatch.setattr(cli_mod, "_eval_run", boom)
    result = runner.invoke(
        app, ["eval", "security", "--fixtures", str(tmp_path), "--backend", "api"]
    )
    # Handled gracefully — the parse error must not bubble out (a clean
    # typer.Exit(1) surfaces as SystemExit on the result, which is fine).
    assert not isinstance(result.exception, FindingsParseError), (
        f"crashed instead of handling: {result.exception!r}"
    )
    # Bad fixture scored as a miss (no findings) -> FAIL verdict, exit 1.
    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output
    # The operator-visible warning must be emitted (CliRunner mixes stderr in).
    assert "unparseable" in result.output


def test_eval_findings_out_marks_parse_error(tmp_path, monkeypatch):
    """On a FindingsParseError the --findings-out record must carry a parse_error
    marker, so eval-analyze can distinguish an unparseable response (scored as
    no findings) from a genuine clean run — both otherwise show zero findings."""
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import FindingsParseError

    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)

    def boom(diff, root, spec, **kw):
        raise FindingsParseError("Extra data: line 1 column 17 (char 16)")

    monkeypatch.setattr(cli_mod, "_eval_run", boom)
    out = tmp_path / "findings"
    runner.invoke(
        app,
        [
            "eval",
            "security",
            "--fixtures",
            str(tmp_path),
            "--findings-out",
            str(out),
            "--backend",
            "api",
        ],
    )
    rec = _json.loads((out / "security" / "good" / "g1__r0.json").read_text())
    assert rec["findings"] == []
    assert "Extra data" in rec.get("parse_error", "")


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
            "--backend",
            "api",
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
            "acknowledged": None,
            "stale": None,
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

    def _fake_run(diff, root, spec, *, report=None, backend=None):
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
        [
            "eval",
            "security",
            "--fixtures",
            str(tmp_path),
            "--findings-out",
            str(out),
            "--backend",
            "api",
        ],
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


def test_eval_aborts_loudly_on_litellm_api_error(tmp_path, monkeypatch):
    """The API path routes through litellm now: a non-rate-limit litellm API error
    (e.g. auth/credit/5xx) must abort with Exit(3), not crash uncaught."""
    import litellm

    import framework_cli.cli as cli_mod

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)

    def _api_wall(diff, root, spec, **kw):
        raise litellm.exceptions.AuthenticationError(
            "invalid api key", llm_provider="anthropic", model="claude-sonnet-4-6"
        )

    monkeypatch.setattr(cli_mod, "_eval_run", _api_wall)
    result = runner.invoke(
        app, ["eval", "security", "--fixtures", str(tmp_path), "--backend", "api"]
    )
    assert result.exit_code == 3, result.output
    assert "ABORTED" in result.output


def test_eval_no_fixtures_skipped_unless_required(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    assert (
        runner.invoke(
            app,
            ["eval", "security", "--fixtures", str(tmp_path), "--backend", "api"],
        ).exit_code
        == 0
    )
    r = runner.invoke(
        app,
        [
            "eval",
            "security",
            "--fixtures",
            str(tmp_path),
            "--require-fixtures",
            "--backend",
            "api",
        ],
    )
    assert r.exit_code == 1
    assert "no fixtures" in r.output


def test_eval_repeat_zero_is_rejected(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    result = runner.invoke(
        app, ["eval", "security", "--repeat", "0", "--backend", "api"]
    )
    assert result.exit_code == 2
    assert "--repeat must be >= 1" in result.output


def test_eval_unknown_agent_errors(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    result = runner.invoke(app, ["eval", "nonsense-agent", "--backend", "api"])
    assert result.exit_code == 1
    assert "unknown review agent" in result.output


# ---------------------------------------------------------------------------
# --backend flag tests
# ---------------------------------------------------------------------------


def test_make_backend_factory():
    import framework_cli.cli as climod
    from framework_cli.review.backend import ApiBackend, SubagentBackend

    # subagent: no key / SDK needed
    assert isinstance(
        climod._make_backend("subagent", "ANTHROPIC_RUNTIME_API_KEY"), SubagentBackend
    )
    # api: constructs ApiBackend directly (no SDK instantiation, just stores key)
    assert isinstance(
        climod._make_backend("api", "ANTHROPIC_RUNTIME_API_KEY"), ApiBackend
    )


def test_eval_subagent_backend_flows_without_key(tmp_path, monkeypatch):
    """--backend subagent must not skip on a missing ANTHROPIC_EVAL_API_KEY and
    must pass the SubagentBackend through to _eval_run without touching the key.

    Design choice: we test _eval_run directly (not via CliRunner + real fixtures)
    because realizing eval fixtures requires rendering a copier template, which is
    heavy and unrelated to the backend-selection concern. Instead we call
    _eval_run(diff, root, spec, backend=stub) and assert (a) it reaches the stub
    backend's messages.create, (b) exit 0 via the CLI with --backend subagent
    and no key set.
    """
    import framework_cli.cli as climod

    recorded: dict = {}

    # Minimal stub backend whose messages.create records the call and returns an
    # empty-findings Message so parse_findings sees "[]" text.
    class _StubMessages:
        def create(self, **kwargs):
            recorded["called"] = True
            from framework_cli.review.backend import Message, TextBlock, Usage

            return Message(
                content=[TextBlock(text="[]")],
                usage=Usage(),
                stop_reason="end_turn",
            )

    class _StubBackend:
        messages = _StubMessages()

    stub = _StubBackend()

    spec = climod.get_agent("security")
    findings = climod._eval_run("+++ b/a.py\n", tmp_path, spec, backend=stub)
    assert recorded.get("called"), "_eval_run did not call backend.messages.create"
    assert findings == []

    # CLI path: --backend subagent must not exit early on a missing key
    _make_backend_calls: list = []

    def _capture_make_backend(name, key_env):
        _make_backend_calls.append(name)
        return stub

    monkeypatch.delenv("ANTHROPIC_EVAL_API_KEY", raising=False)
    monkeypatch.setattr(climod, "_make_backend", _capture_make_backend)
    monkeypatch.setattr(climod, "realize_cached", _fake_realize_cached)
    # Stub resolution so it resolves subagent regardless of whether `claude` is on PATH
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": "subagent", "reason": "resolved", "intent": "subagent"}
        )(),
    )
    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    result = runner.invoke(
        app,
        [
            "eval",
            "security",
            "--fixtures",
            str(tmp_path),
            "--backend",
            "subagent",
        ],
    )
    assert result.exit_code in (0, 1), result.output  # 0=PASS, 1=FAIL; both mean it ran
    assert "skipped" not in result.output, (
        "subagent backend must not skip on missing key"
    )
    assert _make_backend_calls == ["subagent"], (
        f"_make_backend was called with {_make_backend_calls!r}, expected ['subagent']"
    )


def test_review_subagent_backend_skips_key_check(monkeypatch):
    """--backend subagent must not early-exit on a missing ANTHROPIC_RUNTIME_API_KEY."""
    import framework_cli.cli as climod
    from framework_cli.review.backend import Message, TextBlock, Usage

    class _StubMessages:
        def create(self, **kwargs):
            return Message(
                content=[TextBlock(text="[]")],
                usage=Usage(),
                stop_reason="end_turn",
            )

    class _StubBackend:
        messages = _StubMessages()

    stub = _StubBackend()
    _make_backend_calls: list = []

    def _capture_make_backend(name, key_env):
        _make_backend_calls.append(name)
        return stub

    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(climod, "_make_backend", _capture_make_backend)
    monkeypatch.setattr(
        climod, "_review_diff", lambda: "+++ b/src/app/main.py\n# change\n"
    )
    # Stub resolution so it resolves subagent regardless of whether `claude` is on PATH
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": "subagent", "reason": "resolved", "intent": "subagent"}
        )(),
    )
    result = runner.invoke(app, ["review", "security", "--backend", "subagent"])
    assert "skipped" not in result.output.lower(), (
        "subagent backend must not skip on missing key"
    )
    assert _make_backend_calls == ["subagent"], (
        f"_make_backend was called with {_make_backend_calls!r}, expected ['subagent']"
    )


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
        app,
        [
            "eval",
            "security",
            "--fixtures",
            str(tmp_path),
            "--repeat",
            "2",
            "--backend",
            "api",
        ],
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
    """review uses RUNTIME_KEY for API availability; ANTHROPIC_API_KEY is not honoured."""
    import framework_cli.cli as cli_mod
    from framework_cli.cli import app
    from typer.testing import CliRunner

    runner = CliRunner()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_EVAL_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(
        cli_mod, "_review_run", lambda diff, spec, force_agentic=False, **kw: []
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    # --backend api + RUNTIME_KEY present → should run (not skip)
    assert runner.invoke(app, ["review", "security", "--backend", "api"]).exit_code == 0
    # Only ANTHROPIC_API_KEY set (wrong scope) → should skip (api-unavailable)
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    res = runner.invoke(app, ["review", "security", "--backend", "api"])
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
    # Audit-mode fields default to None when absent (legacy/tune records).
    assert r.review_mode is None
    assert r.base_sha is None
    assert r.base_baseline is None


def test_load_records_carries_audit_mode_metadata(tmp_path):
    """Records with review_mode/base_sha/base_baseline preserve them through load.

    Audit baselines persist these fields per-agent so future delta-discovery
    + analysis tooling can reason about each agent's mode without parsing the
    raw JSON. The Record dataclass round-trips them.
    """
    from framework_cli.review.analyze import load_records

    d = tmp_path / "f"
    (d / "security").mkdir(parents=True)
    (d / "security" / "security.json").write_text(
        _json.dumps(
            {
                "agent": "security",
                "findings": [],
                "review_mode": "delta",
                "base_sha": "abc1234567890",
                "base_baseline": "audit-2026-05-30-2446de8",
                "raw_text": "[]",
            }
        )
    )
    records = load_records(d)
    assert len(records) == 1
    r = records[0]
    assert r.review_mode == "delta"
    assert r.base_sha == "abc1234567890"
    assert r.base_baseline == "audit-2026-05-30-2446de8"


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


def test_eval_analyze_scorecard_dir_writes_artifacts(tmp_path):
    """eval-analyze --scorecard-dir writes the tune artifact set: scorecard.md,
    thresholds.proposal.yaml, apply.md, meta.json into the given directory.

    This is the surviving way to produce scored tune artifacts from per-call
    records written by `framework eval --findings-out`.
    """
    findings = tmp_path / "findings"
    out = tmp_path / "scorecard_out"

    # Write two per-call records directly into <findings>/security/bad/ and good/.
    _write_record(
        findings,
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
    _write_record(findings, "security", "good", "g1", 0, findings=[])

    result = runner.invoke(
        app,
        ["eval-analyze", str(findings), "--scorecard-dir", str(out)],
    )
    assert result.exit_code in (0, 1), result.output  # 1 if score FAIL

    assert (out / "scorecard.md").is_file(), "scorecard.md missing"
    assert (out / "thresholds.proposal.yaml").is_file(), (
        "thresholds.proposal.yaml missing"
    )
    assert (out / "apply.md").is_file(), "apply.md missing"
    assert (out / "meta.json").is_file(), "meta.json missing"

    meta = _json.loads((out / "meta.json").read_text())
    assert meta["subagent_call_count"] == 2
    assert meta["agent_count"] == 1
    assert "drift_detected" in meta

    # Pin the non-trivial logic: the scorecard renders the agent, and the yaml
    # block is actually extracted into thresholds.proposal.yaml (not an empty file).
    assert "review-security" in (out / "scorecard.md").read_text()
    prop = (out / "thresholds.proposal.yaml").read_text()
    assert "security:" in prop and "recall_min:" in prop


def test_resolve_audit_base_snapshot_flag_forces_snapshot(tmp_path):
    """snapshot_flag=True → ("snapshot", None, None) regardless of available baselines."""
    from framework_cli.cli import _resolve_audit_base

    # Seed a matching baseline that would otherwise be picked up.
    bd = tmp_path / "audit-2026-01-01-x"
    bd.mkdir()
    (bd / "meta.json").write_text(
        '{"target": "framework", "git_sha": "shaX", "agents": ["security"]}'
    )

    mode, sha, name = _resolve_audit_base(
        "security",
        "framework",
        snapshot_flag=True,
        since_arg=None,
        scorecards_root=tmp_path,
    )
    assert mode == "snapshot"
    assert sha is None
    assert name is None


def test_resolve_audit_base_since_as_baseline_dir_delta_when_agent_in_baseline(
    tmp_path,
):
    """since_arg points at a baseline dir AND agent is in that baseline → delta vs its SHA."""
    from framework_cli.cli import _resolve_audit_base

    bd = tmp_path / "audit-2026-01-01-x"
    bd.mkdir()
    (bd / "meta.json").write_text(
        '{"target": "framework", "git_sha": "shaX", "agents": ["security", "architecture"]}'
    )

    mode, sha, name = _resolve_audit_base(
        "security",
        "framework",
        snapshot_flag=False,
        since_arg=str(bd),
        scorecards_root=tmp_path,
    )
    assert mode == "delta"
    assert sha == "shaX"
    assert name == "audit-2026-01-01-x"


def test_resolve_audit_base_since_as_baseline_dir_snapshot_fallback_when_agent_not_in_baseline(
    tmp_path,
):
    """since_arg points at a baseline dir but agent wasn't in it → snapshot fallback."""
    from framework_cli.cli import _resolve_audit_base

    bd = tmp_path / "audit-2026-01-01-x"
    bd.mkdir()
    (bd / "meta.json").write_text(
        '{"target": "framework", "git_sha": "shaX", "agents": ["security"]}'
    )

    mode, sha, name = _resolve_audit_base(
        "documentation",  # not in the baseline
        "framework",
        snapshot_flag=False,
        since_arg=str(bd),
        scorecards_root=tmp_path,
    )
    assert mode == "snapshot"
    assert sha is None
    assert name is None


def test_resolve_audit_base_since_as_ref_resolves_via_rev_parse(tmp_path, monkeypatch):
    """since_arg looks like a ref (not a baseline dir) → resolve via git rev-parse,
    use the resolved SHA for every agent (no per-agent presence question)."""
    import subprocess

    from framework_cli.cli import _resolve_audit_base

    def fake_run(args, **kwargs):
        # Pretend "v1.0" resolves to "abc123..."
        if args[:3] == ["git", "rev-parse", "--verify"]:
            assert args[3] == "v1.0^{commit}"
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="abc1234567890\n", stderr=""
            )
        raise AssertionError(f"unexpected subprocess call: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    mode, sha, name = _resolve_audit_base(
        "security",
        "framework",
        snapshot_flag=False,
        since_arg="v1.0",
        scorecards_root=tmp_path,
    )
    assert mode == "delta"
    assert sha == "abc1234567890"
    assert name is None  # ref form has no baseline-dir name


def test_resolve_audit_base_baseline_dir_meta_unreadable_raises_valueerror(
    tmp_path, monkeypatch
):
    """If is_baseline_dir passes but meta.json is gone/corrupt by the time the
    baseline-dir branch re-reads it (a TOCTOU window), _resolve_audit_base raises a
    clean ValueError — not a raw OSError/JSONDecodeError. The caller only wraps
    ValueError into the `audit:` error line + exit 2.
    """
    from framework_cli.cli import _resolve_audit_base
    from framework_cli.review import baselines

    bd = tmp_path / "audit-2026-01-01-x"
    bd.mkdir()
    # Simulate the pre-check having seen a valid baseline, but meta.json is
    # absent when the branch re-reads it for the `agents` list.
    monkeypatch.setattr(baselines, "is_baseline_dir", lambda p: True)

    with pytest.raises(ValueError, match="meta.json"):
        _resolve_audit_base(
            "security",
            "framework",
            snapshot_flag=False,
            since_arg=str(bd),
            scorecards_root=tmp_path,
        )


def test_resolve_audit_base_baseline_dir_sha_none_raises_valueerror(
    tmp_path, monkeypatch
):
    """If the agent is in the baseline but its SHA can't be read (None — e.g. the
    file changed under us), _resolve_audit_base raises a clear ValueError rather
    than silently returning ('delta', None, ...), which would later fail in
    `git diff None...HEAD` with a confusing message.
    """
    from framework_cli.cli import _resolve_audit_base
    from framework_cli.review import baselines

    bd = tmp_path / "audit-2026-01-01-x"
    bd.mkdir()
    (bd / "meta.json").write_text(
        '{"target": "framework", "git_sha": "shaX", "agents": ["security"]}'
    )
    monkeypatch.setattr(baselines, "read_baseline_sha", lambda p: None)

    with pytest.raises(ValueError, match="git_sha"):
        _resolve_audit_base(
            "security",
            "framework",
            snapshot_flag=False,
            since_arg=str(bd),
            scorecards_root=tmp_path,
        )


def test_resolve_audit_base_since_as_bad_ref_raises(tmp_path, monkeypatch):
    """since_arg is a ref but git rev-parse fails → ValueError (caller exits 2)."""
    import subprocess

    from framework_cli.cli import _resolve_audit_base

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args, returncode=128, stdout="", stderr="fatal: bad revision"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ValueError) as exc:
        _resolve_audit_base(
            "security",
            "framework",
            snapshot_flag=False,
            since_arg="nope",
            scorecards_root=tmp_path,
        )
    assert "nope" in str(exc.value)


def test_resolve_audit_base_autodiscover_finds_latest_baseline(tmp_path):
    """No flags → auto-discover the newest baseline that included this agent."""
    from framework_cli.cli import _resolve_audit_base

    bd = tmp_path / "audit-2026-03-01-x"
    bd.mkdir()
    (bd / "meta.json").write_text(
        '{"target": "framework", "git_sha": "shaNew", "agents": ["security"]}'
    )

    mode, sha, name = _resolve_audit_base(
        "security",
        "framework",
        snapshot_flag=False,
        since_arg=None,
        scorecards_root=tmp_path,
    )
    assert mode == "delta"
    assert sha == "shaNew"
    assert name == "audit-2026-03-01-x"


def test_resolve_audit_base_autodiscover_falls_back_to_snapshot_when_no_baseline(
    tmp_path,
):
    """No flags + no prior baseline for this agent → snapshot fallback."""
    from framework_cli.cli import _resolve_audit_base

    mode, sha, name = _resolve_audit_base(
        "security",
        "framework",
        snapshot_flag=False,
        since_arg=None,
        scorecards_root=tmp_path,
    )
    assert mode == "snapshot"
    assert sha is None
    assert name is None


def test_gate_finalize_writes_marker_pass(tmp_path):
    """gate-mode finalize writes marker.json with verdict=PASS when no high+ findings."""
    from framework_cli.cli import _finalize_gate

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()
    records = [
        {
            "agent": "security",
            "findings": [],
            "usage": {},
            "latency_ms": None,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
    ]
    meta = {"mode": "gate", "staged_hash": "sha256:abc", "agents_set": ["security"]}
    verdict = _finalize_gate(records, findings_dir, out, meta)
    assert verdict == "PASS"
    marker_path = out.parent / "marker.json"
    assert marker_path.is_file()
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "PASS"
    assert marker["staged_hash"] == "sha256:abc"
    assert marker["agents_run"] == ["security"]
    assert marker["drift_detected"] is False


def test_gate_finalize_writes_marker_fail_on_high_finding(tmp_path):
    """A high-severity finding on security (block_threshold='high') → verdict=FAIL."""
    from framework_cli.cli import _finalize_gate

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()
    records = [
        {
            "agent": "security",
            "findings": [
                {
                    "path": "a.py",
                    "line": 1,
                    "severity": "high",
                    "message": "secret",
                    "suggestion": None,
                },
            ],
            "usage": {},
            "latency_ms": None,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
    ]
    meta = {"mode": "gate", "staged_hash": "sha256:abc", "agents_set": ["security"]}
    verdict = _finalize_gate(records, findings_dir, out, meta)
    assert verdict == "FAIL"
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "FAIL"


def test_gate_finalize_advisory_agent_findings_dont_block_gate(tmp_path):
    """Advisory agents (block_threshold=None — documentation, dependency,
    usability) surface findings but must NEVER cause the gate to FAIL.

    Regression guard for the bug where _finalize_gate reused flags() — which
    for None-threshold agents returns True on any finding (intentional for
    eval-scoring's surfacing metrics) — and turned every advisory-agent
    finding into a gate FAIL. Documented as the root cause of the
    documentation-INFO gate-iteration noise on the audit-semantics branch.
    """
    from framework_cli.cli import _finalize_gate

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()
    # documentation has block_threshold=None (advisory) per the registry.
    records = [
        {
            "agent": "documentation",
            "findings": [
                {
                    "path": "a.py",
                    "line": 1,
                    "severity": "high",
                    "message": "docstring missing",
                    "suggestion": None,
                },
                {
                    "path": "b.py",
                    "line": 2,
                    "severity": "info",
                    "message": "comment could be clearer",
                    "suggestion": None,
                },
            ],
            "usage": {},
            "latency_ms": None,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
    ]
    meta = {
        "mode": "gate",
        "staged_hash": "sha256:abc",
        "agents_set": ["documentation"],
    }
    verdict = _finalize_gate(records, findings_dir, out, meta)
    # Advisory findings surface in the report but do NOT block.
    assert verdict == "PASS", f"Advisory agent findings caused FAIL; verdict={verdict}"
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "PASS", (
        f"Advisory agent findings caused FAIL; marker={marker}"
    )


def test_gate_finalize_marks_drift_detected(tmp_path):
    """A tool_calls entry using a disallowed tool → drift_detected: true in marker."""
    from framework_cli.cli import _finalize_gate

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()
    records = [
        {
            "agent": "architecture",
            "findings": [],
            "usage": {},
            "latency_ms": None,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 2,
            "tool_calls": [{"turn": 1, "tool": "Bash", "input": {"command": "ls"}}],
        },
    ]
    meta = {"mode": "gate", "staged_hash": "sha256:abc", "agents_set": ["architecture"]}
    verdict = _finalize_gate(records, findings_dir, out, meta)
    assert verdict == "FAIL"
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["drift_detected"] is True
    assert marker["verdict"] == "FAIL"


def test_gate_finalize_regrade_skips_dispatch(tmp_path):
    """A regrade-mode payload re-flags existing findings against current thresholds
    without invoking subagents."""
    from framework_cli.cli import _finalize_gate

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()
    findings_dir.joinpath("security.json").write_text(
        _json.dumps(
            {
                "agent": "security",
                "findings": [],
                "usage": {},
                "latency_ms": None,
                "stop_reason": "end_turn",
                "raw_text": "[]",
                "turns": 1,
                "tool_calls": [],
            }
        )
    )
    meta = {"mode": "regrade", "staged_hash": "sha256:abc"}
    verdict = _finalize_gate([], findings_dir, out, meta)
    assert verdict == "PASS"  # empty findings → PASS
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "PASS"  # empty findings → PASS


def _seed_gate_decision(root: Path, decision_id: str, status: str) -> None:
    """Write a minimal decision markdown file under root/docs/superpowers/decisions/."""
    decisions_dir = root / "docs" / "superpowers" / "decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)
    (decisions_dir / f"{decision_id}.md").write_text(
        f"---\n"
        f"id: {decision_id}\n"
        f"status: {status}\n"
        f"agents:\n  - security\n"
        f"concern: test concern\n"
        f"premise: test premise\n"
        f"---\n\nBody text.\n"
    )


def test_gate_finalize_acknowledged_active_decision_passes(tmp_path, monkeypatch):
    """A high-severity finding with acknowledged: <id> where <id> is ACTIVE
    (status=accepted) → the finding is excluded from the blocking set → verdict PASS.
    The integrity guard requires the cited id to be active; here it is, so it passes.
    """
    from framework_cli.cli import _finalize_gate

    monkeypatch.chdir(tmp_path)
    _seed_gate_decision(tmp_path, "DEC-0001", "accepted")

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()
    records = [
        {
            "agent": "security",
            "findings": [
                {
                    "path": "a.py",
                    "line": 1,
                    "severity": "high",
                    "message": "known issue covered by DEC-0001",
                    "suggestion": None,
                    "acknowledged": "DEC-0001",
                },
            ],
            "usage": {},
            "latency_ms": None,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
    ]
    meta = {"mode": "gate", "staged_hash": "sha256:abc", "agents_set": ["security"]}
    verdict = _finalize_gate(records, findings_dir, out, meta)
    assert verdict == "PASS", (
        f"Acknowledged-active finding should not block; verdict={verdict}"
    )
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "PASS", (
        f"Acknowledged-active finding should not block; marker={marker}"
    )
    # The raw finding record must still be written (visible in report).
    findings_file = out / "findings" / "security.json"
    assert findings_file.is_file()
    record = _json.loads(findings_file.read_text())
    assert len(record["findings"]) == 1
    assert record["findings"][0]["acknowledged"] == "DEC-0001"


def test_gate_finalize_acknowledged_but_stale_decision_blocks(tmp_path, monkeypatch):
    """A finding tagged acknowledged: <active-id> AND stale: <id> must still block.
    `stale` signals the decision's premise no longer holds, so the acknowledgement
    is void even though the cited id is active → verdict FAIL. (Without the stale
    check, a contradictory acknowledged+stale pair would silently pass.)
    """
    from framework_cli.cli import _finalize_gate

    monkeypatch.chdir(tmp_path)
    _seed_gate_decision(tmp_path, "DEC-0001", "accepted")

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()
    records = [
        {
            "agent": "security",
            "findings": [
                {
                    "path": "a.py",
                    "line": 1,
                    "severity": "high",
                    "message": "premise no longer holds — re-raised",
                    "suggestion": None,
                    "acknowledged": "DEC-0001",
                    "stale": "DEC-0001",
                },
            ],
            "usage": {},
            "latency_ms": None,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
    ]
    meta = {"mode": "gate", "staged_hash": "sha256:abc", "agents_set": ["security"]}
    verdict = _finalize_gate(records, findings_dir, out, meta)
    assert verdict == "FAIL", (
        f"Acknowledged-but-stale finding must still block; verdict={verdict}"
    )
    marker = _json.loads((out.parent / "marker.json").read_text())
    assert marker["verdict"] == "FAIL", (
        f"Acknowledged-but-stale finding must still block; marker={marker}"
    )


def test_gate_finalize_acknowledged_inactive_decision_blocks(tmp_path, monkeypatch):
    """Integrity guard: acknowledged: <id> citing an INACTIVE decision (status=retired)
    is ignored — the finding blocks normally → verdict FAIL.
    """
    from framework_cli.cli import _finalize_gate

    monkeypatch.chdir(tmp_path)
    _seed_gate_decision(tmp_path, "DEC-0002", "retired")

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()
    records = [
        {
            "agent": "security",
            "findings": [
                {
                    "path": "b.py",
                    "line": 5,
                    "severity": "high",
                    "message": "should block because DEC-0002 is retired",
                    "suggestion": None,
                    "acknowledged": "DEC-0002",
                },
            ],
            "usage": {},
            "latency_ms": None,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
    ]
    meta = {"mode": "gate", "staged_hash": "sha256:abc", "agents_set": ["security"]}
    verdict = _finalize_gate(records, findings_dir, out, meta)
    assert verdict == "FAIL", (
        f"Acknowledged-inactive finding must still block (integrity guard); verdict={verdict}"
    )
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "FAIL", (
        f"Acknowledged-inactive finding must still block (integrity guard); marker={marker}"
    )


def test_gate_finalize_acknowledged_unknown_id_blocks(tmp_path, monkeypatch):
    """Integrity guard: acknowledged: <id> citing an UNKNOWN decision id is ignored —
    the finding blocks normally → verdict FAIL.
    """
    from framework_cli.cli import _finalize_gate

    monkeypatch.chdir(tmp_path)
    # No decision files at all — DEC-9999 is unknown.

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()
    records = [
        {
            "agent": "security",
            "findings": [
                {
                    "path": "c.py",
                    "line": 10,
                    "severity": "high",
                    "message": "should block because DEC-9999 does not exist",
                    "suggestion": None,
                    "acknowledged": "DEC-9999",
                },
            ],
            "usage": {},
            "latency_ms": None,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
    ]
    meta = {"mode": "gate", "staged_hash": "sha256:abc", "agents_set": ["security"]}
    verdict = _finalize_gate(records, findings_dir, out, meta)
    assert verdict == "FAIL", (
        f"Acknowledged-unknown finding must still block (integrity guard); verdict={verdict}"
    )
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "FAIL", (
        f"Acknowledged-unknown finding must still block (integrity guard); marker={marker}"
    )


def test_gate_finalize_stale_finding_blocks(tmp_path, monkeypatch):
    """A finding tagged stale: <id> (premise no longer holds) blocks normally → FAIL."""
    from framework_cli.cli import _finalize_gate

    monkeypatch.chdir(tmp_path)
    _seed_gate_decision(tmp_path, "DEC-0003", "accepted")

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()
    records = [
        {
            "agent": "security",
            "findings": [
                {
                    "path": "d.py",
                    "line": 3,
                    "severity": "high",
                    "message": "premise no longer holds for DEC-0003",
                    "suggestion": None,
                    "stale": "DEC-0003",
                },
            ],
            "usage": {},
            "latency_ms": None,
            "stop_reason": "end_turn",
            "raw_text": "[]",
            "turns": 1,
            "tool_calls": [],
        },
    ]
    meta = {"mode": "gate", "staged_hash": "sha256:abc", "agents_set": ["security"]}
    verdict = _finalize_gate(records, findings_dir, out, meta)
    assert verdict == "FAIL", f"Stale finding must block; verdict={verdict}"
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "FAIL", f"Stale finding must block; marker={marker}"


def test_template_render_renders_all_batteries(tmp_path):
    """template-render --out DIR renders the template with all 11 batteries,
    git-inits the result, and reports the resolved battery list."""
    out = tmp_path / "render"
    result = runner.invoke(app, ["template-render", "--out", str(out)])
    assert result.exit_code == 0, result.output

    from framework_cli.batteries import battery_names

    answers = (out / ".copier-answers.yml").read_text()
    for b in battery_names():
        assert b in answers, f"battery {b} missing from .copier-answers.yml"

    assert (out / "pyproject.toml").exists()
    assert (out / ".git").is_dir()
    assert (out / "frontend").is_dir()  # react battery artifact

    payload = _json.loads(result.stdout)
    assert sorted(payload["batteries"]) == sorted(battery_names())


def test_template_render_accepts_subset(tmp_path):
    """--batteries <csv> renders only the named batteries."""
    out = tmp_path / "render"
    result = runner.invoke(
        app, ["template-render", "--out", str(out), "--batteries", "webhooks"]
    )
    assert result.exit_code == 0, result.output
    answers = (out / ".copier-answers.yml").read_text()
    assert "webhooks" in answers
    assert "graphql" not in answers


def test_template_map_cli_writes_path_map(tmp_path):
    from framework_cli.copier_runner import template_path

    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "security.json").write_text(
        _json.dumps(
            {
                "agent": "security",
                "findings": [
                    {
                        "path": "src/demo/main.py",
                        "line": 5,
                        "severity": "high",
                        "message": "m",
                    }
                ],
            }
        )
    )
    result = runner.invoke(
        app,
        [
            "template-map",
            "--findings",
            str(findings),
            "--template-root",
            str(template_path()),
        ],
    )
    assert result.exit_code == 0, result.output
    out = findings.parent / "path-map.md"
    assert out.exists()
    assert "as-rendered" in out.read_text()


def _make_decision_file(
    dec_dir: Path, id: str, agents: list, status: str = "accepted"
) -> None:
    dec_dir.mkdir(parents=True, exist_ok=True)
    (dec_dir / f"{id.lower()}.md").write_text(
        f"---\nid: {id}\nstatus: {status}\nagents: {agents!r}\n"
        f"concern: test concern\npremise: 'must hold'\ndate: 2026-06-01\n---\n\nbody text\n"
    )


# ---------------------------------------------------------------------------
# Task 4.1 (Plan 20b): framework audit — in-process engine
# ---------------------------------------------------------------------------


def _make_framework_git_repo(tmp_path: Path) -> None:
    """Create a minimal fake framework repo with a git history under tmp_path.

    Matches the structure _detect_audit_target expects:
    - src/framework_cli/ directory
    - pyproject.toml with [project].name = "framework-cli"
    - an initial git commit so tree_signature/snapshot_seed have a HEAD
    """
    import subprocess

    (tmp_path / "src" / "framework_cli").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "framework-cli"\nversion = "0.0.0"\n'
    )
    (tmp_path / "src" / "framework_cli" / "__init__.py").write_text("")
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-gpg-sign", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


def test_audit_runs_in_process_and_writes_report(tmp_path, monkeypatch):
    """framework audit runs selection→engine→finalize in-process and writes
    audit-report.md + meta.json under --out-dir."""
    import framework_cli.cli as climod
    from framework_cli.cli import app
    from framework_cli.review.backend import Message, TextBlock

    class _Msgs:
        def create(self, **kw):
            return Message(content=[TextBlock(text="[]")], stop_reason="end_turn")

    # Stub: _make_backend returns a fake backend whose messages.create returns []
    monkeypatch.setattr(
        climod,
        "_make_backend",
        lambda name, key_env: type("B", (), {"messages": _Msgs()})(),
    )
    # Stub: _resolve_review_backend returns api-resolved so we skip the no-backend exit
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": "api", "reason": "resolved", "intent": "api"}
        )(),
    )

    _make_framework_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    out_dir = tmp_path / "out"
    r = runner.invoke(
        app,
        [
            "audit",
            "--target",
            "framework",
            "--backend",
            "api",
            "--agent",
            "security",
            "--out-dir",
            str(out_dir),
            "--snapshot",
        ],
    )
    assert r.exit_code == 0, r.output
    assert (out_dir / "audit-report.md").is_file()
    assert (out_dir / "meta.json").is_file()


def _audit_stubs(monkeypatch, climod):
    """Apply the standard backend stubs used by hermetic audit tests."""
    from framework_cli.review.backend import Message, TextBlock

    class _Msgs:
        def create(self, **kw):
            return Message(content=[TextBlock(text="[]")], stop_reason="end_turn")

    monkeypatch.setattr(
        climod,
        "_make_backend",
        lambda name, key_env: type("B", (), {"messages": _Msgs()})(),
    )
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": "api", "reason": "resolved", "intent": "api"}
        )(),
    )


def test_audit_preserve_as_writes_baseline(tmp_path, monkeypatch):
    """--preserve-as copies findings/, audit-report.md, meta.json into dst."""
    import framework_cli.cli as climod
    from framework_cli.cli import app

    _audit_stubs(monkeypatch, climod)
    _make_framework_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    out_dir = tmp_path / "out"
    preserve_dir = tmp_path / "baseline"
    r = runner.invoke(
        app,
        [
            "audit",
            "--target",
            "framework",
            "--backend",
            "api",
            "--agent",
            "security",
            "--out-dir",
            str(out_dir),
            "--snapshot",
            "--preserve-as",
            str(preserve_dir),
        ],
    )
    assert r.exit_code == 0, r.output
    assert (preserve_dir / "findings").is_dir()
    assert (preserve_dir / "audit-report.md").is_file()
    assert (preserve_dir / "meta.json").is_file()


def test_audit_preserve_as_non_empty_without_force_exits_2(tmp_path, monkeypatch):
    """--preserve-as over a non-empty target without --force exits 2."""
    import framework_cli.cli as climod
    from framework_cli.cli import app

    _audit_stubs(monkeypatch, climod)
    _make_framework_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    out_dir = tmp_path / "out"
    preserve_dir = tmp_path / "baseline"
    preserve_dir.mkdir()
    (preserve_dir / "existing.txt").write_text("blocker")

    r = runner.invoke(
        app,
        [
            "audit",
            "--target",
            "framework",
            "--backend",
            "api",
            "--agent",
            "security",
            "--out-dir",
            str(out_dir),
            "--snapshot",
            "--preserve-as",
            str(preserve_dir),
        ],
    )
    assert r.exit_code == 2, r.output
    assert "--force" in r.output


def test_audit_preserve_as_non_empty_with_force_overwrites(tmp_path, monkeypatch):
    """--preserve-as over a non-empty target WITH --force overwrites successfully."""
    import framework_cli.cli as climod
    from framework_cli.cli import app

    _audit_stubs(monkeypatch, climod)
    _make_framework_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    out_dir = tmp_path / "out"
    preserve_dir = tmp_path / "baseline"
    preserve_dir.mkdir()
    (preserve_dir / "existing.txt").write_text("old content")

    r = runner.invoke(
        app,
        [
            "audit",
            "--target",
            "framework",
            "--backend",
            "api",
            "--agent",
            "security",
            "--out-dir",
            str(out_dir),
            "--snapshot",
            "--preserve-as",
            str(preserve_dir),
            "--force",
        ],
    )
    assert r.exit_code == 0, r.output
    assert (preserve_dir / "audit-report.md").is_file()
    # Old file should have been wiped
    assert not (preserve_dir / "existing.txt").exists()


def test_audit_failed_agents_reported_on_stderr(tmp_path, monkeypatch):
    """A non-exhaustion agent failure: run continues (exit 0), failed-agent message
    appears in output, and the report is still written."""
    import framework_cli.cli as climod
    from framework_cli.cli import app
    from framework_cli.review.backend import Message, TextBlock

    call_count = [0]

    class _Msgs:
        def create(self, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                # First agent succeeds
                return Message(content=[TextBlock(text="[]")], stop_reason="end_turn")
            # Second agent raises a non-exhaustion error
            raise RuntimeError("simulated agent crash")

    monkeypatch.setattr(
        climod,
        "_make_backend",
        lambda name, key_env: type("B", (), {"messages": _Msgs()})(),
    )
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": "api", "reason": "resolved", "intent": "api"}
        )(),
    )

    _make_framework_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    out_dir = tmp_path / "out"
    # Run two agents so the second one can fail
    r = runner.invoke(
        app,
        [
            "audit",
            "--target",
            "framework",
            "--backend",
            "api",
            "--agent",
            "security",
            "--agent",
            "documentation",
            "--out-dir",
            str(out_dir),
            "--snapshot",
        ],
    )
    assert r.exit_code == 0, r.output
    assert (out_dir / "audit-report.md").is_file()
    assert "agent(s) failed" in r.output


def test_finalize_audit_error_field_persisted_and_surfaced_in_report(
    tmp_path, monkeypatch
):
    """_finalize_audit must (a) persist the 'error' field from a failure record into
    findings/<agent>.json, and (b) render the error reason in audit-report.md instead
    of the generic '_(no findings)_' placeholder."""
    import json as _json

    import framework_cli.cli as climod

    findings_dir = tmp_path / "findings"
    findings_dir.mkdir(parents=True)

    error_text = (
        "RuntimeError: claude -p failed (1): Usage credits required for 1M context"
    )

    records = [
        # A normal passing agent with findings
        {
            "agent": "documentation",
            "findings": [
                {
                    "path": "src/foo.py",
                    "line": 10,
                    "severity": "low",
                    "message": "missing docstring",
                }
            ],
            "review_mode": "snapshot",
            "base_sha": None,
            "base_baseline": None,
            "usage": {},
            "latency_ms": None,
            "stop_reason": "end_turn",
            "raw_text": "",
            "turns": 1,
            "tool_calls": [],
        },
        # A failed agent — error field present
        {
            "agent": "security",
            "findings": [],
            "stop_reason": "error",
            "error": error_text,
            "review_mode": "snapshot",
            "base_sha": None,
            "base_baseline": None,
            "usage": {},
            "latency_ms": None,
            "raw_text": "",
            "turns": 0,
            "tool_calls": [],
        },
    ]

    # _finalize_audit calls git rev-parse and active_decision_ids — stub them
    monkeypatch.setattr(
        climod.subprocess,
        "run",
        lambda *a, **kw: type(
            "CP", (), {"returncode": 0, "stdout": "deadbeef" * 5 + "\n"}
        )(),
    )
    import framework_cli.review.decisions as _dec

    monkeypatch.setattr(_dec, "active_decision_ids", lambda cwd: set())

    climod._finalize_audit(records, findings_dir, tmp_path, {"target": "framework"})

    # (a) Persisted findings/security.json must contain the error text
    security_record = _json.loads((findings_dir / "security.json").read_text())
    assert security_record.get("error") == error_text, (
        f"'error' field missing or wrong in persisted security.json: {security_record}"
    )

    # (b) audit-report.md must show the error reason — NOT just '_(no findings)_'
    report = (tmp_path / "audit-report.md").read_text()
    assert "Usage credits required for 1M context" in report, (
        f"error text not found in audit-report.md:\n{report}"
    )
    # The clean agent's findings must still render normally
    assert "missing docstring" in report, (
        "normal agent findings must still appear in the report"
    )


def test_audit_fresh_run_clears_stale_ghost_records(tmp_path, monkeypatch):
    """A fresh (non-resume) audit over a re-used out-dir removes old agent records
    that are NOT in the current run's agent set."""
    import framework_cli.cli as climod
    from framework_cli.cli import app
    import json as _json

    _audit_stubs(monkeypatch, climod)
    _make_framework_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    out_dir = tmp_path / "out"
    findings_dir = out_dir / "findings"
    findings_dir.mkdir(parents=True)
    # Pre-seed a ghost record for an agent NOT in this run
    ghost_record = {
        "agent": "ghost",
        "findings": [
            {"path": "x.py", "line": 1, "severity": "high", "message": "ghost finding"}
        ],
        "review_mode": "snapshot",
        "base_sha": None,
        "base_baseline": None,
        "usage": {},
        "latency_ms": None,
        "stop_reason": "end_turn",
        "raw_text": "",
        "turns": 1,
        "tool_calls": [],
    }
    (findings_dir / "ghost.json").write_text(_json.dumps(ghost_record))

    r = runner.invoke(
        app,
        [
            "audit",
            "--target",
            "framework",
            "--backend",
            "api",
            "--agent",
            "security",
            "--out-dir",
            str(out_dir),
            "--snapshot",
        ],
    )
    assert r.exit_code == 0, r.output
    assert not (findings_dir / "ghost.json").exists(), (
        "ghost.json should have been cleared"
    )
    report = (out_dir / "audit-report.md").read_text()
    assert "ghost" not in report
    meta = _json.loads((out_dir / "meta.json").read_text())
    assert "ghost" not in meta.get("agents", [])


# ---------------------------------------------------------------------------
# Task 2 (Plan 14): write_lockfile wired into `framework new`
# ---------------------------------------------------------------------------


def test_new_generates_uv_lock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Make write_lockfile deterministic + offline: fake a successful `uv lock`.
    import framework_cli.lockfile as lockmod

    def fake_run(args, cwd=None, capture_output=False, text=False):
        import subprocess

        (Path(cwd) / "uv.lock").write_text("# lock\n")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(lockmod.shutil, "which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr(lockmod.subprocess, "run", fake_run)

    result = runner.invoke(app, ["new", "Demo App"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "demo-app" / "uv.lock").exists()


def test_new_succeeds_when_lock_generation_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import framework_cli.lockfile as lockmod

    monkeypatch.setattr(lockmod.shutil, "which", lambda _: None)  # uv "missing" → warn

    result = runner.invoke(app, ["new", "Demo App"])
    assert result.exit_code == 0, result.output  # scaffold still succeeds
    assert (tmp_path / "demo-app").exists()
    assert not (tmp_path / "demo-app" / "uv.lock").exists()


# ---------------------------------------------------------------------------
# review-config sub-app (Task 1.4 — Plan 20b)
# ---------------------------------------------------------------------------


def test_review_config_set_show_clear(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from framework_cli.cli import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    r = runner.invoke(app, ["review-config", "show"])
    assert r.exit_code == 0 and "none" in r.stdout.lower()

    r = runner.invoke(app, ["review-config", "set-backend", "subagent", "--yes"])
    assert r.exit_code == 0
    assert (
        tmp_path / ".framework" / "review.toml"
    ).read_text().strip() == 'backend = "subagent"'

    r = runner.invoke(app, ["review-config", "show"])
    assert r.exit_code == 0 and "subagent" in r.stdout

    r = runner.invoke(app, ["review-config", "clear"])
    assert r.exit_code == 0 and not (tmp_path / ".framework" / "review.toml").exists()


def test_review_config_set_rejects_invalid_backend(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from framework_cli.cli import app

    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["review-config", "set-backend", "gpt", "--yes"])
    assert r.exit_code == 2


def test_review_config_set_backend_consent_decline_does_not_persist(
    tmp_path, monkeypatch
):
    # The R3 informed-opt-in gate: without --yes, declining the confirm must show the
    # cost caveat AND write nothing (no spend enabled without explicit consent).
    from typer.testing import CliRunner

    from framework_cli.cli import app

    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["review-config", "set-backend", "api"], input="n\n")
    assert r.exit_code == 1  # typer.confirm(abort=True) aborts non-zero on decline
    assert "paid per use" in r.stdout  # the cost caveat was shown before the prompt
    assert not (tmp_path / ".framework" / "review.toml").exists()


def test_review_config_set_backend_consent_accept_persists(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from framework_cli.cli import app

    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["review-config", "set-backend", "api"], input="y\n")
    assert r.exit_code == 0
    assert "paid per use" in r.stdout  # caveat shown even on the accept path
    assert (
        tmp_path / ".framework" / "review.toml"
    ).read_text().strip() == 'backend = "api"'


# ---------------------------------------------------------------------------
# Task 4.2 (Plan 20b): framework gate — in-process gate command
# ---------------------------------------------------------------------------


def test_gate_skip_neutral_without_backend(tmp_path, monkeypatch):
    """framework gate with no backend resolved → skip-neutral PASS, exit 0,
    marker.json written with verdict=PASS and 'skip' visible in stdout."""
    from typer.testing import CliRunner

    from framework_cli.cli import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda n: None)
    r = CliRunner().invoke(app, ["gate"])
    assert r.exit_code == 0 and "skip" in r.stdout.lower()
    assert (tmp_path / ".framework" / "audit" / "marker.json").exists()


def test_audit_errors_without_backend(tmp_path, monkeypatch):
    """framework audit (NOT gate) with no backend → exit 2 with 'backend' in output.
    Regression guard: audit must NOT be skip-neutral."""
    from typer.testing import CliRunner

    from framework_cli.cli import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda n: None)
    r = CliRunner().invoke(app, ["audit", "--target", "framework"])
    # _explain_no_backend writes to stderr; typer's default CliRunner mixes it into output
    assert r.exit_code == 2 and "backend" in r.output.lower()


def test_gate_runs_in_process_and_writes_marker(tmp_path, monkeypatch):
    """framework gate with a review-relevant staged file runs the in-process engine
    and writes marker.json with verdict=PASS (no findings from stub)."""
    import subprocess

    import framework_cli.cli as climod
    from framework_cli.cli import app
    from framework_cli.review.backend import Message, TextBlock

    class _Msgs:
        def create(self, **kw):
            return Message(content=[TextBlock(text="[]")], stop_reason="end_turn")

    monkeypatch.setattr(
        climod,
        "_make_backend",
        lambda name, key_env: type("B", (), {"messages": _Msgs()})(),
    )
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": "api", "reason": "resolved", "intent": "api"}
        )(),
    )

    # Set up a minimal git repo with a staged review-relevant file
    (tmp_path / "src" / "framework_cli" / "review").mkdir(parents=True)
    target_file = tmp_path / "src" / "framework_cli" / "review" / "runner.py"
    target_file.write_text("# original\n")
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-gpg-sign", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    # Now edit + stage the review-relevant file
    target_file.write_text("# modified\n")
    subprocess.run(
        ["git", "add", str(target_file)], cwd=tmp_path, check=True, capture_output=True
    )

    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / ".framework" / "audit" / "latest"
    r = CliRunner().invoke(app, ["gate", "--out-dir", str(out_dir)])
    assert r.exit_code == 0, r.output
    marker_path = tmp_path / ".framework" / "audit" / "marker.json"
    assert marker_path.is_file(), f"marker.json not found; output={r.output}"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# Fix 1 — gate is fail-open on infra errors (never wedges commits)
# ---------------------------------------------------------------------------


def _setup_minimal_git_repo_with_staged_review_file(tmp_path: Path) -> None:
    """Create a minimal git repo with a staged review-relevant file (runner.py)."""
    import subprocess

    (tmp_path / "src" / "framework_cli" / "review").mkdir(parents=True)
    target_file = tmp_path / "src" / "framework_cli" / "review" / "runner.py"
    target_file.write_text("# original\n")
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-gpg-sign", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    target_file.write_text("# modified\n")
    subprocess.run(
        ["git", "add", str(target_file)], cwd=tmp_path, check=True, capture_output=True
    )


def test_gate_infra_error_is_fail_open_exit_0(tmp_path, monkeypatch):
    """An unexpected exception inside the gate's engine block (e.g. _make_backend
    raising) must degrade to exit 0 (skip, not block) so a commit is never wedged
    on an infra error.  Stderr must mention 'errored' and 'skipping'."""
    import framework_cli.cli as climod
    from framework_cli.cli import app

    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": "api", "reason": "resolved", "intent": "api"}
        )(),
    )
    monkeypatch.setattr(
        climod,
        "_make_backend",
        lambda name, key_env: (_ for _ in ()).throw(
            RuntimeError("simulated infra error")
        ),
    )

    _setup_minimal_git_repo_with_staged_review_file(tmp_path)
    monkeypatch.chdir(tmp_path)

    out_dir = tmp_path / ".framework" / "audit" / "latest"
    r = CliRunner().invoke(app, ["gate", "--out-dir", str(out_dir)])
    assert r.exit_code == 0, (
        f"expected exit 0 on infra error; got {r.exit_code}; output={r.output}"
    )
    # CliRunner mixes stdout+stderr into output; check the message is present
    assert "errored" in r.output.lower() or "skipping" in r.output.lower(), (
        f"expected 'errored'/'skipping' in output; got: {r.output!r}"
    )


# ---------------------------------------------------------------------------
# Fix 2 — noop gate must be skip-neutral on stale blocking findings
# ---------------------------------------------------------------------------


def test_gate_noop_is_skip_neutral_with_stale_blocking_findings(tmp_path, monkeypatch):
    """Noop gate (no review-relevant staged files) must write verdict=PASS even when
    findings/ contains a prior high-severity finding that would FAIL on reload.

    Regression guard for [[noop-gate-inherits-stale-fail]]: before the fix the
    noop branch called _finalize_gate(mode='noop') which reloaded prior findings/
    records and re-derived a stale FAIL, blocking every subsequent commit on an
    unrelated file.
    """
    import subprocess

    import framework_cli.cli as climod
    from framework_cli.cli import app

    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **kw: type(
            "R", (), {"backend": "api", "reason": "resolved", "intent": "api"}
        )(),
    )

    # Minimal git repo — stage a NON-review-relevant file so mode → noop.
    (tmp_path / "docs").mkdir(parents=True)
    readme = tmp_path / "docs" / "README.md"
    readme.write_text("hello\n")
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-gpg-sign", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    readme.write_text("hello updated\n")
    subprocess.run(
        ["git", "add", str(readme)], cwd=tmp_path, check=True, capture_output=True
    )

    # Pre-seed findings/security.json with a high-severity finding (would FAIL on reload)
    out_dir = tmp_path / ".framework" / "audit" / "latest"
    findings_dir = out_dir / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    stale_record = {
        "agent": "security",
        "findings": [
            {
                "path": "src/app.py",
                "line": 1,
                "severity": "high",
                "message": "hardcoded secret",
                "suggestion": None,
            }
        ],
        "usage": {},
        "latency_ms": None,
        "stop_reason": "end_turn",
        "raw_text": "[]",
        "turns": 1,
        "tool_calls": [],
    }
    (findings_dir / "security.json").write_text(_json.dumps(stale_record))

    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["gate", "--out-dir", str(out_dir)])
    assert r.exit_code == 0, (
        f"noop gate must exit 0 even with stale FAIL findings; got {r.exit_code}; output={r.output}"
    )
    marker_path = tmp_path / ".framework" / "audit" / "marker.json"
    assert marker_path.is_file(), "marker.json not written"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "PASS", (
        f"noop gate re-derived FAIL from stale findings; marker={marker}"
    )
    # The stale findings/ file must still be present (noop must NOT clear findings)
    assert (findings_dir / "security.json").exists(), (
        "noop must not clear stale findings"
    )


# ---------------------------------------------------------------------------
# Fix 3 — errored agent is surfaced in marker summary (fail-open + auditable)
# ---------------------------------------------------------------------------


def test_gate_finalize_errored_agent_in_marker_summary(tmp_path):
    """When gate-mode meta_in['failed'] is non-empty, _finalize_gate must append
    '<n> agent(s) errored: <names>' to the marker summary. Verdict must still be
    PASS when there are no blocking findings — the fail-open is intentional."""
    from framework_cli.cli import _finalize_gate

    out = tmp_path / "audit"
    out.mkdir()
    findings_dir = out / "findings"
    findings_dir.mkdir()

    meta = {
        "mode": "gate",
        "staged_hash": "sha256:abc",
        "agents_set": ["security"],
        "failed": ["security"],
    }
    # Pass an empty records list — the security agent "errored" with no findings.
    verdict = _finalize_gate([], findings_dir, out, meta)
    assert verdict == "PASS", (
        f"fail-open: errored agent must not cause FAIL; got {verdict}"
    )
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "PASS"
    assert "errored" in marker["summary"].lower(), (
        f"expected 'errored' in marker summary; got: {marker['summary']!r}"
    )
    assert "security" in marker["summary"], (
        f"expected agent name in marker summary; got: {marker['summary']!r}"
    )


def test_version_flag_prints_installed_version():
    from framework_cli.integrity.manifest import installed_framework_version

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert installed_framework_version() in result.stdout
