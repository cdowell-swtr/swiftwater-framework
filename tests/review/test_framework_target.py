import subprocess

from framework_cli.review.diff import framework_diff


def _git(args, cwd):
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def test_framework_diff_excludes_template_payload(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "src" / "framework_cli" / "template" / "src").mkdir(parents=True)
    (repo / "src" / "framework_cli").joinpath("cli.py").write_text("X = 1\n")
    (repo / "src" / "framework_cli" / "template" / "payload.py").write_text("A = 1\n")
    _git(["init", "-q"], repo)
    _git(["add", "-A"], repo)
    _git(["commit", "-qm", "base"], repo)
    (repo / "src" / "framework_cli" / "cli.py").write_text("X = 2\n")
    (repo / "src" / "framework_cli" / "template" / "payload.py").write_text("A = 2\n")
    _git(["commit", "-aqm", "change"], repo)

    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)  # → HEAD~1...HEAD range
    monkeypatch.chdir(repo)
    diff = framework_diff()
    assert "src/framework_cli/cli.py" in diff  # CLI change reviewed
    assert "template/payload.py" not in diff  # template payload excluded
