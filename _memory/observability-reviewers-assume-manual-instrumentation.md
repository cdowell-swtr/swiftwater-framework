---
name: observability-reviewers-assume-manual-instrumentation
description: The observability review-agent prompts (esp. review-observability-db) demand MANUAL spans/metrics the template never writes — it auto-instruments — so they over-flag every code path; the old good fixtures were rigged with manual instrumentation to match the broken prompt. Plan 21 Phase 1 redesign item.
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: e7e23a67-9817-4ea6-8b0e-fbf0bba32de0
---

Discovered in Plan 21 Phase 0b (good-fixture representativeness audit, FF 5fdd8c2). The
**`observability-db` prompt** flags "a new data-store query/write path with no metric or span
around it" as **high** — but the generated template **auto-instruments**: `SQLAlchemyInstrumentor().instrument(engine=engine)`
(observability/datastores.py.jinja), `FastAPIInstrumentor.instrument_app(app)` (tracing.py.jinja),
and an `add_correlation_id` structlog processor (logging_config.py) auto-injects correlation_id.
**Zero** manual `start_as_current_span`/`get_tracer`/`set_attribute` in production code; the real
logging idiom is module-top `get_logger().info("event", **kwargs)`. So the prompt would flag
**every** repository function — incl. the template's own `list_items`/`create_item` — as a
high-severity defect. This is the mechanism behind the Plan 18 observability over-flagging.

**The tell:** re-authoring `observability-db/good/observed-query` to be representative (a plain
auto-instrumented query) made it **byte-identical (minus docstring) to `observability-db/bad/unindexed-unobserved-query`**.
The old good fixture only "passed" because it was rigged with a manual span matching the broken
prompt — fixture + prompt wrong in a mutually-consistent way that hid the defect. The "bad"
defect isn't a real defect under auto-instrumentation.

**Phase 1 must:** rewrite the `observability*` prompts to the auto-instrumentation model — flag
only genuinely-uncovered cases (a raw connection bypassing the instrumented engine; an explicit
business metric that must exist; instrumentation disabled on a hot path; a structured business
event that should be logged but isn't) — and **reseed the bad fixtures** with a real gap.
`observability/good/{instrumented-route,correlation-id-logging}` were re-authored with a valid
good/bad contrast (good emits a structured event, bad emits none) and are OK; `observability-db`
needs full prompt+bad-fixture redesign. Until then `observability-db`'s eval recall is unreliable.
This is the concrete instance of [[reviewer-tuning-is-prompts-not-thresholds]]. Evidence:
`docs/superpowers/eval-scorecards/2026-06-10-plan21-baseline/PHASE0B-FINDINGS.md`.
