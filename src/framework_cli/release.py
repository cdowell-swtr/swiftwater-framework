from __future__ import annotations

import tomllib
from pathlib import Path


def read_project_version(pyproject: Path) -> str:
    data = tomllib.loads(pyproject.read_text())
    return str(data["project"]["version"])


def assert_tag_matches(tag: str, pyproject: Path) -> None:
    """Raise unless `tag` equals `v<project version>` (the RELEASING.md invariant)."""
    version = read_project_version(pyproject)
    expected = f"v{version}"
    if tag != expected:
        raise ValueError(
            f"release tag {tag!r} does not match project version {version!r} "
            f"(expected {expected!r}); fix the tag or the pyproject version"
        )
