# Phase 1 Retrofit Scan — Distributed-Systems & Data-Flow Seams

**Agent:** distributed-systems
**Area:** idempotency (esp. with replication/retries), at-least-once vs exactly-once delivery, event/message backbone, outbox/inbox, eventual-consistency boundaries, API versioning, pagination/cursoring, read-replica & read/write split.

**Scope note — what the framework ALREADY ships (verified in source, NOT re-surfaced below):**
- An **idempotent inbound webhook inbox** (`webhooks` battery): `webhooks/inbox.py` dedups by inserting a row keyed on the webhook's `idempotency_key` with a UNIQUE constraint (`migrations/.../0002_webhook_events.py`). This is *server-side dedup of inbound webhooks* — the OPPOSITE direction from the client-facing idempotency seam below.
- **Bounded limit/offset pagination** with a hard `MAX_PAGE_SIZE = 100` cap (`db/repository.py::list_items`). The delta below is offset→cursor, not "no pagination."
- A **Celery + Redis worker battery with a DB-backed dead-letter queue** (`workers`).
- The **transactional outbox is named but explicitly NOT implemented** — `webhooks/handler.py.jinja` documents the dual-write hazard in a comment and points at the outbox as the fix.
- Review agents `api-design` (GraphQL-only) and `contracts` (Pact-only) do NOT enforce a REST versioning posture, client idempotency, or cursor pagination — verified by reading `review/agents/api-design.md`.

The five findings below are the NEW deltas on top of that baseline.

---

## Seam 1 — REST API versioning posture (no `/v1`, no version negotiation)

**The seam.** The rendered FastAPI app mounts routes with no version prefix and no version-negotiation mechanism (no `Stripe-Version` / `api-version` equivalent). The first time an external client integrates, the response shapes you ship become a contract you cannot evolve without breaking them.

**Why late is brutally expensive.** Versioning is the canonical "cheap early, agonizing late" decision. Stripe's own framing: their date-based versioning (`Stripe-Version: 2017-05-24`) pins each account to the API version available at its first request, and "every API call they make is assigned that version implicitly," so "users don't accidentally receive a breaking change." Their backwards-compat machinery is a pipeline of **"version change modules"** — encapsulated transformation modules that the response generator "walks back through time and applies… until reaching the target version." They have run **nearly 100 backwards-incompatible upgrades over six years** behind this seam without breaking a single integration ([stripe.com/blog/api-versioning](https://stripe.com/blog/api-versioning), [docs.stripe.com/api/versioning](https://docs.stripe.com/api/versioning)). The point isn't that a scaffold should ship Stripe's whole transformation engine — it's that the *place to put the version dimension* (URL segment or header) has to exist on day one. Microsoft's Azure REST guidelines make this a hard rule: every operation takes a **required** `api-version` query parameter, and an omitted version returns `HTTP 400 MissingApiVersionParameter` — versioning is mandatory, not opt-in, and breaking changes require Breaking-Change-Review-Board approval plus a deprecation header and a lengthy notice window ([github.com/microsoft/api-guidelines/azure](https://github.com/microsoft/api-guidelines/blob/vNext/azure/Guidelines.md), [Azure breaking-change policy](https://github.com/Azure/azure-rest-api-specs/blob/main/documentation/Breaking%20changes%20guidelines.md)).

The retrofit story: once N external clients depend on un-versioned `/items` responses, you cannot change a field's shape, rename it, or tighten nullability without breaking deployed integrations you don't control. Retrofitting forces you to either (a) fork every route into `/v1/...` and dual-maintain, or (b) freeze the API forever. Adding the version segment *before* any client integrates costs one router prefix and a settings knob.

