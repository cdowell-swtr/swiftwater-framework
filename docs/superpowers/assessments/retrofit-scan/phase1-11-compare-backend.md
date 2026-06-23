# Phase 1.11 — Comparative scan: backend/fullstack scaffolds

**Agent:** compare-backend
**Method:** survey what mature opinionated backend/fullstack scaffolds **default-include**, then diff against the swiftwater-framework board to find high-retrofit-cost defaults we **lack**. Every seam below anchors to a *named default* of a surveyed scaffold (Cookiecutter Django, Ruby on Rails, Phoenix, create-t3-app, Encore, Nx/Turborepo, and the SaaS starters SaaS Pegasus / Makerkit / ShipFast). Off-mandate seams that surfaced (transactional outbox, general mutation idempotency, full-text search, soft-delete-as-pattern) are folded into the on-method findings or noted as adjacencies — they belong to the data-intensive / distributed-systems scan lanes, not this comparative one.

Scaffolds surveyed and their default bundles (primary sources):
- **Cookiecutter Django** — allauth (auth), Celery/Flower (background jobs), Anymail (email), Docker. ([repo](https://github.com/cookiecutter/cookiecutter-django))
- **Ruby on Rails** — ActiveJob (Solid Queue, DB-backed, default), ActionMailer, ActiveStorage, encrypted credentials (`config/credentials.yml.enc`). ([guides](https://guides.rubyonrails.org/active_job_basics.html), [configuring](https://edgeguides.rubyonrails.org/configuring.html))
- **Phoenix** — PubSub, Presence, Channels, LiveView, `:telemetry` at every lifecycle point. ([Presence](https://hexdocs.pm/phoenix/Phoenix.Presence.html))
- **create-t3-app** — end-to-end type safety: DB schema → Prisma/Drizzle types → tRPC procedures → React components, no codegen step. ([create.t3.gg](https://create.t3.gg/), [repo](https://github.com/t3-oss/create-t3-app))
- **Encore** — infrastructure-from-code: Pub/Sub topics with delivery guarantees, cron, SQL DBs, buckets, secrets declared in app code. ([infra-from-code](https://encore.dev/blog/what-is-infrastructure-from-code), [pubsub](https://encore.dev/docs/ts/primitives/pubsub))
- **Nx / Turborepo** — project graph + affected builds + remote caching for monorepo composition. ([nx vs turborepo](https://nx.dev/docs/guides/adopting-nx/nx-vs-turborepo))
- **SaaS Pegasus / Makerkit / ShipFast** — auth + **teams/multitenancy + RBAC + Stripe subscriptions/metering + entitlements** as the table-stakes default. ([Pegasus](https://www.saaspegasus.com/), [Pegasus subs](https://docs.saaspegasus.com/subscriptions/), [Makerkit](https://makerkit.dev/), [ShipFast](https://shipfa.st/))

What the board already covers that these also default (noted, NOT re-surfaced): background jobs (our `workers`/Celery = Rails ActiveJob / CC-Django Celery); real-time (our `websockets` = Phoenix Channels, modulo Presence — see Finding 5 adjacency); inbound webhook idempotency (`webhooks` idempotent inbox); observability/telemetry (full stack = Phoenix `:telemetry`); email/outbound-comms (board battery = Anymail/Mailgun/Resend); encrypted credentials (board concern: secrets-backing = Rails `credentials.yml.enc`); monorepo composition (board concern: composability/shapes, in flight = Nx/Turborepo).

---

## Finding 1 — Authorization / policy layer (RBAC→ABAC→ReBAC), distinct from authN and tenancy

**The seam.** A first-class, *centralized* authorization layer: a single place that answers "can this principal perform this action on this resource?", with role/permission definitions that live next to features rather than as scattered `if user.is_admin` checks. Every surveyed SaaS starter ships this by default: SaaS Pegasus has "multi-tenant support with **sophisticated role-based access control**"; Makerkit ships "**role-based access control** and a super admin dashboard." Rails/Django scaffolds lean on Pundit/CanCanCan/django-guardian conventions. We have none of this.

**Why late is expensive (the retrofit story).** Authorization is the canonical "design it in or scramble later" seam. Cerbos: once authorization is hard-coded, the logic *"is going to be spread across different, disconnected parts of the codebase"* and to change it you must *"find all the places where the logical checks are made, decipher how it was implemented, and then update it — in every location"* ([Cerbos](https://www.cerbos.dev/blog/badly-designed-authorization-is-technical-debt)). The retrofit story: *"Once a custom authorization system is embedded deeply in an application, replacing it becomes a massive project. Permission data is scattered across database tables. Authorization checks are woven throughout the codebase... Every new permission requirement means hunting down and updating logic in many places"* ([Cerbos via search](https://www.cerbos.dev/blog/badly-designed-authorization-is-technical-debt)). The trigger is almost always reactive: *"you'll be scrambling to retrofit it later, likely after an incident forces your hand"* — and broken authorization is a top OWASP risk. Hard-coded controls (email-domain allowlists, whitelisted user IDs) mean *"if you change the database schema or need to open up to a different user group, you'll need to change all those hard-coded values."*

**Distinctness from the board (defend before the board reviewer collapses it).** This is NOT the board's in-flight **shared-auth** (that's authentication/identity — *who are you*) and NOT **multitenancy** (tenant data isolation — *whose row is this*). Authorization is *who-can-do-what* policy — it composes with both but is a separate enforcement seam. A multitenant app with shared auth still needs a role/permission model, and that model is exactly what's brutal to weave in after endpoints exist. The scaffold's job is the seam: a policy enforcement point (FastAPI dependency that resolves a permission decision), a place to declare roles/permissions, and a convention that every mutating route passes through it — so the answer to "where is access decided?" is one module, not 200 endpoints.

**retrofit_cost: H.** Permission checks woven through every endpoint, permission data spread across tables, and a reactive (post-incident) trigger are the textbook High-retrofit signature; the evidence is explicit that replacement "becomes a massive project."

**Early scaffolding looks like:** a `concern`-level posture — a `Principal`/`permission` enforcement dependency baked into the route layer (every mutating route resolves a decision through it), a declared role→permission map, and an authored example (admin vs member on the demo `Item`). Pluggable backend so a builder can grow from in-code RBAC → a policy engine (Oso/Casbin/OPA-style) without re-touching call sites. Possibly a thin `--with authz` battery for the engine wiring, but the *seam* (the enforcement point + the convention) is posture, not opt-in.

**Disposition: concern.**
**Overlaps:** adjacent to board **multitenancy (logical→physical)** and **composability/shared-auth (in flight)** — defend as the distinct *authorization-policy* third leg; a reviewer (`compliance`/`privacy`) can *enforce usage* but cannot *create the enforcement point* — that must be scaffolded.

---

## Finding 2 — Billing: usage **metering** + **entitlement gating** (the H-cost core of subscriptions)

**The seam.** Subscription billing with a metering model and **entitlement/feature-gating** woven into the code. This is the single most universal SaaS-starter default: SaaS Pegasus ships dj-stripe-synced models, `bootstrap_subscriptions`, per-seat/per-unit billing, a customer portal, and **feature gating via `@active_subscription_required` decorators + a `get_feature_gate_check` helper** ([Pegasus subs](https://docs.saaspegasus.com/subscriptions/)); Makerkit ships "subscription billing with Stripe... per-seat" tied to teams ([Makerkit](https://makerkit.dev/nextjs-saas-starter-kit)); ShipFast ships "Stripe (subscriptions and one-time)" out of the box ([ShipFast](https://shipfa.st/)). We have none of it.

**Why late is expensive — and *which part* is actually High.** Be honest about the split: **checkout** is addable later (M — bolt on a Stripe checkout route). The brutal-to-retrofit parts are **metering** and **entitlements**:

- **Metering is structurally locked once you pick it.** Stripe: *"once you create a meter, you can't change the event name, aggregation method, or customer mapping. If you need to change how usage is aggregated (say, switching from sum to count), you have to create a new meter, create a new price linked to it, and **migrate customers to the new subscription item**"* ([Stripe via search](https://docs.stripe.com/billing/subscriptions/usage-based-legacy/pricing-models)). If you don't emit usage events from day one, you have *no historical usage to bill against* — you cannot backfill a meter, so the entire usage-based pricing option is foreclosed until you instrument and wait out a billing period.
- **Entitlements get woven through code exactly like authorization.** Feature-gating (`@active_subscription_required`, plan-tier checks) lands at every gated route/feature. Add it late and you re-audit every feature surface to decide what each plan unlocks — the same scatter problem as Finding 1.

**retrofit_cost: H** for the metering + entitlement core (no backfillable usage history; entitlement checks woven through the feature surface; a pricing-model change forces a customer migration). Checkout-only would be M — frame the finding on metering+entitlements so the H is honest.

**Early scaffolding looks like:** a `--with billing` battery: a Stripe-synced subscription/plan model, a **usage-event emission seam** (record meterable events to a local table from day one, even before a meter exists — so history is backfillable into Stripe later), a webhook handler for subscription lifecycle (reuses our `webhooks` idempotent inbox), an **entitlement gate** primitive (a dependency/decorator that gates a route on plan/feature — mirrors Pegasus's `get_feature_gate_check`), and a customer-portal redirect. Ties to the tenancy seam (subscription attaches to a tenant/team).

**Disposition: battery.**
**Overlaps:** strong adjacency to board **multitenancy** (subscription→tenant) and **audit-log/activity-trail** (billing events are auditable); the entitlement gate shares machinery with Finding 1's authorization enforcement point.

---

## Finding 3 — End-to-end typed API client (OpenAPI → TypeScript codegen wired into the frontend)

**The seam.** A *generated*, always-in-sync typed client between backend and frontend, so a backend schema change produces compile-time errors in the frontend. This is **create-t3-app's flagship default**: *"types flow automatically from your database schema through your API to your React components. When you change a Prisma model, the tRPC router types update, and any component consuming that data gets compile-time errors if the shape changed"* ([create-t3-app via search](https://create.t3.gg/)) — *"no codegen step, no OpenAPI spec... the TypeScript types flow directly from server to client."*

**Where we stand (verified in-repo).** The `react` battery's frontend hand-writes its API types — `frontend/src/api.ts` literally declares `export type Item = { id: number; name: string }` and `fetch("/items")` by hand, duplicating the backend's Pydantic shape on the TS side with no link between them. The framework *already emits an OpenAPI spec* (CI runs an OpenAPI contract diff in `ci.yml`), so the input for codegen exists — but nothing generates a TS client from it. Every endpoint a builder adds is hand-typed twice, and the two copies drift silently.

**Why late is expensive.** This is the t3 thesis inverted: without the generated seam, *every* frontend call is a hand-maintained duplicate of a backend contract. The retrofit pain scales with surface area — by the time a frontend has dozens of endpoints with hand-written request/response types, introducing codegen means reconciling every hand-typed shape against the generated one and rewriting call sites to the generated client. The cost is *bounded* (it's mechanical, you have the OpenAPI spec) but it grows monotonically with every endpoint added in the interim, and the *class of bug it prevents* — frontend silently consuming a renamed/retyped field — is unbounded and only caught at runtime until then.

**retrofit_cost: M.** The spec already exists and codegen is a known mechanical procedure (openapi-typescript / orval), so it is not High — but it rises steadily with frontend surface area and the bug class it closes is real. Cheapest the day the react battery is first added; M and climbing thereafter.

**Early scaffolding looks like:** wire `openapi-typescript` (or orval) into the `react` battery: a `task`/npm target that regenerates `frontend/src/generated/api.ts` from the backend's OpenAPI spec, replace the hand-written `api.ts` types with the generated client, and add a CI check that fails if the committed generated client is stale vs the spec (mirrors the existing OpenAPI contract-diff gate). The generated-vs-committed staleness guard is the t3 "compile-time error on drift" property, delivered through OpenAPI instead of tRPC's direct inference.

**Disposition: battery** (an enhancement to the existing `react` battery, not a new top-level surface).
**Overlaps:** none on the board; complements the existing OpenAPI contract-diff CI gate (board: Pact CDC) — this is the *frontend*-facing half of contract safety.

---

## Finding 4 — Data-lifecycle convention: `deleted_at` soft-delete base + deletion/retention posture

**The seam.** A baked-in soft-delete / data-lifecycle convention so records carry a `deleted_at` (and the default query scope excludes them) rather than being hard-deleted — making deletion auditable, reversible, and retention-policy-able. This isn't a *scaffold* default of the surveyed set (it's an ORM opt-in — Sequelize's "paranoid" mode, Rails `acts_as_paranoid`), which is why it leads reviewer-enforced rather than battery — but it's the connective tissue the SaaS starters' audit/admin features assume, and it's brutal to retrofit.

**Why late is expensive.** Hard-delete is irreversible by construction: *"If someone asks when a record was removed or by whom, the system has no way to answer unless you've logged that information before the delete"* ([soft-vs-hard via search](https://appmaster.io/blog/soft-delete-vs-hard-delete)). The retrofit is asymmetric — you can *start* soft-deleting tomorrow, but you can never recover the history of everything already hard-deleted, and every existing `DELETE` call site and query must be re-audited to respect the new `deleted_at` scope. The "data-loss paranoia" framing in the industry ([HN/Sequelize via search](https://news.ycombinator.com/item?id=40326815)) is precisely the regret signal: teams retrofit soft-delete *after* an unrecoverable deletion incident.

**Why reviewer-enforced (honoring the task's pivot signal).** The task explicitly routes deletion/erasure/retention to the data-lineage/compliance/privacy reviewers (GDPR right-to-erasure is *their* turf — and soft-delete is in *tension* with erasure, which the privacy reviewer must adjudicate). The only piece the scaffold legitimately owns is a thin **`deleted_at` base-model convention + default-scoped queries** on the demo model; the *policy* (what gets soft- vs hard-deleted, retention windows, erasure-vs-retention conflicts) is a per-feature judgment a reviewer should enforce, not a scaffold should hardcode.

**retrofit_cost: M.** The mechanical change (add `deleted_at`, scope queries, swap `DELETE` for an update) is a bounded procedure and the column is addable; what's *un*recoverable is the already-deleted history, and the call-site re-audit grows with the codebase. Honestly M, not H — the asymmetry (can't recover the past) is the real teeth, not the mechanics.

**Early scaffolding looks like:** a minimal `deleted_at` mixin on the base SQLAlchemy model + a default query scope that excludes soft-deleted rows on the demo `Item`, as a *convention to follow* — and a **reviewer** (compliance/privacy/data-lineage) that flags new models/`DELETE` paths which neither soft-delete nor justify a hard-delete, and that catches soft-delete↔erasure conflicts.

**Disposition: reviewer-enforced** (with a thin scaffolded `deleted_at` base convention as the only scaffold-owned core).
**Overlaps:** board **audit-log/activity-trail** (deletion is an audited event); owned alongside the existing compliance/privacy/data-lineage reviewers (board's GDPR-erasure routing).

---

## Finding 5 — Reliable outbound eventing as a first-class primitive (Encore-anchored)

**The seam.** A declared, reliable *event-publishing* primitive — an internal pub/sub topic with a delivery guarantee — as a first-class part of the app, not a hand-rolled afterthought. **Encore default-includes this**: you declare `new Topic<OrderEvent>("order-created", { deliveryGuarantee: "at-least-once" })` (or `ExactlyOnce`) in app code and the framework provisions SNS/SQS (AWS) or Cloud Pub/Sub (GCP), with equivalent in-memory semantics locally ([Encore pubsub](https://encore.dev/docs/ts/primitives/pubsub), [infra-from-code](https://encore.dev/blog/what-is-infrastructure-from-code)). Phoenix similarly defaults `Phoenix.PubSub` (+ Presence) as a core primitive. We ship a *task queue* (`workers`/Celery) and an *inbound* idempotent inbox (`webhooks`) but no **outbound reliable event-publishing seam** — the place where "this thing happened, tell whoever cares, exactly/at-least once" lives.

**Why late is expensive — the dual-write trap.** The moment an app needs to both persist a change *and* tell another system/service, naive code writes to the DB and then publishes — and *"if these operations are done separately and one of them fails, for example, the message to Kafka fails but the database write succeeds, the system can end up in an inconsistent state... lost messages, duplicated data, or incomplete transactions"* ([Confluent/outbox via search](https://www.confluent.io/blog/dual-write-problem/)). The robust fix is the **transactional outbox** (write the event to an outbox table *in the same DB transaction* as the business data, publish from there), but retrofitting it means re-plumbing every place that already does a naive dual-write — and you can't know which events were silently dropped before. Encore's framing is the prevention: *"the infrastructure can't drift from the application because it's derived from it"* — declaring the topic up front makes the reliable path the *default* path, so builders never hand-roll the lossy one. (This consolidates the off-mandate "transactional outbox" and "general mutation idempotency" seams into one on-method finding: outbound idempotency/exactly-once is a *property of the eventing primitive*, the same way our `webhooks` inbox provides inbound idempotency.)

**retrofit_cost: H.** Dual-write is the natural thing a builder writes without a primitive; converting an app that already publishes naively to an outbox-backed reliable path means touching every publish site and accepting that pre-retrofit dropped events are unrecoverable — the High signature (woven-in call sites + silent unrecoverable history).

**Early scaffolding looks like:** a `--with events` (or fold into `workers`) battery: an **outbox table** + a publisher loop (the `workers` Celery beat/worker can drain it), a typed `publish(event)` seam that writes to the outbox *within the caller's DB transaction*, and an at-least-once delivery contract with a consumer-side idempotency convention (reusing the `webhooks` inbox dedupe machinery). Local = in-process/Redis; the seam is the same shape Encore declares. This gives builders the reliable path as the *only* path, the way Encore/Phoenix do.

**Disposition: battery.**
**Overlaps:** extends board/existing `workers` (the publisher loop) and `webhooks` (idempotent-inbox dedupe, reused consumer-side); adjacent to board **audit-log/activity-trail** (domain events are the natural audit feed). Note: the *real-time fan-out* half of Phoenix's default (Presence — who's online, tracked over PubSub) is an adjacency our `websockets` battery lacks (we have a connection manager, not Presence); parked as a smaller follow-on, not a separate high-retrofit finding.

---

## Summary table

| # | Seam | Anchored default | retrofit_cost | Disposition | Primary overlap |
|---|------|------------------|---------------|-------------|-----------------|
| 1 | Authorization / policy layer (RBAC→ABAC) | Pegasus/Makerkit RBAC | H | concern | multitenancy / shared-auth (distinct: policy ≠ authN ≠ tenancy) |
| 2 | Billing: usage metering + entitlement gating | Pegasus/Makerkit/ShipFast Stripe | H (metering+entitlements) | battery | multitenancy, audit-log |
| 3 | End-to-end typed API client (OpenAPI→TS) | create-t3-app type-safety | M | battery (react) | OpenAPI contract-diff / Pact |
| 4 | Soft-delete `deleted_at` base + retention posture | Rails/Sequelize "paranoid" (ORM) | M | reviewer-enforced | audit-log, compliance/privacy reviewers |
| 5 | Reliable outbound eventing (outbox) primitive | Encore Pub/Sub w/ delivery guarantee | H | battery | workers, webhooks, audit-log |

**Honest notes on cost:** Findings 1, 2 (metering core), and 5 are genuine High (woven-in call sites + unrecoverable pre-retrofit history). Findings 3 and 4 are Medium — bounded mechanical procedures whose cost *grows monotonically* with surface area but which are not foreclosed the way metering history and dropped events are. Checkout-only billing (excluded from Finding 2's H framing) and a basic typed client are both addable later; the scaffold's value is making the *expensive* core (metering instrumentation from day one, the enforcement point, the reliable-publish path) the default path before a builder paints over it.
