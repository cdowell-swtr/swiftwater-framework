# Phase 1 — Data-model & correctness retrofit scan

**Agent:** data-model
**Date:** 2026-06-22
**Area:** ID strategy · money/decimal/currency · time/UTC/DST · soft-delete & data-lifecycle ·
record/schema/API/event versioning · nullability/enum evolution.

These are the classic "wrong default is a data migration to fix" decisions. The unifying
property: the *representation* of a value (its type, its identity, its presence/absence) is
referenced from a thousand places once a product has real data — so changing it later is not a
code change, it's a coordinated data migration against live rows, live integrations, and live
clients.

A recurring discipline runs through the whole area, and the scaffold should encode it
explicitly: **storage/representation is a data-model concern; formatting/display is i18n.**
Integer minor units + ISO-4217 currency code is storage; "$1,234.56" vs "1.234,56 €" is i18n.
`timestamptz`/UTC is storage; "Tuesday at 3pm in the user's locale" is i18n. Keeping that line
sharp is what lets the scaffold bake the storage default without colliding with the i18n/l10n
board item.

Five strong seams below, plus one deliberately-thin sixth that is mostly already-covered (kept
for completeness, not padded to peer status).

---

## Seam 1 — External ID strategy (UUIDv7/ULID identity column), distinct from the authz check

**The seam.** Every table needs an identity that appears in URLs, API responses, webhooks, and
foreign keys. The default choice — a sequential `bigserial` primary key exposed directly as the
external ID — is the single hardest data-model decision to reverse, because the moment that ID
leaves your system it is referenced by clients, deep links, third-party integrations, logs, and
analytics, none of which you control.

**Two independent things are tangled here, and the scaffold must keep them apart:**

1. **Identity *type/exposure*** — a base-model decision (a stable, opaque, non-sequential
   external ID).
2. **Authorization** — whether a request is *allowed* to touch the object it named.

**Why late is expensive.** Buildkite ran the canonical dual-key architecture (sequential int PK
for DB efficiency + UUID secondary key for external use) and migrated to UUIDv7 when sharding
forced their hand: *"using integer IDs as primary keys would quickly become a burden within a
distributed database environment."* Time-ordered UUIDs gave them a **~50% reduction in WAL rate**
and similar write-IO improvement vs random UUIDv4 (because v4's random insertion order destroys
B-tree index locality). The 128-bit storage overhead they call *"marginal"* against row size.
The point for us: even a company that *had* the UUID secondary key from day one paid a migration
to make it the primary identity. A product that exposed `bigserial` directly has it embedded in
every external reference.

