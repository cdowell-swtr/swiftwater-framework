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
    (sub / "copier.yml").write_text(
        "_templates_suffix: .jinja\nname:\n  type: str\n  default: world\n"
    )
    (sub / "framework_line.txt").write_text("framework v1\n")
    (sub / "app.txt.jinja").write_text("app for {{ name }}\n")
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


def _project_at_v1(tmp_path: Path, source: Path) -> Path:
    from copier import run_copy

    proj = tmp_path / "proj"
    run_copy(
        str(source),
        str(proj),
        data={"name": "demo"},
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
    (sub / "Taskfile.yml").write_text(
        "version: '3'\ntasks:\n  test:\n    cmds:\n      - 'false'\n"
    )
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", "v2")
    _git(source, "tag", "v2")

    assert upskill_project(proj) is False


def test_upskill_requires_git_tracked_project(tmp_path: Path):
    source = _source_repo(tmp_path)
    from copier import run_copy

    proj = tmp_path / "bare"
    run_copy(
        str(source),
        str(proj),
        data={"name": "demo"},
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref="v1",
    )
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
    (sub / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml }}"
    )
    (sub / "Taskfile.yml").write_text(
        "version: '3'\ntasks:\n  test:\n    cmds:\n      - 'true'\n"
    )
    (sub / "{{ 'ws.txt' if 'websockets' in batteries else '' }}.jinja").write_text(
        "ws\n"
    )
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
        str(source),
        str(proj),
        data={"name": "demo", "batteries": batteries},
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
    assert read_batteries(proj) == ["websockets"], (
        "recorded battery set lost after upskill"
    )


def test_upskill_with_adds_battery_and_records_it(tmp_path: Path):
    from framework_cli.source import read_batteries

    source = _battery_source_repo(tmp_path)
    proj = _battery_project(tmp_path, source, [])
    assert not (proj / "ws.txt").exists()

    _bump_source_to_v2(source)
    assert upskill_project(proj, with_batteries=["websockets"]) is True

    assert (proj / "ws.txt").is_file(), "battery file not added by upskill --with"
    assert read_batteries(proj) == ["websockets"]


def test_upskill_regenerates_the_manifest(tmp_path, monkeypatch):
    import framework_cli.upskill as up

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".copier-answers.yml").write_text(
        "project_name: demo\nproject_slug: demo\npackage_name: demo\npython_version: '3.12'\nbatteries: []\n"
    )
    (proj / ".framework").mkdir()
    (proj / ".framework" / "integrity.lock").write_text("{}")

    monkeypatch.setattr(up, "_is_git_tracked", lambda p: True)
    monkeypatch.setattr(up, "run_update", lambda *a, **k: None)
    monkeypatch.setattr(
        up.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})()
    )
    captured = {}
    monkeypatch.setattr(
        up, "write_manifest", lambda project, version: captured.update(project=project)
    )

    assert up.upskill_project(proj) is True
    assert captured["project"] == proj  # manifest regenerated after the update


def test_upskill_records_alert_channels(monkeypatch, tmp_path: Path):
    import framework_cli.upskill as up

    project = tmp_path / "demo"
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        "_src_path: gh:x\n_commit: v0.1.0\nbatteries: []\nalert_channels:\n- webhook\n"
    )
    calls = {}

    monkeypatch.setattr(up, "_is_git_tracked", lambda p: True)
    monkeypatch.setattr(
        up, "run_update", lambda *a, **k: calls.update(data=k.get("data"))
    )
    monkeypatch.setattr(
        up.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})()
    )

    up.upskill_project(project, alert_channels=["slack", "email"])

    assert calls["data"]["alert_channels"] == ["slack", "email"]
    answers = (project / ".copier-answers.yml").read_text()
    assert "alert_channels:\n- slack\n- email\n" in answers


def _identity_source_repo(tmp_path: Path) -> Path:
    """Minimal git template with the four identity answers + a src/<package>/ path, tag v1."""
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


def _identity_project(tmp_path: Path, source: Path) -> Path:
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
    # The git+_subdirectory source omits answers from _copier_answers; record identity as the
    # real `framework new` does via the local template (which includes them).
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


def _bump_identity_source(source: Path, tag: str) -> None:
    (source / "tmpl" / "framework_line.txt").write_text(f"framework {tag}\n")
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", tag)
    _git(source, "tag", tag)


def test_identity_survives_two_sequential_updates(tmp_path: Path):
    """The headline invariant: identity + src/<package>/ survive a multi-hop update."""
    from framework_cli.source import read_identity

    source = _identity_source_repo(tmp_path)
    proj = _identity_project(tmp_path, source)
    from framework_cli.upskill import _apply_update

    _bump_identity_source(source, "v2")
    _apply_update(proj, vcs_ref="v2", batteries=[], channels=["webhook"])
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "to v2")

    _bump_identity_source(source, "v3")
    _apply_update(proj, vcs_ref="v3", batteries=[], channels=["webhook"])

    assert read_identity(proj) == {
        "project_name": "demo",
        "project_slug": "demo",
        "package_name": "demo",
        "python_version": "3.12",
    }
    assert (proj / "src" / "demo" / "__init__.py").is_file(), (
        "package dir lost — identity stripped across the second update"
    )


def test_apply_update_refuses_when_identity_missing(tmp_path: Path):
    from framework_cli.upskill import UpskillError, _apply_update

    source = _identity_source_repo(tmp_path)
    proj = _identity_project(tmp_path, source)
    # Strip some identity keys from the recorded answers, leaving others — simulates a
    # partial-strip scenario where the answers file is corrupt (not all four present).
    # The guard fires when ANY identity key is present but the full set is incomplete.
    ans = proj / ".copier-answers.yml"
    ans.write_text(
        "\n".join(
            ln
            for ln in ans.read_text().splitlines()
            if not ln.startswith(("package_name:", "python_version:"))
        )
        + "\n"
    )
    with pytest.raises(UpskillError, match="identity"):
        _apply_update(proj, vcs_ref="v1", batteries=[], channels=["webhook"])
