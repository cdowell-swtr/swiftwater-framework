import pytest
from dataclasses import FrozenInstanceError

from framework_cli.review.registry import (
    ContextPolicy,
    get_agent,
    agent_names,
)


def test_contextpolicy_defaults_to_diff():
    p = ContextPolicy("diff")
    assert p.strategy == "diff"
    assert p.context_globs == ()
    assert p.max_context_tokens is None


def test_every_agent_has_an_explicit_context_strategy():
    # Slice A migrated 11 agents to "bundle"; Slice B migrates 7 to "agentic".
    # After Slice B, NO registered agent is left on the "diff" default.
    bundle = {
        "observability",
        "application-logic",
        "performance",
        "data-integrity",
        "security",
        "compliance",
        "test-quality",
        "documentation",
        "dependency",
        "accessibility",
        "usability",
    }
    agentic = {
        "architecture",
        "coverage-gap",
        "data-lineage",
        "privacy",
        "api-design",
        "observability-infra",
        "observability-db",
        "observability-fe",
        "contracts",
        "env-parity",
    }
    for name in agent_names():
        strat = get_agent(name).context.strategy
        if name in bundle:
            assert strat == "bundle", f"{name} should be bundle, is {strat}"
        elif name in agentic:
            assert strat == "agentic", f"{name} should be agentic, is {strat}"
        else:
            raise AssertionError(f"{name} is in neither tier — classify it")


def test_contextpolicy_bundle_carries_globs():
    p = ContextPolicy("bundle", context_globs=("src/*/observability/*.py",))
    assert p.strategy == "bundle"
    assert p.context_globs == ("src/*/observability/*.py",)


def test_contextpolicy_max_context_tokens_roundtrips():
    p = ContextPolicy("bundle", max_context_tokens=4096)
    assert p.max_context_tokens == 4096


def test_contextpolicy_is_frozen():
    p = ContextPolicy("diff")
    with pytest.raises(FrozenInstanceError):
        p.strategy = "bundle"  # type: ignore[misc]


def test_contextpolicy_max_agentic_turns_defaults_none_and_roundtrips():
    assert ContextPolicy("agentic").max_agentic_turns is None
    assert ContextPolicy("agentic", max_agentic_turns=20).max_agentic_turns == 20
