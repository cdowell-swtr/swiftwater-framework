from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

ObsSurface = Literal["service", "in-process", "rides-existing"]
# §FWK133 backup surface — REQUIRED, keyword-only. Forces every battery author to declare
# whether it adds durable state and how recovery handles it; verified against the rendered
# template by tests/test_backup_completeness.py.
#   "none"               -> stateless: adds no named volume, no effect on backup
#   "store"              -> adds a NEW durable store that `task backup` dumps (e.g. mongodb)
#   "rebuildable"        -> adds a named volume intentionally NOT backed up (cache/broker/build)
#   "postgres-extension" -> no new volume; changes the base Postgres dump/restore (restore needs
#                           the extension-loaded postgres image)
DataSurface = Literal["none", "store", "rebuildable", "postgres-extension"]


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
    data: DataSurface = field(kw_only=True)


_BATTERIES: dict[str, BatterySpec] = {
    "webhooks": BatterySpec(
        "webhooks",
        "Signed inbound webhook ingress (HMAC) with an idempotent inbox",
        obs="in-process",
        data="none",
    ),
    "llm": BatterySpec(
        "llm",
        "LiteLLM-backed LLM runtime (completion + structured output) with "
        "full observability — the agents battery builds its tool loop on this",
        obs="in-process",
        data="none",
    ),
    "agents": BatterySpec(
        "agents",
        "LLM agent: a bounded tool-calling loop over read-only domain tools "
        "(POST /agents/run). requires the llm battery",
        requires=("llm",),
        obs="in-process",
        data="none",
    ),
    "claudesubscriptioncli": BatterySpec(
        "claudesubscriptioncli",
        "Route an LLM profile through your Claude subscription via the claude CLI "
        "(litellm-claude-cli). requires the llm battery; needs an authenticated `claude` on PATH",
        requires=("llm",),
        obs="rides-existing",
        data="none",
    ),
    "websockets": BatterySpec(
        "websockets",
        "FastAPI WebSocket routes + a connection manager",
        obs="in-process",
        data="none",
    ),
    "workers": BatterySpec(
        "workers",
        "Celery + Redis async task workers with a DB-backed dead-letter queue and beat scheduler",
        obs="service",
        data="rebuildable",
    ),
    "graphql": BatterySpec(
        "graphql",
        "Strawberry code-first GraphQL endpoint at /graphql over the demo Item model",
        gates_agents=("api-design",),
        obs="in-process",
        data="none",
    ),
    "pgvector": BatterySpec(
        "pgvector",
        "PostgreSQL pgvector extension + an embeddings table for vector similarity search",
        obs="rides-existing",
        data="postgres-extension",
    ),
    "mongodb": BatterySpec(
        "mongodb",
        "MongoDB document store (pymongo) with a documents collection + full observability",
        obs="service",
        data="store",
    ),
    "timescaledb": BatterySpec(
        "timescaledb",
        "PostgreSQL TimescaleDB extension + a readings hypertable for time-series data",
        obs="rides-existing",
        data="postgres-extension",
    ),
    "age": BatterySpec(
        "age",
        "Apache AGE openCypher graph queries on Postgres (no new service)",
        obs="rides-existing",
        data="postgres-extension",
    ),
    "redis": BatterySpec(
        "redis",
        "Redis key/value datastore (cache/sessions) — shares the workers redis service when both are active",
        obs="service",
        data="rebuildable",
    ),
    "react": BatterySpec(
        "react",
        "React + TypeScript SPA served by FastAPI, with Vitest/Playwright/axe and accessibility/usability/frontend-observability review",
        gates_agents=("accessibility", "usability", "observability-fe"),
        obs="in-process",
        data="rebuildable",
    ),
    "consumers": BatterySpec(
        "consumers",
        "Pact consumer-driven contract testing (consumer + provider verification) for inter-service contracts",
        gates_agents=("contracts",),
        obs="rides-existing",
        data="none",
    ),
    "docs": BatterySpec(
        "docs",
        "Versioning-ready MkDocs+Material documentation site (mkdocstrings Python API, static OpenAPI render, mike per-version docs)",
        obs="rides-existing",
        data="none",
    ),
    "multitenantauth": BatterySpec(
        "multitenantauth",
        "Multitenant identity + sessions + authz mechanism + tenant registry "
        "(control-plane spine; cookie/bearer auth, CSRF-defended)",
        gates_agents=("security",),
        obs="in-process",
        data="none",
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
