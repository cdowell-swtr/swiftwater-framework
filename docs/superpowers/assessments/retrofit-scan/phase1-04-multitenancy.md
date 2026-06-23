# Phase 1 · Agent 04 — Multitenancy & data-isolation retrofit

**Domain:** logical→physical tenant separation · row-level security · per-tenant keys/encryption ·
noisy-neighbor isolation · tenant export/portability/offboarding · sharding.

**Framing.** Multitenancy is already a board-level *concern* ("logical→physical; Meridian already
stubbed logical separation with future physical"). This file does **not** re-litigate that it
belongs on the board — it decomposes it into the **specific seams** that decide whether the
logical→physical jump is cheap or a 6-12-month re-architecture, and rates each on the retrofit
lens. The headline external finding, repeated by every serious source below, is blunt:

> *"Multi-tenancy is not a feature you add; it is a foundation you build on — get it right early,
> and everything else becomes easier."*
> — Reapdat, *Building a Multi-Tenant SaaS Platform: Architecture Lessons from the Trenches*
> (https://www.reapdat.com/blog/multi-tenant-saas-architecture)

> *"One practitioner made a multi-tenancy decision that cost three months of engineering time and
> a complete data migration."* — same source.

AWS frames the impossibility of late retrofit as a **Kobayashi Maru** (an unwinnable scenario):

> *"Attempting to retrofit fairness into single-tenant systems fails. Instead, services like
> DynamoDB were architected from inception with multitenancy and fairness as core principles."*
> — AWS Builders' Library, *Fairness in multi-tenant systems*
> (https://aws.amazon.com/builders-library/fairness-in-multi-tenant-systems/)

The seams below are ordered by retrofit cost (the scaffold's reason to exist is the high-retrofit
quadrant). Seams 1–3 are the cheap-to-seam mechanisms that make seams 4–7 tractable later.

---

## Seam 1 — Tenant-scoped data model: `tenant_id` on every owned table, composite keys, tenant-scoped uniqueness

**The seam.** Every tenant-owned table carries a `tenant_id` (FK to a `tenants`/`organizations`
table) as the **first column of its primary key and every unique constraint**, and every
foreign key is composite (`(tenant_id, parent_id)`). This is the single decision that makes or
breaks every later isolation move (RLS, schema-per-tenant, db-per-tenant, sharding) — they all
key off a clean tenant column being present and consistently propagated.

**Why late is expensive.** Adding `tenant_id` after a product has real data means a backfill of
*every* row of *every* table, plus reworking primary keys, unique constraints, and foreign keys —
the hardest schema changes to make online. Citus (the canonical Postgres sharding extension)
states the requirements and the retrofit shape directly:

> *"The easiest way to achieve this is to simply add a tenant_id column (or "customer_id" column,
> etc) on every object that belongs to a tenant, and backfilling your existing data to have this
> column set correctly."* — Citus, *Choosing Distribution Column*
> (https://docs.citusdata.com/en/stable/sharding/data_modeling.html)

> *"Citus requires that primary keys contain the distribution column, and making primary keys
> compound will require modifying the corresponding foreign keys as well."*
> — Citus, *Multi-tenant Data Model*
> (https://docs.citusdata.com/en/v7.1/migration/transitioning.html)

> *"Unique and foreign-key constraints on values other than the tenant_id present problems in
> distributed systems… add store_id to constraints, effectively scoping objects unique inside a
> given store."* — same Citus migration doc.

The unique-constraint piece is a particularly nasty late surprise: a product that started with
globally-unique `email`/`slug`/`sku` and *then* goes multi-tenant discovers those should have been
unique **per tenant**, not globally — but two tenants now have colliding values, so you cannot
simply add `tenant_id` to the constraint without a data-cleansing migration. And Postgres
referential integrity compounds it:

> *"PostgreSQL doesn't allow a foreign key to reference a set of columns without a unique
> constraint, even if there's a unique constraint on a subset of those columns."*
> (Postgres -hackers thread, https://postgrespro.com/list/thread-id/2564923)

So retrofitting composite PKs forces a cascade: change PK → change every UNIQUE → change every FK
→ rewrite every query that joins on the old keys. Citus calls the non-co-located outcome an
**"extensive rewrite."** OWASP independently mandates the composite-key shape for *security*
reasons, not just sharding:

> *"Use composite keys (tenant_id + resource_id) for all lookups."*
> — OWASP Multi-Tenant Security Cheat Sheet
> (https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html)

**retrofit_cost: H.** It is a full-table backfill plus PK/UNIQUE/FK surgery plus a query rewrite,
and the tenant-scoped-uniqueness flavor can require resolving *real colliding data* that the
single-tenant past created. This is the textbook "cheap as a convention on day one, brutal after
real data" seam.

**Early scaffold (concrete).** A first-class `tenant_id` convention baked into the model layer:
a `TenantScoped` SQLAlchemy declarative mixin that adds `tenant_id` (UUID/ULID, indexed, NOT NULL,
FK to `tenants`), participates as the leading column of the PK, and makes the framework's existing
demo `Item` model tenant-scoped by construction. A migration-template helper / cookbook for
"tenant-scope an existing table" (add column → backfill → swap PK/UNIQUE/FK) that plugs into the
framework's existing **expand-only migration contract**. The framework already ships
Alembic-style migrations with an expand-only guard — this seam is "make tenant-scoping the default
shape of a model and a documented migration pattern," not new infrastructure.

**Disposition:** **concern** (the foundational layer of the existing multitenancy concern).

**Overlaps:** the board's **multitenancy (logical→physical)** concern — this is its data-model
core. Composite-key/IDOR enforcement also overlaps **identity & access retrofit** (Agent 03,
tenant-scoped permissions) and is the precondition for Seams 2–7.

---

## Seam 2 — Tenant context propagation: auth → request → DB session, with no client-trusted tenant ID

**The seam.** A single, framework-owned path that establishes tenant identity **once** per request
from the *authenticated principal* (never a client header/param), stamps it into a request-scoped
context, and makes it available to (a) the query layer and (b) the DB session — so application
code never hand-writes `WHERE tenant_id = …` and never has the chance to forget it.

**Why late is expensive.** Retrofitting context propagation after dozens/hundreds of endpoints
exist means auditing *every* query for a tenant filter — and the failure is silent:

> *"A new endpoint added in a hurry that forgets the `WHERE tenant_id` clause creates a data leak
> with no runtime error to alert you, quietly handing tenant A's documents to tenant B."*
> (search synthesis over the RLS-failure literature, incl.
> https://www.techbuddies.io/2026/01/01/how-to-implement-postgresql-row-level-security-for-multi-tenant-saas/)

OWASP makes the propagation rules explicit and names the anti-patterns:

> *"Establish tenant context early in the request lifecycle (middleware/interceptor)."*
> *"Bind tenant context to the authenticated user session."*
> *"Never trust client-supplied tenant IDs without validation."*
> *"Don't allow queries without tenant filters (even for admins without explicit override)."*
> *"Implement authorization checks at the data access layer, not just API layer."*
> — OWASP Multi-Tenant Security Cheat Sheet (URL above).

The SQLAlchemy community's settled pattern is an ORM-level safety net so developers *can't* forget:

> *"This approach has a significant advantage: developers don't need to remember to filter by
> tenant_id in every query. The ORM enforces it automatically."* — via `before_compile` /
> `with_loader_criteria` event listeners and a `TenantAwareSession`.
> (https://oneuptime.com/blog/post/2026-01-23-build-multi-tenant-apis-python/view ;
>  library: https://github.com/Telemaco019/sqlalchemy-tenants)

Doing this late is expensive precisely because the cheap version is "wire it into the one
middleware + session factory before there are 200 endpoints"; the late version is "audit 200
endpoints and hope the test suite has a cross-tenant assertion for each."

**retrofit_cost: M-H.** Mechanically the middleware/session change is small, but it only *works*
if every query already routes through the scoped session — retrofitting that discipline across an
existing codebase, plus building the cross-tenant negative tests, is the expensive part. M if the
project is young; H once a wide API surface exists.

**Early scaffold (concrete).** A `tenant_context` request-scoped contextvar set by middleware
from the authenticated principal (riding the framework's shared-auth work, in flight); a
session-dependency that injects the tenant filter via SQLAlchemy `with_loader_criteria` /
`before_compile` **and** issues `SET app.current_tenant = …` on the connection (feeding Seam 3);
a first-class **cross-tenant negative test** in the generated test suite (tenant B cannot read
tenant A's `Item` by ID — proves IDOR is closed and stays a regression guard). A "request →
no tenant context" fail-closed default (reject, don't fall through to unscoped).

**Disposition:** **concern** (the request-path layer of multitenancy). The *enforcement* angle
("did this new endpoint/query scope by tenant?") is a strong **reviewer-enforced** complement —
an agentic reviewer catching an unscoped query on a real diff is exactly the open-world half that
the closed-world scaffold can't cover.

**Overlaps:** **composability/shared-auth (in flight)** — tenant context rides the auth principal;
**identity & access retrofit** (Agent 03). The reviewer angle overlaps existing review agents
(authz/privacy) rather than proposing a new one.

---

## Seam 3 — Row-Level Security (RLS) as DB-layer defense-in-depth

**The seam.** Postgres RLS policies (`tenant_id = current_setting('app.current_tenant')::uuid`)
enabled on tenant-scoped tables, with the app connecting as a **non-owner role** so policies
actually apply, and tenant context `SET` on the connection by the session layer (Seam 2). This is
the *second* layer: even a query that forgot its tenant filter cannot return another tenant's rows.

**Why late is expensive.** RLS is far easier to enable on tables that **already** have a clean,
consistently-populated `tenant_id` (Seam 1) and a session layer that sets the context (Seam 2).
Bolting it on later means discovering, table by table, the rows with `NULL`/wrong `tenant_id`,
and the connection-pool and owner-role traps below. AWS's own RLS guide flags the two retrofit
landmines explicitly:

> *"Using session variables may be incompatible with server-side connection pooling such as
> pgBouncer. Be sure to review all implications of your connection pooling strategy and test if it
> shares session state."*
> *"If your application code connects to the database as the same PostgreSQL role as the table
> owner… your security policies aren't in effect by default."*
> — AWS, *Multi-tenant data isolation with PostgreSQL Row Level Security*
> (https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/)

RLS is **not** a silver bullet — its documented failure modes are real and have CVEs, which is
exactly why it's a *defense-in-depth layer*, not a replacement for Seams 1-2:

> *"The biggest failures weren't missing policies, but silent mistakes: a forgotten role, a pool
> reusing connections with the wrong tenant context, or an admin path bypassing RLS entirely."*
> — synthesized from the RLS-failure literature; concrete CVEs:
> **CVE-2024-10976** (row-security policies below subqueries could disregard user-ID changes),
> **CVE-2025-8713** (optimizer statistics could leak sampled data from RLS-hidden rows).

The payoff for designing it early:

> *"Every SQL statement your developers write will look the same, regardless of tenant context,
> and PostgreSQL enforces isolation for you."* — AWS RLS blog (URL above).

**retrofit_cost: M.** Lower than Seams 1-2 *if* they exist (RLS is then a per-table policy + a
role change + a pool-mode setting). But it inherits their cost if `tenant_id` is dirty, and the
pgBouncer transaction-pooling-vs-session-variable trap is a genuinely subtle late-discovered bug
(it can silently leak under load). It is M, not L, because the connection-pool mode interacts with
the framework's worker/async story.

**Early scaffold (concrete).** Generate the RLS-enabled DDL alongside the `TenantScoped` mixin's
migration (policy + `FORCE ROW LEVEL SECURITY` + a dedicated non-owner app role); have the session
dependency `SET LOCAL app.current_tenant` inside the transaction (transaction-scoped, pooling-safe
with `SET LOCAL`); document/configure the connection-pool mode so the session-variable approach is
correct by default (a known trap the scaffold can pre-empt). Pair with the cross-tenant negative
test from Seam 2 so RLS is proven on by construction.

**Disposition:** **concern** (the DB-layer of the multitenancy posture; opt-in depth that the
scaffold can wire correctly so the consumer doesn't hit the pool/owner traps).

**Overlaps:** **multitenancy (logical→physical)** concern; depends on Seams 1-2; interacts with
the framework's existing **datastore-parity (FWK6)** and worker/Celery pooling.

---

## Seam 4 — Logical→physical isolation routing seam (shared-schema → schema-per-tenant → db-per-tenant)

**The seam.** The connection/routing layer is written so that *which physical store a tenant's
data lives in* is a lookup, not a constant — i.e. tenant → DSN/schema resolution is centralized
behind one resolver, even while every tenant currently maps to the same shared schema. This is the
**explicit board ask**: "what makes the logical→physical jump cheap if seamed early." The jump is
cheap iff the app never hardcodes "one database, public schema" and instead asks a resolver.

**Why late is expensive.** This is the most quantified retrofit cost in the literature:

> *"Migrating from shared schema to database-per-tenant after you have 500 customers is a
> 6-12 month re-architecture project. Infrastructure costs jump 5-8x compared to shared schema
> for the same tenant count."*
> — DEV/sequere comparison
> (https://dev.to/young_gao/multi-tenant-architecture-database-per-tenant-vs-shared-schema-1n2e ;
>  https://www.sequere.com/multi-tenant-saas-data-model)

And the *reason* the jump exists at all is contractual, not technical preference — so a product
**will** be asked to make it the moment it lands an enterprise customer:

> *"Larger customers increasingly ask for data isolation as a contractual requirement, not a
> preference."* (same source.)

> *"The standard architectural pattern of using a shared database with a TenantId column provides
> logical separation, but this model is insufficient to meet escalating demands of security and
> regulatory compliance. A single application-level vulnerability, compromised privileged
> credentials, or a malicious database administrator can result in a catastrophic breach, exposing
> the sensitive data of all tenants simultaneously."* — search synthesis over the database-per-tenant
> literature (https://www.ve3.global/the-multi-tenancy-why-a-database-per-tenant-model-is-the-new-standard-for-saas/).

The pragmatic end-state the sources converge on is **hybrid** — shared schema for the long tail,
dedicated DB for high-value/regulated tenants — and that hybrid is *only* cheap if the routing
seam existed from the start:

> *"A hybrid approach is often practical: use shared schema for small tenants and offload
> high-value tenants to dedicated databases… This gives the best of both worlds when automated
> provisioning is available."* (DEV/sequere, URL above.)

**retrofit_cost: H.** Without the seam, every place the app obtains a connection assumes the
shared store; retrofitting per-tenant routing touches the session factory, migrations (now N-per-
tenant), backups, observability cardinality, and the provisioning/onboarding flow simultaneously —
the 6-12-month figure above. *With* the seam (a resolver behind one indirection), promoting a
tenant to its own schema/DB is a data move + a routing-table row.

**Early scaffold (concrete).** A `resolve_tenant_dsn(tenant_id)`-shaped indirection that today
returns the single shared DSN/`public` schema for all tenants, but is the *one* place the mapping
lives — so adding schema-per-tenant (Postgres `SET search_path`) or db-per-tenant (a different DSN)
later is a resolver change, not a codebase change. This composes with the framework's existing
**datastore-parity (FWK6)** work (a store can already be a co-located container *or* an external
endpoint) — Seam 4 is "make the endpoint *tenant-dependent*." Ship it as a no-op-by-default
indirection (shared schema), documented as the promotion path, with a provisioning hook stub for
"create dedicated store for tenant X." Per-tenant migration fan-out (run the expand-only migration
across N stores) is the operational half.

**Disposition:** **concern** (this is the literal "logical→physical jump" the board names; the
routing indirection is a posture decision made on day one).

**Overlaps:** **multitenancy (logical→physical)** concern (its core promotion mechanism);
**datastore-parity (FWK6)** (already covered — Seam 4 extends it to per-tenant endpoints, not a
new store-connection mechanism); sharding (Seam 1's distribution column) is the same `tenant_id`.

---

## Seam 5 — Per-tenant encryption keys & crypto-shredding (envelope encryption)

**The seam.** Encrypt tenant data under a **per-tenant key** (envelope encryption: a per-record
DEK wrapped by a tenant-bound KEK in a KMS/HSM), so each tenant has an independent crypto blast
radius and offboarding can be a **crypto-shred** (destroy the tenant's KEK → all their ciphertext
is permanently unrecoverable) rather than a best-effort row-delete sweep.

**Why late is expensive.** This is the seam with the most categorical "do not retrofit" warning in
the entire research set — from WorkOS (who build Vault, a production key-isolation product):

> *"Do not start with a shared key and plan to migrate later — migrating means re-encrypting all
> existing data, which is significantly more disruptive than setting the context correctly at the
> start."*
> *"[A single shared key means] all tenant data has the same blast radius. Compromise the key and
> you can decrypt every tenant's data."*
> — WorkOS, *Cryptographic key isolation in multi-tenant SaaS*
> (https://workos.com/blog/cryptographic-key-isolation-multi-tenant-saas)

The envelope structure is what makes per-tenant keys operationally affordable *and* makes the
early seam cheap (you wire context, not a key registry):

> *"KEK rotation does not require re-encrypting your data"* (rotations rewrap DEKs, not data);
> *"you manage context, not keys. There is no key registry to build… When you create an object
> with a new organizationId in the context, Vault creates the corresponding KEK just-in-time."*
> — WorkOS (URL above).

The retrofit cost is literally **re-encrypting the entire dataset** — an offline-or-dual-write
migration over every encrypted field of every tenant. The same envelope pattern is the industry
baseline (AWS KMS / GCP KMS / Azure Key Vault all use DEK+MK envelope encryption); BYOK/CMK builds
directly on it for enterprise customers who demand control of their own keys:

> *"BYOK… is per-tenant encryption where your customers can independently monitor usage of their
> data and revoke all access to it if desired."* (IronCore Labs, https://ironcorelabs.com/byok/ ;
> AWS, https://aws.amazon.com/blogs/architecture/simplify-multi-tenant-encryption-with-a-cost-conscious-aws-kms-key-strategy/).

Crypto-shredding is also the cleanest answer to the offboarding/erasure problem in Seam 7 — a
deleted KEK makes scattered ciphertext in backups, replicas, and caches simultaneously
unrecoverable, which a row-delete never achieves.

**retrofit_cost: H.** The cost *is* re-encryption of all existing data — the canonical irreversible
data migration. WorkOS names it explicitly as the thing not to defer.

**Early scaffold (concrete).** A field-encryption helper (encrypt-at-rest for designated
sensitive columns) wired through a **per-tenant key context** from day one — even if the default
backend is a single dev key, the *context* (tenant → KEK) is established so swapping in a real
KMS/Vault later is a backend change, not a data migration. A `crypto_shred(tenant_id)` offboarding
hook. This is a natural **battery** (opt-in capability surface, like the existing `webhooks`/`llm`
batteries) that declares its obs surface and rides the secrets-backing concern already on the
board. It strongly complements the **field-level-encryption / key-rotation** items in Agent 05's
privacy/compliance domain.

**Disposition:** **battery** (opt-in `--with field-encryption` / per-tenant-keys capability),
with a **concern**-flavored insistence that the *key-context indirection* be present even when the
battery isn't pulled (so the later jump is a backend swap). The erasure-*obligation* it satisfies
is **reviewer-enforced** territory (see Seam 7).

**Overlaps:** **secrets-backing** concern (board); **privacy/compliance** (Agent 05 — field-level
encryption, key rotation, PII tokenization); offboarding (Seam 7). Not currently a framework
battery.

---

## Seam 6 — Noisy-neighbor / fairness isolation (per-tenant quotas, query timeouts, connection caps)

**The seam.** Per-tenant fairness controls so one tenant cannot starve others: per-tenant request
quotas/token-buckets at the edge, per-tenant connection caps at the pooler, per-tenant statement
timeouts at the DB, and per-tenant tagging of every unit of work so the controls have a key.

**Why late is expensive.** AWS's Builders' Library is explicit that fairness *cannot* be retrofit
("Kobayashi Maru," quoted at the top) and gives a concrete shared-resource starvation postmortem:

> *"A shared MySQL database served both a deployment service and a fleet operator. The team got
> paged for performance degradation in the deployment tool, discovering that a fleet auditor
> tool's nightly state synchronization cron job created extra load on the shared database."*
> — AWS, *Fairness in multi-tenant systems* (URL above). It prescribes per-tenant token-bucket
> rate-based quotas and admission control as the structural fix.

> *"The noisy neighbor problem is one of the most common causes of silent SLA breaches in
> multi-tenant systems."* (search synthesis;
> https://systemdr.substack.com/p/designing-for-noisy-neighbors-multi).

Neon's writeup gives the concrete database-layer numbers and mechanisms:

> *"A poorly designed client application from one tenant might open a new connection for each user
> session instead of using connection pooling, potentially preventing other tenants from
> connecting during peak hours."*
> *"Use statement_timeout to cap how long queries can run, with different thresholds per tenant
> tier. For example, Enterprise customers get 60 seconds; Basic users get 15."*
> *"Use PgBouncer in front of your RDS instance and cap concurrent connections per tenant.
> Enterprise might get 50, Premium 20, Basic 5."*
> — Neon, *The Noisy Neighbor Problem in Multitenant Architectures*
> (https://neon.com/blog/noisy-neighbor-multitenant)

The reason late is expensive: the controls need a **tenant tag on every request and every query**
(Seam 2) and a metrics dimension on every resource to even *detect* a noisy neighbor — retrofitting
that instrumentation and the throttle points after a contention incident is reactive firefighting,
not design.

**retrofit_cost: M.** The *primitives* (rate-limit middleware, `statement_timeout`, pooler caps)
exist and the framework already ships rate-limiting (board: "rate-limiting (some)"); the retrofit
cost is the **per-tenant dimension** — making the existing limits tenant-aware and adding per-tenant
observability cardinality. M because the framework's existing rate-limit + full obs stack lowers
the floor; it's not L because per-tenant tagging must thread through Seam 2 to be real.

**Early scaffold (concrete).** Make the framework's existing rate-limiter **tenant-keyed** by
default (token bucket per `tenant_id`, not just per-IP/global); a default per-tenant
`statement_timeout` (tiered) on the DB session; per-tenant labels on the existing
Prometheus/Grafana metrics so a noisy neighbor is *visible* (the obs stack is already there — this
adds the tenant dimension). A documented per-tenant connection-cap pattern for the pooler.

**Disposition:** **concern** (a fairness posture extending the existing rate-limiting + obs
surfaces with a tenant dimension). Largely **already partially covered** by the shipped
rate-limiting + observability stack — the gap is the per-tenant key, not the mechanism.

**Overlaps:** **rate-limiting (already covered, "some")**; **observability stack (already
covered)** — this is "add the tenant label/dimension"; depends on Seam 2 for the tenant key.

---

## Seam 7 — Tenant lifecycle: export / portability / offboarding (the "delete one tenant" problem)

**The seam.** A tenant-complete enumeration of "everything that belongs to tenant X" so the
product can **export** (portability / migration to dedicated infra / GDPR Art. 20) and **delete**
(offboarding / GDPR Art. 17) a single tenant's full footprint — across the primary DB, blob
storage, caches, search indices, analytics, and backups.

**Why late is expensive.** In a shared schema, "delete tenant X" is a fan-out delete across every
table in dependency order, plus every *non-DB* store (blobs, caches, search, event logs, backups)
— and you cannot do it correctly without first knowing the complete tenant data map:

> *"To delete data properly, you first need a clear understanding of what data you have and where
> it's stored, including all data repositories like SaaS applications, cloud databases, backups,
> and physical records."*
> — Reform, *Best Practices for GDPR-Compliant Data Deletion*
> (https://www.reform.app/blog/best-practices-gdpr-compliant-data-deletion)

The contrast that makes the early seam valuable is stark — physical isolation (Seam 4) makes this
trivial, shared schema makes it a project:

> *"With dedicated tenant data isolated in a shard, deleting the entire tenant is as easy as
> deleting a file from your system."*
> — search synthesis (https://www.ve3.global/the-multi-tenancy-why-a-database-per-tenant-model-is-the-new-standard-for-saas/).

Late is expensive because the export/delete routine must be kept in sync with the schema **forever**
— every new table/store added without updating the tenant-export manifest silently breaks
offboarding (and creates a GDPR liability that surfaces only at audit/erasure time). That sync
discipline is exactly the kind of cross-cutting obligation an agentic reviewer is built to enforce.

**retrofit_cost: M.** If Seam 1 holds (`tenant_id` everywhere) the enumeration is mechanical;
the cost is the **completeness obligation** across *non-DB* stores and keeping it current. M, not
H — but it degrades toward H the more stores (blobs, search, analytics) accumulate untracked.
Crypto-shredding (Seam 5) collapses the backup/replica problem and is the cleanest implementation.

**Early scaffold (concrete).** A `tenant_export(tenant_id)` / `tenant_delete(tenant_id)` skeleton
driven off the `TenantScoped` model registry (Seam 1) so newly-added tenant-scoped tables are
included automatically; a documented "every store that holds tenant data registers here" manifest.
But the heart of this is the **obligation**: *does this diff's new table/store get wired into
export and erasure?* — which is an implementation-specific data-lineage question, not a generic
scaffold. Per the board taxonomy, **GDPR right-to-erasure is owned by the data-lineage /
compliance / privacy reviewers**, not a new scaffold.

**Disposition:** **reviewer-enforced** for the erasure/export *obligation* (data-lineage +
compliance/privacy reviewers, per the board's stated rule), with a light **concern**-level scaffold
(the export/delete skeleton off the model registry) so the obligation has a home. Not a battery.

**Overlaps:** **audit-log/activity-trail** battery (offboarding events); **privacy/compliance**
(Agent 05 — erasure, residency); the board's explicit **GDPR-erasure → data-lineage +
compliance/privacy reviewer** exemplar; Seam 5 (crypto-shred) is the cleanest delete primitive.

---

## Summary table

| # | Seam | retrofit_cost | Disposition | Overlaps |
|---|------|:---:|---|---|
| 1 | `tenant_id` data model: composite PK/UNIQUE/FK, tenant-scoped uniqueness | **H** | concern | multitenancy concern (its core); identity/access |
| 2 | Tenant context propagation (auth→request→session), no client-trusted tenant ID | **M-H** | concern (+ reviewer-enforced enforcement) | shared-auth (in flight); identity/access |
| 3 | RLS as DB-layer defense-in-depth (non-owner role, pool-safe `SET LOCAL`) | **M** | concern | multitenancy concern; datastore-parity (FWK6) |
| 4 | Logical→physical routing seam (shared→schema→db-per-tenant; hybrid) | **H** | concern | **the literal board "logical→physical" ask**; datastore-parity (FWK6) |
| 5 | Per-tenant encryption keys / crypto-shred (envelope encryption) | **H** | battery (+ concern key-context) | secrets-backing; privacy/compliance (Agent 05) |
| 6 | Noisy-neighbor fairness (per-tenant quotas/timeouts/conn-caps) | **M** | concern (mostly already covered) | rate-limiting + obs stack (covered) — add tenant dimension |
| 7 | Tenant export/portability/offboarding ("delete one tenant") | **M** | reviewer-enforced (+ light scaffold) | data-lineage/compliance/privacy reviewers; audit-log battery; Seam 5 |

**The through-line for triage:** Seams 1-4 are the same investment — a clean, propagated,
indirection-routed `tenant_id` — viewed at four layers (model, request, DB-policy, physical
routing). That is the cheap day-one decision that makes the board's named "logical→physical jump"
a routing-table change instead of a 6-12-month re-architecture. Seam 5 (keys) is the one
*irreversible-data-migration* seam (re-encryption) the literature is most emphatic about not
deferring. Seam 6 is mostly a tenant-dimension add to surfaces the framework already ships. Seam 7
is correctly a reviewer-enforced obligation, not a scaffold.
