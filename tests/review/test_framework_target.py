import json
import subprocess
from pathlib import Path

from framework_cli.review.diff import framework_diff


def _git(args, cwd):
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def test_framework_diff_excludes_template_payload(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "src" / "framework_cli" / "template" / "src").mkdir(parents=True)
    (repo / "src" / "framework_cli").joinpath("cli.py").write_text("X = 1\n")
    (repo / "src" / "framework_cli" / "template" / "payload.py").write_text("A = 1\n")
    _git(["init", "-q"], repo)
    _git(["add", "-A"], repo)
    _git(["commit", "-qm", "base"], repo)
    (repo / "src" / "framework_cli" / "cli.py").write_text("X = 2\n")
    (repo / "src" / "framework_cli" / "template" / "payload.py").write_text("A = 2\n")
    _git(["commit", "-aqm", "change"], repo)

    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)  # → HEAD~1...HEAD range
    monkeypatch.chdir(repo)
    diff = framework_diff()
    assert "src/framework_cli/cli.py" in diff  # CLI change reviewed
    assert "template/payload.py" not in diff  # template payload excluded


# ---------------------------------------------------------------------------
# T2 — FRAMEWORK_AGENTS + framework_target
# ---------------------------------------------------------------------------
from framework_cli.review.context import FRAMEWORK_AGENTS, framework_target  # noqa: E402
from framework_cli.review.registry import agent_names  # noqa: E402


def test_framework_agents_are_the_expected_subset_and_registered():
    assert FRAMEWORK_AGENTS == (
        "application-logic",
        "architecture",
        "dependency",
        "documentation",
        "security",
        "test-quality",
    )
    assert set(FRAMEWORK_AGENTS) <= set(agent_names())


def test_framework_target_profile(tmp_path):
    t = framework_target(tmp_path)
    assert t.root == tmp_path
    assert t.active == FRAMEWORK_AGENTS


# ---------------------------------------------------------------------------
# T3 — review-agents --target framework
# ---------------------------------------------------------------------------
from typer.testing import CliRunner  # noqa: E402

from framework_cli.cli import app  # noqa: E402


def test_review_agents_target_framework_lists_the_subset():
    result = CliRunner().invoke(app, ["review-agents", "--target", "framework"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == sorted(FRAMEWORK_AGENTS)


def test_review_agents_default_target_is_project_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["review-agents", "--event", "pull_request"])
    assert result.exit_code == 0
    agents = json.loads(result.stdout)
    assert agents and agents != sorted(FRAMEWORK_AGENTS)


# ---------------------------------------------------------------------------
# T4 — review --target framework (template-excluded diff + forced agentic)
# ---------------------------------------------------------------------------
def test_review_run_force_agentic_uses_the_loop(monkeypatch, tmp_path):
    import framework_cli.cli as cli_mod
    from framework_cli.review.registry import get_agent

    called = {}

    def fake_agentic(diff, root, spec, client, *, max_turns):
        called["agent"] = spec.name
        return []

    monkeypatch.setattr("framework_cli.review.agentic.run_agent_agentic", fake_agentic)
    monkeypatch.setattr(cli_mod, "default_client", lambda: object())
    out = cli_mod._review_run(
        "--- a/x\n+++ b/x\n", get_agent("security"), force_agentic=True
    )
    assert out == []
    assert called["agent"] == "review-security"


def test_review_command_target_framework_sources_framework_diff(monkeypatch):
    import framework_cli.cli as cli_mod
    from typer.testing import CliRunner
    from framework_cli.cli import app

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(
        cli_mod, "framework_diff", lambda: ""
    )  # empty diff → no findings
    result = CliRunner().invoke(app, ["review", "security", "--target", "framework"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# T5 — .github/workflows/review.yml dogfooding workflow
# ---------------------------------------------------------------------------
def test_review_workflow_is_valid_and_uses_framework_target():
    import yaml

    wf = yaml.safe_load(Path(".github/workflows/review.yml").read_text())
    # PyYAML parses the bare `on:` key as the boolean True; accept either.
    triggers = wf.get("on") or wf.get(True)
    assert "pull_request" in triggers and "push" in triggers
    jobs = wf["jobs"]
    assert {"review-plan", "review", "review-aggregate"} <= set(jobs)
    text = Path(".github/workflows/review.yml").read_text()
    assert "review-agents --target framework" in text
    assert "review ${{ matrix.agent }} --target framework" in text
    # Runtime-scoped reviewer key (review-at-runtime), per the two-tier convention in
    # the repo-root SECRETS.md — distinct from agent-evals.yml's eval-scoped key.
    assert "ANTHROPIC_FRAMEWORK_CI_RUNTIME" in text
    assert (
        "ANTHROPIC_FRAMEWORK_CI_EVAL" not in text
    )  # eval key must not leak into the runtime job
