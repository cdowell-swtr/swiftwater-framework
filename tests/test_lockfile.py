import subprocess
from pathlib import Path

from framework_cli.lockfile import write_lockfile


def test_write_lockfile_success(tmp_path, monkeypatch):
    calls = {}

    def fake_run(args, cwd=None, capture_output=False, text=False):
        calls["args"] = args
        calls["cwd"] = cwd
        (Path(cwd) / "uv.lock").write_text("# lock\n")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("framework_cli.lockfile.shutil.which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr("framework_cli.lockfile.subprocess.run", fake_run)

    assert write_lockfile(tmp_path) is True
    assert calls["args"] == ["uv", "lock"]
    assert Path(calls["cwd"]) == tmp_path
    assert (tmp_path / "uv.lock").exists()


def test_write_lockfile_uv_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("framework_cli.lockfile.shutil.which", lambda _: None)
    assert write_lockfile(tmp_path) is False
    assert "uv.lock" in capsys.readouterr().err


def test_write_lockfile_lock_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("framework_cli.lockfile.shutil.which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr(
        "framework_cli.lockfile.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(["uv", "lock"], 1, "", "boom"),
    )
    assert write_lockfile(tmp_path) is False  # never raises
    err = capsys.readouterr().err
    assert "uv.lock" in err
    assert "boom" in err  # uv's own stderr is forwarded to the builder


def test_write_lockfile_uv_vanished_does_not_raise(tmp_path, monkeypatch, capsys):
    # which() finds uv, but subprocess.run raises OSError (uv removed/not executable since).
    monkeypatch.setattr("framework_cli.lockfile.shutil.which", lambda _: "/usr/bin/uv")

    def boom(*a, **k):
        raise FileNotFoundError("uv")

    monkeypatch.setattr("framework_cli.lockfile.subprocess.run", boom)
    assert write_lockfile(tmp_path) is False  # OSError swallowed → never raises
    assert "uv.lock" in capsys.readouterr().err