Sequential IDs also leak business intelligence — `GET /invoices/1042` followed a week later by
`/invoices/1102` tells a competitor your invoice velocity — and enable trivial enumeration
scraping. ([Buildkite — Goodbye integers, hello UUIDv7](https://buildkite.com/resources/blog/goodbye-integers-hello-uuids/))

**The misconception to NOT reproduce.** Every primary source is emphatic on one load-bearing
point: **non-guessable IDs do not fix IDOR.** OWASP, MDN, and Snyk all say the underlying
vulnerability is *missing ownership/authorization checks*, and an opaque ID that leaks via a
public profile page, a log line, or a prior API response is just as exploitable. *"Unpredictable
identifiers reduce brute force attacks but do not prevent unauthorized access if ownership checks
are missing."* So an opaque external ID is a defense-in-depth + scaling + info-leak win, **not**
an authz substitute. ([OWASP IDOR Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html) ·
[MDN — IDOR](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/IDOR) ·
[Snyk — IDOR in Python](https://snyk.io/blog/insecure-direct-object-references-python/))

**retrofit_cost: H.** Changing a PK or external-ID type after integrations reference the IDs is a
coordinated migration across every client, webhook consumer, deep link, and FK. Identity is the
most-referenced value in the system.

**Early scaffolding.** Base SQLAlchemy model with a `bigserial`/`bigint` *internal* PK for
join/index locality **plus** a separate, indexed, NOT-NULL, unique **external ID** column
defaulting to UUIDv7 (time-ordered — best index locality of the opaque options) or ULID. Route
generators key lookups on the external ID, never the int PK. Provide the dual-key seam by
default so a builder never exposes `bigserial`. Pair with a base "ownership-scoped query" helper
that makes the authz check the path of least resistance.

**Proposed disposition: concern** (base-model external-ID default) **+ reviewer-enforced** (the
authz half). Do not collapse these. The reviewer-enforced half — flag a route that loads an
object by external ID without an ownership/tenant scope — is exactly the IDOR class the sources
say the ID change does *not* cover.

**Overlaps.** The reviewer half is adjacent to the existing privacy/compliance reviewers and to
the **multitenancy** board item (ownership scoping ≈ tenant scoping). The opaque-ID concern is
new and not on the board.

---

## Seam 2 — Money representation (`Money` value type: integer minor units + currency)

**The seam.** How monetary amounts are stored: the near-universal naive default is a `float`/
`double` column (or worse, a bare `numeric` with no currency). Both are wrong in ways that only
surface once real transactions accumulate, and the fix is a data migration over every historical
amount plus every line of arithmetic.

**Why late is expensive.** Modern Treasury's analysis is concrete and quotable:

- A 32-bit float storing **$25,474,937.47 approximates it as $25,474,936.32 — off by $1.15.**
- **$2.78 stored as a float is `2.7799999713897705078125`** (base-10 decimals don't decompose
  cleanly into base-2 powers of two).
- Rounding is not even deterministic across languages: Ruby's `round()` is "half away from zero,"
  Python 3 is "half even" (banker's), JavaScript rounds "half towards positive infinity" — so the
  *same* value rounds differently depending on where the code runs, and *"two different methods of
  adding to a total when using the default Banker's rounding leads to a cent difference."*

Their solution is the industry consensus (Stripe does the same): **store the integer count of the
minor currency unit** — `$12.34` → `1234` (a `bigint`) — **and store the ISO-4217 currency code
alongside it**, because the number of minor-unit decimal places is currency-dependent (USD=2,
JPY=0, BHD=3). `bigint` cents spans ±92,233,720,368,547,758.07.
([Modern Treasury — Floats Don't Work For Storing Cents](https://www.moderntreasury.com/journal/floats-dont-work-for-storing-cents) ·
[HackerOne — Precision Matters](https://www.hackerone.com/blog/precision-matters-why-using-cents-instead-floating-point-transaction-amounts-crucial))

The retrofit pain is twofold: (1) a `float` column has *already lost precision* on historical
rows — you cannot reconstruct the true value, only approximate it; (2) a single amount column
with no currency code means you cannot disambiguate what `1234` even *meant* for international
rows. Adding currency later requires guessing the historical currency per row.

**retrofit_cost: H.** Precision loss on stored float values is irreversible; arithmetic touches
every billing/pricing/ledger code path; adding the currency dimension late is a backfill against
ambiguous historical data.

**Early scaffolding.** An opt-in `Money` value object: `(amount_minor: int, currency: str)` with a
SQLAlchemy composite type (`bigint` + 3-char ISO-4217 `char(3)`), exact `Decimal` for any
intermediate division, an explicit rounding policy, and `__add__`/`__sub__` that refuse to combine
mismatched currencies. Display/formatting is **out of scope here** — that is the i18n board item;
this seam owns storage only.

**Proposed disposition: battery** (not every product handles money — it is a coherent opt-in code
surface) **+ reviewer-enforced** (flag `float`/`double`/`Float`/`real` on money-shaped columns —
names matching `price|amount|cost|total|balance|fee` — and amount columns lacking a paired
currency).

**Overlaps.** Formatting/localization of currency is the **i18n/l10n** concern (display, not
storage) — state the line explicitly. No money battery currently on the board.

---

## Seam 3 — Time storage: `timestamptz`/UTC, with the future-event exception

**The seam.** How instants are stored. The default mistake is a naive `timestamp` (no zone) holding
a server-local wall-clock time. It works in dev (one timezone) and breaks the first time data
crosses a zone or a DST boundary — *"correct for ~363 days per year, or always 30 minutes off for
one region."* ([Tinybird — 10 best practices for timestamps](https://www.tinybird.co/blog/database-timestamps-timezones))

**Why late is expensive — and the high-signal nuance most teams miss.**

- **Past/historical events → store UTC in `timestamptz`.** Plain `timestamp` (no zone) risks
  *"a completely different calendar day"* when compared across offsets. With UTC, "last 24 hours"
  queries and chronological sort *"work forever."*
- **Future/scheduled events are the trap.** "Just store UTC" is *wrong* for a future datetime,
  because converting a future wall-clock time to UTC *now* bakes in today's tzdb rules — and
  **timezone/DST rules change** (governments move DST dates, abolish it, shift offsets). A meeting
  the user scheduled for "9am next March" must be stored as **wall-clock time + IANA zone name**
  (`Europe/London`), not a pre-converted UTC instant, or it silently drifts by an hour when the
  rules change before the event arrives. The robust pattern is to also record the **tzdb version**
  used, so you can re-query future rows whose tzdb is now stale and re-derive UTC.
  ([CodeOpinion — Just store UTC? Not so fast](https://codeopinion.com/just-store-utc-not-so-fast-handling-time-zones-is-complicated/))

The retrofit story has two costs, and they are *very* different:

- Changing the column **type** (`timestamp` → `timestamptz`) is **M** — a column alter plus
  deciding an interpretation for existing values.
- **Un-mangling already-stored naive local times is H.** Once instants were written as
  ambiguous server-local wall-clock with no recorded offset, you often *cannot* recover the true
  UTC instant — you don't know which server/zone wrote each row, and DST-transition rows are
  genuinely ambiguous. That irrecoverability is the real seam, not the type alter.

**retrofit_cost: M for the type, H for the data.** Be honest: the alter is mechanical; the data
loss from naive-local storage is the brutal part, and future-event mangling is its own irreversible
class.

**Early scaffolding.** Base model timestamps (`created_at`/`updated_at`) as `timestamptz`,
application code timezone-aware UTC by default (no naive `datetime.utcnow()` — use aware
`datetime.now(UTC)`); a mypy/ruff posture that resists naive datetimes. For the future-event case,
provide a documented pattern (and ideally a small `ScheduledTime` helper): store wall-clock +
IANA zone name + tzdb version, not a pre-converted UTC instant. DST-boundary regression tests as
a scaffolded test stub.

**Proposed disposition: concern** (base-model timestamp default — every table has timestamps) with
the **future-event sub-pattern** called out as its own documented seam (the highest-signal,
least-obvious detail). A light **reviewer-enforced** half is reasonable: flag naive
`datetime.utcnow()` / `datetime.now()` without `tz` and `timestamp`-without-zone columns.

**Overlaps.** Display/locale formatting of times is **i18n/l10n** (storage vs display line again).
Not currently a board item on the storage side.

---

## Seam 4 — Soft-delete & data-lifecycle (archive table, not `deleted_at` everywhere)

**The seam.** The reflexive default is a `deleted_at` nullable column on every table and an ORM
default scope of `WHERE deleted_at IS NULL`. It feels reversible and safe; it is neither, and it
metastasizes through the entire codebase.

**Why late is expensive.** Brandur Leach (Heroku, Stripe) makes the canonical case:

- **The undelete myth.** Across **10+ years at Heroku, Stripe, and since, undeletion was never
  actually performed** — and it *couldn't* be, because the non-data side effects (external API
  calls, blob deletes, infra teardown) can't be reversed by setting `deleted_at = NULL`. So the
  one benefit soft-delete is sold on doesn't materialize.
- **It leaks into every query.** Every `SELECT` needs `AND deleted_at IS NULL`; forget it once and
  you've exposed records meant to be invisible. Manual/operator queries bypass the ORM scope and
  forget it routinely.
- **Foreign-key integrity is lost.** A soft-deleted customer leaves invoices with valid FKs to a
  "technically still existing" row, with no DB-level check that the invoices were soft-deleted too.
  Hard deletes would have raised a constraint violation; soft deletes silently permit orphans.
- **Unique constraints break.** A `UNIQUE(email)` blocks re-registering an email whose owner was
  soft-deleted; you end up needing partial indexes (`... WHERE deleted_at IS NULL`) or generated-
  column hacks per table.
- **Retention/compliance becomes a brittle 30-table cascading-CTE delete** that breaks whenever the
  schema changes.

His recommended alternative is a single `deleted_record` archive table (`jsonb` payload + original
table/id + `deleted_at`) that hard-deletes the live row but preserves the data for support/debug —
keeping FKs functional, queries clean, and retention a one-liner
(`DELETE FROM deleted_record WHERE deleted_at < now() - '1 year'`).
([Brandur — Soft deletion probably isn't worth it](https://brandur.org/soft-deletion) ·
[PHP Architect — Unique index patterns for soft deletes](https://www.phparch.com/2026/02/advanced-unique-index-patterns-for-soft-deletes-mysql-and-postgresql/))

**retrofit_cost: H.** Brandur says it directly: *once embedded across queries and ORMs, soft
deletion becomes expensive to remove — architectural inertia locks you in.* Ripping out a
default-scoped `deleted_at` after the codebase is littered with implicit filters is a
correctness-critical refactor of every query.

**retrofit_cost: H.**

**Early scaffolding.** Make hard-delete + archive the *default* lifecycle: a base `archive_record`
table (jsonb) and a delete helper that moves the row to the archive in one transaction. Where a
genuine "trash/restore within N days" UX is required, scope it to that one table deliberately —
not a blanket `deleted_at` mixin. This is a base-model *design choice*, not erasure mechanics.

**Proposed disposition: concern** (the base-model lifecycle design — archive-on-delete vs blanket
soft-delete).

**Overlaps.** Strong adjacency to the **audit-log/activity-trail battery** (the archive table is a
deletion audit trail — the battery may subsume or extend it). GDPR **right-to-erasure / retention
enforcement is owned by the existing privacy/compliance/data-lineage reviewers** — per the area
brief that is reviewer-territory, so this finding is scoped to the *base-model lifecycle choice*
and hands erasure/retention to those reviewers.

---

## Seam 5 — Schema / API / event versioning (the compatibility-layer seam)

**The seam.** Once an external client, a webhook consumer, or a stored event references the *shape*
of your data, that shape is a contract. Without a versioning seam built in from day one, the first
breaking change forces a choice between breaking every consumer or littering the codebase with
inline `if version >= X` branches. The user has flagged "versioning of everything (schema / event /
API / record)" as high-value on the board.

**Why late is expensive.** Stripe's architecture is the reference implementation and the retrofit
warning is explicit:

- They keep core code at the **latest version only**, then a **response compatibility layer walks
  backward** through dated **version-change modules**, transforming the modern response *back* to
  whatever version the client is pinned to. This has sustained **~100 backwards-incompatible
  upgrades over six years without breaking existing integrations.**
- The "additive safety" doctrine: *"Fields that were present before should stay present, and fields
  should always preserve their same type and name."* Adding endpoints/fields is safe; removing or
  retyping is not.
- The retrofit cost in their own words: without first-class encapsulation from the start, *"dozens
  of checks on version changes that can't be encapsulated cleanly will be littered throughout the
  project, making it slower, less readable, and more brittle."*

For **stored events** (event-sourcing / outbox / message payloads), the analogous seam is
**upcasting**: transform old event versions to the current shape at read time (chainable N→N+1
upcasters) instead of carrying a handler per historical version. Both share the same principle: a
single transformation seam between "what's stored/sent" and "what the code reads."
([Stripe — APIs as infrastructure: future-proofing with versioning](https://stripe.com/blog/api-versioning) ·
[Stripe API Reference — Versioning](https://docs.stripe.com/api/versioning))

**retrofit_cost: H for external API/event consumers, M if internal-only.** Be precise: if the only
consumer is your own frontend deployed atomically with the backend, you can change shapes freely
and the cost is M (coordinate a deploy). The H case is *external* consumers — third-party
integrators, mobile apps you can't force-update, stored events with years of history — where you
cannot make everyone migrate at once and the compatibility layer is the only sane answer. The
scaffold should make the seam present so the builder doesn't paint into the H corner accidentally.

**Early scaffolding.** Pydantic response/request schemas already give a transform point. Scaffold a
versioning convention: a `Stripe-Version`-style header (or URL/Accept negotiation), a versioned
schema namespace, and a documented "version-change module" pattern (latest-only core +
backward-transform layer). For events, scaffold the upcaster registry seam on the outbox/event
payload. Bias every generator toward additive-only changes.

**Proposed disposition: concern** (a posture-level seam scaffolded early — the compat-layer
convention and additive-change discipline).

**Overlaps.** Directly realizes the board's **"versioning of everything (schema/event/API/record)"**
user-emphasized item. Distinct from the already-covered **Pact consumer-driven contracts**: Pact
*tests* that a contract holds; it does **not** provide the runtime compat-layer seam that lets the
shape evolve without breaking pinned clients. Adjacent to **DB migrations + expand-only contract
guard** (already covered) — that guard handles the *database* shape; this handles the *API/event*
shape.

---

## Seam 6 — Enum & nullability evolution (thin; mostly already-covered)

**The seam.** Two related evolution traps: (a) native DB `ENUM` types on columns whose value set
will grow, and (b) adding a `NOT NULL` column to a large live table.

**Why late is expensive (and where it's already on the board).**

- **Native DB enums.** In Postgres you can `ALTER TYPE ... ADD VALUE` to grow an enum, but **you
  cannot safely remove a value** — even after deleting every row using it, the value can persist in
  upper index pages, and dropping the `pg_enum` entry can break the index. Enums also *"feel cleaner
  until product asks for a label, a translation, or a soft-delete"* — they store no label, carry no
  metadata, and every change is engineer-territory DDL. The guidance: prefer a **FK'd lookup table**
  on any column whose value set is expected to grow or need metadata; reserve native enums for
  truly-fixed sets.
  ([Cybertec — Lookup table or enum type?](https://www.cybertec-postgresql.com/en/lookup-table-or-enum-type/) ·
  [Supabase — Managing Enums in Postgres](https://supabase.com/docs/guides/database/postgres/enums))
- **`NOT NULL` backfill on a large table** is the textbook expand-contract problem: `ALTER TABLE`
  takes a schema lock that blocks reads/writes; on a 100M-row table an operation that's instant in
  dev can lock for minutes. The safe path is the **expand → backfill-in-batches → contract**
  pattern.
  ([GitLab — Avoiding downtime in migrations](https://docs.gitlab.com/development/database/avoiding_downtime_in_migrations/))

**retrofit_cost: M.** Both are real but lower-pull than seams 1–5, and the more painful half is
already on the board.

**Early scaffolding.** A documented "lookup-table over native enum for growing value sets" default
in the model conventions; lean on the existing migration guard for the NOT-NULL case.

**Proposed disposition: park** (lookup-table-vs-enum convention is real but low immediate pull) with
a **reviewer-enforced** option (flag native-DB-enum columns whose name suggests a growing set, e.g.
`status`/`type`/`kind`).

**Overlaps.** The `NOT NULL` / expand-contract / zero-downtime-backfill half is **already covered**
by the board's **"DB migrations + expand-only contract guard"** — folded here, *not* presented as
new. Only the lookup-table-vs-native-enum convention is genuinely distinct, and it's thin.

---

## Summary table

| # | Seam | retrofit_cost | Disposition | Key overlap |
|---|------|---------------|-------------|-------------|
| 1 | External ID (UUIDv7/ULID) + authz | H | concern + reviewer-enforced | multitenancy; privacy reviewers |
| 2 | Money (int minor units + currency) | H | battery + reviewer-enforced | i18n (display only) |
| 3 | Time `timestamptz`/UTC + future-event tz | M type / H data | concern (+ light reviewer) | i18n (display only) |
| 4 | Soft-delete → archive table | H | concern | audit-log battery; erasure reviewers |
| 5 | Schema/API/event versioning | H external / M internal | concern | "versioning of everything"; Pact (distinct) |
| 6 | Enum/nullability evolution | M | park (+ reviewer-enforced) | DB-migration guard (already-covered) |

**The single most important discipline across all six:** keep the *concern* and
*reviewer-enforced* halves intact rather than forcing one disposition per seam. The scaffold picks
a storage default where it can (IDs, time, soft-delete lifecycle); the reviewer catches the
antipattern where the scaffold cannot pick for the builder (missing authz check, float-for-money,
naive datetime, growing native enum). That split *is* the finding.
