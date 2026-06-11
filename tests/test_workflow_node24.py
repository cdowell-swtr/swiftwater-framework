"""Guard: every GitHub Actions `uses:` ref (framework + generated template) is pinned
to a Node-24-capable action version.

GitHub forces the Node 24 actions runtime by default on 2026-06-16 and removes Node 20
from runners on 2026-09-16. This test is the source of truth for the migration policy;
see docs/maintenance/github-actions-node-runtime.md.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source of truth for the Node-24 action policy. `runtime`:
#   "node"          — JS action; the pinned major must be >= min_major (Node-24-capable).
#   "docker"        — container action; no Node runtime, version floor not checked.
#   "node20-forced" — JS action with no Node-24 release yet; GHA force-runs it on Node 24.
#                     Tracked exception — revisit before the 2026-09-16 Node-20 removal.
APPROVED_ACTIONS: dict[str, dict] = {
    "actions/checkout": {"runtime": "node", "min_major": 5},
    "astral-sh/setup-uv": {
        "runtime": "node",
        "min_major": 7,
    },  # node24 only from v7 (v6 is node20)
    "actions/setup-node": {"runtime": "node", "min_major": 6},
    "actions/upload-artifact": {"runtime": "node", "min_major": 6},
    "actions/download-artifact": {"runtime": "node", "min_major": 7},
    "softprops/action-gh-release": {"runtime": "node", "min_major": 3},
    "arduino/setup-task": {
        "runtime": "node20-forced"
    },  # no Node-24 release as of 2026-06-04
    "oasdiff/oasdiff-action/breaking": {"runtime": "docker"},
    "gitleaks/gitleaks-action": {"runtime": "docker"},
}

FRAMEWORK_WORKFLOWS = REPO_ROOT / ".github" / "workflows"
TEMPLATE_WORKFLOWS = (
    REPO_ROOT / "src" / "framework_cli" / "template" / ".github" / "workflows"
)

# Anchored: an optional leading "- " then "uses:" at the start of the (stripped) line.
# Avoids matching "uses:" inside a run: script or a comment.
_USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<ref>\S+)")


def _collect_uses(directory: Path) -> list[tuple[Path, int, str]]:
    """(file, lineno, ref) for every marketplace `uses:` under directory.

    Raw-source scan — the template `.jinja` `uses:` values are static strings, never
    Copier-interpolated, so no render is needed. Local reusable-workflow refs
    (`uses: ./...`) are files, not marketplace actions, and are skipped.
    """
    found: list[tuple[Path, int, str]] = []
    # `*.jinja` (not just `*.yml.jinja`) so brace-templated workflow filenames like
    # `{{ 'docs.yml' if 'docs' in batteries else '' }}.jinja` are scanned too.
    files = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.jinja"))
    for path in files:
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            m = _USES_RE.match(line)
            if not m:
                continue
            ref = m.group("ref").strip().strip("\"'")
            if ref.startswith("./"):
                continue
            found.append((path, i, ref))
    return found


def _major(version: str) -> int | None:
    m = re.match(r"v?(\d+)", version)
    return int(m.group(1)) if m else None


def _check(directory: Path) -> None:
    refs = _collect_uses(directory)
    assert refs, f"no `uses:` refs found under {directory} — the scan is broken"
    violations: list[str] = []
    for path, lineno, ref in refs:
        where = f"{path.relative_to(REPO_ROOT)}:{lineno}"
        if "{{" in ref or "{%" in ref:
            violations.append(
                f"{where} dynamic action ref {ref!r} — raw-scan assumption broken"
            )
            continue
        if "@" not in ref:
            violations.append(f"{where} unpinned action {ref!r} (no @version)")
            continue
        action, _, version = ref.partition("@")
        policy = APPROVED_ACTIONS.get(action)
        if policy is None:
            violations.append(
                f"{where} action {action!r} not in APPROVED_ACTIONS — add it with its "
                "Node-24 min_major (or fix the ref)"
            )
            continue
        if policy["runtime"] == "node":
            major = _major(version)
            if major is None or major < policy["min_major"]:
                violations.append(
                    f"{where} {ref} is below the Node-24 floor v{policy['min_major']} (got {version!r})"
                )
    assert not violations, "Node-24 action policy violations:\n" + "\n".join(violations)


def test_framework_workflows_use_node24_actions() -> None:
    _check(FRAMEWORK_WORKFLOWS)


def test_template_workflows_use_node24_actions() -> None:
    _check(TEMPLATE_WORKFLOWS)
