import subprocess
from pathlib import Path

from framework_cli.source import (
    REPO_GH,
    read_alert_channels,
    record_alert_channels,
    record_portable_source,
    version_tag,
)


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


def test_read_batteries_missing_answers_file_returns_empty(tmp_path):
    from framework_cli.source import read_batteries

    assert read_batteries(tmp_path) == []  # no .copier-answers.yml present


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


def _answers(tmp_path: Path, body: str) -> Path:
    p = tmp_path / ".copier-answers.yml"
    p.write_text(body)
    return tmp_path


def test_read_alert_channels_defaults_to_webhook_when_absent(tmp_path: Path):
    _answers(tmp_path, "_commit: v0.1.0\n")
    assert read_alert_channels(tmp_path) == ["webhook"]


def test_read_alert_channels_reads_recorded_list(tmp_path: Path):
    _answers(tmp_path, "alert_channels:\n- slack\n- email\n")
    assert read_alert_channels(tmp_path) == ["slack", "email"]


def test_record_alert_channels_replaces_existing_block(tmp_path: Path):
    project = _answers(tmp_path, "alert_channels:\n- webhook\nproject_name: Demo\n")
    record_alert_channels(project, ["slack", "pagerduty"])
    text = (project / ".copier-answers.yml").read_text()
    assert "project_name: Demo" in text
    assert "alert_channels:\n- slack\n- pagerduty\n" in text
    assert "- webhook" not in text


def test_record_alert_channels_empty_writes_default(tmp_path: Path):
    project = _answers(tmp_path, "alert_channels:\n- slack\n")
    record_alert_channels(project, [])
    assert (
        "alert_channels:\n- webhook\n" in (project / ".copier-answers.yml").read_text()
    )
