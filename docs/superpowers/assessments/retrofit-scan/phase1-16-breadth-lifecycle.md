# Phase 1.16 — Breadth-first / anti-blind-spot scan: lifecycle-stage seams

**Agent:** `breadth-lifecycle`
**Lens:** high-retrofit-cost architectural seams OUTSIDE the listed domains, across lifecycle
stages & cross-cutting practices a scaffold often ignores — bootstrapping/first-run, migration
tooling *beyond the DB schema*, testing-strategy seams baked early, API/SDK client generation &
publishing for *your* consumers, deprecation/sunset paths, multi-environment promotion, onboarding.

Each seam below was checked against the current candidate board and against what the framework
*already ships* (verified by reading the template under `src/framework_cli/template/`). Evidence is
from fetched primary sources, not search summaries.

Net: **6 findings** — 3 High retrofit-cost (idempotency, API versioning, data backfill), 3 Medium
(consumer SDK generation/publishing, deprecation/sunset path, test-data factories). Honest spread;
deprecation and factories are explicitly *not* rated High because the code is addable late — the
cost there is process/accumulation, not a structural rewrite.

---

## 1. Request idempotency on mutating endpoints (Idempotency-Key + key store)

**The seam.** Every POST/PATCH that mutates state or calls a foreign system (charge a card, send
an email, create an order) needs an `Idempotency-Key` contract and a server-side key store so a
client retry after a timeout returns the *first* result instead of re-executing. The scaffold mounts
a plain FastAPI app (`main.py.jinja`: `include_routers(app)`) with no idempotency middleware and no
key table.

