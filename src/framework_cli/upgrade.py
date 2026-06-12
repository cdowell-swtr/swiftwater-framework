"""`framework upgrade`: move a generated project across framework versions.

The one path that bumps a project's recorded framework version. Re-renders the template at
the target release (default: latest) via the shared `_apply_update` core, preserving project
identity, then runs `task test`. Battery mutation lives in `upskill --with` / `downskill`.

Rollback is plain git: a clean working tree is required up front (so the upgrade is one
reviewable diff), and on success the caller is told to commit and push immediately.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from framework_cli.source import latest_release, read_commit
from framework_cli.upskill import UpskillError, _apply_update, _is_git_tracked


class UpgradeError(Exception):
    """Upgrade cannot proceed (not git-tracked, dirty tree, or no target release)."""


@dataclass
class UpgradeOutcome:
    status: str  # "already-current" | "green" | "red"
    target: str


def _is_clean_tree(project: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == ""


def upgrade_project(project: Path, *, to: str | None = None) -> UpgradeOutcome:
    """Upgrade `project` to `to` (default: latest release). Raises UpgradeError on refusal."""
    if not _is_git_tracked(project):
        raise UpgradeError(
            "upgrade requires a git-tracked project (run `git init` and commit first)"
        )
    if not _is_clean_tree(project):
        raise UpgradeError(
            "commit or stash your changes before upgrading — the upgrade needs a clean "
            "tree so its diff is reviewable and reversible."
        )
    target = to if to is not None else latest_release()
    if target is None:
        raise UpgradeError(
            "no framework release found (or the remote is unreachable); cannot upgrade."
        )
    if read_commit(project) == target:
        return UpgradeOutcome(status="already-current", target=target)

    from framework_cli.source import read_alert_channels, read_batteries

    try:
        green = _apply_update(
            project,
            vcs_ref=target,
            batteries=read_batteries(project),
            channels=read_alert_channels(project),
        )
    except UpskillError as exc:  # missing identity / `task` not found
        raise UpgradeError(str(exc)) from exc
    return UpgradeOutcome(status="green" if green else "red", target=target)
