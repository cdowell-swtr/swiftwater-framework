"""Compare the installed framework CLI version against a project's recorded `_commit`.

`restore`/`integrity` render the canonical from the *bundled* (installed-CLI) template, so
they are only correct when the installed version equals the project's `_commit`. This module
is the single source of truth for that comparison (FWK34).
"""

from __future__ import annotations

import enum
from pathlib import Path

from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.source import REPO_URL, read_commit, version_tag


class VersionSkewError(Exception):
    """The installed CLI version does not match the project's recorded `_commit`."""


class VersionSkew(enum.Enum):
    IN_SYNC = "in_sync"
    CLI_BEHIND = "cli_behind"  # installed < _commit  (project upgraded past the CLI)
    CLI_AHEAD = "cli_ahead"  # installed > _commit  (CLI newer than the project pin)


def parse_version(tag: str) -> tuple[int, int, int]:
    """Parse a ``vX.Y.Z`` (or ``X.Y.Z``) tag into a comparable tuple."""
    core = tag[1:] if tag.startswith("v") else tag
    parts = core.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a vX.Y.Z version: {tag!r}")
    a, b, c = (int(p) for p in parts)
    return (a, b, c)


def project_version_skew(project: Path) -> tuple[VersionSkew, str, str]:
    """Return ``(skew, installed_tag, commit_tag)`` for ``project``.

    Raises ``VersionSkewError`` if the project has no `_commit`, or the installed CLI
    version is unparseable (odd install state).
    """
    installed_tag = version_tag(installed_framework_version())
    commit_tag = read_commit(project)
    if commit_tag is None:
        raise VersionSkewError(
            ".copier-answers.yml has no _commit — cannot determine the project's "
            "framework version"
        )
    try:
        installed_v = parse_version(installed_tag)
    except ValueError as exc:
        raise VersionSkewError(
            f"cannot determine the installed framework CLI version ({installed_tag})"
        ) from exc
    commit_v = parse_version(commit_tag)
    if installed_v == commit_v:
        return (VersionSkew.IN_SYNC, installed_tag, commit_tag)
    if installed_v < commit_v:
        return (VersionSkew.CLI_BEHIND, installed_tag, commit_tag)
    return (VersionSkew.CLI_AHEAD, installed_tag, commit_tag)


def skew_remedy(skew: VersionSkew, installed_tag: str, commit_tag: str) -> str:
    """The directional 'how to fix' sentence for a non-IN_SYNC skew."""
    install_cmd = f"uv tool install git+{REPO_URL}@{commit_tag}"
    if skew is VersionSkew.CLI_BEHIND:
        return f"Upgrade the CLI: {install_cmd}, then retry."
    return (
        f"Either upgrade the project (`framework upgrade`), or pin a matching CLI: "
        f"{install_cmd}."
    )


def require_version_sync(project: Path) -> None:
    """Raise ``VersionSkewError`` with actionable guidance unless installed == `_commit`."""
    skew, installed_tag, commit_tag = project_version_skew(project)
    if skew is VersionSkew.IN_SYNC:
        return
    raise VersionSkewError(
        f"This project is pinned {commit_tag} but your framework CLI is {installed_tag}. "
        + skew_remedy(skew, installed_tag, commit_tag)
    )
