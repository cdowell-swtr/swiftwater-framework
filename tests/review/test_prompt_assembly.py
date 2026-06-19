from framework_cli.review.context import Bundle
from framework_cli.review.registry import agent_names, composed_prompt, get_agent
from framework_cli.review.request import build_agentic_request, build_review_request

_CENTRALIZED_HEADERS = (
    "## Severity (one scale",
    "## Codebase-bar principle",
    "## Internal consistency within one review",
    "## Grounding & diff-awareness",
    "## Output",
)


def test_composed_prompt_has_rubric_then_domain():
    text = composed_prompt(get_agent("security"))
    assert "## Severity (one scale, consistent across all agents)" in text
    assert "## Your domain: `review-security`" in text
    assert text.index("## Severity") < text.index("## Your domain")


def test_domain_files_do_not_redefine_centralized_sections():
    # NOTE: this test is EXPECTED TO FAIL until a later task trims the agent files.
    # Leave it in place; it guards the trim. Mark it xfail ONLY if your runner blocks
    # on it — but prefer leaving it red and telling the controller it is the known-red
    # guard for the not-yet-done trim task.
    for name in agent_names():
        domain = get_agent(name).prompt
        for header in _CENTRALIZED_HEADERS:
            assert header not in domain, (
                f"{name}.md re-defines a centralized section: {header}"
            )


def test_review_request_system_carries_composed_prompt(tmp_path):
    spec = get_agent("security")
    bundle = Bundle(
        diff="--- a\n+++ b\n", context_files=(), truncated=False, decisions=()
    )
    req = build_review_request(bundle, spec, root=tmp_path)
    assert req.system[-1]["text"] == composed_prompt(spec)


def test_agentic_request_system_carries_composed_prompt(tmp_path):
    spec = get_agent("architecture")
    req = build_agentic_request("--- a\n+++ b\n", spec, root=tmp_path, max_turns=8)
    assert req.system[-1]["text"] == composed_prompt(spec)
