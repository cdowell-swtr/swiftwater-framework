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
    assert "framework eval" in run and "--require-key" in run
    # the fixtures root must be passed via --fixtures, not as the positional `agent` arg
    # (a bare path there is read as an agent name and fails with "unknown review agent").
    assert "--fixtures tests/eval/fixtures" in run
    assert "framework eval tests/eval/fixtures" not in run
    # the key is supplied from secrets
    env_blocks = [s.get("env", {}) for s in steps]
    assert any("ANTHROPIC_API_KEY" in e for e in env_blocks)
