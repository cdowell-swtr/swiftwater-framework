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


def _clone_template(src_path: str, vcs_ref: str | None, dest: str) -> None:
    """Clone the template source (`gh:owner/repo` or a local path) at `vcs_ref` into `dest`."""
    url = (
        "https://github.com/" + src_path[3:] if src_path.startswith("gh:") else src_path
    )
    # --depth 1 keeps the gh: clone cheap (a tag's tip only); git ignores it for local paths.
    cmd = ["git", "clone", "--quiet", "--depth", "1"]
    if vcs_ref:
        cmd += ["--branch", vcs_ref]
    cmd += [url, dest]
    subprocess.run(cmd, check=True, capture_output=True)


def _template_subdir(clone_root: Path) -> Path:
    """The directory copier renders from — the `_subdirectory` of the cloned source, if any."""
    import yaml

    cfg = yaml.safe_load((clone_root / "copier.yml").read_text()) or {}
    sub = cfg.get("_subdirectory")
    return clone_root / sub if sub else clone_root


def _derived_defaults_for_absent_questions(
    project: Path,
    *,
    vcs_ref: str | None,
    identity: dict[str, str],
    batteries: list[str],
    channels: list[str],
) -> dict[str, object]:
    """Compute derived defaults for questions the project's answers predate (DV-1).

    A question added after a project was created (e.g. `pi_prefix`, added in FWK9) has no
    recorded answer; copier's update path then renders the managed block that uses it with
    an empty value instead of the default a fresh render would compute. (Copier computes a
    question's derived default only when rendering the template *directory* — as `framework
    new` does — not through the portable `_subdirectory` source that `update` uses.) Mirror
    a fresh `new`: clone the template at `vcs_ref`, render its subdirectory into a throwaway
    dir with the project's identity, and return the `{question: value}` map copier computed
    for questions ABSENT from the project's recorded answers — to force via `data`.

    Best-effort: any failure (no `_src_path`, clone/render error) returns `{}`, leaving
    today's behavior. The real `run_update` below remains the source of truth.
    """
    import tempfile
    from datetime import date

    import yaml
    from copier import run_copy

    from framework_cli.migrations import migration_context

    answers_file = project / ".copier-answers.yml"
    if not answers_file.is_file():
        return {}
    recorded = yaml.safe_load(answers_file.read_text()) or {}
    src_path = recorded.get("_src_path")
    if not src_path:
        return {}
    data = {
        **identity,
        "batteries": batteries,
        "alert_channels": channels,
        "render_date": date.today().isoformat(),
        **migration_context(batteries),
    }
    try:
        with (
            tempfile.TemporaryDirectory() as clone,
            tempfile.TemporaryDirectory() as dst,
        ):
            _clone_template(str(src_path), vcs_ref, clone)
            run_copy(
                str(_template_subdir(Path(clone))),
                dst,
                data=data,
                defaults=True,
                overwrite=True,
                quiet=True,
            )
            fresh = (
                yaml.safe_load((Path(dst) / ".copier-answers.yml").read_text()) or {}
            )
    except Exception:
        return {}
    # Preserve each value's native type (a derived default may be a bool/int, not a str).
    return {
        k: v
        for k, v in fresh.items()
        if not k.startswith("_")
        and k not in recorded
        and k not in data
        and v is not None
    }


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
    # Fail-closed guard: ALL four identity keys must be present.  Real framework projects
    # always have them; a missing set (partial OR all-absent) means the answers were stripped
    # by a prior update — refuse rather than silently render an empty package name.
    missing = [k for k in IDENTITY_KEYS if not identity.get(k)]
    if missing:
        raise UpskillError(
            f".copier-answers.yml is missing identity answers ({', '.join(missing)}); "
            "refusing to proceed rather than render an empty project. Restore them and retry."
        )

    # DV-1: supply derived defaults for questions added after the project was created, so
    # their managed blocks render the computed default instead of an empty value.
    derived = _derived_defaults_for_absent_questions(
        project,
        vcs_ref=vcs_ref,
        identity=identity,
        batteries=batteries,
        channels=channels,
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
            **derived,
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
    """Add batteries / reconfigure channels for `project` at its recorded version, then test."""
    from framework_cli.source import read_alert_channels, read_batteries, read_commit

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
    pinned = vcs_ref if vcs_ref is not None else read_commit(project)
    return _apply_update(
        project, vcs_ref=pinned, batteries=effective, channels=channels
    )
