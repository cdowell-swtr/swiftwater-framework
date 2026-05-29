from __future__ import annotations

import fnmatch
import os
import re
import subprocess


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
