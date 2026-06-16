from framework_cli.review.context import FRAMEWORK_AGENTS
from framework_cli.review.diff import matches_globs
from framework_cli.review.registry import (
    AGENTIC_MODEL,
    AgentSpec,
    DEFAULT_MODEL,
    active_agents,
    get_agent,
    _prompt,
)


def test_agentspec_has_framework_only_and_reviews_template_defaults_false():
    spec = AgentSpec("review-x", "p", None, "always", DEFAULT_MODEL)
    assert spec.framework_only is False
    assert spec.reviews_template is False


def test_active_agents_excludes_framework_only_agents(monkeypatch):
    from framework_cli.review import registry

    registry._SPECS["_fwonly"] = AgentSpec(
        "review-fwonly",
        "p",
        None,
        "file-trigger",
        DEFAULT_MODEL,
        trigger_globs=("src/framework_cli/template/**",),
        framework_only=True,
    )
    try:
        # Present in the registry, but never in the generated-project PR set.
        assert "_fwonly" not in active_agents("pull_request")
        assert "_fwonly" not in active_agents("push")
    finally:
        del registry._SPECS["_fwonly"]


def test_coverage_gap_prompt_loads_and_demands_json():
    p = _prompt("coverage-gap")
    assert p.strip()
    assert "JSON" in p


def test_coverage_gap_prompt_states_its_boundaries_and_registry_defer():
    p = _prompt("coverage-gap")
    # Hard boundary against neighbouring reviewers.
    assert "review-architecture" in p and "review-observability" in p
    # Defers to the FWK29 registry, by name, read through tools.
    assert "registry.py" in p and "enumerate.py" in p
    # The two halves and the diff-anchored discipline.
    assert "new kind" in p.lower()
    assert "exercised" in p.lower()


def test_coverage_gap_spec_is_advisory_agentic_filetrigger_framework_only():
    spec = get_agent("coverage-gap")
    assert spec.name == "review-coverage-gap"
    assert spec.block_threshold is None  # advisory — never blocks
    assert spec.active_when == "file-trigger"
    assert spec.model == AGENTIC_MODEL
    assert spec.on_push is False
    assert spec.context.strategy == "agentic"
    assert spec.framework_only is True
    assert spec.reviews_template is True
    assert spec.trigger_globs is not None
    assert set(spec.trigger_globs) == {
        "src/framework_cli/template/**",
        "tests/runtime_coverage/**",
    }


def test_coverage_gap_trigger_globs_match_template_and_registry_changes():
    spec = get_agent("coverage-gap")
    assert matches_globs(
        ["src/framework_cli/template/infra/compose/cache.yml.jinja"], spec.trigger_globs
    )
    assert matches_globs(["tests/runtime_coverage/registry.py"], spec.trigger_globs)
    # framework CLI source is NOT a trigger (that's the other five agents' job)
    assert not matches_globs(["src/framework_cli/cli.py"], spec.trigger_globs)


def test_coverage_gap_is_in_framework_agents_only():
    assert "coverage-gap" in FRAMEWORK_AGENTS
    assert "coverage-gap" not in active_agents("pull_request")  # not a project agent
