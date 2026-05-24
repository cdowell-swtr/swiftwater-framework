import subprocess
from pathlib import Path

import pytest

from framework_cli.upskill import UpskillError, upskill_project


def _git(repo: Path, *a):
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)


def _source_repo(tmp_path: Path) -> Path:
    """A minimal git template repo: root copier.yml (_subdirectory) + a tiny template, tag v1."""
    repo = tmp_path / "src"
    sub = repo / "tmpl"
    sub.mkdir(parents=True)
    (repo / "copier.yml").write_text('_subdirectory: tmpl\n_exclude: ["copier.yml"]\n')
    (sub / "copier.yml").write_text("_templates_suffix: .jinja\nname:\n  type: str\n  default: world\n")
    (sub / "framework_line.txt").write_text("framework v1\n")
    (sub / "app.txt.jinja").write_text("app for {{ name }}\n")
    (sub / "{{ _copier_conf.answers_file }}.jinja").write_text("{{ _copier_answers|to_nice_yaml }}")
    (sub / "Taskfile.yml").write_text("version: '3'\ntasks:\n  test:\n    cmds:\n      - 'true'\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "s@x")
    _git(repo, "config", "user.name", "s")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "v1")
    _git(repo, "tag", "v1")
    return repo


def _project_at_v1(tmp_path: Path, source: Path) -> Path:
    from copier import run_copy

    proj = tmp_path / "proj"
    run_copy(str(source), str(proj), data={"name": "demo"}, defaults=True, overwrite=True, quiet=True, vcs_ref="v1")
    ans = proj / ".copier-answers.yml"
    kept = [ln for ln in ans.read_text().splitlines() if not ln.startswith(("_src_path:", "_commit:"))]
    kept += [f"_src_path: {source}", "_commit: v1"]
    ans.write_text("\n".join(kept) + "\n")
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "b@x")
    _git(proj, "config", "user.name", "b")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "scaffold")
    return proj


def test_upskill_applies_framework_change_and_stays_green(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project_at_v1(tmp_path, source)

    (proj / "app.txt").write_text("app for demo\nMY BUILDER LINE\n")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "edit")

    sub = source / "tmpl"
    (sub / "framework_line.txt").write_text("framework v2 CHANGED\n")
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", "v2")
    _git(source, "tag", "v2")

    green = upskill_project(proj)

    assert green is True
    assert (proj / "framework_line.txt").read_text() == "framework v2 CHANGED\n"
    assert "MY BUILDER LINE" in (proj / "app.txt").read_text()
    assert "_commit: v2" in (proj / ".copier-answers.yml").read_text()


def test_upskill_reports_not_green_when_tests_fail(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project_at_v1(tmp_path, source)
    sub = source / "tmpl"
    (sub / "Taskfile.yml").write_text("version: '3'\ntasks:\n  test:\n    cmds:\n      - 'false'\n")
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", "v2")
    _git(source, "tag", "v2")

    assert upskill_project(proj) is False


def test_upskill_requires_git_tracked_project(tmp_path: Path):
    source = _source_repo(tmp_path)
    from copier import run_copy

    proj = tmp_path / "bare"
    run_copy(str(source), str(proj), data={"name": "demo"}, defaults=True, overwrite=True, quiet=True, vcs_ref="v1")
    with pytest.raises(UpskillError, match="git"):
        upskill_project(proj)


def _battery_source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "bsrc"
    sub = repo / "tmpl"
    sub.mkdir(parents=True)
    (repo / "copier.yml").write_text('_subdirectory: tmpl\n_exclude: ["copier.yml"]\n')
    (sub / "copier.yml").write_text(
        "_templates_suffix: .jinja\n"
        "name:\n  type: str\n  default: world\n"
        "batteries:\n  type: yaml\n  default: []\n"
    )
    (sub / "app.txt.jinja").write_text("app for {{ name }}\n")
    (sub / "{{ _copier_conf.answers_file }}.jinja").write_text("{{ _copier_answers|to_nice_yaml }}")
    (sub / "Taskfile.yml").write_text("version: '3'\ntasks:\n  test:\n    cmds:\n      - 'true'\n")
    (sub / "{{ 'ws.txt' if 'websockets' in batteries else '' }}.jinja").write_text("ws\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "s@x")
    _git(repo, "config", "user.name", "s")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "v1")
    _git(repo, "tag", "v1")
    return repo


def _battery_project(tmp_path: Path, source: Path, batteries: list[str]) -> Path:
    from copier import run_copy

    from framework_cli.source import record_batteries

    proj = tmp_path / "bproj"
    run_copy(
        str(source), str(proj), data={"name": "demo", "batteries": batteries},
        defaults=True, overwrite=True, quiet=True, vcs_ref="v1",
    )
    ans = proj / ".copier-answers.yml"
    kept = [ln for ln in ans.read_text().splitlines() if not ln.startswith(("_src_path:", "_commit:"))]
    kept += [f"_src_path: {source}", "_commit: v1"]
    ans.write_text("\n".join(kept) + "\n")
    # The git+_subdirectory source doesn't include yaml-typed answers in _copier_answers;
    # record_batteries writes the initial battery set (mirrors what the real framework new does
    # via the local template, which does include batteries in _copier_answers).
    record_batteries(proj, batteries)
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "b@x")
    _git(proj, "config", "user.name", "b")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "scaffold")
    return proj


def _bump_source_to_v2(source: Path) -> None:
    (source / "tmpl" / "app.txt.jinja").write_text("app for {{ name }} v2\n")
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", "v2")
    _git(source, "tag", "v2")


def test_upskill_preserves_recorded_batteries(tmp_path: Path):
    from framework_cli.source import read_batteries

    source = _battery_source_repo(tmp_path)
    proj = _battery_project(tmp_path, source, ["websockets"])
    assert (proj / "ws.txt").is_file()
    assert read_batteries(proj) == ["websockets"]

    _bump_source_to_v2(source)
    assert upskill_project(proj) is True  # plain upskill, no --with

    assert (proj / "ws.txt").is_file(), "battery file dropped by a plain upskill"
    assert read_batteries(proj) == ["websockets"], "recorded battery set lost after upskill"


def test_upskill_with_adds_battery_and_records_it(tmp_path: Path):
    from framework_cli.source import read_batteries

    source = _battery_source_repo(tmp_path)
    proj = _battery_project(tmp_path, source, [])
    assert not (proj / "ws.txt").exists()

    _bump_source_to_v2(source)
    assert upskill_project(proj, with_batteries=["websockets"]) is True

    assert (proj / "ws.txt").is_file(), "battery file not added by upskill --with"
    assert read_batteries(proj) == ["websockets"]
