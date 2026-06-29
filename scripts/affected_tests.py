#!/usr/bin/env python
"""FWK90 — per-mutation test selection for the worktree inner loop.

Given the current working-tree mutation, run only the fast-tier tests it *affects* instead of
the whole suite — keeping interim, per-change feedback fast. This is an **interim accelerator
only**; `task test:fast` stays the commit gate (it can never silently drop coverage — any path
this does not understand widens to the full fast tier).

Two halves:
  * `select_targets(changed_paths)` — a pure function (unit-tested) mapping changed repo-relative
    paths to a fast-tier pytest target list, or the `FULL` sentinel.
  * `main()` — a thin runner: gather the mutation from git, print a loud interim banner, run
    pytest over the selection.

Design + rationale: docs/superpowers/specs/2026-06-29-fwk90-per-mutation-test-selection-design.md
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

# Sentinel: run the whole fast tier (mirrors `task test:fast`).
FULL = "FULL"

_REPO_ROOT = Path(__file__).resolve().parent.parent

# The two docker/dind acceptance files live in the full tier only — kept out of every fast-tier
# invocation, byte-for-byte with the CI `gate` / `task test:fast` ignore set (FWK96).
_DOCKER_IGNORES = (
    "--ignore=tests/acceptance/test_rendered_project.py",
    "--ignore=tests/acceptance/test_deploy_e2e.py",
)

# A template-payload edit re-runs the framework-side template guards (the fast-tier subset that
# can catch render/integrity/completeness drift). Generated-project *unit* tests run in a
# different venv and are out of scope here (the template-payload TDD loop owns them).
TEMPLATE_GUARDS = (
    "tests/integrity/",
    "tests/runtime_coverage/",
    "tests/test_copier_runner.py",
    "tests/test_template_map.py",
)

_TEMPLATE_PREFIX = "src/framework_cli/template/"
_FRAMEWORK_PREFIX = "src/framework_cli/"

# Subpackage → owning test area. A change anywhere under the key runs the whole area (coarse on
# purpose: predictable + robust beats minimal + fragile for an inner-loop aid).
_AREA_MAP = {
    "src/framework_cli/integrity/": "tests/integrity/",
    "src/framework_cli/review/": "tests/review/",
    "src/framework_cli/runtime_coverage/": "tests/runtime_coverage/",
}

# Paths that never affect a test result.
_DOC_SUFFIXES = (".md",)
_DOC_PREFIXES = ("docs/",)


def fixture_anchored_paths(repo_root: Path | None = None) -> set[str]:
    """The set of (rendered or template-source) paths every eval-fixture `change.patch` anchors on.

    The fixtures are hand-authored unified diffs applied to a fresh render; a template edit that
    drifts one of these anchors is invisible to the render/integrity set and caught only by
    `tests/review/test_evals.py::test_every_fixture_realizes`. Parsing the `+++ b/` / `--- a/`
    headers lets the selector *derive* that coupling rather than hand-maintain it.
    """
    root = repo_root or _REPO_ROOT
    anchored: set[str] = set()
    for patch in (root / "tests/eval/fixtures").rglob("change.patch"):
        for line in patch.read_text().splitlines():
            if line.startswith(("+++ ", "--- ")):
                target = line[4:].strip()
                if target == "/dev/null":
                    continue
                # Strip git's a/ b/ prefix.
                if target.startswith(("a/", "b/")):
                    target = target[2:]
                anchored.add(target)
    return anchored


def _rendered_forms(template_path: str) -> set[str]:
    """Candidate match keys for a changed template-source path against the anchored set.

    Fixture anchors live in two namespaces: rendered-project paths (`.env.example`,
    `src/demo/routes/items.py` — the fixtures render with package `demo`) and, for a few, the raw
    template-source path. Return both the raw path and its rendered normalization so an exact
    set-membership test bridges the gap.
    """
    keys = {template_path}
    rel = template_path[len(_TEMPLATE_PREFIX) :]
    if rel.endswith(".jinja"):
        rel = rel[: -len(".jinja")]
    # Copier path-templating: `src/{{package_name}}/...` renders under the fixtures' package `demo`.
    for token in ("{{package_name}}", "{{ package_name }}"):
        rel = rel.replace(token, "demo")
    keys.add(rel)
    return keys


def _template_targets(template_paths: Iterable[str], anchored: set[str]) -> list[str]:
    targets = list(TEMPLATE_GUARDS)
    for path in template_paths:
        if _rendered_forms(path) & anchored:
            targets.append("tests/review/test_evals.py")
            break
    return targets


def _is_doc(path: str) -> bool:
    return path.endswith(_DOC_SUFFIXES) or path.startswith(_DOC_PREFIXES)


def _framework_target(path: str) -> str | None:
    """The test target for a non-template framework-source path, or None if unmapped (→ FULL)."""
    for prefix, area in _AREA_MAP.items():
        if path.startswith(prefix):
            return area
    # A top-level module `src/framework_cli/<stem>.py` → its `tests/test_<stem>.py`, if one exists.
    rel = path[len(_FRAMEWORK_PREFIX) :]
    if "/" not in rel and rel.endswith(".py"):
        candidate = f"tests/test_{rel[:-3]}.py"
        if (_REPO_ROOT / candidate).is_file():
            return candidate
    return None


def select_targets(
    changed_paths: Iterable[str], *, repo_root: Path | None = None
) -> list[str] | str:
    """Map changed repo-relative paths to a sorted fast-tier pytest target list, or `FULL`.

    `FULL` is absorbing: any single unmapped path forces the whole fast tier (fail-safe —
    selection only ever narrows from a known-safe map).
    """
    paths = list(changed_paths)
    template_paths = [p for p in paths if p.startswith(_TEMPLATE_PREFIX)]
    targets: set[str] = set()

    if template_paths:
        anchored = fixture_anchored_paths(repo_root)
        targets.update(_template_targets(template_paths, anchored))

    for path in paths:
        if path.startswith(_TEMPLATE_PREFIX):
            continue
        if path.startswith(_FRAMEWORK_PREFIX):
            # Framework source — incl. `review/agents/*.md` prompts, which drive tests/review/.
            # Checked before the doc skip so a code-relevant `.md` is not mistaken for a doc.
            target = _framework_target(path)
            if target is None:
                return FULL
            targets.add(target)
            continue
        if path.startswith("tests/") and path.endswith(".py"):
            targets.add(path)
            continue
        if _is_doc(path):
            continue
        # Anything we do not understand widens to the full fast tier.
        return FULL

    return sorted(targets)


def _changed_from_git(repo_root: Path) -> list[str]:
    """The working-tree mutation: tracked changes vs HEAD + untracked files (new fixtures count)."""
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return sorted(set(tracked) | set(untracked))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    changed = args if args else _changed_from_git(_REPO_ROOT)

    print("── per-mutation test selection (FWK90) ──", file=sys.stderr)
    print(
        "INTERIM ACCELERATOR ONLY — run `task test:fast` before you commit.",
        file=sys.stderr,
    )
    if not changed:
        print("no changes detected — nothing to run.", file=sys.stderr)
        return 0

    selection = select_targets(changed)
    if selection == FULL:
        print(
            "selection: FULL fast tier (an unmapped path was touched).", file=sys.stderr
        )
        pytest_args = ["-q", "-n", "auto", *_DOCKER_IGNORES]
    elif not selection:
        print("selection: no test-affecting changes (docs only).", file=sys.stderr)
        return 0
    else:
        print(f"selection: {' '.join(selection)}", file=sys.stderr)
        pytest_args = ["-q", "-n", "auto", *selection]

    return subprocess.run(
        ["uv", "run", "pytest", *pytest_args], cwd=_REPO_ROOT
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
