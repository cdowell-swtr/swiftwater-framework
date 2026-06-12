import subprocess
from pathlib import Path

import pytest

from framework_cli.upgrade import UpgradeError, upgrade_project


def _git(repo: Path, *a):
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)


def _source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "isrc"
    sub = repo / "tmpl"
    pkg = sub / "src" / "{{ package_name }}"
    pkg.mkdir(parents=True)
    (repo / "copier.yml").write_text('_subdirectory: tmpl\n_exclude: ["copier.yml"]\n')
    (sub / "copier.yml").write_text(
        "_templates_suffix: .jinja\n"
        "project_name:\n  type: str\n"
        'project_slug:\n  type: str\n  default: "{{ project_name|lower }}"\n'
        'package_name:\n  type: str\n  default: "{{ project_slug }}"\n'
        'python_version:\n  type: str\n  default: "3.12"\n'
        "batteries:\n  type: yaml\n  default: []\n"
        'alert_channels:\n  type: yaml\n  default: ["webhook"]\n'
    )
    (pkg / "__init__.py.jinja").write_text("# {{ package_name }}\n")
    (sub / "framework_line.txt").write_text("framework v1\n")
    (sub / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml }}"
    )
    (sub / "Taskfile.yml").write_text(
        "version: '3'\ntasks:\n  test:\n    cmds:\n      - 'true'\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "s@x")
    _git(repo, "config", "user.name", "s")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "v1")
    _git(repo, "tag", "v1")
    return repo


def _project(tmp_path: Path, source: Path) -> Path:
    from copier import run_copy

    from framework_cli.source import record_identity

    proj = tmp_path / "iproj"
    run_copy(
        str(source),
        str(proj),
        data={
            "project_name": "demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref="v1",
    )
    ans = proj / ".copier-answers.yml"
    kept = [
        ln
        for ln in ans.read_text().splitlines()
        if not ln.startswith(("_src_path:", "_commit:"))
    ]
    kept += [f"_src_path: {source}", "_commit: v1"]
    ans.write_text("\n".join(kept) + "\n")
    record_identity(
        proj,
        {
            "project_name": "demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "b@x")
    _git(proj, "config", "user.name", "b")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "scaffold")
    return proj


def _bump(source: Path, tag: str, *, green: bool = True) -> None:
    (source / "tmpl" / "framework_line.txt").write_text(f"framework {tag}\n")
    if not green:
        (source / "tmpl" / "Taskfile.yml").write_text(
            "version: '3'\ntasks:\n  test:\n    cmds:\n      - 'false'\n"
        )
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", tag)
    _git(source, "tag", tag)


def test_upgrade_refuses_dirty_tree(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    _bump(source, "v2")
    (proj / "dirty.txt").write_text("uncommitted\n")  # dirty working tree
    with pytest.raises(UpgradeError, match="clean"):
        upgrade_project(proj, to="v2")
    assert (proj / "framework_line.txt").read_text() == "framework v1\n"  # untouched


def test_upgrade_no_op_when_already_at_target(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    outcome = upgrade_project(proj, to="v1")
    assert outcome.status == "already-current"
    assert outcome.target == "v1"


def test_upgrade_applies_target_and_reports_green(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    _bump(source, "v2")
    outcome = upgrade_project(proj, to="v2")
    assert outcome.status == "green"
    assert outcome.target == "v2"
    assert (proj / "framework_line.txt").read_text() == "framework v2\n"
    assert "_commit: v2" in (proj / ".copier-answers.yml").read_text()
    assert (proj / "src" / "demo" / "__init__.py").is_file()  # identity preserved


def test_upgrade_reports_red_when_tests_fail(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    _bump(source, "v2", green=False)
    outcome = upgrade_project(proj, to="v2")
    assert outcome.status == "red"
    assert outcome.target == "v2"


def test_upgrade_requires_git_tracked(tmp_path: Path):
    from copier import run_copy

    source = _source_repo(tmp_path)
    proj = tmp_path / "bare"
    run_copy(
        str(source),
        str(proj),
        data={"project_name": "demo"},
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref="v1",
    )
    with pytest.raises(UpgradeError, match="git"):
        upgrade_project(proj, to="v1")
