"""Tests for framework_cli.review.baselines (baseline discovery on disk)."""

from __future__ import annotations

import json
from pathlib import Path

from framework_cli.review.baselines import (
    find_latest_baseline_for_agent,
    is_baseline_dir,
    read_baseline_sha,
)


def _write_baseline(
    root: Path,
    name: str,
    target: str,
    git_sha: str,
    agents: list[str],
) -> Path:
    """Helper: create a baseline dir with a minimal meta.json."""
    d = root / name
    d.mkdir(parents=True)
    (d / "meta.json").write_text(
        json.dumps(
            {"target": target, "git_sha": git_sha, "agents": agents},
            indent=2,
            sort_keys=True,
        )
    )
    return d


def test_is_baseline_dir_true_for_valid_dir(tmp_path: Path) -> None:
    d = _write_baseline(
        tmp_path, "audit-2026-01-01-aaa", "framework", "abc1234", ["security"]
    )
    assert is_baseline_dir(d) is True


def test_is_baseline_dir_false_for_missing_meta(tmp_path: Path) -> None:
    d = tmp_path / "no-meta"
    d.mkdir()
    assert is_baseline_dir(d) is False


def test_is_baseline_dir_false_for_meta_without_git_sha(tmp_path: Path) -> None:
    d = tmp_path / "bad-meta"
    d.mkdir()
    (d / "meta.json").write_text('{"target": "framework"}')
    assert is_baseline_dir(d) is False


def test_is_baseline_dir_false_for_unparseable_meta(tmp_path: Path) -> None:
    d = tmp_path / "broken-meta"
    d.mkdir()
    (d / "meta.json").write_text("not json {{{")
    assert is_baseline_dir(d) is False


def test_is_baseline_dir_false_for_file(tmp_path: Path) -> None:
    f = tmp_path / "not-a-dir"
    f.write_text("just a file")
    assert is_baseline_dir(f) is False


def test_read_baseline_sha_returns_git_sha(tmp_path: Path) -> None:
    d = _write_baseline(tmp_path, "audit-x", "framework", "deadbeef1234", ["x"])
    assert read_baseline_sha(d) == "deadbeef1234"


def test_read_baseline_sha_returns_none_for_missing_meta(tmp_path: Path) -> None:
    d = tmp_path / "no-meta"
    d.mkdir()
    assert read_baseline_sha(d) is None


def test_read_baseline_sha_returns_none_for_meta_without_git_sha(
    tmp_path: Path,
) -> None:
    d = tmp_path / "incomplete"
    d.mkdir()
    (d / "meta.json").write_text('{"target": "framework"}')
    assert read_baseline_sha(d) is None


def test_find_latest_baseline_for_agent_picks_newest_match(tmp_path: Path) -> None:
    _write_baseline(
        tmp_path,
        "audit-2026-01-01-a",
        "framework",
        "sha-old",
        ["security", "documentation"],
    )
    _write_baseline(
        tmp_path, "audit-2026-03-01-c", "framework", "sha-new", ["security"]
    )
    _write_baseline(
        tmp_path,
        "audit-2026-02-01-b",
        "framework",
        "sha-mid",
        ["security", "architecture"],
    )

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-03-01-c"


def test_find_latest_baseline_for_agent_filters_by_target(tmp_path: Path) -> None:
    _write_baseline(
        tmp_path, "audit-2026-01-01-fwk", "framework", "sha-f", ["security"]
    )
    _write_baseline(tmp_path, "audit-2026-02-01-tpl", "project", "sha-p", ["security"])

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-01-01-fwk"


def test_find_latest_baseline_for_agent_filters_by_agent(tmp_path: Path) -> None:
    _write_baseline(tmp_path, "audit-2026-01-01-a", "framework", "sha-1", ["security"])
    _write_baseline(
        tmp_path, "audit-2026-02-01-b", "framework", "sha-2", ["architecture"]
    )

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-01-01-a"


def test_find_latest_baseline_for_agent_returns_none_when_no_match(
    tmp_path: Path,
) -> None:
    _write_baseline(tmp_path, "audit-2026-01-01-a", "project", "sha-1", ["security"])

    assert find_latest_baseline_for_agent("framework", "security", tmp_path) is None


def test_find_latest_baseline_for_agent_returns_none_when_root_missing(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "nonexistent"
    assert find_latest_baseline_for_agent("framework", "security", missing) is None


def test_find_latest_baseline_for_agent_skips_malformed_meta(tmp_path: Path) -> None:
    _write_baseline(
        tmp_path, "audit-2026-01-01-good", "framework", "sha-good", ["security"]
    )
    bad = tmp_path / "audit-2026-02-01-bad"
    bad.mkdir()
    (bad / "meta.json").write_text("not json {{{")

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-01-01-good"


def test_find_latest_baseline_for_agent_ignores_non_audit_dirs(tmp_path: Path) -> None:
    _write_baseline(tmp_path, "audit-2026-01-01-a", "framework", "sha-1", ["security"])
    # Tune scorecards live in the same parent — must NOT be picked up.
    tune = tmp_path / "2026-02-01-something"
    tune.mkdir()
    (tune / "meta.json").write_text(
        json.dumps(
            {"target": "framework", "git_sha": "sha-tune", "agents": ["security"]}
        )
    )

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-01-01-a"


def test_find_latest_baseline_for_agent_lexicographic_tiebreak(tmp_path: Path) -> None:
    # Two baselines with same prefix — lexicographic order is deterministic.
    _write_baseline(
        tmp_path, "audit-2026-01-01-aaa", "framework", "sha-aaa", ["security"]
    )
    _write_baseline(
        tmp_path, "audit-2026-01-01-bbb", "framework", "sha-bbb", ["security"]
    )

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-01-01-bbb"
