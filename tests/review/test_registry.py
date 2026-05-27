import pytest

from framework_cli.review.registry import (
    AgentSpec,
    active_agents,
    agent_names,
    get_agent,
)

_EXPECTED_PR = sorted(
    [
        "security",
        "data-integrity",
        "data-lineage",
        "application-logic",
        "observability",
        "test-quality",
        "architecture",
        "performance",
        "compliance",
        "privacy",
        "documentation",
        "dependency",
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


def test_active_agents_excludes_battery_agents_by_default():
    from framework_cli.review.registry import active_agents

    # No batteries → no battery-gated agent appears (and the call still works with the new arg).
    assert active_agents("pull_request") == active_agents("pull_request", [])


def test_active_agents_adds_gated_agent_when_battery_present(monkeypatch):
    from framework_cli import batteries as bat
    from framework_cli.review import registry

    bat._BATTERIES["_demo"] = bat.BatterySpec(
        "_demo", "x", gates_agents=("_demo-agent",)
    )
    bat._BATTERIES["_demo2"] = bat.BatterySpec(
        "_demo2", "x", gates_agents=("_demo-push-agent",)
    )
    registry._SPECS["_demo-agent"] = registry.AgentSpec(
        "review-demo", "p", "high", "battery", registry.DEFAULT_MODEL
    )
    registry._SPECS["_demo-push-agent"] = registry.AgentSpec(
        "review-demo-push", "p", "high", "battery", registry.DEFAULT_MODEL, on_push=True
    )
    try:
        # PR: a present battery activates its gated agent; an absent battery does not.
        assert "_demo-agent" in registry.active_agents("pull_request", ["_demo"])
        assert "_demo-agent" not in registry.active_agents("pull_request", [])
        # Push: a battery agent WITHOUT on_push must NOT appear, even when its battery is present
        # (the push set stays the curated always-on-main subset).
        assert "_demo-agent" not in registry.active_agents("push", ["_demo"])
        # Push: a battery agent WITH on_push appears only when its battery is present.
        assert "_demo-push-agent" in registry.active_agents("push", ["_demo2"])
        assert "_demo-push-agent" not in registry.active_agents("push", [])
    finally:
        del bat._BATTERIES["_demo"], bat._BATTERIES["_demo2"]
        del registry._SPECS["_demo-agent"], registry._SPECS["_demo-push-agent"]


def test_active_agents_ignores_empty_gates_agents():
    from framework_cli.review.registry import active_agents

    # webhooks/websockets/workers have gates_agents=() → adding them changes nothing.
    assert active_agents("pull_request", ["webhooks", "workers"]) == active_agents(
        "pull_request"
    )


def test_graphql_battery_gates_api_design():
    from framework_cli.batteries import get_battery
    from framework_cli.review.registry import active_agents

    assert get_battery("graphql").gates_agents == ("api-design",)
    assert "api-design" in active_agents("pull_request", ["graphql"])
    assert "api-design" not in active_agents("pull_request", [])


def test_active_agents_battery_can_gate_multiple(monkeypatch):
    import framework_cli.batteries as bat
    from framework_cli.review.registry import active_agents

    monkeypatch.setitem(
        bat._BATTERIES,
        "_multi",
        bat.BatterySpec("_multi", "x", gates_agents=("api-design", "documentation")),
    )
    out = active_agents("pull_request", ["_multi"])
    assert "api-design" in out and "documentation" in out
