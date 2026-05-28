from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class BatterySpec:
    name: str  # token used in templates + `--with`
    summary: str  # one line, for --help / error messages
    requires: tuple[
        str, ...
    ] = ()  # batteries this one implies (e.g. pgvector -> postgres, later)
    gates_agents: tuple[
        str, ...
    ] = ()  # review agents activated when this battery is present (8d/8g)


_BATTERIES: dict[str, BatterySpec] = {
    "webhooks": BatterySpec(
        "webhooks", "Signed inbound webhook ingress (HMAC) with an idempotent inbox"
    ),
    "websockets": BatterySpec(
        "websockets", "FastAPI WebSocket routes + a connection manager"
    ),
    "workers": BatterySpec(
        "workers",
        "Celery + Redis async task workers with a DB-backed dead-letter queue and beat scheduler",
    ),
    "graphql": BatterySpec(
        "graphql",
        "Strawberry code-first GraphQL endpoint at /graphql over the demo Item model",
        gates_agents=("api-design",),
    ),
    "pgvector": BatterySpec(
        "pgvector",
        "PostgreSQL pgvector extension + an embeddings table for vector similarity search",
    ),
    "mongodb": BatterySpec(
        "mongodb",
        "MongoDB document store (pymongo) with a documents collection + full observability",
    ),
    "timescaledb": BatterySpec(
        "timescaledb",
        "PostgreSQL TimescaleDB extension + a readings hypertable for time-series data",
    ),
    "age": BatterySpec(
        "age",
        "Apache AGE openCypher graph queries on Postgres (no new service)",
    ),
    "redis": BatterySpec(
        "redis",
        "Redis key/value datastore (cache/sessions) — shares the workers redis service when both are active",
    ),
    "react": BatterySpec(
        "react",
        "React + TypeScript SPA served by FastAPI, with Vitest/Playwright/axe and accessibility/usability review",
        gates_agents=("accessibility", "usability"),
    ),
    "consumers": BatterySpec(
        "consumers",
        "Pact consumer-driven contract testing (consumer + provider verification) for inter-service contracts",
        gates_agents=("contracts",),
    ),
}


def battery_names() -> list[str]:
    return sorted(_BATTERIES)


def get_battery(name: str) -> BatterySpec:
    if name not in _BATTERIES:
        raise KeyError(f"unknown battery: {name}")
    return _BATTERIES[name]


def resolve(selected: Iterable[str]) -> list[str]:
    """Validate the selection and return its dependency-closed set (sorted, unique).

    Unknown names raise ValueError naming the offender.
    """
    seen: set[str] = set()
    stack = list(selected)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        if name not in _BATTERIES:
            raise ValueError(
                f"unknown battery: {name!r} (known: {', '.join(battery_names())})"
            )
        seen.add(name)
        stack.extend(_BATTERIES[name].requires)
    return sorted(seen)
