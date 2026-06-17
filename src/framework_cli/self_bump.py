"""Assisted CLI self-bump for `framework upgrade` (FWK34).

When the upgrade target is newer than the installed CLI, the developer's CLI must be bumped
to the target first (restore/integrity render from the installed CLI). `decide_bump` is the
pure policy; the I/O seams below are monkeypatched in tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from framework_cli.source import REPO_URL
from framework_cli.version_sync import parse_version


class BumpRefused(Exception):
    """The CLI must be bumped to the target but cannot/should not be self-bumped."""


@dataclass(frozen=True)
class BumpDecision:
    action: str  # "proceed" | "prompt" | "bump" | "refuse"
    message: str  # populated only for "refuse"


def decide_bump(
    *,
    installed_tag: str,
    target_tag: str,
    is_uv_tool: bool,
    is_tty: bool,
    bump_flag: bool,
) -> BumpDecision:
    """Pure policy: proceed (target not newer), bump, prompt, or refuse-with-message."""
    if parse_version(target_tag) <= parse_version(installed_tag):
        return BumpDecision("proceed", "")
    install_cmd = f"uv tool install git+{REPO_URL}@{target_tag}"
    if not is_uv_tool:
        return BumpDecision(
            "refuse",
            f"Your framework CLI is {installed_tag}; the target is {target_tag}. "
            f"restore/integrity render from the installed CLI, so it must match the target. "
            f"This CLI was not installed via `uv tool`, so it can't self-update — upgrade it "
            f"manually: {install_cmd}, then re-run.",
        )
    if bump_flag:
        return BumpDecision("bump", "")
    if is_tty:
        return BumpDecision("prompt", "")
    return BumpDecision(
        "refuse",
        f"Your framework CLI is {installed_tag}; the target is {target_tag}. Upgrade the "
        f"CLI first: {install_cmd} (or pass --bump-cli), then re-run.",
    )


# --- I/O seams (monkeypatched in tests) ---
def is_uv_tool_install() -> bool:
    """True if the running `framework` console-script lives under `uv tool dir`.

    Fail safe: any uncertainty (no `uv`, unreadable path) returns False so we never
    self-mutate a non-`uv tool` install.
    """
    try:
        tool_dir = subprocess.run(
            ["uv", "tool", "dir"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    if not tool_dir:
        return False
    exe = shutil.which("framework") or sys.argv[0]
    try:
        Path(exe).resolve().relative_to(Path(tool_dir).resolve())
        return True
    except (ValueError, OSError):
        return False


def run_uv_tool_install(target_tag: str) -> None:
    subprocess.run(
        ["uv", "tool", "install", f"git+{REPO_URL}@{target_tag}"], check=True
    )


def reexec(argv: list[str]) -> None:
    os.execvp(argv[0], argv)  # replaces the process image; returns only on failure


def _interactive() -> bool:
    return sys.stdin.isatty()


def _confirm(message: str) -> bool:
    import typer

    return typer.confirm(message, default=True)


def maybe_self_bump(*, target_tag: str, bump_flag: bool, argv: list[str]) -> None:
    """If the target is newer than the installed CLI: self-bump+re-exec, or raise BumpRefused.

    Returns normally only when the upgrade should proceed in *this* process (the target is not
    newer than the installed CLI). On a bump it `reexec`s and never returns.
    """
    from framework_cli.version_sync import installed_version_tag

    installed_tag = installed_version_tag()
    if parse_version(target_tag) <= parse_version(installed_tag):
        return  # target not newer than the installed CLI — proceed in this process

    decision = decide_bump(
        installed_tag=installed_tag,
        target_tag=target_tag,
        is_uv_tool=is_uv_tool_install(),
        is_tty=_interactive(),
        bump_flag=bump_flag,
    )
    if decision.action == "refuse":
        raise BumpRefused(decision.message)
    if decision.action == "prompt":
        if not _confirm(
            f"Your framework CLI is {installed_tag}; the target is {target_tag}. "
            "Bump the CLI and continue the upgrade?"
        ):
            raise BumpRefused(
                f"Upgrade the CLI when ready: uv tool install git+{REPO_URL}@{target_tag}"
            )
    run_uv_tool_install(target_tag)
    reexec(argv)
