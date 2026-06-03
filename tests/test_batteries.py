import pytest


def test_websockets_is_registered():
    from framework_cli.batteries import battery_names, get_battery

    assert "websockets" in battery_names()
    spec = get_battery("websockets")
    assert spec.name == "websockets" and spec.requires == () and spec.gates_agents == ()


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
    assert spec.name == "webhooks" and spec.requires == () and spec.gates_agents == ()


def test_resolve_includes_dependency_closure():
    # Use a synthetic spec to prove the closure walks `requires` (no real multi-battery yet).
    from framework_cli import batteries

    batteries._BATTERIES["_child"] = batteries.BatterySpec(
        "_child", "x", requires=("websockets",), obs="rides-existing"
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


def test_redis_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "redis" in battery_names()
    assert get_battery("redis").requires == ()
    assert resolve(["redis"]) == ["redis"]


def test_react_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "react" in battery_names()
    assert get_battery("react").requires == ()
    assert get_battery("react").gates_agents == (
        "accessibility",
        "usability",
        "observability-fe",
    )
    assert get_battery("react").obs == "in-process"
    assert resolve(["react"]) == ["react"]


def test_consumers_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "consumers" in battery_names()
    assert get_battery("consumers").requires == ()
    assert resolve(["consumers"]) == ["consumers"]


def test_consumers_battery_gates_contracts():
    from framework_cli.batteries import get_battery

    assert "contracts" in get_battery("consumers").gates_agents


def test_batteryspec_requires_obs():
    from framework_cli.batteries import BatterySpec

    with pytest.raises(TypeError):
        BatterySpec("x", "y")  # obs is a required keyword-only field


def test_every_battery_declares_a_valid_obs_surface():
    from framework_cli.batteries import battery_names, get_battery

    valid = {"service", "in-process", "rides-existing"}
    for name in battery_names():
        assert get_battery(name).obs in valid, name


@pytest.mark.parametrize(
    "name,expected",
    [
        ("mongodb", "service"),
        ("workers", "service"),
        ("redis", "service"),
        ("webhooks", "in-process"),
        ("websockets", "in-process"),
        ("graphql", "in-process"),
        ("pgvector", "rides-existing"),
        ("timescaledb", "rides-existing"),
        ("age", "rides-existing"),
        ("react", "in-process"),
        ("consumers", "rides-existing"),
    ],
)
def test_battery_obs_surface(name, expected):
    from framework_cli.batteries import get_battery

    assert get_battery(name).obs == expected
