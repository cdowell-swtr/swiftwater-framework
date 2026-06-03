"""Generate a project's uv.lock at scaffold time (Plan 14 push-readiness).

`framework new` ships a committed uv.lock so the generated ci.yml's `uv sync --frozen`
jobs + the Dockerfile `COPY uv.lock` work on the builder's first push. `uv lock` only
RESOLVES dependencies (writes uv.lock) — it does not install or create a venv, so this
stays cheap. Failure is non-fatal: a transient/offline scaffold still succeeds and the
builder's first `uv sync` recovers the lock.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import typer

_FALLBACK = "run `uv sync` (or `uv lock`) before your first push to generate it"


def write_lockfile(project: Path) -> bool:
    """Run `uv lock` in `project` to produce uv.lock. Returns True on success; on any
    failure warns to stderr and returns False (never raises)."""
    if shutil.which("uv") is None:
        typer.echo(
            f"Warning: `uv` not found — skipping uv.lock generation; {_FALLBACK}.",
            err=True,
        )
        return False
    # uv vanished / not executable since the which() check — swallow so we never raise.
    try:
        result = subprocess.run(
            ["uv", "lock"], cwd=str(project), capture_output=True, text=True
        )
    except OSError as exc:
        typer.echo(
            f"Warning: skipping uv.lock generation — `uv lock` could not be launched "
            f"({exc}); {_FALLBACK}.",
            err=True,
        )
        return False
    if result.returncode != 0:
        typer.echo(
            f"Warning: `uv lock` failed — skipping uv.lock generation; {_FALLBACK}.\n"
            f"{result.stderr}",
            err=True,
        )
        return False
    return True
