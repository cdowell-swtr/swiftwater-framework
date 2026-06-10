from __future__ import annotations

import tomllib
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Resolution:
    backend: str | None  # "api" | "subagent" | None (degrade)
    reason: str  # resolved | no-intent | api-unavailable | subagent-unavailable
    intent: str | None  # chosen backend before availability check (for messaging)


def resolve_backend(
    *,
    root: Path,
    flag: str | None,
    env: dict[str, str],
    availability: dict[str, bool],
) -> Resolution:
    intent = flag or env.get("FRAMEWORK_REVIEW_BACKEND") or read_backend_choice(root)
    if intent not in _VALID:
        return Resolution(backend=None, reason="no-intent", intent=None)
    if intent == "api":
        if availability.get("api_key_present"):
            return Resolution(backend="api", reason="resolved", intent="api")
        return Resolution(backend=None, reason="api-unavailable", intent="api")
    if availability.get("claude_available"):
        return Resolution(backend="subagent", reason="resolved", intent="subagent")
    return Resolution(backend=None, reason="subagent-unavailable", intent="subagent")
