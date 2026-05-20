from importlib.resources import files
from pathlib import Path

from copier import run_copy


def template_path() -> Path:
    """Absolute path to the bundled Copier template directory."""
    return Path(str(files("framework_cli"))) / "template"


def render_project(dest: Path, data: dict[str, str]) -> None:
    """Render the bundled template into `dest` using the provided answers."""
    run_copy(
        str(template_path()),
        str(dest),
        data=data,
        defaults=True,
        overwrite=True,
        quiet=True,
    )
