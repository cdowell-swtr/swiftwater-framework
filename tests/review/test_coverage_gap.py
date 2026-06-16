from framework_cli.review.registry import (
    AgentSpec,
    DEFAULT_MODEL,
    active_agents,
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
