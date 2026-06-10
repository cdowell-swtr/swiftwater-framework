from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path


_NEW_PATH_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


def changed_files(diff: str) -> list[str]:
    """The new-side paths of files changed in a unified diff (deletions → /dev/null are skipped)."""
    return _NEW_PATH_RE.findall(diff)


def matches_globs(paths: list[str], globs: tuple[str, ...]) -> bool:
    """True if any path matches any glob, by full path or basename."""
    return any(
        fnmatch.fnmatch(p, g) or fnmatch.fnmatch(os.path.basename(p), g)
        for p in paths
        for g in globs
    )


def _diff_range() -> str:
    """The git range to review, from the CI environment (PR base...HEAD, else HEAD~1...HEAD)."""
    base = os.environ.get("GITHUB_BASE_REF")
    if base:
        subprocess.run(
            ["git", "fetch", "--depth=1", "origin", base],
            check=False,
            capture_output=True,
        )
        return f"origin/{base}...HEAD"
    return "HEAD~1...HEAD"


def pr_diff() -> str:
    """The unified diff to review, derived from the CI environment.

    On a PR, GITHUB_BASE_REF names the base branch (diff base...HEAD); otherwise diff the
    last commit (HEAD~1...HEAD).
    """
    result = subprocess.run(
        ["git", "diff", _diff_range()], capture_output=True, text=True, check=False
    )
    return result.stdout


def staged_diff() -> str:
    """The unified diff of the currently-staged set (`git diff --cached`).

    Used by `framework gate` so the agents review the about-to-be-committed
    content, not the prior commit (which is what pr_diff() returns).
    Returns an empty string when nothing is staged.
    """
    result = subprocess.run(
        ["git", "diff", "--cached"], capture_output=True, text=True, check=False
    )
    return result.stdout


def framework_diff() -> str:
    """Like `pr_diff`, but excludes the template payload — the framework reviews only its
    own CLI/tooling source; template-payload quality is the product's concern (Slice C)."""
    result = subprocess.run(
        [
            "git",
            "diff",
            _diff_range(),
            "--",
            ".",
            ":(exclude)src/framework_cli/template",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def snapshot_seed(target: str, root: Path) -> str:
    """Return the diff seed for audit snapshot mode.

    For bundle agents this is always empty: the per-agent bundled context block
    (driven by ContextPolicy.context_globs) already carries the relevant source
    files, so no diff is needed. Agentic agents get a root_dir at the workflow
    layer and explore the tree via their tools; they also don't need a diff
    seed here.

    Returns an empty string. The `target` and `root` parameters are kept for
    symmetry with `delta_diff(base_sha)` and to allow future extension (e.g.,
    target-specific synthetic diffs) without breaking the call sites.
    """
    del target, root  # currently unused; kept for symmetry and future extension
    return ""


def delta_diff(base_sha: str) -> str:
    """Return ``git diff <base_sha>...HEAD`` as a unified diff string.

    Raises ValueError when ``git diff`` exits non-zero (e.g., ref unreachable).
    The CLI layer translates this into a clear ``typer.Exit(2)`` with the
    git error attached.
    """
    result = subprocess.run(
        ["git", "diff", f"{base_sha}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = (
            result.stderr or ""
        ).strip() or f"unable to compute diff for {base_sha}...HEAD"
        raise ValueError(
            f"delta_diff({base_sha!r}) failed: {msg}. Is that ref reachable?"
        )
    return result.stdout
