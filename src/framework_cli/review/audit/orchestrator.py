"""Deterministic, checkpoint-resumable work-queue for the audit stages. Each item's
output persists to <run_dir>/findings/<id>.json; a resume re-reads completed ids and
skips re-running them. Mirrors review/engine.run_engine, reusing checkpoint.py. ALL
orchestration is script-authored — no LLM 'manager' agent spawns sub-agents."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
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
    concurrency: int = 1,
) -> list[dict[str, Any]]:
    ids = [item_id(it) for it in items]
    if not resume or not (run_dir / "run-state.json").exists():
        init_run(run_dir, planned=ids, git_sha="", dirty_hash="", backend="audit")
    todo = set(pending_items(run_dir))
    todo_list = [
        iid for iid in ids if iid in todo
    ]  # stable order (insertion order of ids)
    total = len(ids)
    done = total - len(todo)
    by_id = dict(zip(ids, items))

    if concurrency <= 1 or len(todo_list) <= 1:
        # Serial path — byte-for-byte equivalent to the prior implementation.
        for iid in todo_list:
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
    else:
        # Concurrent path — thread pool over pending items.
        # CRITICAL: append_record (run-state.json read+write) races under concurrency;
        # the lock serialises all state mutations.  Per-item findings/<id>.json writes
        # inside append_record are safe because each thread writes a distinct file.
        lock = threading.Lock()
        exhausted: list[BackendExhausted] = []
        stop = (
            threading.Event()
        )  # set on first exhaustion → skip not-yet-started workers

        def _do(iid: str) -> None:
            nonlocal done
            if stop.is_set():
                # Backend already exhausted: don't burn a doomed call on a dead backend
                # (mirrors the serial path's immediate stop-scheduling).
                return
            try:
                record = work(by_id[iid])
            except BackendExhausted as exc:
                # Capture, stop scheduling new work, let in-flight workers finish,
                # re-raise after the pool drains.
                stop.set()
                with lock:
                    exhausted.append(exc)
                return
            except Exception as exc:  # noqa: BLE001
                record = {"item": iid, "error": f"{type(exc).__name__}: {exc}"}
            with lock:
                append_record(run_dir, iid, record)
                done += 1
                log(f"[{label} {done}/{total}] {iid}")

        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            wait([ex.submit(_do, iid) for iid in todo_list])

        if exhausted:
            raise exhausted[0]

    completed = load_state(run_dir)["done"]
    return [_persisted(run_dir, iid) for iid in ids if iid in completed]
