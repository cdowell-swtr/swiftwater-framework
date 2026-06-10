from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

_STATE = "run-state.json"


def _state_path(run_dir: Path) -> Path:
    return run_dir / _STATE


def init_run(
    run_dir: Path, *, planned: list[str], git_sha: str, dirty_hash: str, backend: str
) -> None:
    (run_dir / "findings").mkdir(parents=True, exist_ok=True)
    _write_state(
        run_dir,
        {
            "planned": list(planned),
            "done": [],
            "git_sha": git_sha,
            "dirty_hash": dirty_hash,
            "backend": backend,
        },
    )


def _write_state(run_dir: Path, state: dict[str, Any]) -> None:
    tmp = _state_path(run_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(_state_path(run_dir))  # atomic: a crash mid-write never corrupts state


def load_state(run_dir: Path) -> dict[str, Any]:
    return json.loads(_state_path(run_dir).read_text())


def append_record(run_dir: Path, agent: str, record: dict[str, Any]) -> None:
    """Write one agent's record AND mark it done — so resume never re-runs a completed
    agent or loses a written record."""
    rec = run_dir / "findings" / f"{agent}.json"
    rec.write_text(json.dumps(record, indent=2, sort_keys=True))
    rec.chmod(0o600)
    state = load_state(run_dir)
    if agent not in state["done"]:
        state["done"].append(agent)
    _write_state(run_dir, state)


def pending_items(run_dir: Path) -> list[str]:
    state = load_state(run_dir)
    done = set(state["done"])
    return [a for a in state["planned"] if a not in done]


def is_stale(run_dir: Path, *, git_sha: str, dirty_hash: str) -> bool:
    state = load_state(run_dir)
    return state["git_sha"] != git_sha or state["dirty_hash"] != dirty_hash


def tree_signature(root: Path) -> tuple[str, str]:
    """(HEAD sha, dirty-hash). The dirty-hash digests `git status --porcelain` + `git diff`,
    so any uncommitted change moves it. Fail-open: a non-git dir returns ("", <digest>)."""

    def _git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True, check=True
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    sha = _git("rev-parse", "HEAD").strip()
    digest = hashlib.sha256(
        (_git("status", "--porcelain") + _git("diff")).encode("utf-8", "replace")
    ).hexdigest()[:16]
    return sha, digest
