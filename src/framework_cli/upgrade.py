"""`framework upgrade`: move a generated project across framework versions.

The one path that bumps a project's recorded framework version. Re-renders the template at
the target release (default: latest) via the shared `_apply_update` core, preserving project
identity, then runs `task test`. Battery mutation lives in `upskill --with` / `downskill`.

Rollback is plain git: a clean working tree is required up front (so the upgrade is one
reviewable diff), and on success the caller is told to commit and push immediately.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from framework_cli.source import latest_release, read_commit
from framework_cli.upskill import UpskillError, _apply_update, _is_git_tracked


class UpgradeError(Exception):
    """Upgrade cannot proceed (not git-tracked, dirty tree, or no target release)."""


@dataclass
class UpgradeOutcome:
    status: str  # "already-current" | "green" | "red"
    target: str
    warnings: list[str] = field(default_factory=list)


_TOP_LEVEL_KEY = re.compile(r"^([A-Za-z0-9_][\w-]*):")


def _duplicate_top_level_keys(text: str) -> list[str]:
    """Top-level YAML keys appearing more than once (sorted). Detects the duplicate-key
    class `check-yaml` rejects — e.g. a hand-added key the managed region now also provides."""
    counts: dict[str, int] = {}
    for line in text.splitlines():
        m = _TOP_LEVEL_KEY.match(line)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return sorted(k for k, n in counts.items() if n > 1)


def _precommit_warnings(project: Path) -> list[str]:
    """DV-4: a non-fatal warning if `.pre-commit-config.yaml` has a duplicate top-level key.

    v0.4.0 moved keys (`default_install_hook_types`, `conventional-pre-commit`) into the
    managed region; a project that had hand-added its own copies ends up with a duplicate
    top-level key → invalid YAML → `check-yaml` fails the first post-upgrade commit. We can't
    safely auto-de-dupe (a builder's intentional override is indistinguishable from a
    redundant copy), so we warn and let them resolve it.
    """
    precommit = project / ".pre-commit-config.yaml"
    if not precommit.is_file():
        return []
    dups = _duplicate_top_level_keys(precommit.read_text())
    if not dups:
        return []
    return [
        ".pre-commit-config.yaml has duplicate top-level key(s): "
        + ", ".join(dups)
        + " — likely a hand-added copy now also provided by the framework-managed region. "
        "Remove your copy (the managed region covers it) so `check-yaml` passes before "
        "you commit."
    ]


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
    return UpgradeOutcome(
        status="green" if green else "red",
        target=target,
        warnings=_precommit_warnings(project),
    )