**retrofit_cost: H.** The cost is unbounded in the number of external integrations and is paid in coordinated client migrations — the most expensive kind of change. Brandur notes Stripe deliberately does NOT auto-upgrade pinned versions precisely because the blast radius of a silent shape change is too large ([brandur.org/api-upgrades](https://brandur.org/api-upgrades)).

**What early scaffolding looks like.** Mount the app router under a configurable version segment (`/v1` default, `settings.api_version`), with a documented posture comment in `routes/__init__.py` explaining "additive changes stay in v1; a shape-breaking change cuts v2 — here is the seam." Optionally a thin `Stripe-Version`-style header reader scaffolded but no-op until a second version exists. Ship a one-paragraph "API evolution contract" in the README/DEPLOY docs (additive-is-safe rules, mirroring Stripe's compat list).

**Proposed disposition:** `concern` (posture scaffolded early — a versioned route prefix + an evolution-contract doc; not a battery, it's structural). A complementary `reviewer-enforced` angle exists (flag a shape-breaking change to a versioned REST response), but the structural seam must be scaffolded first.

**Overlaps with the board.** Adjacent to the `api-design` reviewer (GraphQL breaking-change detection) and `contracts`/Pact, but NEITHER covers REST versioning posture — confirmed uncovered. No existing board item.

---

## Seam 2 — Client-facing idempotency keys for mutating endpoints

**The seam.** The framework gives its *own server* an idempotent inbox for *inbound webhooks*, but offers the app's *own API callers* no idempotency surface. Any client that retries a timed-out `POST`/`PATCH` (mobile on flaky cellular, a gateway retry, a queue redelivery) can trigger the side effect twice. This is the opposite direction from the existing inbox: here, *your API is the server offering idempotency to its callers*.

**Why late is brutally expensive.** This is the double-charge class of bug. Brandur's canonical Postgres design opens with Rocket Rides: *"We'll be charging users' credit cards as part of the request, and we absolutely can't take the risk of charging them twice."* The failure is statistical, not exceptional: *"After we reach the scale of millions of API calls a day, basic probability will dictate that we'll be seeing these sorts of things happening all the time"* — connection drops before the response is received, the client can't tell success from failure, retries, and without dedup *"the system cannot distinguish between a legitimate new request and a retry."* The fix is an `idempotency_keys` table with `UNIQUE (user_id, idempotency_key)`, a `locked_at` to serialize concurrent same-key requests, a `recovery_point` state machine across atomic phases, and cached `response_code`/`response_body` so a retry short-circuits to the stored result ([brandur.org/idempotency-keys](https://brandur.org/idempotency-keys), [stripe.com/blog/idempotency](https://stripe.com/blog/idempotency)). This is now a standards track: the IETF HTTPAPI WG `Idempotency-Key` header draft defines exactly this — *"can be used to make non-idempotent HTTP methods such as POST or PATCH fault-tolerant"* — with prescribed `409 Conflict` semantics for an in-flight key and retry rules ([draft-ietf-httpapi-idempotency-key-header](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header)).

The retrofit story: by the time you discover duplicate orders/charges/emails in production, you've already shipped non-idempotent mutation endpoints, clients are already retrying, and you have no key column to dedup on. Retrofitting means changing the *client contract* (clients must now send a key), adding the table + locking + response-caching to every mutating route, and reconciling the duplicates already in the data. Scaffolding the `Idempotency-Key` middleware + table once, before any mutation ships, is a fixed one-time cost.

**retrofit_cost: H.** Requires a client-contract change (the hardest kind), touches every mutating endpoint, and the damage (duplicate side effects) is often irreversible money/state. The framework already proves it understands the mechanism (the webhook inbox) — it just isn't offered outward.

**What early scaffolding looks like.** A `idempotency` battery (or fold into the existing webhook/inbox machinery): an `Idempotency-Key` request-header middleware/dependency, an `idempotency_keys` table migration, a `locked_at` + `recovery_point` helper mirroring Brandur's phases, and a documented "wrap your POST handler in `@idempotent`" seam over the demo `create_item`. Default OFF; one flag turns the demo mutation idempotent as the worked example. Reuses the project's existing UNIQUE-constraint-on-key idiom.

**Proposed disposition:** `battery` (opt-in capability surface; mirrors the webhook inbox machinery, fits the battery model cleanly). Could alternatively be a `concern` if the team wants every mutation idempotent by default, but battery matches the existing inbox precedent.

**Overlaps with the board.** Reuses the existing webhook idempotent-inbox machinery (same UNIQUE-on-key + dedup idiom) but is a distinct, outward-facing surface. No existing board item; complementary to outbound-comms (idempotency prevents duplicate notification sends).

---

## Seam 3 — Transactional outbox (close the dual-write gap the template already names)

**The seam.** The webhook handler enqueues a Celery task *inside the route's inbox transaction, before commit* — a dual-write. The template's own comment in `webhooks/handler.py.jinja` states it verbatim: *"If the commit fails after enqueue, the task ran but no dedup row exists, so a redelivery could process twice… for exactly-once, adopt a transactional outbox (enqueue a row in the same tx, relay it to the broker after commit)."* The fix is named but not shipped.

**Why late is expensive.** The dual-write problem is the canonical reason exactly-once delivery is hard: *"How to atomically update the database and send messages to a message broker?"* — and *"If the database transaction commits then the messages must be sent. Conversely, if the database rolls back, the messages must not be sent"* ([microservices.io transactional-outbox](https://microservices.io/patterns/data/transactional-outbox.html)). 2PC is rejected because *"the database and/or the message broker might not support 2PC"* and it *"couples the service to both."* The concrete failure: *"if Kafka goes down, you have orders in your database but no events published, meaning downstream services never learn about these orders and you have inconsistent state"* ([RisingWave / Debezium outbox](https://risingwave.com/blog/debezium-outbox-pattern-microservices/), [AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)). The solution: write the event to an outbox table **in the same local transaction** as the business write, then a separate relay publishes it — via **transaction-log tailing / CDC** (Debezium) or a **polling publisher**.

The retrofit story is the gentler of the High seams because the framework already has the inbox half and a worker/broker. But retrofitting outbox semantics *after* downstream consumers exist means you've been silently dropping events on every commit-after-enqueue failure, and you can't recover the lost ones — you only learn the consistency was a lie when a downstream reconciliation diverges. Scaffolding the outbox table + a polling relay now, as the symmetric partner to the existing inbox, makes the "robust path" the template already advertises actually exist.

**retrofit_cost: H** (the data-loss is silent and unrecoverable, and consumer contracts harden around the un-reliable delivery), but **the framework is unusually well-positioned** — it has the inbox, the worker, and the broker; the missing piece is one table + a relay loop + a "write to outbox in the same session" helper.

**What early scaffolding looks like.** Extend the `webhooks`/`workers` batteries: an `outbox` table migration, a `publish_event(session, event)` helper that inserts into the outbox within the caller's transaction, and a polling-publisher Celery beat task (the framework already has beat) that relays committed rows to the broker and marks them sent (at-least-once + the existing inbox dedup on the consumer = effectively-once). Rewrite the `handler.py.jinja` dual-write comment into a real `# robust path: outbox` branch. Document the CDC/Debezium upgrade path as the next rung.

**Proposed disposition:** `battery` (extends the existing `webhooks`+`workers` batteries; the template already gestures at it).

**Overlaps with the board.** Directly closes the gap the template names; symmetric partner to the shipped webhook inbox. Complements outbound-comms and audit-log (reliable event emission underpins both). No existing board item.

---

## Seam 4 — Cursor / keyset pagination (offset → cursor)

**The seam.** `list_items` ships bounded `limit`/`offset`. Offset is fine for an admin grid over small data; it breaks down on large, frequently-mutated, or infinite-scroll collections — and the cursor contract is the part that's expensive to add late because it changes the *API shape clients consume*.

**Why late is expensive.** Two distinct, well-evidenced failures:
1. **Deep-offset cost.** `OFFSET 10000 LIMIT 20` "does not start reading at item 10,000. The database reads and discards 10,000 rows, then returns 20" — O(n) in the offset. Benchmarks show keyset giving **a 17x speedup over offset on million-row datasets**, and at page 50,000 offset takes ~87 ms while keyset stays sub-millisecond regardless of depth ([Stacksync keyset vs offset](https://www.stacksync.com/blog/keyset-cursors-postgres-pagination-fast-accurate-scalable), [use-the-index-luke.com](https://use-the-index-luke.com/no-offset)).
2. **Page drift (correctness, not just speed).** "Offset pagination suffers from data consistency issues when rows are deleted or inserted, causing duplicate or missed records." A row inserted/deleted between page fetches shifts every subsequent offset, so a client paging or exporting **silently skips or double-reads rows**. Keyset uses a stable `WHERE (sort_key, id) > (:last_key, :last_id)` cursor, immune to drift ([Merge keyset pagination](https://www.merge.dev/blog/keyset-pagination)).

The retrofit story: cursor pagination is a *response-shape change* (you return an opaque `next_cursor` instead of accepting `offset`), so retrofitting it forces every paginating client to migrate — the same client-contract pain as versioning, on a smaller surface. Shipping an opaque cursor in the response envelope from day one means the offset→keyset swap is server-internal and invisible to clients.

**retrofit_cost: M.** Honest rating: the framework already paginates with a hard cap, so there's no unbounded-scan emergency; the delta is the cursor *contract* + keyset query. The pain is real (client migration + drift bugs surfacing in exports) but bounded to paginating endpoints, and the deep-offset cost only bites at scale.

**What early scaffolding looks like.** Make the list response return an opaque `next_cursor` (base64 of `(last_sort_value, last_id)`) alongside `items`, and have `list_items` accept `cursor` and emit `WHERE (id) > :after` keyset SQL — keeping `offset` as a deprecated fallback for admin use. The cap stays. One worked example over the demo `Item` model; a docstring pointing at use-the-index-luke for the keyset rationale.

**Proposed disposition:** `concern` (a thin posture decision baked into the demo list endpoint's response shape — return a cursor envelope from the start so the offset→keyset swap never breaks a client). Lighter than a battery.

**Overlaps with the board.** Adjacent to the `api-design` reviewer's "unbounded list fields" finding and `db/repository.py`'s existing bound — but those are about *unboundedness*; this is about *cursor correctness + deep-offset scale* on already-bounded reads. Distinct.

---

## Seam 5 — Read/write split & replication-lag posture

**The seam.** `settings.py` notes the DB URL is "an opaque DSN — replica-set hosts… all go here," but the data layer has a single engine/session and no read-path/write-path distinction. Adding a read replica later is operationally trivial; the *code* retrofit is painful only if reads and writes aren't separable in the data layer — and stale-read bugs (read-your-writes violations) are subtle and data-dependent.

**Why late is expensive.** DDIA ch.5: an async follower lags the leader by "a fraction of a second or several seconds or even minutes," so "running identical queries on a leader and a follower could yield different results." The user-visible failure is the **read-your-writes** violation: a user submits a change, immediately reloads, and the read hits a lagging replica that doesn't have their write yet — "they will [not] always see any updates they submitted themselves." DDIA's prescribed mitigation requires the *application* to route: "when reading some data that may have been modified by the user, read it from the leader… for some period greater than replica lag" (also monotonic-reads to stop a user seeing time "go backwards" across replicas) ([DDIA replication-lag summary](https://www.clemsau.com/posts/designing-data-intensive-applications-replication-part-2/), [read-your-writes consistency](https://www.wasteman.codes/blog/read-your-writes-consistency)).

The retrofit story: if every query goes through one undifferentiated session, then on the day you add a replica you must hunt down which reads are safe to send to the replica and which must read-your-writes from the leader — across a codebase that never tracked the distinction. If instead the data layer exposes `read_session()` / `write_session()` from day one (both pointing at the same DB until a replica exists), the split is a config change, and the read-your-writes routing rule has an obvious home.

**retrofit_cost: M.** Honest rating, NOT H: a replica is easy to add operationally, and many products never need read/write split. The cost is paid only if the data layer is monolithic when scale forces a replica, and the stale-read bugs are debuggable (just expensive to chase). Worth scaffolding the *seam*, not the replica.

**What early scaffolding looks like.** A `read_session`/`write_session` (or `replica_engine` defaulting to the primary) distinction in `db/`, with `list_items` using the read session and `create_item` the write session — both identical until `APP_DATABASE_REPLICA_URL` is set. A documented "reads after a user's own write should use the write/leader session for read-your-writes" note at the seam. No replica is shipped; the *separability* is.

**Proposed disposition:** `concern` if scaffolded (a cheap read/write session seam + a read-your-writes doc note), else `park`. Given the M rating and that many products never split, **lean `park`** unless the composability/shapes work makes the session-provider seam free to add — then it's a trivial `concern`.

**Overlaps with the board.** Touches the in-flight composability/shapes/shared-auth work (session providers are a shape seam) and multitenancy (logical→physical isolation also wants a routable data layer). Lands most naturally as a small rider on composability rather than standalone.

---

## Summary table

| # | Seam | retrofit_cost | Disposition | One-line why-late |
|---|------|---------------|-------------|-------------------|
| 1 | REST API versioning posture | H | concern | Un-versioned shapes become an unbreakable contract once external clients integrate (Stripe: ~100 breaking upgrades behind the seam). |
| 2 | Client-facing idempotency keys | H | battery | Retried timed-out POSTs double-charge; fixing it later is a client-contract change + duplicate-data cleanup. |
| 3 | Transactional outbox | H | battery | Template already NAMES the dual-write hazard; commit-after-enqueue silently loses events you can't recover. |
| 4 | Cursor/keyset pagination | M | concern | Offset is O(n) + page-drift skips/dupes; the cursor contract is a client-shape change, cheap to ship up front. |
| 5 | Read/write split posture | M | concern / park | Monolithic data layer makes read-your-writes routing un-findable when a replica is finally added. |

**Highest-signal:** Seams 1 (versioning) and 3 (outbox) — #1 because the blast radius is every external integration, #3 because the framework already named the gap and is one table away from closing it.
