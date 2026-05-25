from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from framework_cli.batteries import get_battery, resolve
from framework_cli.copier_runner import render_project
from framework_cli.integrity.classes import HYBRID_TRACKED
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.integrity.restore import _answers, _restore_section
from framework_cli.source import read_batteries, record_batteries
from framework_cli.upskill import UpskillError, _is_git_tracked


class DownskillError(Exception):
    """Battery removal cannot proceed (refusal or invalid request)."""


_MIGRATIONS_PREFIX = "migrations/versions/"
_LOCK_REL = ".framework/integrity.lock"


@dataclass
class RemovalReport:
    removed: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _render_paths(answers: Mapping[str, object], batteries: list[str], dest: Path) -> set[str]:
    render_project(dest, {**answers, "batteries": batteries})
    return {str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()}


def owned_files(answers: Mapping[str, object], battery: str) -> set[str]:
    """Files a battery owns = those present WITH it but absent at the reduced set (two renders)."""
    current = [str(b) for b in answers.get("batteries", [])]  # type: ignore[attr-defined]
    reduced = [b for b in current if b != battery]
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        with_paths = _render_paths(answers, current, Path(a) / "r")
        without_paths = _render_paths(answers, reduced, Path(b) / "r")
    return with_paths - without_paths


def blocking_dependents(active: list[str], battery: str) -> list[str]:
    """Active batteries (other than `battery`) whose dependency-closure includes `battery`."""
    return sorted(b for b in active if b != battery and battery in resolve([b]))


def usage_references(
    project: Path,
    battery: str,
    *,
    package_name: str,
    owned: set[str],
    with_render_root: Path | None = None,
) -> list[str]:
    """Builder files that reference the battery (heuristic). Excludes the battery's own owned files.

    Looks for the battery's package import (`<package_name>.<battery>`) or a bare `<battery>`
    token in the project's `src/` tree. A guardrail, not a guarantee (can't see dynamic refs).

    Files whose content is byte-identical to the framework-rendered version (``with_render_root``)
    are excluded — their battery references are framework-managed gated blocks, not builder code.
    """
    hits: list[str] = []
    needles = (f"{package_name}.{battery}", battery)
    src = project / "src"
    if not src.is_dir():
        return hits
    for path in sorted(src.rglob("*.py")):
        rel = str(path.relative_to(project))
        if rel in owned:
            continue
        text = path.read_text()
        if any(n in text for n in needles):
            # Skip if the file is unmodified from the framework's battery render — the
            # reference lives inside a gated `{% if battery %}` block and will be spliced
            # out by remove_battery's shared-file step.  Only builder-added references
            # (i.e. the project file differs from the template render) are actionable.
            if with_render_root is not None:
                rendered = with_render_root / rel
                if rendered.is_file() and rendered.read_bytes() == path.read_bytes():
                    continue
            hits.append(rel)
    return hits


def remove_battery(project: Path, battery: str, *, force: bool = False) -> RemovalReport:
    """Remove `battery` from `project` (framework-owned). Raises DownskillError on a refusal."""
    get_battery(battery)  # KeyError -> unknown battery
    current = read_batteries(project)
    if battery not in current:
        raise DownskillError(f"battery {battery!r} is not active in this project")
    dependents = blocking_dependents(current, battery)
    if dependents:
        raise DownskillError(f"cannot remove {battery!r}: still required by {', '.join(dependents)}")

    answers = _answers(project)
    package_name = str(answers.get("package_name", ""))
    reduced = [b for b in current if b != battery]

    # Single pair of renders shared by owned-file detection, usage scan, and shared-file splice.
    with tempfile.TemporaryDirectory() as _a, tempfile.TemporaryDirectory() as _b:
        with_root = Path(_a) / "r"
        without_root = Path(_b) / "r"
        with_paths = _render_paths(answers, current, with_root)
        without_paths = _render_paths(answers, reduced, without_root)
        owned = with_paths - without_paths

        refs = usage_references(
            project,
            battery,
            package_name=package_name,
            owned=owned,
            with_render_root=with_root,
        )
        if refs and not force:
            raise DownskillError(
                f"battery {battery!r} appears in use by: {', '.join(refs)}. "
                "Re-run with --force to remove it anyway."
            )

        report = RemovalReport()

        # 1) delete owned whole-files, preserving migrations
        for rel in sorted(owned):
            if rel.startswith(_MIGRATIONS_PREFIX):
                report.preserved.append(rel)
                continue
            target = project / rel
            if target.is_file():
                target.unlink()
            report.removed.append(rel)
        # prune now-empty owned dirs (deepest first)
        for rel in sorted(owned, key=len, reverse=True):
            d = (project / rel).parent
            if d.is_dir() and d != project and not any(d.iterdir()):
                d.rmdir()

        # 2) shared files the battery CHANGED: splice hybrid / overwrite-if-unmodified / warn
        for rel in sorted(with_paths & without_paths):
            if rel == ".copier-answers.yml":
                continue  # step 3 (record_batteries) owns this file
            wf, wo = with_root / rel, without_root / rel
            if wf.read_bytes() == wo.read_bytes():
                continue  # battery didn't touch this file
            target = project / rel
            if rel in HYBRID_TRACKED:
                _restore_section(target, wo)
            elif target.is_file() and target.read_bytes() == wf.read_bytes():
                target.write_bytes(wo.read_bytes())
            else:
                report.warnings.append(rel)

    # 3) re-record + regenerate the manifest (inverse of 8b's upskill regen)
    record_batteries(project, reduced)
    if (project / _LOCK_REL).is_file():
        write_manifest(project, installed_framework_version())

    if report.preserved:
        report.warnings.append(
            "migration(s) preserved: " + ", ".join(report.preserved)
            + " — write a contract down-migration to drop the table(s) if desired."
        )
    return report


def downskill_project(project: Path, battery: str, *, force: bool = False) -> bool:
    """Remove `battery`, then run `task test`. Returns whether the project is green afterward."""
    if not _is_git_tracked(project):
        raise DownskillError(
            "downskill requires a git-tracked project (commit first, so you can review/revert)"
        )
    remove_battery(project, battery, force=force)
    try:
        test = subprocess.run(["task", "test"], cwd=project, check=False)
    except FileNotFoundError as exc:
        raise UpskillError(
            "`task` (go-task) not found on PATH — install it to run the project's tests"
        ) from exc
    return test.returncode == 0
