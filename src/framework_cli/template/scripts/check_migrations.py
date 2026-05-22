"""Block irreversible migrations: every migration's downgrade() must really reverse it.

Rollback (infra/deploy/strategy.sh) reverses migrations to the previous release; a migration
with no real downgrade makes that release un-rollback-able and risks unreconstructable data
loss. This guard fails any migration whose downgrade() is missing / empty / just `pass` /
raises. Run in pre-commit and CI. The same discipline applies to every database paradigm
added later (Plan 8) — each carries its own reversible-migration tooling and a guard like this.

This is a structural guard (is there a real reversal?), not a semantic one (does it lose
data?) — semantic data-loss is caught by the data-integrity review agent + the expand/contract
discipline (see infra/deploy/README.md).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

VERSIONS = Path("migrations/versions")


def _is_trivial(func: ast.FunctionDef) -> bool:
    # Drop a leading docstring; what remains is the real body.
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


def _problem(path: Path) -> str | None:
    tree = ast.parse(path.read_text(), filename=str(path))
    downgrade = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
        ),
        None,
    )
    if downgrade is None:
        return f"{path}: no downgrade() function"
    if _is_trivial(downgrade):
        return f"{path}: downgrade() is empty / pass / raise — write a real reversal (expand/contract)"
    return None


def main() -> int:
    if not VERSIONS.is_dir():
        return 0
    failures = [
        msg for path in sorted(VERSIONS.glob("*.py")) if (msg := _problem(path))
    ]
    for msg in failures:
        print(f"::error::{msg}", file=sys.stderr)
    if failures:
        print(
            f"\n{len(failures)} irreversible migration(s). Every migration must have a real "
            "downgrade(); never destroy unreconstructable data. See infra/deploy/README.md.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
