from pathlib import Path

from framework_cli.source import REPO_GH, record_portable_source, version_tag


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
