# Phase 0b — good-fixture representativeness audit (2026-06-10)

21 Opus judges, one per `good` eval fixture, each checking whether the fixture's clean
code mirrors a pattern the template actually uses (vs. arbitrary clean code). Full
per-fixture verdicts: `representativeness-verdicts.json`.

## Result: 18 / 21 representative

The 18 representative fixtures faithfully extend real template files with the codebase's
own conventions (verified citations to `routes/items.py`, `db/repository.py`,
`graphql/schema.py`, etc.). They are sound consistency oracles.

## 3 non-representative — all `observability`, same root cause

All three demonstrated **manual instrumentation the template never uses**. Verified against
the template: zero manual `start_as_current_span`/`get_tracer`/`set_attribute` in production
code; tracing is auto-instrumentation (`FastAPIInstrumentor`, `SQLAlchemyInstrumentor`);
`correlation_id` is auto-injected by the `add_correlation_id` structlog processor; the real
logging idiom is module-top `get_logger().info("event", **kwargs)`.

| fixture | was | re-authored to |
|---|---|---|
| `observability-db/good/observed-query` | manual `tracer.start_as_current_span` around a query | a plain auto-instrumented repo function (no manual span) |
| `observability/good/correlation-id-logging` | manual `correlation_id=` kwarg | structured events via module-level `_log`, no manual correlation_id |
| `observability/good/instrumented-route` | manual span + `set_attribute` | auto-traced route + `get_logger().info(...)` + `response_model` |

## Headline finding → carried into Phase 1 (prompt redesign)

Re-authoring `observability-db/good/observed-query` to be representative made it
**byte-identical (minus docstring) to `observability-db/bad/unindexed-unobserved-query`**.
That is not a fixture bug — it exposes a **prompt bug**:

> `observability-db`'s prompt flags "a query with no metric or span around it" as **high**,
> but the codebase auto-instruments every query, so *no* repo function (incl. the template's
> own `list_items`/`create_item`) has a manual span. The prompt would flag every query →
> the Plan 18 observability over-flagging. The old good fixture "passed" only because it was
> rigged with manual instrumentation to match the broken prompt — fixture and prompt wrong
> in a mutually-consistent way that hid the defect.

**Decision (user, Option A):** commit all 3 representative good fixtures; the 0c baseline
will show the over-flagging loudly. `observability-db`'s 0c **recall is unreliable** (its
"bad" defect is not a real defect under auto-instrumentation). **Phase 1 redesigns the
`observability*` prompts to the auto-instrumentation model and redesigns their bad fixtures
to seed genuinely-uncovered gaps** (raw connection bypassing the instrumented engine, an
explicit business metric that must exist, instrumentation disabled on a hot path).

The two `observability/good/{instrumented-route,correlation-id-logging}` re-authorings keep
a valid good/bad contrast (good emits a structured event; bad emits none) and are sound.
