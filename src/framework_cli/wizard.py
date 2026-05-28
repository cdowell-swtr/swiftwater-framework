"""The `framework new` wizard: needs→battery resolution, alert-channel parsing, and an
interactive/non-interactive runner. Sources answers only — rendering is unchanged."""

from __future__ import annotations

# Needs-language → atomic battery (the db-paradigm half). Relational is always-on (not listed).
NEED_TO_BATTERY: dict[str, str] = {
    "document": "mongodb",
    "vector": "pgvector",
    "timeseries": "timescaledb",
    "graph": "age",
    "cache": "redis",
}

# Alert channels, in canonical render order. `webhook` is the always-available default.
KNOWN_CHANNELS: tuple[str, ...] = ("webhook", "slack", "email", "pagerduty")


def resolve_needs(needs: list[str]) -> list[str]:
    """Map data-need keys to batteries (deduped, input order preserved). Unknown → ValueError."""
    out: list[str] = []
    for need in needs:
        if need not in NEED_TO_BATTERY:
            raise ValueError(
                f"unknown data need: {need!r} (known: {', '.join(NEED_TO_BATTERY)})"
            )
        battery = NEED_TO_BATTERY[need]
        if battery not in out:
            out.append(battery)
    return out


def parse_channels(channels: list[str]) -> list[str]:
    """Validate + dedup an alert-channel selection, returned in canonical order.

    Empty → ValueError (a project must have at least one channel; the silent no-op is what
    this whole feature exists to kill). Unknown channel → ValueError.
    """
    selected = set()
    for c in channels:
        if c not in KNOWN_CHANNELS:
            raise ValueError(
                f"unknown alert channel: {c!r} (known: {', '.join(KNOWN_CHANNELS)})"
            )
        selected.add(c)
    if not selected:
        raise ValueError("select at least one alert channel")
    return [c for c in KNOWN_CHANNELS if c in selected]


# Drift guard (mirrors migrations.py): every mapped battery must be a real, registered battery,
# so a battery rename fails loudly at import rather than silently downstream.
from framework_cli.batteries import battery_names as _battery_names  # noqa: E402

assert set(NEED_TO_BATTERY.values()) <= set(_battery_names()), (
    "NEED_TO_BATTERY references an unknown battery — sync it with framework_cli.batteries"
)
