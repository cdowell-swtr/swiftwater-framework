from __future__ import annotations

import tomllib
from pathlib import Path

_VALID: tuple[str, ...] = ("api", "subagent")
_CONFIG_REL = Path(".framework") / "review.toml"


def _config_path(root: Path) -> Path:
    return root / _CONFIG_REL


def read_backend_choice(root: Path) -> str | None:
    """The persisted backend, or None. Fail-open: malformed config → None (the
    resolution layer treats None as 'no intent')."""
    path = _config_path(root)
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, OSError):
        return None
    choice = data.get("backend")
    return choice if choice in _VALID else None


def write_backend_choice(root: Path, backend: str) -> None:
    if backend not in _VALID:
        raise ValueError(f"unknown backend {backend!r}; expected one of {_VALID}")
    path = _config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'backend = "{backend}"\n')


def clear_backend_choice(root: Path) -> None:
    """Remove the persisted choice → resolution returns to the no-intent default."""
    _config_path(root).unlink(missing_ok=True)
