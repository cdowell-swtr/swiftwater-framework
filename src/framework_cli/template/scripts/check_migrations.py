"""Block migrations that aren't safe for a rolling / no-downtime deploy.

Two structural guards, both run in pre-commit and CI over migrations/versions/*.py:

1. Reversible  — every migration's downgrade() must really reverse it (not missing / empty /
   pass / raise), so a rollback can always step back.
2. Backward-compatible — a rolling (or blue-green) deploy runs old and new code against ONE
   shared schema, so each deploy's migration must be expand-only (additive). A destructive
   "contract" change in upgrade() (drop_column / drop_table / drop_constraint / drop_index /
   rename_table, or a column rename via alter_column(new_column_name=...)) breaks the old code
   still running during the roll. Ship such a change as its OWN post-rollout release; add a
   `# deploy: contract` comment to the file to acknowledge that and exempt it from this guard.

Structural, not semantic: these don't decide whether a drop is *actually* safe given current
code — Plan 7's data-integrity review agent adds that judgement. See infra/deploy/README.md
for the expand/contract-across-releases workflow.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

VERSIONS = Path("migrations/versions")

_DESTRUCTIVE_OPS = {
    "drop_column",
    "drop_table",
    "drop_constraint",
    "drop_index",
    "rename_table",
}
_CONTRACT_MARKER = "deploy: contract"


def _top_level_func(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    return next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name),
        None,
    )


def _is_trivial(func: ast.FunctionDef) -> bool:
    # Drop docstrings / bare literal statements (runtime no-ops); what remains is the real body.
    body = [
        node
        for node in func.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    ]
    if not body:
        return True
    if all(isinstance(node, ast.Pass) for node in body):
        return True
    return len(body) == 1 and isinstance(body[0], ast.Raise)


def _destructive_op(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    name = node.func.attr
    if name in _DESTRUCTIVE_OPS:
        return name
    if name == "alter_column" and any(
        kw.arg == "new_column_name" for kw in node.keywords
    ):
        return "alter_column (rename)"
    return None


def _downgrade_problem(path: Path, tree: ast.Module) -> str | None:
    downgrade = _top_level_func(tree, "downgrade")
    if downgrade is None:
        return f"{path}: no downgrade() function"
    if _is_trivial(downgrade):
        return f"{path}: downgrade() is empty / pass / raise — write a real reversal (expand/contract)"
    return None


def _contract_problem(path: Path, tree: ast.Module, source: str) -> str | None:
    if _CONTRACT_MARKER in source:
        return None  # explicitly acknowledged as a standalone, post-rollout contract release
    upgrade = _top_level_func(tree, "upgrade")
    if upgrade is None:
        return None
    for node in ast.walk(upgrade):
        op = _destructive_op(node)
        if op is not None:
            return (
                f"{path}: upgrade() makes a destructive (contract) change ({op}) — it breaks "
                f"old code during a rolling deploy. Ship it as its own post-rollout release, "
                f"or add a '# {_CONTRACT_MARKER}' comment to acknowledge it."
            )
    return None


def _problems(path: Path) -> list[str]:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    found = [_downgrade_problem(path, tree), _contract_problem(path, tree, source)]
    return [msg for msg in found if msg is not None]


def main() -> int:
    if not VERSIONS.is_dir():
        return 0
    failures = [
        msg for path in sorted(VERSIONS.glob("*.py")) for msg in _problems(path)
    ]
    for msg in failures:
        print(f"::error::{msg}", file=sys.stderr)
    if failures:
        print(
            f"\n{len(failures)} unsafe migration(s). Migrations must be reversible AND "
            "backward-compatible (expand-only); never destroy unreconstructable data. "
            "See infra/deploy/README.md.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
