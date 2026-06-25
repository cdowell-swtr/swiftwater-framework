"""Template-source coordinates and the portable-answers rewrite.

The bundled render records a machine-specific `_src_path`; we rewrite it to the portable
git source + version tag so `copier update` / `framework upskill` work from any machine.
"""

from __future__ import annotations

import json
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


def read_batteries(project: Path) -> list[str]:
    """The battery set recorded in the project's .copier-answers.yml ([] if none/absent)."""
    import yaml

    answers = project / _ANSWERS_REL
    if not answers.is_file():
        return []
    data = yaml.safe_load(answers.read_text()) or {}
    value = data.get("batteries", [])
    return [str(b) for b in value] if isinstance(value, list) else []


def read_package_name(project: Path) -> str | None:
    """The `package_name` answer recorded in the project's .copier-answers.yml (None if absent).

    Needed to resolve `{package_name}`-templated locked paths (e.g. the multitenantauth mechanism
    tree under src/<package_name>/) against a concrete rendered project.
    """
    import yaml

    answers = project / _ANSWERS_REL
    if not answers.is_file():
        return None
    data = yaml.safe_load(answers.read_text()) or {}
    value = data.get("package_name")
    return str(value) if value else None


def record_batteries(project: Path, batteries: list[str]) -> None:
    """Write the battery set into the project's .copier-answers.yml (framework-owned).

    Copier does not reliably re-emit the subdir-declared `batteries` answer through the portable
    `_subdirectory` source on update, so the framework owns this record: drop any existing
    `batteries:` block and append the current set.
    """
    answers = project / _ANSWERS_REL
    out: list[str] = []
    skipping = False
    for line in answers.read_text().splitlines():
        if line.startswith("batteries:"):
            skipping = True
            continue
        if skipping and line.startswith("- "):
            continue
        skipping = False
        out.append(line)
    if batteries:
        out.append("batteries:")
        out.extend(f"- {b}" for b in batteries)
    else:
        out.append("batteries: []")
    answers.write_text("\n".join(out) + "\n")


def read_alert_channels(project: Path) -> list[str]:
    """The alert channels recorded in .copier-answers.yml (['webhook'] if none/absent)."""
    import yaml

    answers = project / _ANSWERS_REL
    if not answers.is_file():
        return ["webhook"]
    data = yaml.safe_load(answers.read_text()) or {}
    value = data.get("alert_channels")
    # Unlike batteries, an *empty* channel set is incoherent (a project must alert somewhere),
    # so present-but-empty falls back to the default rather than being returned as-is.
    if isinstance(value, list) and value:
        return [str(c) for c in value]
    return ["webhook"]


def record_alert_channels(project: Path, channels: list[str]) -> None:
    """Write the alert-channel set into .copier-answers.yml (framework-owned, like batteries).

    Empty input records the ['webhook'] default so a project always has a channel.
    """
    effective = channels or ["webhook"]
    answers = project / _ANSWERS_REL
    out: list[str] = []
    skipping = False
    for line in answers.read_text().splitlines():
        if line.startswith("alert_channels:"):
            skipping = True
            continue
        if skipping and line.startswith("- "):
            continue
        skipping = False
        out.append(line)
    out.append("alert_channels:")
    out.extend(f"- {c}" for c in effective)
    answers.write_text("\n".join(out) + "\n")


IDENTITY_KEYS = ("project_name", "project_slug", "package_name", "python_version")


def read_identity(project: Path) -> dict[str, str]:
    """The identity answers present in .copier-answers.yml ({} if none/absent).

    Only keys actually present are returned, so callers can detect a missing/stripped set.
    """
    import yaml

    answers = project / _ANSWERS_REL
    if not answers.is_file():
        return {}
    data = yaml.safe_load(answers.read_text()) or {}
    return {k: str(data[k]) for k in IDENTITY_KEYS if k in data and data[k] is not None}


def record_identity(project: Path, identity: dict[str, str]) -> None:
    """Write the identity answers into .copier-answers.yml (framework-owned, like batteries).

    Copier does not reliably re-emit these subdir-declared answers through the portable
    `_subdirectory` source on update, so the framework re-records them: drop any existing
    line for each key and re-append it. Values are JSON-quoted, which is valid YAML and
    preserves strings such as python_version ("3.12") and names with spaces.
    """
    answers = project / _ANSWERS_REL
    out = [
        line
        for line in answers.read_text().splitlines()
        if not any(line.startswith(f"{k}:") for k in IDENTITY_KEYS)
    ]
    for key in IDENTITY_KEYS:
        if key in identity:
            out.append(f"{key}: {json.dumps(identity[key])}")
    answers.write_text("\n".join(out) + "\n")


def read_commit(project: Path) -> str | None:
    """The framework version tag recorded in .copier-answers.yml `_commit` (None if absent)."""
    import yaml

    answers = project / _ANSWERS_REL
    if not answers.is_file():
        return None
    data = yaml.safe_load(answers.read_text()) or {}
    value = data.get("_commit")
    return str(value) if value is not None else None


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
