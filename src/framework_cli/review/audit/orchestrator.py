"""Deterministic, checkpoint-resumable work-queue for the audit stages. Each item's
output persists to <run_dir>/findings/<id>.json; a resume re-reads completed ids and
skips re-running them. Mirrors review/engine.run_engine, reusing checkpoint.py. ALL
orchestration is script-authored — no LLM 'manager' agent spawns sub-agents."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from framework_cli.review.backend import BackendExhausted
from framework_cli.review.checkpoint import (
    append_record,
    init_run,
    load_state,
    pending_items,
)


def _persisted(run_dir: Path, item_id: str) -> dict[str, Any]:
    return json.loads((run_dir / "findings" / f"{item_id}.json").read_text())


def run_stage(
    items: list[Any],
    work: Callable[[Any], dict[str, Any]],
    *,
    run_dir: Path,
    item_id: Callable[[Any], str],
    resume: bool = False,
    label: str = "stage",
    log: Callable[[str], None] = lambda _msg: None,
) -> list[dict[str, Any]]:
    ids = [item_id(it) for it in items]
    if not resume or not (run_dir / "run-state.json").exists():
        init_run(run_dir, planned=ids, git_sha="", dirty_hash="", backend="audit")
    todo = set(pending_items(run_dir))
    total = len(ids)
    done = total - len(todo)
    by_id = dict(zip(ids, items))
    for iid in list(todo):
        item = by_id[iid]
        try:
            record = work(item)
        except BackendExhausted:
            raise  # stop scheduling; a later resume continues
        except Exception as exc:  # noqa: BLE001 — record the one-off failure, keep going
            record = {"item": iid, "error": f"{type(exc).__name__}: {exc}"}
        append_record(run_dir, iid, record)
        done += 1
        log(f"[{label} {done}/{total}] {iid}")
    completed = load_state(run_dir)["done"]
    return [_persisted(run_dir, iid) for iid in ids if iid in completed]
