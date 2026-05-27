import pytest


def test_websockets_is_registered():
    from framework_cli.batteries import battery_names, get_battery

    assert "websockets" in battery_names()
    spec = get_battery("websockets")
    assert (
        spec.name == "websockets" and spec.requires == () and spec.gates_agent is None
    )


def test_resolve_unknown_battery_errors():
    from framework_cli.batteries import resolve

    with pytest.raises(ValueError, match="bogus"):
        resolve(["bogus"])


def test_resolve_returns_sorted_unique():
    from framework_cli.batteries import resolve

    assert resolve(["websockets", "websockets"]) == ["websockets"]


def test_webhooks_is_registered():
    from framework_cli.batteries import get_battery

    spec = get_battery("webhooks")
    assert spec.name == "webhooks" and spec.requires == () and spec.gates_agent is None


def test_resolve_includes_dependency_closure():
    # Use a synthetic spec to prove the closure walks `requires` (no real multi-battery yet).
    from framework_cli import batteries

    batteries._BATTERIES["_child"] = batteries.BatterySpec(
        "_child", "x", requires=("websockets",)
    )
    try:
        assert batteries.resolve(["_child"]) == ["_child", "websockets"]
    finally:
        del batteries._BATTERIES["_child"]


def test_workers_battery_is_registered():
    from framework_cli.batteries import get_battery, resolve

    spec = get_battery("workers")
    assert spec.name == "workers"
    assert spec.requires == ()  # standalone — depends on nothing
    assert resolve(["workers"]) == ["workers"]


def test_graphql_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "graphql" in battery_names()
    assert get_battery("graphql").requires == ()
    assert resolve(["graphql"]) == ["graphql"]


def test_pgvector_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "pgvector" in battery_names()
    assert get_battery("pgvector").requires == ()
    assert resolve(["pgvector"]) == ["pgvector"]


def test_mongodb_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "mongodb" in battery_names()
    assert get_battery("mongodb").requires == ()
    assert resolve(["mongodb"]) == ["mongodb"]


def test_timescaledb_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "timescaledb" in battery_names()
    assert get_battery("timescaledb").requires == ()
    assert resolve(["timescaledb"]) == ["timescaledb"]


def test_age_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "age" in battery_names()
    assert get_battery("age").requires == ()
    assert resolve(["age"]) == ["age"]
