from __future__ import annotations

import os
import subprocess


def pr_diff() -> str:
    """The unified diff to review, derived from the CI environment.

    On a PR, GITHUB_BASE_REF names the base branch (diff base...HEAD); otherwise diff the
    last commit (HEAD~1...HEAD).
    """
    base = os.environ.get("GITHUB_BASE_REF")
    if base:
        subprocess.run(
            ["git", "fetch", "--depth=1", "origin", base], check=False, capture_output=True
        )
        rng = f"origin/{base}...HEAD"
    else:
        rng = "HEAD~1...HEAD"
    result = subprocess.run(
        ["git", "diff", rng], capture_output=True, text=True, check=False
    )
    return result.stdout
