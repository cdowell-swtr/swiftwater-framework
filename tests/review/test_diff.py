import subprocess
from pathlib import Path

import pytest

from framework_cli.review.diff import changed_files, matches_globs, pr_diff

_DIFF = (
    "diff --git a/pyproject.toml b/pyproject.toml\n"
    "--- a/pyproject.toml\n+++ b/pyproject.toml\n@@ -1 +1 @@\n-x\n+y\n"
    "diff --git a/src/app/main.py b/src/app/main.py\n"
    "--- a/src/app/main.py\n+++ b/src/app/main.py\n@@ -1 +1 @@\n-a\n+b\n"
)


def test_changed_files_extracts_new_paths():
    assert changed_files(_DIFF) == ["pyproject.toml", "src/app/main.py"]


def test_changed_files_skips_deletions():
    deletion = "--- a/gone.txt\n+++ /dev/null\n"
    assert changed_files(deletion) == []


def test_matches_globs_basename_and_path():
    assert matches_globs(["frontend/package.json"], ("package.json",)) is True
    assert matches_globs(["pyproject.toml"], ("uv.lock", "pyproject.toml")) is True
    assert matches_globs(["src/app/main.py"], ("pyproject.toml", "uv.lock")) is False


def _git(repo: Path, *a):
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)


def test_pr_diff_returns_last_commit_changes_without_base(tmp_path: Path, monkeypatch):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@x")
    _git(repo, "config", "user.name", "t")
    (repo / "f.py").write_text("a = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "one")
    (repo / "f.py").write_text("a = 1\nb = 2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "two")

    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.chdir(repo)
    diff = pr_diff()
    assert "b = 2" in diff and "f.py" in diff


def test_snapshot_seed_returns_empty_string(tmp_path: Path) -> None:
    """snapshot_seed is intentionally empty for bundle agents — the bundled
    context block carries the source files, no diff seed needed."""
    from framework_cli.review.diff import snapshot_seed

    assert snapshot_seed("framework", tmp_path) == ""


def test_snapshot_seed_returns_empty_for_any_target(tmp_path: Path) -> None:
    """Behavior is the same for project target — empty seed; bundled context
    does the work."""
    from framework_cli.review.diff import snapshot_seed

    assert snapshot_seed("project", tmp_path) == ""


def test_delta_diff_returns_diff_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """delta_diff calls `git diff <base_sha>...HEAD` and returns its stdout."""
    import subprocess

    from framework_cli.review.diff import delta_diff

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        result = subprocess.CompletedProcess(args=args, returncode=0)
        result.stdout = "diff --git a/foo b/foo\n+++ added line\n"
        result.stderr = ""
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = delta_diff("abc1234")
    assert "diff --git" in out
    assert captured["args"] == ["git", "diff", "abc1234...HEAD"]


def test_delta_diff_raises_when_ref_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """delta_diff raises a ValueError with a clear message when git diff fails
    (e.g., bad ref). Callers translate that into a CLI exit."""
    import subprocess

    from framework_cli.review.diff import delta_diff

    def fake_run(args, **kwargs):
        result = subprocess.CompletedProcess(args=args, returncode=128)
        result.stdout = ""
        result.stderr = "fatal: bad revision 'nope...HEAD'\n"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ValueError) as exc:
        delta_diff("nope")
    assert "nope" in str(exc.value)
    assert (
        "bad revision" in str(exc.value).lower()
        or "is that ref reachable" in str(exc.value).lower()
    )
