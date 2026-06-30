import pytest

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
