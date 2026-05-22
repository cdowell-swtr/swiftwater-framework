import subprocess
from pathlib import Path

from framework_cli.source import REPO_GH, record_portable_source, version_tag


def _tagged_repo(tmp_path: Path, tags: list[str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(*a):
        subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)

    g("init", "-q")
    g("config", "user.email", "t@x")
    g("config", "user.name", "t")
    (repo / "f").write_text("x")
    g("add", "-A")
    g("commit", "-qm", "c")
    for t in tags:
        g("tag", t)
    return repo


def test_latest_release_picks_highest_semver(tmp_path: Path):
    from framework_cli.source import latest_release

    repo = _tagged_repo(tmp_path, ["v0.1.0", "v0.2.0", "v0.10.0", "v0.2.1"])
    assert latest_release(str(repo)) == "v0.10.0"


def test_latest_release_none_when_no_tags(tmp_path: Path):
    from framework_cli.source import latest_release

    repo = _tagged_repo(tmp_path, [])
    assert latest_release(str(repo)) is None


def test_version_tag():
    assert version_tag("0.3.0") == "v0.3.0"


def test_record_portable_source_rewrites_answers(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    answers = project / ".copier-answers.yml"
    answers.write_text(
        "# managed\n_src_path: /abs/local/path\nproject_name: Demo\npackage_name: demo\n"
    )
    record_portable_source(project, "0.3.0")
    text = answers.read_text()
    assert f"_src_path: {REPO_GH}" in text
    assert "_commit: v0.3.0" in text
    assert "/abs/local/path" not in text
    assert "project_name: Demo" in text and "package_name: demo" in text
