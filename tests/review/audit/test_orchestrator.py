import threading
import time
from pathlib import Path

from framework_cli.review.audit.orchestrator import run_stage


def test_run_stage_persists_each_item_and_resumes(tmp_path: Path):
    calls = []

    def work(item):
        calls.append(item)
        return {"item": item, "out": item.upper()}

    run_dir = tmp_path / "audit" / "stage1"
    results = run_stage(["a", "b", "c"], work, run_dir=run_dir, item_id=lambda x: x)
    assert {r["out"] for r in results} == {"A", "B", "C"}
    assert (run_dir / "findings" / "a.json").exists()

    calls.clear()
    results2 = run_stage(
        ["a", "b", "c"], work, run_dir=run_dir, item_id=lambda x: x, resume=True
    )
    assert calls == []  # nothing re-run
    assert {r["out"] for r in results2} == {"A", "B", "C"}


def test_run_stage_records_failure_and_continues(tmp_path: Path):
    def work(item):
        if item == "b":
            raise ValueError("boom")
        return {"item": item, "out": item}

    run_dir = tmp_path / "audit" / "stage1"
    results = run_stage(["a", "b", "c"], work, run_dir=run_dir, item_id=lambda x: x)
    by = {r["item"]: r for r in results}
    assert by["a"]["out"] == "a" and by["c"]["out"] == "c"
    assert "error" in by["b"]


def test_run_stage_logs_progress_per_item(tmp_path: Path):
    """log is called once per completed item with a monotonic done/total count."""
    logged: list[str] = []

    def work(item):
        return {"item": item, "out": item.upper()}

    run_dir = tmp_path / "audit" / "stage1"
    run_stage(
        ["a", "b", "c"],
        work,
        run_dir=run_dir,
        item_id=lambda x: x,
        label="myStage",
        log=logged.append,
    )

    assert len(logged) == 3
    # Each line must contain the label and a monotonic done/total fraction.
    assert all("myStage" in line for line in logged)
    counts = []
    for line in logged:
        # Expect pattern "[myStage N/3]"
        import re

        m = re.search(r"\[myStage (\d+)/(\d+)\]", line)
        assert m is not None, f"Expected progress pattern in {line!r}"
        counts.append(int(m.group(1)))
    assert counts == sorted(counts), "done counts are not monotonically increasing"
    assert counts[-1] == 3


# ── H2.1 concurrent run_stage tests ────────────────────────────────────────


def test_run_stage_concurrency_matches_serial(tmp_path: Path):
    """concurrency=4 produces the same result set as concurrency=1 (serial)."""

    def work(item):
        return {"item": item, "out": item.upper()}

    serial_dir = tmp_path / "serial"
    concurrent_dir = tmp_path / "concurrent"

    serial_results = run_stage(
        ["a", "b", "c", "d"], work, run_dir=serial_dir, item_id=lambda x: x
    )
    concurrent_results = run_stage(
        ["a", "b", "c", "d"],
        work,
        run_dir=concurrent_dir,
        item_id=lambda x: x,
        concurrency=4,
    )

    # Same result set (order may differ since concurrent completes out-of-order)
    assert {r["out"] for r in serial_results} == {r["out"] for r in concurrent_results}
    assert {r["item"] for r in serial_results} == {
        r["item"] for r in concurrent_results
    }

    # All per-item files written
    for iid in ["a", "b", "c", "d"]:
        assert (concurrent_dir / "findings" / f"{iid}.json").exists()


def test_run_stage_concurrency_is_actually_parallel(tmp_path: Path):
    """With concurrency=4, workers genuinely overlap (peak-active >= 2)."""
    lock = threading.Lock()
    active = 0
    peak = 0

    def work(item):
        nonlocal active, peak
        with lock:
            active += 1
            if active > peak:
                peak = active
        time.sleep(0.05)
        with lock:
            active -= 1
        return {"item": item, "out": item}

    run_stage(
        ["a", "b", "c", "d"],
        work,
        run_dir=tmp_path / "par",
        item_id=lambda x: x,
        concurrency=4,
    )
    assert peak >= 2, f"Expected peak active >= 2, got {peak}"


def test_run_stage_concurrent_resume_skips_done(tmp_path: Path):
    """A second concurrent run with resume=True re-runs nothing."""
    calls = []

    def work(item):
        calls.append(item)
        return {"item": item, "out": item.upper()}

    run_dir = tmp_path / "res"
    run_stage(
        ["a", "b", "c"], work, run_dir=run_dir, item_id=lambda x: x, concurrency=3
    )
    calls.clear()

    run_stage(
        ["a", "b", "c"],
        work,
        run_dir=run_dir,
        item_id=lambda x: x,
        concurrency=3,
        resume=True,
    )
    assert calls == [], f"Expected no re-runs, but got: {calls}"


def test_run_stage_concurrent_reraises_exhaustion(tmp_path: Path):
    """BackendExhausted from a concurrent worker propagates after the pool drains."""
    import json

    import pytest

    from framework_cli.review.backend import BackendExhausted

    def work(x):
        if x == "b":
            raise BackendExhausted("limit")
        return {"item": x, "out": x}

    with pytest.raises(BackendExhausted):
        run_stage(
            ["a", "b", "c", "d"],
            work,
            run_dir=tmp_path / "e",
            item_id=lambda x: x,
            concurrency=4,
        )

    # The non-exhausted items that completed are checkpointed
    done = json.load(open(tmp_path / "e" / "run-state.json"))["done"]
    assert "b" not in done  # the exhausted item is NOT marked done


def test_run_stage_concurrent_exhaustion_short_circuits(tmp_path: Path):
    # When the backend exhausts early, not-yet-started workers must skip (don't burn
    # doomed calls on a dead backend) — mirrors the serial path's stop-scheduling.
    import pytest

    from framework_cli.review.backend import BackendExhausted

    started: list[str] = []
    started_lock = threading.Lock()

    def work(x):
        with started_lock:
            started.append(x)
        # the very first item to run exhausts the backend
        raise BackendExhausted("limit")

    items = [f"i{n:02d}" for n in range(20)]
    with pytest.raises(BackendExhausted):
        run_stage(
            items, work, run_dir=tmp_path / "sc", item_id=lambda x: x, concurrency=4
        )
    # at most ~concurrency workers got in flight before the stop Event was observed;
    # the bulk of the backlog is skipped, not run against the dead backend.
    assert len(started) < len(items)
