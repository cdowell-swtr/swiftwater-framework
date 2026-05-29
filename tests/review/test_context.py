from framework_cli.review.context import Bundle, context_budget_chars


def test_budget_derives_from_model_window_minus_reserve():
    # 200k-token window - 4096 output - 8000 margin = 187904 tokens * 4 chars.
    assert context_budget_chars("claude-sonnet-4-6") == (200_000 - 4096 - 8_000) * 4


def test_budget_unknown_model_uses_default_window():
    assert context_budget_chars("some-future-model") == (200_000 - 4096 - 8_000) * 4


def test_budget_override_is_tokens_capped_to_window():
    assert context_budget_chars("claude-sonnet-4-6", override_tokens=1_000) == 1_000 * 4
    # An override larger than the window is clamped to the derived ceiling.
    assert (
        context_budget_chars("claude-sonnet-4-6", override_tokens=10_000_000)
        == (200_000 - 4096 - 8_000) * 4
    )


def test_bundle_is_frozen_with_defaults():
    b = Bundle(diff="d")
    assert b.diff == "d"
    assert b.context_files == ()
    assert b.truncated is False
