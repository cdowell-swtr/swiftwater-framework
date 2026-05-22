"""Template-source coordinates and the portable-answers rewrite.

The bundled render records a machine-specific `_src_path`; we rewrite it to the portable
git source + version tag so `copier update` / `framework upskill` work from any machine.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Copier source form (recorded in .copier-answers.yml _src_path).
REPO_GH = "gh:cdowell-swtr/swiftwater-framework"
# HTTPS form (for `git ls-remote` and `uv tool install git+...`).
REPO_URL = "https://github.com/cdowell-swtr/swiftwater-framework"

_ANSWERS_REL = ".copier-answers.yml"


def version_tag(version: str) -> str:
    """Map a package version to its git release tag."""
    return f"v{version}"


_TAG_RE = re.compile(r"refs/tags/(v\d+\.\d+\.\d+)$")


def latest_release(url: str = REPO_URL) -> str | None:
    """Highest vX.Y.Z tag in the remote, or None. `url` may be a local path (for tests)."""
    result = subprocess.run(
        ["git", "ls-remote", "--tags", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    tags: dict[tuple[int, int, int], str] = {}
    for line in result.stdout.splitlines():
        m = _TAG_RE.search(line)
        if m:
            tag = m.group(1)
            major, minor, patch = (int(n) for n in tag[1:].split("."))
            tags[(major, minor, patch)] = tag
    if not tags:
        return None
    return tags[max(tags)]


def record_portable_source(project: Path, version: str) -> None:
    """Rewrite the project's .copier-answers.yml to a portable git source + version tag.

    Drops any `_src_path`/`_commit` lines and re-adds them pointing at REPO_GH / vX.Y.Z;
    leaves all real answers untouched.
    """
    answers = project / _ANSWERS_REL
    kept = [
        line
        for line in answers.read_text().splitlines()
        if not line.startswith(("_src_path:", "_commit:"))
    ]
    kept += [f"_src_path: {REPO_GH}", f"_commit: {version_tag(version)}"]
    answers.write_text("\n".join(kept) + "\n")
