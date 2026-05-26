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
    gates_agent: str | None = (
        None  # review agent activated when present (wired by 8d/8g)
    )


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
        gates_agent="api-design",
    ),
    "pgvector": BatterySpec(
        "pgvector",
        "PostgreSQL pgvector extension + an embeddings table for vector similarity search",
    ),
    "mongodb": BatterySpec(
        "mongodb",
        "MongoDB document store (pymongo) with a documents collection + full observability",
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
