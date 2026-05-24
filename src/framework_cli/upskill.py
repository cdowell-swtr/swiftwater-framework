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
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UpskillError("git not found on PATH — install git to upskill") from exc
    return result.returncode == 0 and result.stdout.strip() == "true"


def upskill_project(
    project: Path, vcs_ref: str | None = None, with_batteries: list[str] | None = None
) -> bool:
    """Update `project` to `vcs_ref` (default: latest tag) and run `task test`.

    When `with_batteries` is given, that battery set is passed as the update's `batteries`
    answer (used by `upskill --with`); otherwise the recorded answers — including the existing
    `batteries` — are reused as-is.
    """
    if not _is_git_tracked(project):
        raise UpskillError(
            "upskill requires a git-tracked project (run `git init` and commit first)"
        )
    data = {"batteries": with_batteries} if with_batteries is not None else None
    run_update(
        str(project),
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref=vcs_ref,
        data=data,
    )
    try:
        test = subprocess.run(["task", "test"], cwd=project, check=False)
    except FileNotFoundError as exc:
        raise UpskillError(
            "`task` (go-task) not found on PATH — install it to run the project's tests"
        ) from exc
    return test.returncode == 0
