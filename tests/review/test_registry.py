import pytest

from framework_cli.review.registry import AgentSpec, active_agents, agent_names, get_agent

_EXPECTED_PR = sorted(
    [
        "security", "data-integrity", "data-lineage", "application-logic", "observability",
        "test-quality", "architecture", "performance", "compliance", "privacy",
        "documentation", "dependency",
    ]
)
_EXPECTED_PUSH = sorted(["security", "data-integrity", "data-lineage", "observability"])


def test_security_agent_spec():
    spec = get_agent("security")
    assert isinstance(spec, AgentSpec)
    assert spec.name == "review-security"
    assert spec.block_threshold == "high"
    assert spec.active_when == "always"
    assert spec.model  # a model id is set
    assert "OWASP" in spec.prompt or "injection" in spec.prompt
    assert "JSON" in spec.prompt  # instructs JSON-only output


def test_unknown_agent_raises():
    with pytest.raises(KeyError):
        get_agent("nope")


def test_agent_names_lists_security():
    assert "security" in agent_names()


def test_security_is_on_push():
    assert get_agent("security").on_push is True


def test_active_agents_push_is_subset_of_pull_request():
    pr = active_agents("pull_request")
    push = active_agents("push")
    assert "security" in pr and "security" in push
    assert set(push).issubset(set(pr))


def test_active_agents_excludes_battery_and_is_sorted():
    pr = active_agents("pull_request")
    assert pr == sorted(pr)


def test_full_active_sets():
    assert active_agents("pull_request") == _EXPECTED_PR
    assert active_agents("push") == _EXPECTED_PUSH


@pytest.mark.parametrize("name", _EXPECTED_PR)
def test_every_agent_prompt_loads_and_demands_json(name):
    spec = get_agent(name)
    assert spec.name == f"review-{name}"
    assert spec.prompt.strip()
    assert "JSON" in spec.prompt


def test_advisory_and_filetrigger_config():
    assert get_agent("documentation").block_threshold is None
    dep = get_agent("dependency")
    assert dep.block_threshold is None and dep.active_when == "file-trigger"
    assert dep.trigger_globs and "pyproject.toml" in dep.trigger_globs
    assert get_agent("data-integrity").block_threshold == "info"
