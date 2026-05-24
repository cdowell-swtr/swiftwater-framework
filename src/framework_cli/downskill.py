from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path

from framework_cli.batteries import resolve
from framework_cli.copier_runner import render_project


class DownskillError(Exception):
    """Battery removal cannot proceed (refusal or invalid request)."""


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
