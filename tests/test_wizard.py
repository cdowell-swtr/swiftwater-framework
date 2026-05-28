import pytest

from framework_cli import wizard as wiz
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


def _fail_if_called(*_a, **_k):
    raise AssertionError("prompt should not be called when its flag is provided")


def test_run_wizard_non_interactive_no_flags_uses_defaults():
    out = wiz.run_wizard(with_=[], alerts=None, interactive=False)
    assert out == {"batteries": [], "alert_channels": ["webhook"]}


def test_run_wizard_with_flag_skips_needs_prompt(monkeypatch):
    # interactive, but --with passed → the needs prompt must NOT run
    monkeypatch.setattr(wiz, "_prompt_needs", _fail_if_called)
    monkeypatch.setattr(wiz, "_prompt_channels", lambda: ["webhook"])
    out = wiz.run_wizard(with_=["graphql"], alerts=None, interactive=True)
    assert out["batteries"] == ["graphql"]


def test_run_wizard_alerts_flag_skips_channel_prompt(monkeypatch):
    monkeypatch.setattr(wiz, "_prompt_needs", lambda: [])
    monkeypatch.setattr(wiz, "_prompt_channels", _fail_if_called)
    out = wiz.run_wizard(with_=[], alerts="slack,email", interactive=True)
    assert out["alert_channels"] == ["slack", "email"]


def test_run_wizard_interactive_prompts_both(monkeypatch):
    monkeypatch.setattr(wiz, "_prompt_needs", lambda: ["vector"])
    monkeypatch.setattr(wiz, "_prompt_channels", lambda: ["webhook", "slack"])
    out = wiz.run_wizard(with_=[], alerts=None, interactive=True)
    assert out == {"batteries": ["pgvector"], "alert_channels": ["webhook", "slack"]}


def test_run_wizard_parses_comma_separated_alerts_flag():
    out = wiz.run_wizard(with_=[], alerts="webhook, pagerduty", interactive=False)
    assert out["alert_channels"] == ["webhook", "pagerduty"]
