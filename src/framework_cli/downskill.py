from __future__ import annotations

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


def usage_references(project: Path, battery: str, *, package_name: str, owned: set[str]) -> list[str]:
    """Builder files that reference the battery (heuristic). Excludes the battery's own owned files.

    Looks for the battery's package import (`<package_name>.<battery>`) or a bare `<battery>`
    token in the project's `src/` tree. A guardrail, not a guarantee (can't see dynamic refs).
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
    owned = owned_files(answers, battery)

    refs = usage_references(project, battery, package_name=package_name, owned=owned)
    if refs and not force:
        raise DownskillError(
            f"battery {battery!r} appears in use by: {', '.join(refs)}. "
            "Re-run with --force to remove it anyway."
        )

    report = RemovalReport()
    reduced = [b for b in current if b != battery]

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
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        with_root = Path(a) / "r"
        without_root = Path(b) / "r"
        with_paths = _render_paths(answers, current, with_root)
        without_paths = _render_paths(answers, reduced, without_root)
        for rel in sorted(with_paths & without_paths):
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
