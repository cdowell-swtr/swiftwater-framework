"""`framework upskill`: bring a project up to a newer framework version.

Runs Copier's update (3-way merge from the project's recorded version to the target),
then `task test`; reports whether the upgraded project is green. Conflicts are left as
inline markers for manual resolution (Copier's standard behavior).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from copier import run_update


class UpskillError(Exception):
    """Upskill cannot proceed (e.g., the project is not git-tracked)."""


def _is_git_tracked(project: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def upskill_project(project: Path, vcs_ref: str | None = None) -> bool:
    """Update `project` to `vcs_ref` (default: latest tag) and run `task test`.

    Returns True if the project is green afterward. Raises UpskillError if the project is
    not git-tracked (Copier's update requires it).
    """
    if not _is_git_tracked(project):
        raise UpskillError(
            "upskill requires a git-tracked project (run `git init` and commit first)"
        )
    run_update(
        str(project),
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref=vcs_ref,
    )
    test = subprocess.run(["task", "test"], cwd=project, check=False)
    return test.returncode == 0
