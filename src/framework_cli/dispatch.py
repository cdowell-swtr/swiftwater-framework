"""Self-dispatch: run the CLI version that matches the project, automatically.

A version-coupled CLI installed as an unversioned global floats free of each
project's `_commit` pin. `dispatch()` (called before Typer parses) re-execs the
project-pinned version via cached `uvx` so the running CLI and the project's
template are always in lockstep. Pure policy (`classify`, `decide_dispatch`) is
separated from the I/O seams for unit-testing.
"""

from __future__ import annotations

from dataclasses import dataclass

from framework_cli.version_sync import parse_version

_ADVANCING = frozenset({"new", "upgrade"})
_CWD_PROJECT = frozenset({"integrity", "restore"})
_ARG_PROJECT = frozenset({"upskill", "downskill"})


def classify(command: str | None) -> str:
    """Map a subcommand to its dispatch kind."""
    if command in _ADVANCING:
        return "advancing"
    if command in _CWD_PROJECT:
        return "cwd_project"
    if command in _ARG_PROJECT:
        return "arg_project"
    return "self"


@dataclass(frozen=True)
class Dispatch:
    """The dispatch decision: run ourselves, or re-exec the CLI at `ref`."""

    action: str  # "self" | "reexec"
    ref: str | None = None


def _same_version(a: str, b: str) -> bool:
    """True when two refs name the same version (`vX.Y.Z` parse, else string)."""
    try:
        return parse_version(a) == parse_version(b)
    except Exception:
        return a == b


def decide_dispatch(
    *,
    kind: str,
    installed_tag: str,
    target_tag: str | None,
    project_commit: str | None,
    reexecuted: bool,
) -> Dispatch:
    """Decide whether to run self or re-exec a pinned CLI.

    `reexecuted` (the loop guard) and `kind == "self"` always run self. Otherwise
    the relevant ref — the advancing target, or the project's pin — is compared to
    the installed CLI: equal (or absent) runs self, a difference re-execs that ref.
    """
    if reexecuted or kind == "self":
        return Dispatch("self")
    ref = target_tag if kind == "advancing" else project_commit
    if ref is None or _same_version(ref, installed_tag):
        return Dispatch("self")
    return Dispatch("reexec", ref)
