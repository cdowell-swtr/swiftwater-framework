from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path

from copier import run_copy


def template_path() -> Path:
    """Absolute path to the bundled Copier template directory."""
    return Path(str(files("framework_cli"))) / "template"


def render_project(dest: Path, data: Mapping[str, object]) -> None:
    """Render the bundled template into `dest` using the provided answers."""
    from framework_cli.migrations import migration_context

    merged = dict(data)
    batteries = merged.get("batteries", []) or []
    merged.update(migration_context(batteries if isinstance(batteries, list) else []))
    run_copy(
        str(template_path()),
        str(dest),
        data=merged,
        defaults=True,
        overwrite=True,
        quiet=True,
    )
