"""Self-dispatch: run the CLI version that matches the project, automatically.

A version-coupled CLI installed as an unversioned global floats free of each
project's `_commit` pin. `dispatch()` (called before Typer parses) re-execs the
project-pinned version via cached `uvx` so the running CLI and the project's
template are always in lockstep. Pure policy (`classify`, `decide_dispatch`) is
separated from the I/O seams for unit-testing.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from framework_cli.source import REPO_URL, latest_release, read_commit
from framework_cli.version_sync import installed_version_tag, parse_version

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


def resolve_project_commit(kind: str, positionals: list[str]) -> str | None:
    """The `_commit` pin of the project this command targets (None if no project).

    `cwd_project` commands act on the current directory; `arg_project` commands
    take the project path as their first positional. Any other kind has no project.
    """
    if kind == "cwd_project":
        return read_commit(Path.cwd())
    if kind == "arg_project" and positionals:
        return read_commit(Path(positionals[0]))
    return None


def _uvx_available() -> bool:
    """True when `uvx` is on PATH to run the pinned CLI ephemerally."""
    return shutil.which("uvx") is not None


def reexec(ref: str, argv: list[str]) -> None:  # pragma: no cover - exec seam
    """Replace this process with the CLI at `ref`, fetched ephemerally via `uvx`.

    No global mutation: `uvx --from git+REPO@ref` runs the pinned version from the
    uv cache. The loop-guard env var stops the re-execed CLI from dispatching again.
    """
    env = {**os.environ, "FRAMEWORK_PINNED_EXEC": "1"}
    cmd = ["uvx", "--from", f"git+{REPO_URL}@{ref}", "framework", *argv]
    os.execvpe("uvx", cmd, env)


def _split_argv(argv: list[str]) -> tuple[str | None, list[str]]:
    """Return (command, positionals-after-command) ignoring leading options."""
    command: str | None = None
    positionals: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if command is None:
            if tok.startswith("-"):
                i += 1
                continue
            command = tok
        elif not tok.startswith("-"):
            positionals.append(tok)
        i += 1
    return command, positionals


def _target_tag(argv: list[str]) -> str | None:
    """The advancing target: an explicit `--to <tag>`, else the latest release."""
    if "--to" in argv:
        idx = argv.index("--to")
        if idx + 1 < len(argv):
            return argv[idx + 1]
    return latest_release()


def dispatch(argv: list[str]) -> None:
    """Re-exec the project-pinned CLI when the installed version differs.

    A no-op under the loop guard / dev escape hatch, for `self` commands, and when
    already in sync. On a real mismatch it re-execs the correct CLI via `uvx`, or —
    if `uvx` is unavailable — fails loud rather than run a mismatched CLI.
    """
    if os.environ.get("FRAMEWORK_PINNED_EXEC") or os.environ.get(
        "FRAMEWORK_NO_DISPATCH"
    ):
        return
    command, positionals = _split_argv(argv)
    kind = classify(command)
    if kind == "self":
        return
    installed = installed_version_tag()
    target = _target_tag(argv) if kind == "advancing" else None
    project_commit = resolve_project_commit(kind, positionals)
    decision = decide_dispatch(
        kind=kind,
        installed_tag=installed,
        target_tag=target,
        project_commit=project_commit,
        reexecuted=False,
    )
    if decision.action == "self":
        return
    if not _uvx_available():
        raise SystemExit(
            f"framework: this project needs CLI {decision.ref} but `uvx` is "
            f"unavailable to run it (install uv, or "
            f"`uv tool install git+{REPO_URL}@{decision.ref}`). "
            "Refusing to run a mismatched CLI."
        )
    assert decision.ref is not None  # reexec implies a concrete ref
    reexec(decision.ref, argv)
