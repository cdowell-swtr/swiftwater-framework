from pathlib import Path

import yaml

_WF = Path(__file__).parent.parent / ".github" / "workflows" / "agent-evals.yml"


def test_agent_evals_workflow_is_valid():
    wf = yaml.safe_load(_WF.read_text())
    triggers = (
        wf[True] if True in wf else wf["on"]
    )  # PyYAML parses `on:` as the bool True
    assert "schedule" in triggers
    # path-filtered push/PR on agent prompts or review logic
    push_paths = triggers["push"]["paths"]
    assert any("agents" in p for p in push_paths)
    assert any("review" in p for p in push_paths)

    steps = wf["jobs"]["eval"]["steps"]
    run = " ".join(str(s.get("run", "")) for s in steps)
    # framework eval runs WITHOUT --require-key post-Slice-E: the job is opt-in
    # (skip-neutral when ANTHROPIC_FRAMEWORK_CI_EVAL is unset) — set the secret only
    # for a deliberate paid-API anchor run (Slice E3 future).
    assert "framework eval" in run
    assert "--require-key" not in run
    # the fixtures root must be passed via --fixtures, not as the positional `agent` arg
    # (a bare path there is read as an agent name and fails with "unknown review agent").
    assert "--fixtures tests/eval/fixtures" in run
    assert "framework eval tests/eval/fixtures" not in run
    # the key is supplied from secrets (still wired; just not --require-key'd)
    env_blocks = [s.get("env", {}) for s in steps]
    assert any("ANTHROPIC_EVAL_API_KEY" in e for e in env_blocks)


_CI = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"


def test_framework_ci_fast_tier():
    wf = yaml.safe_load(_CI.read_text())
    triggers = wf[True] if True in wf else wf["on"]
    assert "pull_request" in triggers
    assert "workflow_call" in triggers  # reusable by release.yml
    steps = wf["jobs"]["gate"]["steps"]
    run = " ".join(str(s.get("run", "")) for s in steps)
    assert "ruff check" in run
    assert "ruff format --check" in run
    assert "mypy src" in run
    assert "pytest -q --ignore=tests/acceptance" in run
    assert "uv lock --check" in run
    assert "uv build" in run


_RM = Path(__file__).parent.parent / ".github" / "workflows" / "render-matrix.yml"


def test_render_matrix_workflow():
    wf = yaml.safe_load(_RM.read_text())
    triggers = wf[True] if True in wf else wf["on"]
    assert "pull_request" in triggers
    assert "push" in triggers
    assert "schedule" in triggers
    assert "workflow_call" in triggers
    assert "workflow_dispatch" in triggers

    jobs = wf["jobs"]
    gen_run = " ".join(str(s.get("run", "")) for s in jobs["generate-matrix"]["steps"])
    assert "framework dev-combos" in gen_run
    assert jobs["generate-matrix"]["outputs"]["combos"]

    render = jobs["render"]
    assert "fromJSON" in str(render["strategy"]["matrix"]["combo"])
    assert render["strategy"]["fail-fast"] is False
    render_run = " ".join(str(s.get("run", "")) for s in render["steps"])
    assert "framework new demo" in render_run
    assert "framework integrity --ci" in render_run
    assert "task ci" in render_run
    assert "npm ci" in render_run  # react frontend gate
    assert any(
        "setup-node" in str(s.get("uses", "")) and "react" in str(s.get("if", ""))
        for s in render["steps"]
    )


_REL = Path(__file__).parent.parent / ".github" / "workflows" / "release.yml"


def test_release_workflow():
    wf = yaml.safe_load(_REL.read_text())
    triggers = wf[True] if True in wf else wf["on"]
    assert triggers["push"]["tags"] == ["v*"]
    assert wf["permissions"]["contents"] == "write"  # to create a Release

    jobs = wf["jobs"]
    guard_run = " ".join(str(s.get("run", "")) for s in jobs["guard"]["steps"])
    assert "verify_release_tag.py" in guard_run
    assert jobs["gate"]["uses"].endswith("ci.yml")
    assert jobs["matrix"]["uses"].endswith("render-matrix.yml")
    assert set(jobs["release"]["needs"]) >= {"gate", "matrix"}
    rel_uses = " ".join(str(s.get("uses", "")) for s in jobs["release"]["steps"])
    assert "action-gh-release" in rel_uses


def test_agent_evals_triggers_cover_all_agent_prompts():
    wf = yaml.safe_load(_WF.read_text())
    triggers = wf[True] if True in wf else wf["on"]
    push_paths = triggers["push"]["paths"]
    agents_dir = (
        Path(__file__).parent.parent / "src" / "framework_cli" / "review" / "agents"
    )
    prompts = list(agents_dir.glob("*.md"))
    have = {p.stem for p in prompts}
    assert {"contracts", "observability-infra", "observability-db"} <= have
    assert any("agents" in p for p in push_paths)
