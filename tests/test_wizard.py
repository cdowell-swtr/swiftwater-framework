import pytest

from framework_cli.wizard import (
    KNOWN_CHANNELS,
    NEED_TO_BATTERY,
    parse_channels,
    resolve_needs,
)


def test_need_to_battery_covers_the_five_paradigms():
    assert NEED_TO_BATTERY == {
        "document": "mongodb",
        "vector": "pgvector",
        "timeseries": "timescaledb",
        "graph": "age",
        "cache": "redis",
    }


def test_resolve_needs_maps_and_dedups():
    assert resolve_needs(["vector", "cache", "vector"]) == ["pgvector", "redis"]


def test_resolve_needs_maps_every_paradigm():
    assert resolve_needs(["document", "timeseries", "graph"]) == [
        "mongodb",
        "timescaledb",
        "age",
    ]


def test_need_to_battery_values_are_registered_batteries():
    from framework_cli.batteries import battery_names

    assert set(NEED_TO_BATTERY.values()) <= set(battery_names())


def test_resolve_needs_empty_is_empty():
    assert resolve_needs([]) == []


def test_resolve_needs_unknown_raises():
    with pytest.raises(ValueError, match="unknown data need: 'blob'"):
        resolve_needs(["blob"])


def test_parse_channels_validates_dedups_and_orders():
    # canonical order, deduped
    assert parse_channels(["email", "webhook", "email"]) == ["webhook", "email"]


def test_parse_channels_rejects_empty():
    with pytest.raises(ValueError, match="select at least one alert channel"):
        parse_channels([])


def test_parse_channels_rejects_unknown():
    with pytest.raises(ValueError, match="unknown alert channel: 'sms'"):
        parse_channels(["sms"])


def test_known_channels_order():
    assert KNOWN_CHANNELS == ("webhook", "slack", "email", "pagerduty")
