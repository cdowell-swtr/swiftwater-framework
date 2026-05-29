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


def test_agentspec_context_defaults_to_diff():
    # Every currently-registered agent defaults to the diff strategy until migrated.
    for name in agent_names():
        assert get_agent(name).context.strategy == "diff"


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
