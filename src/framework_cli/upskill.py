"""`framework upskill`: bring a project up to a newer framework version.

Runs Copier's update (3-way merge from the project's recorded version to the target),
then `task test`; reports whether the upgraded project is green. Conflicts are left as
inline markers for manual resolution (Copier's standard behavior).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from copier import run_update

from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.manifest import installed_framework_version


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


def _apply_update(
    project: Path,
    *,
    vcs_ref: str | None,
    batteries: list[str],
    channels: list[str],
) -> bool:
    """Re-render `project` at `vcs_ref` via Copier, preserving identity, then run `task test`.

    The single low-level update path shared by `framework upgrade` and `upskill --with`.
    Assumes preconditions (git-tracked, and for upgrade a clean tree) are already checked.
    """
    from framework_cli.migrations import migration_context
    from framework_cli.source import IDENTITY_KEYS, read_identity, record_identity

    identity = read_identity(project)
    # Fail-closed guard: if the project has ANY identity key recorded (it was initialised
    # from the real framework template), ALL four must be present. A partial set means the
    # answers were stripped by a prior update — refuse rather than render an empty package.
    # Projects built from simpler templates (no identity questions) have none of the keys
    # and are allowed through unchanged.
    if identity:
        missing = [k for k in IDENTITY_KEYS if not identity.get(k)]
        if missing:
            raise UpskillError(
                f".copier-answers.yml is missing identity answers ({', '.join(missing)}); "
                "refusing to update rather than render an empty project. Restore them and retry."
            )

    run_update(
        str(project),
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref=vcs_ref,
        data={
            **identity,
            "batteries": batteries,
            "alert_channels": channels,
            **migration_context(batteries),
        },
    )
    from framework_cli.source import record_alert_channels, record_batteries

    record_batteries(project, batteries)
    record_alert_channels(project, channels)
    record_identity(project, identity)
    # The update may have changed managed sections / locked files (incl. battery-conditional
    # lines like the webhooks secret in .env.example). Re-record the integrity manifest so
    # `framework integrity` reflects the upgraded state.
    # Guard: only regenerate when a manifest already exists — minimal-template upskill tests
    # (no .framework/integrity.lock) must not raise AuthoringError.
    if (project / ".framework" / "integrity.lock").is_file():
        write_manifest(project, installed_framework_version())
    try:
        test = subprocess.run(["task", "test"], cwd=project, check=False)
    except FileNotFoundError as exc:
        raise UpskillError(
            "`task` (go-task) not found on PATH — install it to run the project's tests"
        ) from exc
    return test.returncode == 0


def upskill_project(
    project: Path,
    vcs_ref: str | None = None,
    with_batteries: list[str] | None = None,
    alert_channels: list[str] | None = None,
) -> bool:
    """Add batteries / reconfigure channels for `project`, then run `task test`."""
    from framework_cli.source import read_alert_channels, read_batteries

    if not _is_git_tracked(project):
        raise UpskillError(
            "upskill requires a git-tracked project (run `git init` and commit first)"
        )
    effective = (
        with_batteries if with_batteries is not None else read_batteries(project)
    )
    channels = (
        alert_channels if alert_channels is not None else read_alert_channels(project)
    )
    return _apply_update(
        project, vcs_ref=vcs_ref, batteries=effective, channels=channels
    )
