"""Self-dispatch: run the CLI version that matches the project, automatically.

A version-coupled CLI installed as an unversioned global floats free of each
project's `_commit` pin. `dispatch()` (called before Typer parses) re-execs the
project-pinned version via cached `uvx` so the running CLI and the project's
template are always in lockstep. Pure policy (`classify`, `decide_dispatch`) is
separated from the I/O seams for unit-testing.
"""

from __future__ import annotations

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
