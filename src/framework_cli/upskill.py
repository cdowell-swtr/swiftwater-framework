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


def upskill_project(
    project: Path, vcs_ref: str | None = None, with_batteries: list[str] | None = None
) -> bool:
    """Update `project` to `vcs_ref` (default: latest tag) and run `task test`.

    The effective battery set (`with_batteries` if given, else the project's recorded set) is
    passed to the update AND re-recorded afterward — the framework owns the battery record,
    since Copier does not preserve the subdir-declared `batteries` answer through the portable
    source on update.
    """
    from framework_cli.source import read_batteries, record_batteries

    if not _is_git_tracked(project):
        raise UpskillError(
            "upskill requires a git-tracked project (run `git init` and commit first)"
        )
    effective = (
        with_batteries if with_batteries is not None else read_batteries(project)
    )
    run_update(
        str(project),
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref=vcs_ref,
        data={"batteries": effective},
    )
    record_batteries(project, effective)
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
