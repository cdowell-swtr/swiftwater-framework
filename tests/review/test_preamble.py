from framework_cli.review.preamble import build_preamble, severity_enum_for
from framework_cli.review.registry import get_agent


def test_severity_enum_full_ladder_for_blocking_agent():
    assert severity_enum_for(get_agent("security")) == "high|medium|low|info"


def test_severity_enum_capped_for_advisory_agent():
    assert severity_enum_for(get_agent("usability")) == "low|info"


def test_severity_enum_respects_override():
    assert severity_enum_for(get_agent("dependency")) == "high|low|info"


def test_preamble_contains_rubric_core_and_output_contract():
    text = build_preamble(get_agent("security"))
    assert "## Severity (one scale, consistent across all agents)" in text
    assert "## Codebase-bar principle" in text
    assert "## Grounding & diff-awareness" in text
    assert "Return **JSON ONLY**" in text
    assert '"severity": "high|medium|low|info"' in text
    # the JSON example renders literal braces (no leftover .format() escaping)
    assert "{{" not in text and "}}" not in text


def test_preamble_advisory_note_only_for_advisory_agents():
    blocking = build_preamble(get_agent("security"))
    advisory = build_preamble(get_agent("usability"))
    assert "ADVISORY agent" not in blocking
    assert "ADVISORY agent" in advisory
    assert "NEVER emit high/medium" in advisory
    # composition is clean on both paths — no triple-newline runs
    assert "\n\n\n" not in blocking and "\n\n\n" not in advisory
