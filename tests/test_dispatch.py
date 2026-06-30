import pytest

import framework_cli.dispatch as disp
from framework_cli.dispatch import Dispatch, classify, decide_dispatch


@pytest.mark.parametrize(
    "command,kind",
    [
        ("new", "advancing"),
        ("upgrade", "advancing"),
        ("integrity", "cwd_project"),
        ("restore", "cwd_project"),
        ("upskill", "arg_project"),
        ("downskill", "arg_project"),
        ("check", "self"),
        ("eval", "self"),
        ("review-aggregate", "self"),
        (None, "self"),
        ("totally-unknown", "self"),
    ],
)
def test_classify(command, kind):
    assert classify(command) == kind


def D(**kw):
    base = dict(
        kind="cwd_project",
        installed_tag="v0.4.5",
        target_tag=None,
        project_commit=None,
        reexecuted=False,
    )
    base.update(kw)
    return decide_dispatch(**base)


def test_loop_guard_forces_self():
    assert D(reexecuted=True, project_commit="v0.4.2") == Dispatch("self")


def test_self_kind_runs_self():
    assert D(kind="self", project_commit="v0.4.2") == Dispatch("self")


def test_project_in_sync_runs_self():
    assert D(project_commit="v0.4.5") == Dispatch("self")


def test_project_behind_reexecs_pin():
    assert D(project_commit="v0.4.2") == Dispatch("reexec", "v0.4.2")


def test_no_project_runs_self():
    assert D(project_commit=None) == Dispatch("self")


def test_advancing_to_newer_reexecs_target():
    assert D(kind="advancing", target_tag="v0.5.0") == Dispatch("reexec", "v0.5.0")


def test_advancing_to_installed_runs_self():
    assert D(kind="advancing", target_tag="v0.4.5") == Dispatch("self")


def test_sha_pin_differs_reexecs():
    assert D(project_commit="abc1234") == Dispatch("reexec", "abc1234")


def test_dispatch_reexecs_pin_for_cwd_project(monkeypatch, tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.4.2\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(disp, "installed_version_tag", lambda: "v0.4.5")
    monkeypatch.setattr(disp, "_uvx_available", lambda: True)
    captured = {}
    monkeypatch.setattr(
        disp, "reexec", lambda ref, argv: captured.update(ref=ref, argv=argv)
    )
    disp.dispatch(["integrity", "--ci"])
    assert captured == {"ref": "v0.4.2", "argv": ["integrity", "--ci"]}


def test_dispatch_self_when_in_sync(monkeypatch, tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.4.5\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(disp, "installed_version_tag", lambda: "v0.4.5")
    called = {"reexec": False}
    monkeypatch.setattr(disp, "reexec", lambda *a: called.update(reexec=True))
    disp.dispatch(["integrity"])
    assert called["reexec"] is False


def test_dispatch_noop_when_reexecuted(monkeypatch):
    monkeypatch.setenv("FRAMEWORK_PINNED_EXEC", "1")
    monkeypatch.setattr(disp, "reexec", lambda *a: pytest.fail("must not re-exec"))
    disp.dispatch(["integrity"])  # returns cleanly


def test_dispatch_fail_loud_when_uvx_missing(monkeypatch, tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.4.2\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(disp, "installed_version_tag", lambda: "v0.4.5")
    monkeypatch.setattr(disp, "_uvx_available", lambda: False)
    with pytest.raises(SystemExit) as exc:
        disp.dispatch(["integrity"])
    assert exc.value.code != 0


def test_dispatch_advancing_reexecs_latest(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no project
    monkeypatch.setattr(disp, "installed_version_tag", lambda: "v0.4.5")
    monkeypatch.setattr(disp, "latest_release", lambda: "v0.5.0")
    monkeypatch.setattr(disp, "_uvx_available", lambda: True)
    captured = {}
    monkeypatch.setattr(disp, "reexec", lambda ref, argv: captured.update(ref=ref))
    disp.dispatch(["upgrade", "someproj"])
    assert captured["ref"] == "v0.5.0"


@pytest.mark.parametrize("to_args", [["--to", "v0.4.9"], ["--to=v0.4.9"]])
def test_dispatch_advancing_honors_explicit_to(monkeypatch, tmp_path, to_args):
    # `--to <tag>` and the joined `--to=<tag>` form must both target that tag,
    # not silently fall back to latest_release().
    monkeypatch.chdir(tmp_path)  # no project
    monkeypatch.setattr(disp, "installed_version_tag", lambda: "v0.4.5")
    monkeypatch.setattr(disp, "latest_release", lambda: "v0.5.0")
    monkeypatch.setattr(disp, "_uvx_available", lambda: True)
    captured = {}
    monkeypatch.setattr(disp, "reexec", lambda ref, argv: captured.update(ref=ref))
    disp.dispatch(["upgrade", "someproj", *to_args])
    assert captured["ref"] == "v0.4.9"
