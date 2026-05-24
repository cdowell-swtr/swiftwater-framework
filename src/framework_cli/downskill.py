from __future__ import annotations

from pathlib import Path

from framework_cli.batteries import resolve


class DownskillError(Exception):
    """Battery removal cannot proceed (refusal or invalid request)."""


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
