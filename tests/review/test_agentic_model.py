from framework_cli.review.registry import get_agent

_AGENTIC = (
    "architecture",
    "data-lineage",
    "privacy",
    "api-design",
    "observability-infra",
    "observability-db",
    "contracts",
)


def test_agentic_agents_use_opus_4_8():
    for name in _AGENTIC:
        assert get_agent(name).model == "claude-opus-4-8", name


def test_bundle_agents_stay_on_sonnet():
    for name in ("security", "observability", "documentation"):
        assert get_agent(name).model == "claude-sonnet-4-6", name
