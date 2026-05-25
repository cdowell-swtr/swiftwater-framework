_ANSWERS = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
    "batteries": ["webhooks"],
}


def test_owned_files_for_webhooks():
    from framework_cli.downskill import owned_files

    owned = owned_files(_ANSWERS, "webhooks")
    assert "src/demo/routes/webhooks.py" in owned
    assert "src/demo/webhooks/signature.py" in owned
    assert "tests/functional/test_webhooks.py" in owned
    assert (
        "migrations/versions/0002_webhook_events.py" in owned
    )  # owned, preserved at delete time
    # shared files the battery only *edited* (not created) are NOT owned:
    assert ".env.example" not in owned
    assert "src/demo/config/settings.py" not in owned


def test_owned_files_empty_for_absent_battery():
    from framework_cli.downskill import owned_files

    assert owned_files({**_ANSWERS, "batteries": []}, "webhooks") == set()


def test_blocking_dependents_flags_a_requirer():
    from framework_cli import batteries as bat
    from framework_cli.downskill import blocking_dependents

    bat._BATTERIES["_pgvector"] = bat.BatterySpec(
        "_pgvector", "x", requires=("_postgres",)
    )
    bat._BATTERIES["_postgres"] = bat.BatterySpec("_postgres", "x")
    try:
        assert blocking_dependents(["_pgvector", "_postgres"], "_postgres") == [
            "_pgvector"
        ]
        assert blocking_dependents(["_postgres"], "_postgres") == []
    finally:
        del bat._BATTERIES["_pgvector"], bat._BATTERIES["_postgres"]


def test_usage_references_finds_builder_import(tmp_path):
    from framework_cli.downskill import usage_references

    (tmp_path / "src" / "demo").mkdir(parents=True)
    (tmp_path / "src" / "demo" / "app.py").write_text(
        "from demo.webhooks.handler import handle_event\n"
    )
    (tmp_path / "src" / "demo" / "clean.py").write_text("x = 1\n")
    refs = usage_references(
        tmp_path,
        "webhooks",
        package_name="demo",
        owned={"src/demo/webhooks/handler.py"},
    )
    assert any("app.py" in r for r in refs)
    assert not any("clean.py" in r for r in refs)


def test_usage_references_ignores_owned_files(tmp_path):
    from framework_cli.downskill import usage_references

    (tmp_path / "src" / "demo" / "webhooks").mkdir(parents=True)
    (tmp_path / "src" / "demo" / "webhooks" / "handler.py").write_text(
        "import demo.webhooks\n"
    )
    refs = usage_references(
        tmp_path,
        "webhooks",
        package_name="demo",
        owned={"src/demo/webhooks/handler.py"},
    )
    assert refs == []


def test_usage_references_excludes_framework_gated_files(tmp_path):
    """A non-owned file whose battery reference is unmodified framework-gated content
    (byte-identical to the with-battery render) is excluded; a builder-modified file is not."""
    from framework_cli.downskill import usage_references

    project = tmp_path / "proj"
    with_root = tmp_path / "with"
    (project / "src" / "demo").mkdir(parents=True)
    (with_root / "src" / "demo").mkdir(parents=True)

    # Framework-gated: identical bytes in the project and the with-battery render → excluded.
    gated = "from demo.webhooks.metrics import webhook_metrics\n"
    (project / "src" / "demo" / "health.py").write_text(gated)
    (with_root / "src" / "demo" / "health.py").write_text(gated)

    # Builder-modified: references the battery but differs from the render → flagged.
    (project / "src" / "demo" / "mine.py").write_text(
        "import demo.webhooks  # my code\n"
    )
    (with_root / "src" / "demo" / "mine.py").write_text("import demo.webhooks\n")

    refs = usage_references(
        project,
        "webhooks",
        package_name="demo",
        owned=set(),
        with_render_root=with_root,
    )
    assert not any("health.py" in r for r in refs)
    assert any("mine.py" in r for r in refs)


def test_remove_battery_webhooks_end_to_end(tmp_path, monkeypatch):
    import subprocess

    from typer.testing import CliRunner

    from framework_cli.cli import app
    from framework_cli.downskill import remove_battery
    from framework_cli.source import read_batteries

    monkeypatch.chdir(tmp_path)
    assert (
        CliRunner().invoke(app, ["new", "My App", "--with", "webhooks"]).exit_code == 0
    )
    project = tmp_path / "my-app"
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(project),
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.email=b@b",
            "-c",
            "user.name=b",
            "commit",
            "-qm",
            "scaffold",
        ],
        check=True,
    )

    report = remove_battery(project, "webhooks", force=False)

    assert not (project / "src" / "my_app" / "routes" / "webhooks.py").exists()
    assert not (project / "src" / "my_app" / "webhooks").exists()
    assert not (project / "tests" / "functional" / "test_webhooks.py").exists()
    assert (
        project / "migrations" / "versions" / "0002_webhook_events.py"
    ).is_file()  # preserved
    assert any("0002_webhook_events" in p for p in report.preserved)
    assert "WEBHOOK_SIGNING_SECRET" not in (project / ".env.example").read_text()
    assert (
        "webhook_signing_secret"
        not in (project / "src" / "my_app" / "config" / "settings.py").read_text()
    )
    # the migrations/env.py battery import must be stripped (else alembic breaks)
    assert "webhooks" not in (project / "migrations" / "env.py").read_text()
    assert (
        ".copier-answers.yml" not in report.warnings
    )  # step 3 owns it; not a builder-modified warning
    assert read_batteries(project) == []
    monkeypatch.chdir(project)
    assert CliRunner().invoke(app, ["integrity", "--ci"]).exit_code == 0


def test_remove_battery_usage_refusal(tmp_path, monkeypatch):
    import subprocess

    import pytest
    from typer.testing import CliRunner

    from framework_cli.cli import app
    from framework_cli.downskill import DownskillError, remove_battery

    monkeypatch.chdir(tmp_path)
    assert (
        CliRunner().invoke(app, ["new", "My App", "--with", "webhooks"]).exit_code == 0
    )
    project = tmp_path / "my-app"
    (project / "src" / "my_app" / "uses_it.py").write_text(
        "from my_app.webhooks.handler import handle_event\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(project),
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.email=b@b",
            "-c",
            "user.name=b",
            "commit",
            "-qm",
            "s",
        ],
        check=True,
    )
    with pytest.raises(DownskillError, match="in use"):
        remove_battery(project, "webhooks", force=False)
    remove_battery(project, "webhooks", force=True)  # --force proceeds
    assert not (project / "src" / "my_app" / "routes" / "webhooks.py").exists()


def test_downskill_project_runs_remove_then_task_test(tmp_path, monkeypatch):
    import framework_cli.downskill as ds

    calls = {}
    monkeypatch.setattr(ds, "_is_git_tracked", lambda p: True)
    monkeypatch.setattr(
        ds,
        "remove_battery",
        lambda project, battery, *, force=False: (
            calls.setdefault("removed", (battery, force)) or ds.RemovalReport()
        ),
    )
    monkeypatch.setattr(
        ds.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})()
    )

    ok = ds.downskill_project(tmp_path, "webhooks", force=True)
    assert ok is True and calls["removed"] == ("webhooks", True)
