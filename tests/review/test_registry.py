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
        "observability-infra",
        "observability-db",
        "env-parity",
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
# Battery-gated agents (active_when="battery") — excluded from the always-on sets above.
_EXPECTED_BATTERY = [
    "accessibility",
    "api-design",
    "contracts",
    "observability-fe",
    "usability",
]


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


@pytest.mark.parametrize("name", _EXPECTED_BATTERY)
def test_every_battery_agent_prompt_loads_and_demands_json(name):
    spec = get_agent(name)
    assert spec.name == f"review-{name}"
    assert spec.active_when == "battery"
    assert spec.prompt.strip()
    assert "JSON" in spec.prompt


def test_advisory_and_filetrigger_config():
    assert get_agent("documentation").block_threshold is None
    dep = get_agent("dependency")
    assert dep.block_threshold is None and dep.active_when == "file-trigger"
    assert dep.trigger_globs and "pyproject.toml" in dep.trigger_globs
    # Plan 21: raised info->high so low/medium over-flags on clean code no longer block;
    # only a demonstrable high atomicity/data-loss defect gates.
    assert get_agent("data-integrity").block_threshold == "high"


def test_active_agents_excludes_battery_agents_by_default():
    from framework_cli.review.registry import active_agents

    # No batteries → no battery-gated agent appears (and the call still works with the new arg).
    assert active_agents("pull_request") == active_agents("pull_request", [])


def test_active_agents_adds_gated_agent_when_battery_present(monkeypatch):
    from framework_cli import batteries as bat
    from framework_cli.review import registry

    bat._BATTERIES["_demo"] = bat.BatterySpec(
        "_demo", "x", gates_agents=("_demo-agent",), obs="rides-existing"
    )
    bat._BATTERIES["_demo2"] = bat.BatterySpec(
        "_demo2", "x", gates_agents=("_demo-push-agent",), obs="rides-existing"
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
        bat.BatterySpec(
            "_multi",
            "x",
            gates_agents=("api-design", "documentation"),
            obs="rides-existing",
        ),
    )
    out = active_agents("pull_request", ["_multi"])
    assert "api-design" in out and "documentation" in out


def test_react_agents_active_on_pr_not_push():
    from framework_cli.review.registry import active_agents

    pr = active_agents("pull_request", ["react"])
    assert "accessibility" in pr and "usability" in pr
    push = active_agents(
        "push", ["react"]
    )  # battery agents are off-push unless on_push
    assert "accessibility" not in push and "usability" not in push


def test_review_contracts_registered_and_gated():
    from framework_cli.review.registry import active_agents, get_agent

    spec = get_agent("contracts")
    assert spec.name == "review-contracts"
    assert spec.block_threshold == "high"
    assert spec.active_when == "battery"
    # gated by the consumers battery, PR-only (battery agents are off on push)
    assert "contracts" in active_agents("pull_request", ["consumers"])
    assert "contracts" not in active_agents("pull_request", [])
    assert "contracts" not in active_agents("push", ["consumers"])


def test_observability_split_infra():
    from framework_cli.review.registry import active_agents, get_agent

    spec = get_agent("observability-infra")
    assert spec.name == "review-observability-infra"
    assert spec.block_threshold == "high"
    assert spec.active_when == "file-trigger"
    assert spec.trigger_globs and "infra/*" in spec.trigger_globs
    # the glob actually matches real infra paths (fnmatch '*' spans '/') and misses app code.
    from framework_cli.review.diff import matches_globs

    assert matches_globs(["infra/compose/dev.yml"], spec.trigger_globs)
    assert not matches_globs(["src/demo/db/repository.py"], spec.trigger_globs)
    # file-trigger agents are PR candidates; gated at runtime by the diff's changed files.
    assert "observability-infra" in active_agents("pull_request")
    # not on push (file-trigger, on_push defaults False) — keeps the curated push subset.
    assert "observability-infra" not in active_agents("push")


def test_observability_fe_registered_and_battery_gated():
    from framework_cli.review.registry import active_agents, get_agent

    spec = get_agent("observability-fe")
    assert spec.name == "review-observability-fe"
    assert spec.active_when == "battery"
    assert spec.block_threshold == "high"
    assert spec.context.strategy == "agentic"
    # inactive without the react battery; active with it (PR event)
    assert "observability-fe" not in active_agents("pull_request", batteries=[])
    assert "observability-fe" in active_agents("pull_request", batteries=["react"])


def test_observability_split_db():
    from framework_cli.review.registry import active_agents, get_agent

    spec = get_agent("observability-db")
    assert spec.name == "review-observability-db"
    assert spec.block_threshold == "high"
    assert spec.active_when == "file-trigger"
    # data-layer globs, NOT battery-gated (baseline always ships postgres).
    assert spec.trigger_globs and "*/db/*" in spec.trigger_globs
    from framework_cli.review.diff import matches_globs

    assert matches_globs(["src/demo/db/repository.py"], spec.trigger_globs)
    assert matches_globs(["migrations/versions/0001_init.py"], spec.trigger_globs)
    assert not matches_globs(["infra/compose/dev.yml"], spec.trigger_globs)
    assert "observability-db" in active_agents("pull_request")
    assert "observability-db" not in active_agents("push")


def test_env_parity_agent_spec():
    from framework_cli.review.registry import AGENTIC_MODEL

    spec = get_agent("env-parity")
    assert spec.name == "review-env-parity"
    assert spec.block_threshold == "high"
    assert spec.active_when == "file-trigger"
    assert spec.model == AGENTIC_MODEL
    assert spec.on_push is False
    assert spec.context.strategy == "agentic"
    assert spec.trigger_globs is not None
    assert set(spec.trigger_globs) == {
        "infra/*",
        ".env.example",
        "src/*/config/settings.py",
    }
    assert "JSON" in spec.prompt
    assert "dev-only" in spec.prompt.lower() or "parity" in spec.prompt.lower()
    # The composition-oracle must be in the prompt (the whole reason the agent is agentic) —
    # a tighter check than "parity", which guards against a prompt swap.
    assert "base.yml" in spec.prompt and "Taskfile.yml" in spec.prompt
