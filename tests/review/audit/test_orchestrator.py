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
