"""Discovery helpers for prior audit baseline directories.

Audit baselines live under `docs/superpowers/eval-scorecards/audit-*/`. Each
contains a `meta.json` with at least `target`, `git_sha`, and `agents`. These
helpers locate the newest baseline for a given (target, agent) and read its
SHA. Used by `framework audit` (via `_resolve_audit_base`) to compute
per-agent delta diffs.
"""

from __future__ import annotations

import json
from pathlib import Path

_AUDIT_PREFIX = "audit-"


def is_baseline_dir(path: Path) -> bool:
    """True iff `path` is a directory with a readable meta.json containing a
    non-empty `git_sha`. Used to disambiguate `--since <ref>` from
    `--since <baseline-dir>`.
    """
    if not path.is_dir():
        return False
    meta_path = path / "meta.json"
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return bool(meta.get("git_sha"))


def read_baseline_sha(baseline_dir: Path) -> str | None:
    """Return the `git_sha` recorded in baseline_dir/meta.json, or None if
    the file is missing, unreadable, or missing the field.
    """
    meta_path = baseline_dir / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    sha = meta.get("git_sha")
    return sha if isinstance(sha, str) and sha else None


def find_latest_baseline_for_agent(
    target: str, agent: str, scorecards_root: Path
) -> Path | None:
    """Return the newest baseline dir under `scorecards_root` whose target
    matches and whose `agents` list includes `agent`.

    Scan order: lexicographic dir name (deterministic). Newest = greatest
    name. Skips dirs that don't start with `audit-`, that aren't valid
    baseline dirs (`is_baseline_dir`), or whose meta.json doesn't list the
    requested agent. Returns None if no match.
    """
    if not scorecards_root.is_dir():
        return None
    matches: list[Path] = []
    for entry in scorecards_root.iterdir():
        if not entry.is_dir() or not entry.name.startswith(_AUDIT_PREFIX):
            continue
        if not is_baseline_dir(entry):
            continue
        try:
            meta = json.loads((entry / "meta.json").read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if meta.get("target") != target:
            continue
        agents = meta.get("agents") or []
        if not isinstance(agents, list) or agent not in agents:
            continue
        matches.append(entry)
    if not matches:
        return None
    matches.sort(key=lambda p: p.name)
    return matches[-1]
