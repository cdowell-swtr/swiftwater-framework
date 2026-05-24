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
    assert "migrations/versions/0002_webhook_events.py" in owned  # owned, preserved at delete time
    # shared files the battery only *edited* (not created) are NOT owned:
    assert ".env.example" not in owned
    assert "src/demo/config/settings.py" not in owned


def test_owned_files_empty_for_absent_battery():
    from framework_cli.downskill import owned_files

    assert owned_files({**_ANSWERS, "batteries": []}, "webhooks") == set()


def test_blocking_dependents_flags_a_requirer():
    from framework_cli import batteries as bat
    from framework_cli.downskill import blocking_dependents

    bat._BATTERIES["_pgvector"] = bat.BatterySpec("_pgvector", "x", requires=("_postgres",))
    bat._BATTERIES["_postgres"] = bat.BatterySpec("_postgres", "x")
    try:
        assert blocking_dependents(["_pgvector", "_postgres"], "_postgres") == ["_pgvector"]
        assert blocking_dependents(["_postgres"], "_postgres") == []
    finally:
        del bat._BATTERIES["_pgvector"], bat._BATTERIES["_postgres"]


def test_usage_references_finds_builder_import(tmp_path):
    from framework_cli.downskill import usage_references

    (tmp_path / "src" / "demo").mkdir(parents=True)
    (tmp_path / "src" / "demo" / "app.py").write_text("from demo.webhooks.handler import handle_event\n")
    (tmp_path / "src" / "demo" / "clean.py").write_text("x = 1\n")
    refs = usage_references(tmp_path, "webhooks", package_name="demo", owned={"src/demo/webhooks/handler.py"})
    assert any("app.py" in r for r in refs)
    assert not any("clean.py" in r for r in refs)


def test_usage_references_ignores_owned_files(tmp_path):
    from framework_cli.downskill import usage_references

    (tmp_path / "src" / "demo" / "webhooks").mkdir(parents=True)
    (tmp_path / "src" / "demo" / "webhooks" / "handler.py").write_text("import demo.webhooks\n")
    refs = usage_references(
        tmp_path, "webhooks", package_name="demo", owned={"src/demo/webhooks/handler.py"}
    )
    assert refs == []
