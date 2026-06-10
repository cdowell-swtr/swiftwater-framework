import subprocess

from framework_cli.review.checkpoint import (
    init_run,
    append_record,
    load_state,
    pending_items,
    is_stale,
    tree_signature,
)


def test_checkpoint_tracks_done_and_pending(tmp_path):
    run = tmp_path / "run"
    init_run(
        run,
        planned=["security", "architecture", "documentation"],
        git_sha="abc123",
        dirty_hash="d0",
        backend="subagent",
    )
    append_record(run, "security", {"agent": "security", "findings": []})
    state = load_state(run)
    assert state["done"] == ["security"]
    assert pending_items(run) == ["architecture", "documentation"]
    assert (run / "findings" / "security.json").is_file()


def test_is_stale_detects_tree_change(tmp_path):
    run = tmp_path / "run"
    init_run(
        run, planned=["security"], git_sha="abc123", dirty_hash="d0", backend="api"
    )
    assert is_stale(run, git_sha="abc123", dirty_hash="d0") is False
    assert is_stale(run, git_sha="abc123", dirty_hash="d1") is True
    assert is_stale(run, git_sha="zzz", dirty_hash="d0") is True


def test_tree_signature_changes_with_content(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True
    )
    (tmp_path / "f.txt").write_text("one")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    _, dirty1 = tree_signature(tmp_path)
    (tmp_path / "f.txt").write_text("two")
    _, dirty2 = tree_signature(tmp_path)
    assert dirty1 != dirty2
