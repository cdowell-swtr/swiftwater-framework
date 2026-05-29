from pathlib import Path

from framework_cli.review.context import (
    ReviewTarget,
    assemble,
    generated_project_target,
)
from framework_cli.review.registry import ContextPolicy


def test_assemble_is_target_blind(tmp_path: Path):
    """assemble() depends only on (diff, root, policy) — never on target identity.

    Two ReviewTargets pointing at the same tree produce identical bundles. This is the
    invariant Slice C relies on when it adds the framework-repo target: the runner and
    assembler stay target-blind; only the ReviewTarget profile differs.
    """
    (tmp_path / "a.py").write_text("X = 1\n")
    diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n X = 1\n+Y = 2\n"
    policy = ContextPolicy("bundle", context_globs=("*.py",))
    t1 = generated_project_target(tmp_path, ("security",))
    t2 = ReviewTarget(root=tmp_path, active=("performance", "security"))
    b1 = assemble(diff, t1.root, policy, model="claude-sonnet-4-6")
    b2 = assemble(diff, t2.root, policy, model="claude-sonnet-4-6")
    assert b1 == b2
    assert b1.context_files  # sanity: the bundle actually assembled context
