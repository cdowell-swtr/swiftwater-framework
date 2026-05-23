import subprocess
from pathlib import Path

from framework_cli.review.diff import pr_diff


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
