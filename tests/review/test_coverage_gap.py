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


def test_realize_cached_builds_framework_shaped_base_for_coverage_gap(tmp_path):
    """coverage-gap fixtures realize a framework-shaped tree (template + runtime_coverage),
    not a rendered project, so the patch applies and registry.py is readable."""
    from framework_cli.review.evals import Fixture, realize_cached

    patch = (
        "--- a/tests/runtime_coverage/registry.py\n"
        "+++ b/tests/runtime_coverage/registry.py\n"
        "@@ -1,4 +1,5 @@\n"
        ' """FWK29 classification registry — the closed-world ratchet\'s data.\n'
        "+# seeded comment for the fixture\n"
        " \n"
        " Every operational surface that `enumerate.py` finds must appear here exactly once,\n"
        " classified as EXERCISED (a test drives it — evidence names the test function), EXEMPT\n"
    )
    fx = Fixture(
        agent="coverage-gap",
        kind="bad",
        name="seed",
        batteries=(),
        patch=patch,
        seeded_file="tests/runtime_coverage/registry.py",
    )
    root, diff = realize_cached(fx, {}, tmp_path)
    # The framework subtrees are present in the realized base.
    assert (root / "tests" / "runtime_coverage" / "registry.py").is_file()
    assert (root / "src" / "framework_cli" / "template").is_dir()
    # The seeded change is in the diff (proves the patch applied to this base).
    assert "seeded comment for the fixture" in diff


def test_active_agents_excludes_battery_gated_framework_only_agent(monkeypatch):
    """Defense-in-depth: a battery-gated framework_only agent must also be excluded."""
    from framework_cli import batteries as bat
    from framework_cli.review import registry

    bat._BATTERIES["_fwbat"] = bat.BatterySpec(
        "_fwbat", "x", gates_agents=("_fwbat-agent",), obs="rides-existing"
    )
    registry._SPECS["_fwbat-agent"] = registry.AgentSpec(
        "review-fwbat",
        "p",
        None,
        "battery",
        registry.DEFAULT_MODEL,
        framework_only=True,
    )
    try:
        assert "_fwbat-agent" not in registry.active_agents("pull_request", ["_fwbat"])
    finally:
        del bat._BATTERIES["_fwbat"], registry._SPECS["_fwbat-agent"]


def test_reviews_template_agent_sources_full_diff_on_framework_target(monkeypatch):
    """coverage-gap (reviews_template) must be fed pr_diff (template-inclusive), not the
    template-excluding framework_diff — otherwise its template trigger-globs never match."""
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    template_diff = (
        "diff --git a/src/framework_cli/template/infra/compose/cache.yml.jinja "
        "b/src/framework_cli/template/infra/compose/cache.yml.jinja\n"
        "--- /dev/null\n"
        "+++ b/src/framework_cli/template/infra/compose/cache.yml.jinja\n"
        "@@ -0,0 +1,1 @@\n+services: {}\n"
    )
    seen = {}

    def fake_pr_diff():
        return template_diff

    def fake_framework_diff():
        return ""  # template excluded → empty

    def fake_review_run(diff, spec, force_agentic=False, backend=None):
        seen["diff"] = diff
        seen["agent"] = spec.name
        return []

    monkeypatch.setattr(cli_mod, "pr_diff", fake_pr_diff)
    monkeypatch.setattr(cli_mod, "framework_diff", fake_framework_diff)
    monkeypatch.setattr(cli_mod, "_review_run", fake_review_run)

    from typer.testing import CliRunner
    from framework_cli.cli import app

    result = CliRunner().invoke(
        app, ["review", "coverage-gap", "--target", "framework", "--backend", "api"]
    )
    assert result.exit_code == 0
    # It was NOT skipped as not-triggered, and it saw the template-inclusive diff.
    assert seen.get("agent") == "review-coverage-gap"
    assert "template/infra/compose/cache.yml.jinja" in seen["diff"]
