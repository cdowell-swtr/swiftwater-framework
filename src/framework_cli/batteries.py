from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

ObsSurface = Literal["service", "in-process", "rides-existing"]


@dataclass(frozen=True)
class BatterySpec:
    name: str  # token used in templates + `--with`
    summary: str  # one line, for --help / error messages
    requires: tuple[
        str, ...
    ] = ()  # batteries this one implies (e.g. pgvector -> postgres)
    gates_agents: tuple[str, ...] = ()  # review agents activated when present (8d/8g)
    # §5 observability surface — REQUIRED, keyword-only. Forces every battery author to
    # declare obs intent; verified against the rendered template by tests/test_obs_completeness.py.
    #   "service"        -> a separate process/exporter: owes scrape + alert + dashboard + prod-wiring
    #   "in-process"     -> metrics on the app's own /metrics: owes alert + dashboard
    #   "rides-existing" -> no new §5 surface (postgres-extension, frontend-deferred, test harness)
    obs: ObsSurface = field(kw_only=True)


_BATTERIES: dict[str, BatterySpec] = {
    "webhooks": BatterySpec(
        "webhooks",
        "Signed inbound webhook ingress (HMAC) with an idempotent inbox",
        obs="in-process",
    ),
    "llm": BatterySpec(
        "llm",
        "LiteLLM-backed LLM runtime (completion + structured output) with "
        "full observability — the agents battery builds its tool loop on this",
        obs="in-process",
    ),
    "agents": BatterySpec(
        "agents",
        "LLM agent: a bounded tool-calling loop over read-only domain tools "
        "(POST /agents/run). requires the llm battery",
        requires=("llm",),
        obs="in-process",
    ),
    "claudesubscriptioncli": BatterySpec(
        "claudesubscriptioncli",
        "Route an LLM profile through your Claude subscription via the claude CLI "
        "(litellm-claude-cli). requires the llm battery; needs an authenticated `claude` on PATH",
        requires=("llm",),
        obs="rides-existing",
    ),
    "websockets": BatterySpec(
        "websockets",
        "FastAPI WebSocket routes + a connection manager",
        obs="in-process",
    ),
    "workers": BatterySpec(
        "workers",
        "Celery + Redis async task workers with a DB-backed dead-letter queue and beat scheduler",
        obs="service",
    ),
    "graphql": BatterySpec(
        "graphql",
        "Strawberry code-first GraphQL endpoint at /graphql over the demo Item model",
        gates_agents=("api-design",),
        obs="in-process",
    ),
    "pgvector": BatterySpec(
        "pgvector",
        "PostgreSQL pgvector extension + an embeddings table for vector similarity search",
        obs="rides-existing",
    ),
    "mongodb": BatterySpec(
        "mongodb",
        "MongoDB document store (pymongo) with a documents collection + full observability",
        obs="service",
    ),
    "timescaledb": BatterySpec(
        "timescaledb",
        "PostgreSQL TimescaleDB extension + a readings hypertable for time-series data",
        obs="rides-existing",
    ),
    "age": BatterySpec(
        "age",
        "Apache AGE openCypher graph queries on Postgres (no new service)",
        obs="rides-existing",
    ),
    "redis": BatterySpec(
        "redis",
        "Redis key/value datastore (cache/sessions) — shares the workers redis service when both are active",
        obs="service",
    ),
    "react": BatterySpec(
        "react",
        "React + TypeScript SPA served by FastAPI, with Vitest/Playwright/axe and accessibility/usability/frontend-observability review",
        gates_agents=("accessibility", "usability", "observability-fe"),
        obs="in-process",
    ),
    "consumers": BatterySpec(
        "consumers",
        "Pact consumer-driven contract testing (consumer + provider verification) for inter-service contracts",
        gates_agents=("contracts",),
        obs="rides-existing",
    ),
    "docs": BatterySpec(
        "docs",
        "Versioning-ready MkDocs+Material documentation site (mkdocstrings Python API, static OpenAPI render, mike per-version docs)",
        obs="rides-existing",
    ),
    "multitenantauth": BatterySpec(
        "multitenantauth",
        "Multitenant identity + sessions + authz mechanism + tenant registry "
        "(control-plane spine; cookie/bearer auth, CSRF-defended)",
        gates_agents=("security",),
        obs="in-process",
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
