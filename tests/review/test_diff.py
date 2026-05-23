import subprocess
from pathlib import Path

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
