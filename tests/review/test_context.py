from pathlib import Path

from framework_cli.review.context import (
    Bundle,
    ReviewTarget,
    assemble,
    context_budget_chars,
)
from framework_cli.review.registry import ContextPolicy

_DIFF = (
    "--- a/src/demo/observability/metrics.py\n"
    "+++ b/src/demo/observability/metrics.py\n"
    "@@ -1,2 +1,3 @@\n"
    " import x\n"
    "+y = 1\n"
)


def _tree(root: Path) -> None:
    obs = root / "src" / "demo" / "observability"
    obs.mkdir(parents=True)
    (obs / "metrics.py").write_text("import x\ny = 1\nFULL_METRICS_FILE = True\n")
    (obs / "tracing.py").write_text("TRACING = True\n")
    (root / "src" / "demo" / "main.py").write_text("APP = True\n")


def test_diff_strategy_returns_diff_only(tmp_path: Path):
    _tree(tmp_path)
    b = assemble(_DIFF, tmp_path, ContextPolicy("diff"), model="claude-sonnet-4-6")
    assert b.diff == _DIFF
    assert b.context_files == ()
    assert b.truncated is False


def test_bundle_includes_changed_files_and_glob_subtree(tmp_path: Path):
    _tree(tmp_path)
    policy = ContextPolicy("bundle", context_globs=("src/*/observability/*.py",))
    b = assemble(_DIFF, tmp_path, policy, model="claude-sonnet-4-6")
    paths = [p for p, _ in b.context_files]
    assert "src/demo/observability/metrics.py" in paths
    assert any(
        "FULL_METRICS_FILE" in c for p, c in b.context_files if p.endswith("metrics.py")
    )
    assert "src/demo/observability/tracing.py" in paths
    assert "src/demo/main.py" not in paths


def test_changed_file_appears_once_even_if_glob_also_matches(tmp_path: Path):
    _tree(tmp_path)
    policy = ContextPolicy("bundle", context_globs=("src/*/observability/*.py",))
    b = assemble(_DIFF, tmp_path, policy, model="claude-sonnet-4-6")
    paths = [p for p, _ in b.context_files]
    assert paths.count("src/demo/observability/metrics.py") == 1


def test_budget_truncates_subtree_keeping_priority(tmp_path: Path):
    _tree(tmp_path)
    policy = ContextPolicy(
        "bundle", context_globs=("src/*/observability/*.py",), max_context_tokens=1
    )  # 1 token * 4 = 4 chars: nothing but the diff fits
    b = assemble(_DIFF, tmp_path, policy, model="claude-sonnet-4-6")
    assert b.truncated is True
    assert b.context_files == ()


def test_bundle_truncated_flag_constructs():
    from framework_cli.review.context import Bundle

    assert Bundle(diff="d", truncated=True).truncated is True


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


def test_bundle_skips_changed_file_missing_on_disk(tmp_path: Path):
    # A diff may name a path not present at root (e.g. a rename's old side); assemble
    # silently skips it rather than crashing, and does not mark the bundle truncated.
    _tree(tmp_path)
    diff = "--- a/src/demo/gone.py\n+++ b/src/demo/gone.py\n@@ -1 +1,2 @@\n a\n+b\n"
    b = assemble(diff, tmp_path, ContextPolicy("bundle"), model="claude-sonnet-4-6")
    assert b.context_files == ()
    assert b.truncated is False


def test_reviewtarget_defaults_active_to_empty(tmp_path: Path):
    assert ReviewTarget(root=tmp_path).active == ()
    assert ReviewTarget(root=tmp_path, active=("security",)).active == ("security",)
