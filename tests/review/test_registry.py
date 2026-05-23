import pytest

from framework_cli.review.registry import AgentSpec, active_agents, agent_names, get_agent


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