**Why late = expensive (the retrofit story).** Stripe's canonical write-up frames the core problem
exactly: when a connection breaks mid-exchange "the success of the operation is ambiguous from the
perspective of the client," and *"If we were designing an API endpoint to charge a customer money;
accidentally calling it twice would lead to the customer being double-charged, which is very bad."*
(<https://stripe.com/blog/idempotency>). The reason this is a *structural* retrofit, not a feature
you sprinkle on later, is laid out in Brandur Leach's Postgres implementation: a correct
implementation requires decomposing each endpoint into ordered **atomic phases** — *"a set of local
state mutations that occur in transactions between foreign state mutations"* — with a
`recovery_point` checkpoint persisted between every external call, plus an `idempotency_keys` table
(`locked_at`, `request_params` JSONB, `recovery_point`, cached `response_code`/`response_body`),
`SERIALIZABLE` locking (*"If two different transactions both try to lock any one key, one of them
will be aborted by Postgres"*), and background **completer**/**reaper** sweepers
(<https://brandur.org/idempotency-keys>). He states the retrofit cost directly: endpoints
*"originally designed as single atomic operations need decomposition"* into ordered phases. After a
product has real money/data flowing through endpoints that were written as one big transaction with
foreign calls interleaved, re-sequencing them into recoverable phases touches every mutating handler
— and the duplicate-charge/duplicate-record bugs are already in production by the time you notice.

**retrofit_cost: H.** Adding the key store is mechanical; restructuring already-shipped handlers
into atomic phases (and getting every client to send keys) is not. The damage (double charges,
duplicate records) lands in prod before the fix.

**Early scaffolding looks like.** An idempotency middleware/dependency + an `idempotency_keys`
Alembic migration shipped behind a flag or as the default for the example mutating route; a
`require_idempotency_key` FastAPI dependency that 400s a keyless mutating request and 409s a still-
locked one; a documented "wrap your foreign call between recovery points" pattern in the example
route so builders copy the shape instead of inventing it. Cheap now because the example route and DB
session already exist; the scaffold just bakes the seam.

**Disposition: concern** (posture scaffolded early — middleware + key table + an example handler in
the recoverable-phase shape). Could also surface a small **reviewer-enforced** half: flag a new
mutating route that performs a foreign-state mutation with no idempotency guard.

**Overlaps.** NOT the `webhooks` battery — that handles *inbound* webhook-inbox dedup
(`webhooks/inbox.py`), i.e. *receiving* events idempotently. This seam is the opposite direction:
*your own* mutating endpoints being safely retryable by *your* clients. Distinct. No board item.

---

## 2. API versioning namespace + breaking-change posture from day 1

**The seam.** Routes are mounted with no version segment (`include_routers(app)` in `main.py.jinja`
mounts at the bare path; there is no `/v1`). The day a second consumer integrates, any breaking
change to a response shape breaks them with no escape hatch.

**Why late = expensive.** Speakeasy's versioning guide puts a number on the retrofit:
once an API has paying consumers, *"changing the API can be very difficult"* and the migration cost
scales linearly with consumers — *10 customers × 2 days = 160 person-hours; 1,000 customers × 2 days
= 16,000 person-hours*, at which point *"it becomes unconscionable to ask paying customers to do
that much work"* (<https://www.speakeasy.com/api-design/versioning>). External consumers *"may
resist updates due to the effort and risk… A major change could result in lost business,
dissatisfaction, or churn."* The structural trap: with no version namespace there is nowhere to put
a `/v2` without rewriting every client's base URL, so teams default to either never making the
change or shipping the breaking change anyway. Adding `/v1` *before* anyone integrates is one router
prefix; adding it *after* means coordinating a base-URL migration across every consumer.

**retrofit_cost: H.** The router prefix itself is trivial — the cost is that *introducing* a
version dimension after consumers have hardcoded unversioned URLs is a coordinated, cross-org
migration. The whole point is to reserve the seam before it costs anything.

**Early scaffolding looks like.** Mount the example router under a `/v1` prefix (or an
`APIRouter(prefix="/v1")` the builder extends), with the version recorded in OpenAPI `info.version`;
a documented "additive-only within a version, new version for breaking changes" rule in the
generated `documentation/api/rest.md`; optionally a CI check that fails on a non-additive OpenAPI
diff *within* a version (the export script already commits `openapi.json` and the existing CI
"diffs it for breaking changes" — extend that to enforce the within-version additive rule).

**Disposition: concern** (scaffold the `/v1` namespace + the additive-only posture early).

**Overlaps.** Complements — does not duplicate — the already-covered **Pact consumer-driven
contract testing** and the existing `openapi.json` export + breaking-change CI diff. Pact verifies a
*contract*; the OpenAPI diff *detects* a breaking change; **versioning provides the namespace that
lets you make one without breaking consumers**. The three are a stack, and the namespace layer is
the missing one.

---

## 3. Data backfill / long-running migration jobs (migration tooling BEYOND the schema)

**The seam.** The framework ships Alembic + an expand-only contract guard for *schema* migrations.
But the hard, dangerous part of a real migration is the **data** step: populating a new column, or
re-deriving a value, across millions of *existing* rows — batched, resumable, observable, and gentle
on production load. The schema-migration tooling explicitly does NOT cover this; it's typically left
to an ad-hoc one-off script written under pressure.

**Why late = expensive.** A naive `UPDATE` over a large table *"can lock the table, thrash the I/O
subsystem, and generally ruin your day"* (<https://fly.io/phoenix-files/backfilling-data/>). The
Carwow case study is the concrete failure-and-fix: backfilling ~48.7M rows of
`factory_order_quotes`, a live approach with cross-service lookups *"would have been prohibitively
slow."* Their working pattern — pre-compute mappings out-of-band, dump to S3 in **10,000-row
chunks**, run idempotent background jobs to apply them — completed in *"just under 6 hours"* and,
critically, the chunking gave *"natural checkpoints"* so they could *"easily and quickly stop and
start the backfill"* when DB load spiked and *"resume without duplicating work due to idempotent
jobs"* (<https://medium.com/carwow-product-engineering/backfilling-50-million-records-quickly-eaa04ba5617f>).
The expand/contract canon makes the ordering non-negotiable: *"Add the column as nullable first…
backfill existing rows in batches, then only after coverage is high… enforce NOT NULL as a final
step"* (<https://blogs.reliablepenguin.com/2025/11/16/database-migrations-without-drama-expand-contract-in-practice>).
Retrofit pain: by the time you need a backfill you already have the millions of rows, so the *first*
backfill is the one that locks the table or dies at row 2M with no resume — there is no "do it
gently next time." A builder who learned the batched/resumable pattern from a scaffolded example
ships a safe backfill the first time.

**retrofit_cost: H.** The retrofit asymmetry is the point: you *need* the safe-backfill pattern the
moment you have a large table — which is precisely when you have the most rows and the least slack —
and there is **no second chance to do the first backfill gently**. A scaffold that hands the builder
the batched/resumable/observable loop up front converts a one-shot, table-locking, non-resumable
production hazard into a copy-the-example task. Retrofitting the pattern *after* the first bad run
means doing it post-incident (or post-corruption), with the rows already migrated wrong.

**Early scaffolding looks like.** A small `backfill` helper/base (batch by primary-key range,
configurable chunk size + inter-batch sleep, progress persisted to a `backfill_progress` table or
last-processed-id so it's resumable, reentrant/idempotent per batch, emits OTel spans/metrics so it
shows up in the already-shipped observability stack); an example backfill that follows the
nullable→backfill→NOT NULL sequence so it composes with the expand-only guard. The observability and
DB-session seams already exist — the scaffold supplies the safe loop.

**Disposition: concern** (a posture/helper scaffolded early) or **battery** if gated behind the DB
batteries. Either fits; lean concern because *any* project with a non-trivial table will eventually
backfill.

**Overlaps.** Distinct from the already-covered **DB migrations + expand-only contract guard**:
that governs *schema* DDL; this is the *data* step the expand/contract dance depends on but doesn't
itself provide. Complementary, not a re-surface.

---

## 4. Generate & publish a typed client SDK for YOUR consumers

**The seam.** The framework already exports `openapi.json` (`scripts/export-openapi.sh.jinja`) and CI
keeps it fresh — but it stops at the spec. Nothing generates or publishes a typed client *from* that
spec for the teams who call your API. They hand-write clients, which drift.

**Why late = expensive.** The drift is concrete: ten Brinke documents a real failure where an API
adds a nullable `DeliveryDate` (`DateTimeOffset?` in C#) but the hand-written TypeScript client
types it as a non-nullable `Date`, causing runtime failures because *"the front-end won't expect a
nullable `DeliveryDate`"* (<https://stenbrinke.nl/blog/openapi-api-client-generation/>). Maintaining
the same client across C#/TS/Java/Python by hand is *"boring and error-prone work"*, and clients
*"often call things differently compared to their API counterparts"*, so teams *"have difficulty
communicating about the same thing because of different names."* The retrofit asymmetry: once
multiple consumers each maintain a hand-written client, every spec change requires N teams to
manually chase it; with generation wired into CI, *"regeneration and republication happen in one
pipeline run, eliminating the coordination failure that kills hand-written client ecosystems."*
Migrating an ecosystem *off* hand-written clients onto a generated package after the fact is a
multi-team coordination effort — the same class of cost as un-versioning.

**retrofit_cost: M.** Lower than 1–3: the fix lives in *consumers'* repos and a publish job, not a
rewrite of your own codebase, and consumers can be migrated incrementally. The pain is real but
bounded and external.

**Early scaffolding looks like.** A CI job that runs `openapi-generator`/`openapi-typescript` (or
`datamodel-code-generator` for a Python client) off the already-committed `openapi.json`, versions
the client to the API version (ties into finding #2), and publishes to a package feed on release —
plus a generated `documentation/api/` snippet telling consumers to install the package instead of
hand-rolling. Cheap now: the spec export and CI already exist; this is one more job consuming an
artifact the scaffold already produces.

**Disposition: battery** (opt-in CI publish job + generated-client package; clean fit for the
battery model, gated like the existing `docs`/`consumers` batteries).

**Overlaps.** NOT the `consumers` battery — that ships Pact *consumer-driven contracts* + outbound
client stubs for services *this app calls* (`src/.../clients/inventory.py`, `pacts/`). This is the
**opposite direction**: a published client for the people who call *your* API. Also distinct from
the existing OpenAPI-export/MkDocs docs (spec + human docs, not a typed installable client).

---

## 5. Deprecation & sunset path (Deprecation/Sunset headers + usage telemetry)

**The seam.** When you eventually retire an endpoint or a v1 (finding #2), you need a
machine-readable retirement signal *and* the usage telemetry to know who still calls it. Neither is
scaffolded.

**Why late = expensive (and why it's only M).** The standards are middleware-addable at any time:
RFC 8594's `Sunset` header *"indicates that a URI is likely to become unresponsive at a specified
point in the future"* and is appropriate specifically for the *decommissioning* stage (it is "not
appropriate" while "the API remains operational") (<https://www.rfc-editor.org/rfc/rfc8594.html>);
the `Deprecation` header (RFC 9745) covers the earlier not-recommended stage. The genuinely
high-cost part is NOT the headers — it's the **usage monitoring**, which you cannot retroactively
obtain for a window that already passed. Zalando's guideline makes this a hard MUST: owners *"must
monitor the usage of the sunset API… in order to observe migration progress and avoid uncontrolled
breaking effects on ongoing consumers"*, because without per-deprecated-endpoint usage data *"you
cannot know who still depends on the deprecated feature, making it impossible to safely sunset
without causing unexpected failures"*; and *"Before shutting down an API… the producer must make
sure that all clients have given their consent on a sunset date"*
(<https://github.com/zalando/restful-api-guidelines/blob/main/chapters/deprecation.adoc>). If
per-route usage telemetry wasn't being captured *before* you announced deprecation, you're flying
blind on the migration. The header middleware is cheap whenever you add it; the *measurement seam*
benefits from being on from day one — and the framework already ships the OTel/Prometheus stack to
carry it.

**retrofit_cost: M.** The headers are addable any time (middleware). The only sticky part — per-route
usage telemetry — rides on the observability stack that's already there, so even that is moderate,
not High. Resisting the temptation to over-rate this.

**Early scaffolding looks like.** A tiny `deprecate(sunset=..., link=...)` route decorator/dependency
that emits RFC-compliant `Deprecation`/`Sunset`/`Link` headers and *also* increments a
`deprecated_endpoint_calls{route,version}` counter on the existing Prometheus surface (so a Grafana
panel + alert can watch a deprecated route trend to zero before sunset); an example in the docs. Use
middleware so it's consistent and not "developers remembering to add them manually"
(<https://oneuptime.com/blog/post/2026-01-30-api-deprecation-headers/view>).

**Disposition: concern** for the header/telemetry middleware (scaffolded early so the usage signal
exists when you need it) + a **reviewer-enforced** half: flag a route/response-shape removal or a
version retirement that ships with no Deprecation header / no sunset window / no migration link.

**Overlaps.** Pairs with finding #2 (versioning gives you the thing to deprecate) and rides the
already-covered observability stack (the metric is the only sticky part, and it's already
instrumentable).

---

## 6. Test-data factories vs. seed/fixtures baked early

**The seam.** The template ships `db/seed.py` + `scripts/seed.py.jinja` (static seed data). There's
no factory pattern (Faker-backed, association-aware builders) for *test* data. The choice of how
tests construct data is one of the earliest testing-strategy seams and the most quietly expensive to
reverse.

**Why late = expensive (and why it's M, not H).** The Rails ecosystem learned this the hard way and
it's well documented: early fixture-heavy suites became *"brittle and confusing,"* which is why
*"factories and factory_girl grew very quickly and became the default way to manage test data."* But
the over-correction is just as real — because factories make *"deep object associations… easy to set
up, many applications now create so much data that tests are unbearably slow"*
(<https://semaphore.io/blog/2014/01/14/rails-testing-antipatterns-fixtures-and-factories.html>). The
guidance is to *"generate data using factories… while keeping fixtures small, fast, and
deterministic."* The retrofit cost is *accumulation*: every test written against ad-hoc inline setup
or sprawling shared fixtures becomes a brittle coupling, and a 2,000-test suite's worth of those is
expensive to migrate to factories later — but it's migratable *incrementally*, file by file, which
is why this is Medium, not High. Establishing the factory convention in the scaffold means the
suite grows in the right shape from test #1.

**retrofit_cost: M.** Brittleness accumulates, but conversion is incremental and local — no
structural rewrite, no production data at stake. Over-rating this H would be the easy overclaim.

**Early scaffolding looks like.** A `tests/factories/` module with a Faker-backed factory for the
example model (deterministic seed for reproducibility, association-aware, "build minimal data per
test" convention documented), used by the example tests so builders copy the pattern; keep the
existing static `seed.py` for *dev/demo* data and clearly separate it from *test* factories.

**Disposition: concern** (a testing-posture convention scaffolded early — small, but it's exactly the
kind of seam a scaffold exists to set).

**Overlaps.** Adjacent to the existing `db/seed.py`/`scripts/seed.py` (dev/demo seed) but distinct:
seed = realistic demo data for a running app; factories = minimal, deterministic, per-test
construction. No board item.

---

## Things checked and deliberately NOT raised as new findings

- **Background jobs / Celery task queue** — already covered: the template ships `workers`
  (worker/beat, DLQ, tracing). Adding async was the search hypothesis; it's already in. Not new.
- **Data export / GDPR portability** — real, but correctly owned by the privacy / data-lineage /
  compliance reviewer (per the prompt's own example: right-to-erasure → reviewer-enforced). The
  schema-coupling pain (denormalized data hard to export) is genuine but it's a *reviewer-enforced*
  concern, not a scaffold seam; the board's "audit-log/activity-trail" and the compliance reviewers
  already shoulder this. Noted, not developed.
- **First-run / developer onboarding ergonomics** — substantially overlaps the board's "in-project
  scaffolding," and the framework *is* the golden-path scaffold (one-command dev via Taskfile +
  compose isolation already ship). No distinct high-retrofit seam beyond what's covered. Park.

### Explicit lifecycle-stage sweep (every stage the brief named — accounted for)

The brief named specific lifecycle stages. Roll call so none is silently dropped:

- **Bootstrapping / first-run** → covered (framework *is* the scaffold; one-command dev). Park.
- **Migration beyond the DB:**
  - *data backfill* → **raised (#3).**
  - *config / settings-schema migration* → **not raised; park (M).** Evolving a settings schema
    (renamed/removed env vars, changed defaults) across already-deployed environments is real, but
    the framework already centralizes settings (Pydantic `settings`) and env parity is covered, so a
    rename is a grep + a deprecation shim, not a structural retrofit. Lower pull than #1–#3. The
    additive-only + deprecation posture from findings #2/#5 transfers conceptually.
  - *content migration* → maps to the board's **CMS battery**; not re-surfaced here.
  - *feature migration* → maps to the board's **experimentation/feature-flags** concern; not
    re-surfaced here.
- **Testing-strategy seams baked early:**
  - *contract testing* → covered (**Pact**, `consumers` battery).
  - *load testing* → covered (**k6**).
  - *property-based testing* (e.g. Hypothesis) → **not raised; park.** Genuinely valuable, but it's
    cheap to add to any test file at any time (no structural coupling, no production data at stake) —
    low retrofit cost, so it fails the lens. The one *seam*-shaped slice of testing strategy — how
    tests construct data — is **raised (#6, factories).**
- **API/SDK client generation & publishing for your consumers** → **raised (#4).**
- **Deprecation & sunset paths** → **raised (#5).**
- **Multi-environment promotion** → **not raised; park (borderline M).** Env *parity* (dev/test/
  staging/prod compose + config) is already covered, and the deploy contract governs how an artifact
  ships. The *un*covered slice — promoting the **same built image** dev→staging→prod (immutable
  artifact promotion rather than per-env rebuild) with per-env config injection and promotion gates —
  is a real 12-factor seam ("build, release, run" strict separation), but the existing deploy
  contract + env-parity already establish most of the posture, leaving promotion-gate orchestration
  as the residual. Parked as borderline M, not raised as a distinct H — flagged here so the call is
  conscious, not a blind spot.
- **Developer onboarding ergonomics** → covered/park (see above).
