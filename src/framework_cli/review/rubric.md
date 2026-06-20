## Severity (one scale, consistent across all agents)
- **high** — blocks a builder: a concrete, demonstrable defect that **will** cause incorrect
  behavior, data loss, a security/privacy breach, or a broken contract **in the changed code**.
  It must be a defect that exists **today on a changed line** — not a speculative future failure,
  and not the mere absence of an optional hardening.
- **medium** — should fix before merge but does not block: a real issue with a plausible path to
  harm, or a clear violation of an established project convention.
- **low** — advisory: style, minor clarity, redundant test coverage, bounded micro-optimization, or
  a non-urgent improvement. Carries an action, but never blocks.
- **info** — observation only; never implies an action is required. If you want the author to DO
  something, it is at least **low**, not info. Defense-in-depth hardening the codebase does not
  itself adopt is **info at most**.

## Codebase-bar principle (the dominant false-positive guard)
Do not hold new code to a stricter standard than the surrounding codebase already meets. Before
flagging a pattern, check whether the template/baseline already does the same thing **unflagged**;
if it does, do not flag the new instance. This explicitly includes:

- **Auto-provided behavior.** The framework auto-injects `correlation_id`/`trace_id` (structlog
  `add_correlation_id`/`add_trace_context` processors), auto-traces via `FastAPIInstrumentor` /
  `SQLAlchemyInstrumentor` (registered on the engine), auto-meters requests via
  `ObservabilityMiddleware`, and instruments frontend errors globally via `window`
  `error`/`unhandledrejection` listeners. The **absence of a manual span/metric/log/correlation_id**
  on a path that runs through the instrumented seam is **NOT a defect**. Flag only a path that
  genuinely **BYPASSES** the seam: a raw driver / a second engine not registered with the
  instrumentor / a background task outside the instrumented session, or **active suppression** of a
  global signal (a `catch` that consumes a rejection so it never reaches the global handler).
- **Hardening the baseline omits.** `SecretStr` / `min_length` / rotation docs (the template's own
  `webhook_signing_secret` is a plain `str = ""`, with zero `SecretStr`/`get_secret_value`/
  `min_length` uses anywhere in `template/`); upper version bounds (the template pins bare `>=`
  floors); per-endpoint SLOs (the template ships **fleet-wide SLOs only**, no per-endpoint
  convention); per-view RUM (the template instruments globally). Demanding any of these is **info at
  most**, and only when not already redundant with an existing mitigation (e.g. `.env` is already
  in the template `.gitignore`).
- **Specific verified template facts (do NOT flag their absence):** the session factory sets
  `expire_on_commit=False`, so ORM attributes survive commit without a manual `refresh`;
  `created_at` uses `server_default=func.now()`, so it is always populated in the DB; `items.name`
  has **no UNIQUE constraint** (migration 0001 is NOT NULL only), so absence of de-dup is not a
  violated invariant; `repository.create_item` / `list_items` store and return values **verbatim**
  with no normalization and hydrate the full ORM row; structured `get_logger().info(event, key=…)`
  logging of an **opaque identifier** is the sanctioned request-logging idiom
  (`middleware/observability.py`, `webhooks/inbox.py`).

## Internal consistency within one review
Apply one standard to every instance of a pattern you see in the same diff. If you do not flag
instance A, do not flag an identical instance B (the `create_item` / bulk-insert lesson). Do not
demand a mitigation on one fixture then flag a sibling for **having** that same mitigation. Apply the
**same severity** to identical findings. Report one root defect **once**: fold in-domain secondary
symptoms into that finding rather than emitting them as independent blockers.

## Scope discipline (one owner per class)
Stay within this agent's domain (stated per-agent, including an explicit "do **NOT** flag X — agent
Y owns it" list). Do not flag issues another agent owns; cross-reference instead of re-flagging.
Canonical ownership: **PII (logged / echoed / captured into telemetry / over-collected /
retained-beyond-purpose) → privacy**; **audit-gap / retention-path / erasure-path → compliance**;
**non-atomic writes / transaction & session state / store invariants → data-integrity**;
**correctness / edge cases / wrong conditionals / swallowed errors → application-logic**;
**unbounded scans / raw query cost / N+1 / the pagination-defect itself, AND any unbounded input/resource cap (e.g. a missing MAX_BATCH_SIZE on a bulk write) → performance, NOT data-integrity; an unbounded GraphQL list-resolver SHAPE → api-design; input validation (empty/whitespace/over-length on a non-NULL-but-emptyable field) → application-logic, NOT data-integrity; PII appearing in a log line — and any missing log-retention or log-erasure path for that LOGGED PII — → privacy, NEVER compliance (compliance owns audit/retention of personal data in durable STORED records only); import hygiene / dead code / unused names → code-quality, and no agent emits a standalone import/unused finding (it may only be folded into its own root finding). One-owner-per-class: each owner grades the class at its own output contract's severity — this assigns ownership, it does NOT impose a single severity across these distinct facets.**; **REST/OpenAPI parity &
response_model & spec regen → contracts / api-design**; **import hygiene / dead code / naming /
style → code-quality**; **runtime/async behavior the manifest diff cannot show → performance /
application-logic, not dependency**. Integration/wiring completeness ("a new component is not yet
used by a parent") is **not a review concern** for any agent.

## Grounding & diff-awareness
Cite only file/line facts you have actually **READ in this run**. Do not enumerate `.env.example`
declarations, settings, alert/dashboard inventories, CVE identifiers, or any baseline **from
memory**, and do not assert what is or isn't declared without a read. Treat files **created or
modified in THIS diff as present**: before flagging a surface as missing (an alert, a dashboard, a
declaration), confirm it is absent from **both** the diff and the existing tree. Speculative
"IF the middleware does not…" findings against established framework wiring are disallowed.
