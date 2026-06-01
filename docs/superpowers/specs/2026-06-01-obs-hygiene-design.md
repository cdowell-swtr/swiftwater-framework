# Obs hygiene: bounded latency window + GraphQL toggle logging — design

**Date:** 2026-06-01
**Status:** approved (brainstorm) → ready for implementation plan
**Source findings:** template-audit `template-audit-2026-05-31-76d9b65` (observability, 2× medium) — `_latencies_ms` is an unbounded list (memory + O(n log n) per scrape) and the GraphQL introspection/IDE toggle is resolved with no log. obs-completeness **sub-slice C** (A = data-store tracing `806ecc5`; B = obs-infra self-monitoring `10aa2bc`, both merged). After this, the deferred work is the **DLQ/webhook-PII** slice.

## Problem

1. **`observability/metrics.py` — `MetricsRegistry._latencies_ms` is an unbounded `list`.** It grows one entry per request (`record_request`) and is fully `sorted()` on every `/metrics` scrape and `/health` call (`_p99`). For a long-running, high-traffic service this is an unbounded memory leak and O(n log n)-growing scrape cost — the metrics endpoint degrades the process it monitors.
2. **`routes/graphql.py` — the introspection/IDE toggle is resolved silently.** `_ide = get_settings().resolved_graphql_ide` and `disable_introspection=not _ide` are evaluated at import with no log. When introspection/IDE is enabled (e.g. a misconfigured prod), nothing records that the schema is exposed — the config drift is invisible to logs.

## Scope

**In scope**
1. Bound the latency samples to a fixed window (memory + scrape cost bounded).
2. Log the GraphQL introspection/IDE decision at router construction.

**Out of scope** — anything else (the DLQ/webhook-PII slice is separate); changing the p99 algorithm beyond windowing; alerting on the toggle.

## Design

### Fix 1 — bounded latency window (`observability/metrics.py`)

- Add `_MAX_LATENCY_SAMPLES = 2048` (module constant).
- `MetricsRegistry.__init__`: `self._latencies_ms: deque[float] = deque(maxlen=_MAX_LATENCY_SAMPLES)` (`from collections import deque`). The deque auto-evicts the oldest sample past the cap.
- `record_request`: unchanged (`self._latencies_ms.append(latency_ms)` — works on a deque).
- `_p99(latencies)`: accept an `Iterable[float]`; `sorted(...)` already works on a deque. (Signature/type-hint update only.)
- `reset()`: `self._latencies_ms.clear()` — `deque.clear()` exists; unchanged.
- Reword the module docstring: the latency window is now a **bounded** last-N reservoir (p99 is over the last `_MAX_LATENCY_SAMPLES` requests — a windowed p99), so memory + per-scrape sort cost stay constant.

Behavior change: p99 is now over the last N requests rather than all-time. For a scaffold this is the correct default (all-time p99 in a process-local list is neither accurate across restarts nor scalable; Prometheus/Tempo own the fleet/historical view).

### Fix 2 — log the GraphQL toggle (`routes/graphql.py`)

Refactor the module-level router wiring into a small factory so the decision is logged once at construction and is testable:

```python
from ..logging_config import get_logger
...
def _configure_graphql_router() -> GraphQLRouter:
    ide = get_settings().resolved_graphql_ide
    get_logger().info("graphql_ide_configured", introspection_enabled=ide)
    return GraphQLRouter(
        build_schema(disable_introspection=not ide),
        context_getter=get_context,
        graphql_ide="graphiql" if ide else None,
    )

router = APIRouter()
router.include_router(_configure_graphql_router(), prefix="/graphql")
```

`introspection_enabled=ide` because `disable_introspection=not ide` (IDE on ⇒ introspection on). The factory preserves the existing behavior (same schema, same `graphql_ide` value) and makes the log assertable without a running server.

## Testing (rendered-project hermetic)

- **metrics** (`tests/unit/test_metrics.py`, always-rendered): record `_MAX_LATENCY_SAMPLES + 100` requests; assert the internal window length is capped at `_MAX_LATENCY_SAMPLES` (e.g. `len(reg._latencies_ms) == metrics._MAX_LATENCY_SAMPLES`) and `p99_latency_ms()` still returns a finite value. Confirm `reset()` empties it.
- **graphql** (battery-gated `tests/unit/`): monkeypatch the `routes.graphql` module's `get_logger` to a recorder, call `_configure_graphql_router()`, assert it logged `graphql_ide_configured` and that `introspection_enabled` equals `get_settings().resolved_graphql_ide`.

## File changes (summary)

| File | Change |
|---|---|
| `src/{{package_name}}/observability/metrics.py` | bounded deque + `_MAX_LATENCY_SAMPLES` + docstring reword |
| `src/{{package_name}}/routes/{…graphql…}.py.jinja` | `_configure_graphql_router()` factory + `graphql_ide_configured` log |
| `tests/unit/test_metrics.py` (template) | latency-window-bounded test |
| `tests/unit/{…graphql…}` (template, battery-gated) | toggle-logged test |

## Risks

- **Windowed p99 is a behavior change** — acceptable + documented; the prior all-time list was itself approximate and unbounded.
- **Existing `test_metrics.py` assumptions** — confirm no test asserts `_latencies_ms` is a `list` or relies on all-time accumulation; adjust if so.
- **Format/long-line** — run `ruff format --check` on the rendered files.
- **Fixture safety** — not fixture-anchored; re-run the per-fixture `git apply --check` scan (expect 0 broken).
