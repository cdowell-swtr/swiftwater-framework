# Retrofit-Cost Horizon Scan — Synthesis

Consolidated candidate board, deduplicated across 16 research agents and against the
current board. Each distinct seam is ONE row with merged evidence, a single best
retrofit_cost, a crisp claim, and a Meridian-shaped pull (H/M/L). `is_new=false`
means the seam is a facet of an existing board concern (named in `overlaps`) — it
keeps its own row + disposition; `is_new=true` is reserved for capabilities with no
board home.

Coverage facts verified against the template this session:
- Base `Item` model = int PK + `name` + `created_at` as `timestamptz` (so the
  timestamp **column-type** default already ships; no external-ID, no `tenant_id`,
  no authz seam).
- Routes mount bare: `include_routers(app)` — **no `/v1` prefix, no version dimension.**
- `frontend/src/api.ts` **hand-writes** the `Item` type + `fetch` (no generated client).
- Idempotency exists **inbound only** (`webhooks/inbox.py`); no outbound/own-endpoint key store.
- Outbox is **named in a comment** in `webhooks/handler.py.jinja` but **not shipped.**
- Offset pagination with `MAX_PAGE_SIZE` (no cursor/keyset).
- **No** license-policy CI gate, **no** SBOM/provenance/signing, **no** data backup/restore-drill,
  **no** GDPR data-export endpoint, **no** test-data factories.
- a11y CI gate (`@axe-core/playwright` e2e) + `accessibility` reviewer + `accessibility`
  battery **already ship**; only `eslint-plugin-jsx-a11y` static lint is absent.
- Graceful shutdown (SIGTERM engine-dispose) + health/readiness probes **already ship**.

---

## BATTERY (opt-in capability surfaces)

### money — Money value type (integer minor units + ISO-4217)
- **claim:** Store money as integer minor units (or Decimal) paired with an ISO-4217 currency; never float, never a bare amount.
- **retrofit_cost:** H — a float column has already lost precision irrecoverably; adding a currency dimension late is a backfill against ambiguous history.
- **pull:** M (Meridian is a platform; money is product-specific, not universal).
- **is_new:** true. **overlaps:** display/formatting is the i18n concern (storage-vs-display line); reviewer-half flags float on money-named columns lacking a currency.
- **sources:** data-model, breadth-industries.

### ledger — Double-entry append-only ledger for value movement
- **claim:** Balances derived from balanced double-entry postings in an append-only table; corrections are reversing postings, never edits — distinct from an audit log (value movement vs system events).
- **retrofit_cost:** H — foundational data model; mutable-balance designs destroy the events needed to reconstruct.
- **pull:** L (fintech-shaped; Meridian not stated to move money).
- **is_new:** true. **overlaps:** adjacent to audit-log battery (could share append-only machinery); requires the money primitive.
- **sources:** breadth-industries.

### outbound-idempotency — Client-facing idempotency keys for mutating endpoints
- **claim:** Your own mutating POST/PATCH endpoints must offer an Idempotency-Key contract + server-side key store so a client retry replays instead of re-executing. The OPPOSITE direction from the shipped webhook inbox.
- **retrofit_cost:** H — client-contract change (clients must send the key), touches every mutating endpoint, needs recovery-point atomic-phase decomposition, and duplicates already in prod can't be de-duped retroactively.
- **pull:** H (multi-product API with external/mobile callers).
- **is_new:** true. **overlaps:** reuses webhook-inbox dedup idiom but is outward-facing; reviewer-half flags unguarded mutating routes. Merged: distributed-systems + breadth-industries(money) + breadth-lifecycle.
- **sources:** distributed-systems, breadth-industries, breadth-lifecycle.

### transactional-outbox — Reliable outbound eventing (close the named dual-write gap)
- **claim:** Write the event to an outbox table in the SAME tx as the business write; a relay publishes after commit. The framework's own `handler.py.jinja` comment names this fix but doesn't ship it.
- **retrofit_cost:** H — silent unrecoverable event loss on commit-after-enqueue failure; consumer contracts harden around unreliable delivery. But the framework is one table + relay away (inbox, workers, broker, beat all ship).
- **pull:** H (multi-product event fan-out; underpins audit-log + outbound-comms).
- **is_new:** true. **overlaps:** extends webhooks+workers; symmetric partner to the inbox. Merged distributed-systems "outbox" + compare-backend "reliable eventing".
- **sources:** distributed-systems, compare-backend.

### field-encryption — Per-subject/per-tenant field encryption + crypto-shred (+ vault mode)
- **claim:** Encrypt sensitive fields under a per-subject (or per-tenant) DEK so erasure = destroy the key (crypto-shred), leaving ciphertext in backups/replicas computationally dead. Vault/tokenization is the heavyweight mode.
- **retrofit_cost:** H — sources unanimous it cannot be retrofitted; the retrofit IS re-encrypting the whole dataset over every backup/replica.
- **pull:** H (multitenant platform with PII; turns the reviewers' currently-unfixable "no erasure path" finding into a key delete).
- **is_new:** false. **overlaps:** secrets-backing concern (KMS/Vault) + multitenancy concern (per-tenant keys) + reviewer-enforced erasure obligation (data-lineage/privacy/compliance). Merged multitenancy "per-tenant keys" + privacy "per-subject field encryption" + privacy "PII vault" into ONE battery, three modes.
- **sources:** multitenancy, privacy-compliance-security.

### identity-principal — Multi-identity principal model (humans + machines + federated)
- **claim:** A principal abstraction with identities (credential bindings) as a separate table from day one, so a second auth method is a row not a migration, and account-merge surgery is avoided.
- **retrofit_cost:** H — `user_id` is referenced everywhere; widening the identity model later is a schema-wide FK migration + live account-merge surgery.
- **pull:** H (shared auth across multiple products IS the multi-identity-per-account problem).
- **is_new:** false. **overlaps:** identity half of composability/shapes/shared-auth (in flight).
- **sources:** identity-access.

### enterprise-sso-scim — Federated enterprise identity (SAML+OIDC, per-tenant IdP, JIT + SCIM)
- **claim:** SAML AND OIDC, per-tenant IdP config, JIT provisioning, AND SCIM lifecycle — the under-appreciated half is deprovisioning (JIT-only leaves zombie accounts).
- **retrofit_cost:** M — if the multi-identity principal + per-tenant scoping seams exist, this is adding a provider, not a re-architecture.
- **pull:** H (B2B multi-product platform; enterprise customers force it).
- **is_new:** false. **overlaps:** rides the principal model; same federated surface as shared-auth.
- **sources:** identity-access.

### api-keys — Machine principals as first-class actors
- **claim:** API keys/service accounts modeled as principals flowing through the same authorize() path — hashed at rest, scoped, rotatable via dual-credential window — not a parallel auth side-channel.
- **retrofit_cost:** M — added after a human-only model they become a second scattered-authz path; retrofitting hashing/rotation after live plaintext keys means customer-facing breakage.
- **pull:** H (AI agents + multi-product M2M traffic).
- **is_new:** false. **overlaps:** same decision point as the authz spine; key material rides secrets-backing. Depends on principal + authz seams.
- **sources:** identity-access.

### billing — Subscription billing: usage metering + entitlement gating
- **claim:** Stripe-synced subscriptions whose H-retrofit core is usage METERING (emit events from day one — no backfill) + ENTITLEMENT gating woven into routes.
- **retrofit_cost:** H — Stripe meters are immutable once created; no usage history backfill; entitlement checks weave through every gated route like authorization.
- **pull:** M (platform may monetize; not stated as core to Meridian).
- **is_new:** true. **overlaps:** subscription→tenant (multitenancy); billing events→audit-log; entitlement gate shares machinery with the authz spine; lifecycle webhook reuses the webhook inbox.
- **sources:** compare-backend.

### typed-frontend-data-layer — Generated OpenAPI→TS client + server-state cache (TanStack Query)
- **claim:** Replace hand-written `api.ts` + useEffect/useState fetch with a client GENERATED from the OpenAPI spec, wrapped in a query cache that owns fetch/cache/invalidation. The shipped `react` battery models the antipattern every builder copies.
- **retrofit_cost:** M — incremental per-component, no data migration, but the antipattern propagates to every feature and contract-drift ships in the meantime.
- **pull:** H (rich interactive multi-product UI).
- **is_new:** true (FE seam not on board). **overlaps:** quality upgrade to the shipped `react` battery; the generated client is the FE side of composability/shared-shapes; complements Pact (build-time type contract vs runtime behavior). Folds in the forms/shared-validation finding (derive from OpenAPI, not a second Zod copy).
- **sources:** frontend-architecture (x2), compare-frontend, compare-backend.

### published-sdk — Typed client SDK published FOR your consumers
- **claim:** A CI job that generates a typed client off the committed `openapi.json`, version-pins it to the API version, and publishes to a package feed on release — so consuming teams install instead of hand-rolling drifting clients.
- **retrofit_cost:** M — the fix lives in consumers' repos + a publish job; bounded, external, incremental.
- **pull:** M (depends how many teams consume Meridian's API).
- **is_new:** true. **overlaps:** DISTINCT from the internal FE client (inward) and from the `consumers`/Pact battery (outbound stubs for services THIS app calls). Consumes the spec the scaffold already exports; ties to api-versioning.
- **sources:** breadth-lifecycle.

### structured-content — Editor-agnostic versioned document schema
- **claim:** Rich text/docs need a canonical, versioned, editor-AGNOSTIC document schema (canonical JSON + schema_version, HTML as a cache, import/export round-trip) — the editor widget is swappable; the stored content schema is not.
- **retrofit_cost:** H — cost scales with accumulated user content (worst class); raw-HTML/proprietary-blob storage is unmigratable.
- **pull:** M (rich UI platform likely has rich-text surfaces).
- **is_new:** false. **overlaps:** belongs under the CMS + admin/CRUD UI battery's content model.
- **sources:** design-system-components.

### admin-crud-ui — Admin / internal-CRUD UI (the "free Django admin" FastAPI lacks)
- **claim:** A sqladmin/starlette-admin CRUD UI auto-derived from the models, behind auth, with the audit trail wired in (admin writes are a top insider-risk surface).
- **retrofit_cost:** L — additive over existing models; no data/history/legal multiplier. Pain is bespoke tooling built during the gap.
- **pull:** M.
- **is_new:** false. **overlaps:** the admin/CRUD half of the CMS + admin/CRUD UI battery; requires-audit-log coupling. Confirms the board item, pins honest cost at L-M.
- **sources:** product-growth-martech.

### data-grid — Headless interactive data-grid engine
- **claim:** A headless table ENGINE (TanStack Table + virtualization) styled with tokens, not a styled grid — one exemplar with keyboard nav + ARIA + virtualization as the prescribed pattern.
- **retrofit_cost:** M — replaceable screen-by-screen; bites through a11y (TanStack has no built-in keyboard nav) and design-language lock-in, not irreplaceable data.
- **pull:** H (Meridian-class data-heavy apps live on tables).
- **is_new:** true. **overlaps:** rides headless-primitive + tokens; complements admin/CRUD UI (CRUD lists ARE grids).
- **sources:** design-system-components.

### product-analytics — Server-side typed consent-gated event collection point
- **claim:** One server-side `track(event, props, *, consent)` seam; events as a closed typed registry (object-action naming + owner); capture-nothing-by-default allowlist; swappable sink (never the vendor SDK inlined); identity discipline to prevent login-stitch corruption.
- **retrofit_cost:** H — behavioral events can't be backfilled; identity-stitch / type divergence permanently poisons every prior cohort/funnel; ad blockers strip 25-40% client-side.
- **pull:** H (multi-product platform measuring behavior).
- **is_new:** false. **overlaps:** concretizes the product-analytics (consent-gated) concern; SPLIT — battery = collection seam, reviewer-enforced = per-diff taxonomy/consent conformance (review-privacy). Distinct from audit-log (compliance who-did-what).
- **sources:** product-growth-martech.

### marketing-capi — Consent-gated server-side attribution forwarder (CAPI)
- **claim:** A server-side CAPI forwarder (Meta/Google-shape) as the DEFAULT attribution path behind the swappable sink, gated on granular marketing consent — never an inlined browser pixel that fires before consent.
- **retrofit_cost:** H — driven up by active legal exposure during the retrofit (CNIL €135M etc.) + the "tear out twice" (consent + ITP/ad-blocker durability) problem.
- **pull:** M (depends on Meridian's marketing motion).
- **is_new:** false. **overlaps:** consent half of product-analytics concern + a new martech battery; SPLIT — battery (CAPI forwarder) + reviewer-enforced (consent-gate compliance, review-privacy). Outbound analogue of the inbound RUM UTM allowlist.
- **sources:** product-growth-martech.

### durable-agent-state — Durable/resumable agent run state (checkpointer + thread_id)
- **claim:** A runs/threads table; `run(thread_id=...)` persists the serialized thread after each tool turn; a RunStore protocol (in-memory + Postgres). Upstream of HITL, crash-recovery, run-history/audit, multi-turn — none exist without it. The current loop holds state in a discarded local list.
- **retrofit_cost:** H — durable state is a data-model + control-flow shape; retrofitting threads run_id through every call site, rewrites RunResult/routes, and permanently loses all historical runs.
- **pull:** H (AI agents are first-class for Meridian).
- **is_new:** false. **overlaps:** facet of the AI-agents battery surface; shares storage seam with the genai-trace schema; HITL (human-approval) folds in as a design constraint (you can't pause/resume what you didn't persist). Merged agent-harness "run state" + compare-agents "checkpointer".
- **sources:** agent-framework-harness, compare-agents.

### agent-tool-permission — Tool capability/scope model (+ mutating-tool idempotency)
- **claim:** Extend the tool registry with scope/capabilities, a `mutates` flag, and an idempotency hook; dispatch enforces scope against caller identity. Read-only-by-docstring leaves the dangerous (mutating) case structureless.
- **retrofit_cost:** H — scoping is a property of the registry INTERFACE; if it never carried capability/scope annotations, every tool assumed none. OWASP + Willison: the defense is architectural/design-time (lethal trifecta), not a later detection bolt-on.
- **pull:** H.
- **is_new:** false. **overlaps:** facet of AI-agents battery; SPLIT — capability INTERFACE is battery, "this tool mutates with no scope/idempotency key" is reviewer-enforced (agentic). ToolContext identity rides shared-auth. Merged agent-harness "capability model" + compare-agents "least-privilege".
- **sources:** agent-framework-harness, compare-agents.

### agent-eval — Prompt registry + eval harness for the BUILDER's agent
- **claim:** A prompts/ module with version-tagged artifacts (content hash on each run) + a tests/agent_evals/ harness (golden set, judge/assertion scorer, CI gate) mirroring the framework's OWN reviewer-eval infra — for the generated project's agent.
- **retrofit_cost:** M — a registry can wrap inline strings, but the golden DATASET is brutal: cheapest goldens are captured production traces (need durable-state + trace schema first), so deferring leaves no corpus and no version history.
- **pull:** H.
- **is_new:** true. **overlaps:** EXPLICITLY distinct from the queued "AI-eval for the builder's OWN [reviewer] agents" — this evals the GENERATED app's agent. Shares run-record write with durable-state + trace schema. Merged agent-harness "prompt registry+eval" + compare-agents "eval CI gate".
- **sources:** agent-framework-harness, compare-agents.

### agent-memory — Persistent first-class agent memory (memory blocks)
- **claim:** Memory as a DB-backed primitive with stable per-subject identity (editable blocks), not conversation history re-stuffed into the prompt. The agent is fully stateless today.
- **retrofit_cost:** H — data-shaped; you can't retroactively capture facts never persisted; a schema added on day 400 starts empty.
- **pull:** H (AI agents).
- **is_new:** false. **overlaps:** AI-retrieval (vector/RAG) board battery + pgvector battery (archival tier is vector-backed); distinct from durable-state (execution checkpoints) — keep separate.
- **sources:** compare-agents.

### human-approval — Human-in-the-loop approval interrupts for sensitive actions
- **claim:** Mark tools `requires_approval`; on hitting one, checkpoint + raise PendingApproval carrying the proposed call; `resume(run_id, approved=...)` continues or aborts.
- **retrofit_cost:** H — only implementable on a resumable loop (depends on durable-state); bolted on after a synchronous in-memory loop requires that whole re-architecture first.
- **pull:** H (mutating AI agents need a human gate).
- **is_new:** false. **overlaps:** folds INTO durable-state battery as the motivating case; same threat model as tool-permission from the runtime side. Merged compare-agents "human-approval" + agent-harness HITL note.
- **sources:** compare-agents, agent-framework-harness.

### agent-guardrails — Input/output guardrail interception hooks + tripwire
- **claim:** First-class hook points before the model runs (input) and before output egresses (output), with a tripwire that halts the run. The loop has zero interception points today.
- **retrofit_cost:** H — retrofitting interception into an in-memory loop with early returns is control-flow surgery; output guardrails are most valuable redacting before egress, impossible to insert non-invasively once responses flow straight through.
- **pull:** H.
- **is_new:** false. **overlaps:** facet of AI-agents battery; static half (tool least-privilege/injection) is the reviewer-enforced tool-permission row; input guardrails are also a spend lever (agent-cost).
- **sources:** compare-agents.

### data-backup-restore-drill — DATA backup + runnable restore DRILL (RPO/RTO)
- **claim:** A scaffolded backup+restore contract with declared RPO/RTO and — the load-bearing part — a runnable restore DRILL into a throwaway env that asserts success, so a silently-broken backup (GitLab's pg_dump version skew) is caught before it's needed.
- **retrofit_cost:** H — for the lost-data property the drill protects: every byte between launch and the first VERIFIED restore is lost if it falls in an untested window; 30-40% discover backup failures only at recovery.
- **pull:** H (every production platform).
- **is_new:** true. **overlaps:** DISTINCT from deploy contract + migration-aware rollback (already covered = CODE/schema recovery; `strategy.sh` says irreversible migrations can't be restored). This is DATA recovery. Adjacent to per-tenant restore (multitenancy).
- **sources:** breadth-nonfunctional.

### marketplace-provenance — Write-time payout/compliance provenance (KYC, tax ID, gross-vs-net)
- **claim:** Store gross + itemized fees (net derived) + effective-dated seller tax/identity at onboarding; per-payout line attribution. These are write-time facts a later feature can't reconstruct.
- **retrofit_cost:** H — purest irrecoverable-history seam; IRS requires gross + tax-ID-updated-in-reporting-year, no backfill.
- **pull:** L (marketplace/payout-shaped; niche for Meridian).
- **is_new:** true. **overlaps:** none direct; audit-log records system events not compliance provenance; pairs with a reviewer guard.
- **sources:** breadth-industries.

### telemetry-ingest-contract — Typed event-ingest contract (schema + retention + cardinality)
- **claim:** On top of the timescaledb battery: a Pydantic-typed ingest endpoint, a default retention + continuous-aggregate/downsampling policy, and a documented cardinality budget for tag columns.
- **retrofit_cost:** M — recoverable: you can introduce a contract going forward and downsample retroactively, but a live ad-hoc schema becomes a breaking change across consumers and high-cardinality tags can't be un-ingested.
- **pull:** L (IoT/data-platform-shaped).
- **is_new:** true. **overlaps:** extends the timescaledb battery (ships storage, no ingest discipline); data-level contract, distinct from Pact (API-level).
- **sources:** breadth-industries.

---

## CONCERN (first-class scaffolded posture / shape seams)

### external-id — Opaque non-sequential external ID on the base model
- **claim:** Every externally-referenced object needs a stable opaque external ID (UUIDv7/ULID) baked into the base model, kept architecturally separate from the authz check.
- **retrofit_cost:** H — an exposed bigserial is embedded in clients, deep links, webhooks, logs, FKs you don't control; changing it post-integration is a coordinated migration.
- **pull:** H (multi-product platform with external references). Verified: base `Item` has bare int PK, no external ID.
- **is_new:** true. **overlaps:** the IDOR class the ID does NOT cover (missing ownership/tenant scope) is the reviewer-half — adjacent to privacy reviewers + multitenancy. Do NOT collapse the two halves.
- **sources:** data-model.

### time-future-events — Future-event wall-clock+IANA storage + naive-datetime posture
- **claim:** The base `created_at` is already `timestamptz` (covered). The RESIDUAL seam: future/scheduled datetimes stored as wall-clock + IANA zone + tzdb version (NOT pre-converted UTC, since tz rules change), plus an app-code lint posture against naive `datetime.utcnow()`/`datetime.now()`.
- **retrofit_cost:** H — un-mangling already-stored naive local times is irrecoverable (DST-ambiguous); future-event pre-conversion silently drifts an hour.
- **pull:** M.
- **is_new:** false. **overlaps:** i18n/l10n concern (tz-aware display); reinforces the expand-only migration guard (naive→aware is the painful non-expand alter). Base column-type default ALREADY SHIPS — only the future-event sub-pattern + naive-datetime lint are residual. Merged data-model "time storage" + i18n "UTC-everywhere".
- **sources:** data-model, i18n-content.

### soft-delete-lifecycle — Base-model deletion/archive lifecycle (design choice)
- **claim:** Pick the base-model deletion lifecycle deliberately. Two sources CONFLICT: data-model recommends hard-delete-into-an-archive-table (avoid blanket `deleted_at` default-scope inertia); compare-backend recommends a `deleted_at` soft-delete mixin. PRIMARY = the archive-table design (avoids the implicit-WHERE correctness trap Brandur warns of); the policy/erasure side is reviewer-enforced.
- **retrofit_cost:** H (data-model framing) / M (mixin framing) — ripping out a default-scoped `deleted_at` after queries are littered with implicit filters is a correctness-critical refactor; a single missed filter exposes hidden records.
- **pull:** M.
- **is_new:** true. **overlaps:** audit-log/activity-trail battery (the archive table is a deletion trail); GDPR erasure/retention is reviewer-territory (data-lineage/privacy/compliance). Disposition TENSION noted — one primary, both fixes recorded.
- **sources:** data-model, compare-backend.

### api-versioning — Version namespace + breaking-change/compat posture from day 1
- **claim:** Mount routes under `/v1` (or a settings-driven segment); record `info.version`; document additive-only-within-a-version; extend the existing OpenAPI breaking-change CI diff to enforce within-version additivity. For external/event consumers, a Stripe-style backward-compat layer + an upcaster registry for stored events.
- **retrofit_cost:** H for external consumers (no namespace = nowhere to put /v2; cost scales linearly with integrations); M if internal-only/atomic-deploy.
- **pull:** H (multi-product API). Verified: bare `include_routers(app)`, no prefix.
- **is_new:** true (the board text doesn't list versioning; one finding asserts it's user-emphasized — flagged as uncertainty for the controller's authoritative check). **overlaps:** complements Pact (verifies a contract) + the OpenAPI diff (detects a break) — versioning provides the NAMESPACE to make one safely; the API/event shape layer, distinct from the DB expand-only guard. Merged data-model "schema/API/event versioning" + distributed-systems "REST /v1" + breadth-lifecycle "namespace".
- **sources:** data-model, distributed-systems, breadth-lifecycle.

### authz-spine — Default-deny authorization decision point (RBAC→ReBAC, data-layer scoping)
- **claim:** A single default-deny `authorize(principal, action, resource)` chokepoint that scopes at the data-access layer (not scattered per-endpoint conditionals), pluggable from in-code RBAC to a policy engine, with a route convention enforced by a test. THE separate third leg of access control — distinct from authentication (who) and tenancy (whose row).
- **retrofit_cost:** H — cost scales with endpoints/queries written; retrofitting is a line-by-line data-layer audit with no tooling proving completeness; a miss is a breach (OWASP A01 #1). No authz layer ships today (verified).
- **pull:** H.
- **is_new:** false. **overlaps:** enforcement half of composability/shapes/shared-auth (in flight); shares data-layer scoping with multitenancy; RBAC→ReBAC growth is M IF this seam exists. Defend against collapse into shared-auth (that's authentication) or multitenancy (that's isolation). Merged identity-access "enforcement seam" + "RBAC→ReBAC" + compare-backend "policy layer".
- **sources:** identity-access (x2), compare-backend.

### session-revocation — Revocable session/token architecture (opaque-vs-JWT fork)
- **claim:** Short-lived access tokens + a server-side revocable refresh/session record (hybrid), so logout/compromise/role-change actually revokes — not pure long-lived stateless JWTs valid until expiry; centralized issuance/validation as a config seam.
- **retrofit_cost:** M — touches the auth hot path + every client; retrofitting revocation onto long-lived JWTs means a refresh store, shorter TTLs, a request-path revocation check, and a coordinated client migration.
- **pull:** H (enterprise security review forces it).
- **is_new:** false. **overlaps:** sessions hang off the principal model; signing keys come from secrets-backing.
- **sources:** identity-access.

### tenant-data-model — `tenant_id` on every owned table + composite keys + tenant-scoped uniqueness
- **claim:** A TenantScoped mixin (tenant_id NOT NULL, indexed, FK, leading PK column) making the demo model tenant-scoped by construction; a documented tenant-scope migration plugging into the expand-only contract.
- **retrofit_cost:** H — full-table backfill + PK/UNIQUE/FK cascade + query rewrite; tenant-scoped uniqueness can require cleansing real colliding data. The decision every later isolation move keys off.
- **pull:** H (Meridian IS multitenant). Verified: no `tenant_id` ships.
- **is_new:** false. **overlaps:** data-model core of the multitenancy (logical→physical) concern; precondition for the other tenancy facets.
- **sources:** multitenancy.

### tenant-context-propagation — Auth→request→DB-session tenant context (no client-trusted tenant ID)
- **claim:** A request-scoped tenant contextvar set by middleware from the authenticated principal; a session dependency injecting the tenant filter + `SET app.current_tenant`; a first-class cross-tenant negative test; fail-closed when no context.
- **retrofit_cost:** M (young) → H (once wide) — the middleware is small but only works if every query routes through the scoped session; the failure is silent cross-tenant leakage with no runtime error.
- **pull:** H.
- **is_new:** false. **overlaps:** the propagation facet of multitenancy; rides shared-auth principal; "did this new query scope by tenant?" is a reviewer complement (existing authz/privacy reviewers). Locale rides the same middleware (i18n).
- **sources:** multitenancy.

### tenant-rls — Postgres Row-Level Security as DB-layer defense-in-depth
- **claim:** RLS-enabled DDL alongside the TenantScoped mixin (policy + FORCE RLS + a non-owner app role); `SET LOCAL app.current_tenant` inside the tx (pooling-safe); pool-mode configured so the session-variable approach is correct by default.
- **retrofit_cost:** M — lower if the data-model + context seams exist; inherits their cost if tenant_id is dirty; the pgBouncer transaction-pooling-vs-session-variable trap silently leaks under load.
- **pull:** H.
- **is_new:** false. **overlaps:** multitenancy concern; depends on tenant-data-model + context; interacts with worker/Celery pooling.
- **sources:** multitenancy.

### tenant-physical-routing — logical→physical isolation routing seam
- **claim:** A `resolve_tenant_dsn(tenant_id)` indirection that today returns the single shared DSN but is the ONE place the mapping lives — so schema-per-tenant / db-per-tenant later is a resolver change, not a re-architecture. The literal board ask.
- **retrofit_cost:** H — without the seam every connection-acquire assumes the shared store; retrofitting per-tenant routing touches session factory, migrations (N-per-tenant), backups, obs cardinality, onboarding simultaneously (quantified 6-12mo / 5-8x infra after 500 customers).
- **pull:** H (enterprise customers demand dedicated isolation contractually).
- **is_new:** false. **overlaps:** the core promotion mechanism of the multitenancy (logical→physical) concern; extends datastore-parity (FWK6) to per-tenant endpoints; distribution column = the same tenant_id.
- **sources:** multitenancy.

### tenant-fairness — Noisy-neighbor isolation (per-tenant quotas/timeouts/caps)
- **claim:** Make the existing rate-limiter tenant-keyed; a tiered per-tenant `statement_timeout`; per-tenant labels on existing Prometheus metrics; a documented per-tenant connection cap.
- **retrofit_cost:** M — the primitives (rate-limit, statement_timeout, pooler caps) + obs already ship; the retrofit cost is the per-tenant DIMENSION threading through the tenant key.
- **pull:** M.
- **is_new:** false. **overlaps:** mostly already-covered (rate-limiting + obs); the gap is the per-tenant key/dimension; depends on tenant-context.
- **sources:** multitenancy.

### data-residency — Region atom + `resolve_region(subject)` indirection
- **claim:** ONE cheap early indirection: a `region` column on the residency atom + a resolver pinned to the home region, so no code assumes "the database" — it asks for "this atom's database." Park the full multi-region data plane.
- **retrofit_cost:** H (the full build) — single-region bakes in synchronous-local-reads + shared-DB + global-access assumptions "fundamentally incompatible" with region boundaries; but the cheap region-indirection seam is the lever.
- **pull:** M (multi-product B2B; residency is a contractual ask at enterprise scale).
- **is_new:** false. **overlaps:** the residency atom is usually the tenant — bound to the multitenancy concern; the full multi-region plane = the board's PARK item; scaffold only the no-op indirection now.
- **sources:** privacy-compliance-security.

### consent-records — Consent / lawful-basis record substrate
- **claim:** A lean `consents` model (subject, purpose, lawful_basis, method, timestamp, evidence, policy_version) + a `has_consent(subject, purpose)` gate, so the evidence trail + purpose tag exist from day one.
- **retrofit_cost:** M — the table is easy; non-backfillable parts are lawful-basis/policy-version for pre-consent data + threading `purpose` through collection paths; split-brain across tools is the failure mode.
- **pull:** H (the enforcement substrate the consent-gated product-analytics presupposes).
- **is_new:** false. **overlaps:** under product-analytics (consent-gated) + the marketing-capi consent gate; over-collection/retention judgment stays review-privacy's lane.
- **sources:** privacy-compliance-security.

### secrets-rotation — Secrets externalization + key rotation/versioning dimension
- **claim:** Extend secrets-backing with ROTATION/VERSIONING: secrets fetched from an external store at runtime, never env-baked for KEKs; every DEK/secret the encryption seams mint is `key_id`-versioned so rotation never implies a global re-encrypt; a `rotate_keys` command + a guard against env-only KEKs.
- **retrofit_cost:** M — externalization is mechanical (L); versioned-keys-with-rotation is the hard part (if DEKs weren't key_id-tagged, rotation forces a re-encrypt).
- **pull:** H (the key-management layer field-encryption + per-tenant keys consume).
- **is_new:** false. **overlaps:** the rotation dimension of the secrets-backing concern; gitleaks/dependabot cover the leak-detection half (covered); leaked-value calls stay review-security.
- **sources:** privacy-compliance-security.

### healthcare-access-control — Consent/purpose-of-use/break-glass + per-read access log
- **claim:** An ABAC-style `authorize(subject, action, resource, purpose, context)` chokepoint all sensitive reads route through; effective-dated consent; a break-glass path elevating with a mandatory reason + high-severity log; an append-only per-read access log.
- **retrofit_cost:** H — HIPAA 164.312(b) requires per-read logging (6yr retention); if reads weren't logged the history never existed; consent/purpose/break-glass woven into scattered reads is a whole-app refactor.
- **pull:** L (regulated-data/healthcare-shaped; niche for Meridian).
- **is_new:** false. **overlaps:** rides audit-log (PHI read logging) + shared-auth; the consent/purpose/break-glass shape itself could be a regulated-data battery; distinct axis from multitenancy.
- **sources:** breadth-industries.

### i18n-string-externalization — String catalog + ICU message format (the keystone i18n seam)
- **claim:** Every user-visible string behind a `t(key, params)` ICU-shaped catalog call (CLDR plurals, gender/select, translator-controlled word order) — never inline concatenation. The single seam everything else depends on.
- **retrofit_cost:** H — O(strings × templates) non-mechanizable rewrites (word order is language-specific); Slack wrapped ~20k strings org-wide; concatenation produces silently-wrong grammar with no error thrown.
- **pull:** H (multi-product platform; the keystone of the i18n/l10n concern).
- **is_new:** false. **overlaps:** core seam of the i18n/l10n concern; the battery installs the catalog/format surface; pairs with the i18n reviewer; CMS + outbound-comms strings need the same `t()`.
- **sources:** i18n-content.

### i18n-locale-formatting — Locale-aware CLDR number/date/currency formatting
- **claim:** Numbers/dates/currency formatted through a Babel/CLDR locale formatter at the display boundary, taking request locale — never hardcoded separators or `'$%.2f'`.
- **retrofit_cost:** M — the same call-site sweep as string externalization, mechanical once a formatter exists; H only if money was stored as floats (re-modeling).
- **pull:** H.
- **is_new:** false. **overlaps:** i18n/l10n concern; the money/minor-units half is the money battery + reviewer-enforced; CMS + outbound-comms emit formatted values.
- **sources:** i18n-content.

### i18n-locale-resolution — Request-scoped locale context + URL i18n structure
- **claim:** A middleware resolving locale once per request (URL/path-prefix → cookie/user → Accept-Language → default) into a contextvar that `t()` + formatters read by default; a documented URL i18n posture decided before content is indexed.
- **retrofit_cost:** M — locale-plumbing is the same sweep as string externalization; URL-structure is H for an indexed content site but the framework is API/backend-first.
- **pull:** M.
- **is_new:** false. **overlaps:** the request-resolution seam of i18n/l10n; locale is a request-scoped ambient alongside the auth principal (composability/shared request-context) + the tenant (same middleware).
- **sources:** i18n-content.

### i18n-encoding — Explicit UTF-8 end-to-end (emoji/BMP-safe)
- **claim:** Pin `client_encoding=UTF8` + explicit createdb UTF-8 in scaffold config; document the MySQL `utf8mb4 not utf8` gotcha; an emoji round-trip test on the sample model.
- **retrofit_cost:** L on Postgres (the default; largely handled) — the residual is the cheap explicit-create + round-trip test so a future MySQL swap doesn't inherit the silent 3-byte-utf8 truncation trap (H on MySQL).
- **pull:** L.
- **is_new:** false. **overlaps:** i18n/l10n; reinforces the expand-only migration posture (charset change is the painful non-expand alter).
- **sources:** i18n-content.

### frontend-design-tokens — Semantic CSS-variable token layer
- **claim:** A thin semantic-token layer (`--background`, `--foreground`, `--primary` = role not value) with light+dark sets resolved before first paint, worked components referencing tokens only. Dark-mode is the forcing function that exposes the missing layer. The template ships zero CSS.
- **retrofit_cost:** H — cost scales with component count (239-component / 3.5-sprint migration class); trivial if the indirection exists before the first styled component.
- **pull:** H (rich interactive multi-product UI; theming/re-brand across products).
- **is_new:** true (no FE design-system item on board). **overlaps:** rides the headless primitive; RTL/locale theming touches i18n. Merged design-system "tokens" + compare-frontend "tokens".
- **sources:** design-system-components, compare-frontend.

### frontend-headless-primitive — Headless interaction/a11y primitive layer
- **claim:** The most upstream FE decision: render components on a maintained headless library (React Aria / Base UI) that owns keyboard/focus/ARIA/RTL while you own styling — not bare hand-rolled `<div onClick>` (verified: App.tsx is bare semantic HTML). Pick a maintained default deliberately (Radix slowed post-WorkOS).
- **retrofit_cost:** H — swapping the primitive layer after real screens means re-implementing every interactive component's behavior (70+-export multi-quarter class).
- **pull:** H.
- **is_new:** true. **overlaps:** keystone that tokens + a11y both depend on; rides the `react` battery.
- **sources:** design-system-components.

### frontend-rendering-strategy — Explicit SPA boundary with an SSR escape hatch
- **claim:** Make rendering a recorded choice at `framework new`: keep static-SPA default for behind-auth app shells (correct here) but document the boundary + offer an SSR-capable variant / static-prerender carve-out, so a later SEO/first-paint surface isn't a re-architecture.
- **retrofit_cost:** M for THIS framework (API/dashboard-shaped; SPA usually stays correct) — H in general (CSR→SSR/RSC is a deploy-runtime change + app-wide rewrite; "wasted a lot of company money," "almost a year").
- **pull:** M.
- **is_new:** true. **overlaps:** touches the deploy contract + compose isolation (SSR variant adds a service); distinct from the CSR-only `react` battery; adjacent to CDN/static-assets battery. Merged frontend-arch "rendering" + compare-frontend "posture".
- **sources:** frontend-architecture, compare-frontend.

### frontend-perf-budget — Bundle-size / CWV budget as a CI ratchet
- **claim:** A size-limit/bundlesize gzipped-JS ceiling (+ optional Lighthouse-CI budget.json) that FAILS the build on regression, pre-wired so the budget exists from commit #1 and the team ratchets DOWN.
- **retrofit_cost:** H on the retrofit axis (clawing back a 2 MB bundle post-launch is a multi-sprint excavation) — but L to scaffold; the asymmetry is the finding. (compare-frontend rates the gate-add itself L; the consolidated cost is the post-launch excavation it prevents.)
- **pull:** M (rich UI; grows with feature count).
- **is_new:** true. **overlaps:** DISTINCT from k6 (server load/latency) — this is client bundle/render budget per-PR; same enforcement philosophy as the coverage/ruff/mypy gates. Merged frontend-arch "bundle budget" + compare-frontend "Lighthouse".
- **sources:** frontend-architecture, compare-frontend.

### frontend-auth-storage — Token-storage posture on the FE seam
- **claim:** When auth lands, ship the secure default as the example: access token in memory + refresh token in HttpOnly+Secure+SameSite cookie + silent-refresh-on-load + a client interceptor handling 401→refresh — never localStorage JWTs.
- **retrofit_cost:** M — token storage is woven through every authed request + refresh + logout + CSRF; moving off localStorage later is a security-critical re-plumb done under XSS pressure.
- **pull:** H (rich interactive UI on a multi-product platform).
- **is_new:** false. **overlaps:** the FE-specific token-storage posture WITHIN composability/shapes/shared-auth (in flight); reviewer complement flags localStorage token writes + missing SameSite/CSRF.
- **sources:** compare-frontend.

### read-write-split — Read/write session separability + replication-lag posture
- **claim:** A `read_session`/`write_session` distinction in db/ (replica defaulting to primary) so adding a replica is a config change, with a documented read-your-writes note — not a monolithic data layer.
- **retrofit_cost:** M — a replica is operationally easy; the cost is paid only if the data layer is monolithic when scale forces one (hunting which reads are replica-safe; subtle stale-read bugs).
- **pull:** L (low immediate pull; many products never split).
- **is_new:** true. **overlaps:** rides the composability work (session providers are a shape seam) + multitenancy (routable data layer); upgrades from park to a trivial concern IF composability makes the provider free. Parked-ish, surfaced as a concern rider.
- **sources:** distributed-systems.

### cursor-pagination — Opaque cursor/keyset envelope on list responses
- **claim:** Return an opaque `next_cursor` (base64 of last-sort-value+id) from day one so the offset→keyset swap is server-internal; keep offset as a deprecated admin fallback. Verified: offset + MAX_PAGE_SIZE ships.
- **retrofit_cost:** M — already bounded (no unbounded-scan emergency); the delta is the cursor CONTRACT (a response-shape change forcing client migration) + the keyset query; deep-offset cost + page-drift correctness bite at scale.
- **pull:** M (data-heavy platform; bites at scale).
- **is_new:** true. **overlaps:** adjacent to the api-design reviewer's "unbounded list" + the existing MAX_PAGE_SIZE bound, but those are about UNBOUNDEDNESS; this is cursor CORRECTNESS (drift) + deep-offset SCALE.
- **sources:** distributed-systems.

### data-backfill-jobs — Resumable long-running data-migration jobs (beyond the schema)
- **claim:** A backfill base (PK-range batching, configurable chunk + inter-batch sleep, persisted progress for resumability, reentrant per batch, OTel spans) + an example following nullable→backfill→NOT NULL so it composes with the expand-only guard.
- **retrofit_cost:** H — you need the safe-backfill pattern the moment you have a large table (most rows, least slack), and there's no second chance to do the first backfill gently; a naive UPDATE locks the table, a non-resumable script dies at row 2M.
- **pull:** M (any non-trivial table eventually backfills).
- **is_new:** true. **overlaps:** distinct from the DB migrations + expand-only guard (governs schema DDL); this is the DATA step expand/contract depends on but doesn't provide.
- **sources:** breadth-lifecycle.

### genai-trace-schema — GenAI span/record schema at the agent call sites
- **claim:** Wrap the loop in an OTel `invoke_agent` span with `execute_tool`/`chat` child spans carrying `gen_ai.*` attributes (tool call id/args/result, conversation id, token/cost), parented under a run span; persist a per-run record. The battery emits only flat counters today.
- **retrofit_cost:** H — irreversible data loss: a year of runs recorded only as counters can't be reconstructed into traces or an eval dataset; conforming at the seam now is near-free.
- **pull:** H (AI agents).
- **is_new:** false. **overlaps:** explicitly NOT the already-covered observability stack (the stack carries it; the SPAN INSTRUMENTATION is the gap) — a gap INSIDE covered observability; shares the runs-table write with durable-state; the golden-dataset source for agent-eval. Merged agent-harness "trace schema" + compare-agents "OTel GenAI spans".
- **sources:** agent-framework-harness, compare-agents.

### agent-cost-budget — Pre-call budget gate at the LLM-call seam
- **claim:** A BudgetGuard checked in `LLMService._call` BEFORE completion: per-run + per-tenant ceilings raising BudgetExceeded; cost is already computed, this decrements a ledger and gates. The only ceiling today is `max_iterations` (turns, not dollars).
- **retrofit_cost:** M — the framework centralizes calls in LLMService (one gate point), lowering cost; M not L because per-tenant attribution couples to multitenancy and a late ledger means backfilling attribution.
- **pull:** H (AI agents + multitenant; a runaway/injected loop is unbounded spend).
- **is_new:** false. **overlaps:** facet of AI-agents; distinct from HTTP rate-limiting (requests/time vs cost/time + per-subject spend); per-tenant attribution rides multitenancy; input guardrails are also a spend lever. Merged agent-harness "cost enforcement" + compare-agents "budget gate".
- **sources:** agent-framework-harness, compare-agents.

### license-policy-gate — Dependency license-policy CI gate (copyleft)
- **claim:** A CI gate resolving every dep to its SPDX license, failing the build on a denied class (GPL-*/AGPL-*/SSPL) with an override list — protecting which legal obligations the codebase incurs. The dependency reviewer explicitly does NOT do license.
- **retrofit_cost:** H — the gate is M to add but prevents an UNRECOVERABLE cost: by M&A discovery, years of proprietary code depend on the copyleft dep ($10M write-down case); the obligation is already incurred.
- **pull:** M (any commercial multi-product codebase).
- **is_new:** true. **overlaps:** different axis from supply-chain (gitleaks/dependabot = secrets+CVEs, not license class); adjacent to the dependency advisory reviewer.
- **sources:** breadth-nonfunctional.

### sbom-provenance — SBOM + build provenance + artifact signing
- **claim:** Emit a CycloneDX/SPDX SBOM at build time, attach SLSA provenance, cosign-sign the image keylessly via GHA OIDC, publish the SBOM per release — wired into the pipeline the framework already owns.
- **retrofit_cost:** M — build-pipeline config addable anytime; the pull is a regulatory DEADLINE (EU CRA reporting Sept 2026 / full Dec 2027, €15M penalties), not irrecoverability; a narrow provenance-fidelity tail on old releases.
- **pull:** M.
- **is_new:** true. **overlaps:** extends supply-chain (gitleaks=secrets, dependabot=CVE-bumps, this=SBOM/provenance/signing — name the distinction on the board).
- **sources:** breadth-nonfunctional.

### test-factories — Test-data factories (vs the static dev seed)
- **claim:** A tests/factories/ module: a Faker-backed, association-aware factory for the example model (deterministic seed, "build minimal data per test"), used by the example tests so the suite grows the right shape from test #1; keep the static seed.py separate.
- **retrofit_cost:** M — brittleness accumulates (ad-hoc inline setup / sprawling shared fixtures), but conversion is incremental and local with no production data at stake; value is setting the convention before the suite grows wrong.
- **pull:** M (large platform test suite).
- **is_new:** true. **overlaps:** adjacent to db/seed.py (dev/demo data) but distinct (minimal deterministic per-test construction); the one seam-shaped slice of the testing-strategy mandate (Pact + k6 covered; property-based parked).
- **sources:** breadth-lifecycle.

---

## REVIEWER-ENFORCED (per-PR judgment, not a scaffold)

### i18n-reviewer — Hardcoded-string / i18n-antipattern rot-guard
- **claim:** An agentic reviewer flagging inline user-facing string literals not behind `t()`, sentence concatenation, hardcoded format strings + float money, naive datetimes, physical-direction CSS — prompt-scoped to genuine user-facing contexts so it doesn't over-fire on backend-only paths.
- **retrofit_cost:** H (the cost it PREVENTS — the i18n seam decays linearly with features unless enforced per-PR; Shopify ran linters against every file).
- **pull:** H (the enforcement arm of the i18n/l10n concern).
- **is_new:** false. **overlaps:** the reviewer/enforcement arm of i18n/l10n; delivered via the existing reviewer system; keep advisory where appropriate.
- **sources:** i18n-content.

### frontend-direction-rtl — Direction-agnostic layout (logical CSS, dir, text-expansion)
- **claim:** Scaffolded UI defaults to logical CSS properties + a dir-driven `<html>`, no fixed-width text containers, a pseudo-localization dev locale; document icon-mirroring rules. Leaning reviewer (framework is backend-first) — where it renders UI, catch the physical-CSS/fixed-width antipattern.
- **retrofit_cost:** M — high effort (full stylesheet sweep + icon audit) but contained to presentation and partly codemod-able; moderate exposure given the thin FE story.
- **pull:** M.
- **is_new:** false. **overlaps:** the CMS + admin/CRUD UI battery should ship direction-agnostic defaults (secondary battery facet); i18n/l10n concern.
- **sources:** i18n-content.

### tenant-offboarding — Tenant export / portability / delete-one-tenant obligation
- **claim:** A `tenant_export`/`tenant_delete` skeleton driven off the TenantScoped registry (so new scoped tables are included automatically) + a "every store holding tenant data registers here" manifest. The heart is the OBLIGATION — does this diff's new table/store get wired into export + erasure? — a per-diff data-lineage question.
- **retrofit_cost:** M — mechanical if tenant_id holds; the cost is the COMPLETENESS obligation across non-DB stores + keeping it current (degrading toward H as untracked blobs/search/analytics accumulate).
- **pull:** H (multitenant platform; GDPR Art. 17/20 + offboarding).
- **is_new:** false. **overlaps:** the board's GDPR-erasure→data-lineage exemplar (obligation is reviewer-enforced, NOT a battery); audit-log (offboarding events); crypto-shred (field-encryption) is the cleanest delete primitive. A light concern-level skeleton gives it a home.
- **sources:** multitenancy.

### data-export-portability — Machine-readable data export (GDPR Art. 20)
- **claim:** A `GET /me/export` (+ tenant variant) serializing owned rows to labeled JSON via existing Pydantic schemas + a registry of exportable models the builder extends per table — turning future archaeology into one-line registration.
- **retrofit_cost:** M — recoverable (build the pipeline later against whatever exists); friction is store-enumeration archaeology + format constraints, not irrecoverable loss.
- **pull:** M.
- **is_new:** true. **overlaps:** heavy overlap with the data-lineage erasure-gap reviewer (same "find every store" problem — extend it to assert export/erasure symmetry); tenant-level variant rides multitenancy; thin battery option exists but leans reviewer-enforced.
- **sources:** breadth-nonfunctional.

### soft-delete-erasure-policy — Deletion/retention policy + erasure tension
- **claim:** A reviewer (compliance/privacy/data-lineage) flagging new models/DELETE paths that neither soft-delete nor justify a hard-delete, and catching soft-delete↔right-to-erasure conflicts. The scaffold owns only the base lifecycle convention; the policy is per-feature judgment.
- **retrofit_cost:** M (the policy enforcement; the base convention is the soft-delete-lifecycle concern row).
- **pull:** M.
- **is_new:** false. **overlaps:** routes to existing compliance/privacy/data-lineage reviewers; adjacent to audit-log (deletion is an audited event); the policy half of the soft-delete-lifecycle seam.
- **sources:** compare-backend.

### rum-trace-correlation — RUM→backend trace-context propagation
- **claim:** Inject W3C `traceparent` on the FE's outbound fetches (via the generated-client interceptor) and/or attach the RUM session/trace id to the `/internal/rum` beacon, so web-vitals and backend spans share a correlation id in the existing Tempo/Loki stack. The RUM plumbing exists; trace propagation doesn't.
- **retrofit_cost:** L — the beacon/RUM plumbing exists; adding trace-context on fetch is contained + additive; value is catching it early so traces are correlatable.
- **pull:** M.
- **is_new:** false. **overlaps:** a gap INSIDE the already-covered full observability stack — not a new battery; reviewer flags FE fetches that don't propagate trace context.
- **sources:** compare-frontend.

### frontend-a11y-static-lint — eslint-plugin-jsx-a11y static gate (residual)
- **claim:** Add `eslint-plugin-jsx-a11y` (recommended ruleset) to the rendered eslint config + ensure the existing axe e2e is an enforced gate assertion. The static lint catches author-time issues the single rendered-path axe check cannot.
- **retrofit_cost:** L — tool install is trivial; the H accumulated-debt story is ALREADY mostly prevented by the shipped axe gate + `accessibility` reviewer + battery.
- **pull:** M.
- **is_new:** false. **overlaps:** MOSTLY ALREADY COVERED (verified: `@axe-core/playwright` e2e + `accessibility` reviewer + `accessibility` battery ship). The design-system finding's "register a NET-NEW frontend-a11y reviewer" is WRONG — only `eslint-plugin-jsx-a11y` static lint is genuinely absent. Down-ranked to a thin residual. Merged design-system "a11y" + compare-frontend "jsx-a11y" + breadth-nonfunctional "already covered".
- **sources:** design-system-components, compare-frontend, breadth-nonfunctional.

### agent-tool-safety-reviewer — Agent tool least-privilege + injection-aware gating
- **claim:** An agentic reviewer (firing when agents/llm present) flagging new mutating/broad-scope tools without authorization scoping, and untrusted tool-output/retrieved-content flowing into a privileged prompt without isolation; recommends per-tool least-privilege + human-approval for high-risk actions.
- **retrofit_cost:** M (registering/tuning the reviewer is cheap; the consequence of catching it late is H).
- **pull:** H (AI agents).
- **is_new:** false. **overlaps:** the static half of agent safety paired with the agent-tool-permission battery (interface) + agent-guardrails (runtime) + human-approval; extend the existing privacy/security reviewers (don't reinvent).
- **sources:** compare-agents.

---

## PARK (high retrofit cost but low immediate pull, or covered/conscious-defer)

### realtime-sync — Conflict-resolved collaborative/offline sync (CRDT/version vectors)
- **claim:** Per-entity version/sequence + optimistic-concurrency writes + presence separate from persisted state + a documented CRDT upgrade path — for genuinely collaborative/offline products. The websockets battery is transport-only.
- **retrofit_cost:** H when truly needed (a data-layer inversion / collaboration-layer rewrite) — M for merely live-updating reads (server-authoritative suffices).
- **pull:** L (server-authoritative FastAPI is the right default; only the minority need it; Meridian not stated as collaborative co-editing).
- **is_new:** true. **overlaps:** the websockets battery ships no conflict/version/presence semantics above the transport; optimistic-UI rides the server-state query seam for free; tangentially the composability theme. Promote to an opt-in battery only if a consumer needs it. Merged frontend-arch "local-first" + breadth-industries "sync above WebSocket".
- **sources:** frontend-architecture, breadth-industries.

### enum-lookup-table — Lookup-table over native DB enum (thin)
- **claim:** A documented "lookup-table over native enum for growing value sets" convention; native enums can't safely remove values + carry no labels/metadata.
- **retrofit_cost:** M — enum→lookup-table later is "doable but unpleasant on a hot table"; the painful NOT-NULL/backfill half is already covered by the migration guard.
- **pull:** L.
- **is_new:** true. **overlaps:** the NOT-NULL/expand-contract half is ALREADY COVERED (DB migrations + expand-only guard); only the lookup-vs-native convention is distinct and thin; optional reviewer flag for native-enum columns named status/type/kind.
- **sources:** data-model.

### structured-output-repair — Bounded validate-retry on structured output (+ HITL note)
- **claim:** A bounded repair loop inside `complete_structured()` (re-prompt with the ValidationError, cap ~2 retries, count repairs).
- **retrofit_cost:** L — localized to a single method, no data-model lock-in, wrappable anytime.
- **pull:** M.
- **is_new:** false. **overlaps:** facet of AI-agents; HITL is rolled into durable-state; adjacent to Pact (different contract surface — model output).
- **sources:** agent-framework-harness.

### frontend-routing — Data-router seam
- **claim:** A minimal data-router (TanStack Router / React Router data APIs) with one example route loading via the server-state cache + generated client.
- **retrofit_cost:** M — mostly downstream of the rendering choice; rises to M when route-level data-loading/code-splitting/auth-guards are hand-scattered.
- **pull:** L.
- **is_new:** false. **overlaps:** subordinate to frontend-rendering-strategy; fold into whichever rendering variant ships.
- **sources:** frontend-architecture.

### micro-frontends — Module federation / build streams
- **claim:** Module federation is the FE face of composability + parallel build streams; the single-SPA scaffold lacks the multi-team shell that justifies it.
- **retrofit_cost:** M — real work but low pull for a single-service scaffold (no shell to federate).
- **pull:** L.
- **is_new:** false. **overlaps:** the FE instance of composability/shapes/shared-auth (in flight); address there if a multi-team shell materializes.
- **sources:** frontend-architecture.

### storybook-vrt — Component isolation + visual-regression
- **claim:** Storybook + Chromatic/Playwright snapshots; a LATE, CHEAP add whose adoption cost stays flat.
- **retrofit_cost:** L — cost doesn't scale with accumulated components; not a corner you paint yourself into.
- **pull:** L.
- **is_new:** true. **overlaps:** none on board; optional light-battery upside.
- **sources:** design-system-components.

### finops-cost-attribution — Per-feature/per-tenant cost attribution
- **claim:** A cost/usage label convention on the OTel surface + a budget-alert stub — better folded into the AI-battery + multitenancy work than scaffolded standalone.
- **retrofit_cost:** M — small irrecoverable edge (un-tagged historical spend) but low pull for a fresh scaffold; high-value slices live elsewhere.
- **pull:** L.
- **is_new:** false. **overlaps:** per-tenant cost→multitenancy; LLM/vector cost→AI batteries; no standalone seam after those.
- **sources:** breadth-nonfunctional.

### agent-conscious-parks — MCP / provider fallbacks / prompt versioning / multi-agent orchestration
- **claim:** Four capabilities first-class elsewhere but low/medium-retrofit or out-of-scope for a single-service scaffold: MCP tool protocol (ToolRegistry is already a clean adapter seam), LiteLLM Router fallbacks (config swap), Langfuse prompt versioning (profiles already externalize config), CrewAI/AutoGen multi-agent orchestration (out of scope).
- **retrofit_cost:** L (each is config/adapter, not surgery; multi-agent is out of scope by design).
- **pull:** L.
- **is_new:** false. **overlaps:** MCP→ToolRegistry; fallbacks→LLMService/LiteLLM; prompt-versioning→profiles config; multi-agent→no board item (out of scope for a single-service scaffold).
- **sources:** compare-agents.

### capacity-scaling-covered — Connection-pool/N+1/unbounded-scan + load testing
- **claim:** Already owned — pool exhaustion/N+1/unbounded scan are the `performance` reviewer's verbatim domain; load/capacity is k6.
- **retrofit_cost:** L (re-treading covered ground; effectively reject — park since the schema has no reject).
- **pull:** L.
- **is_new:** false. **overlaps:** fully covered by the `performance` reviewer + k6.
- **sources:** breadth-nonfunctional.

### operability-covered — Graceful shutdown / health probes / runbook stubs
- **claim:** The operability CORE ships (verified: SIGTERM engine-dispose + graceful-shutdown test + health/readiness routes + compose healthchecks); only soft RUNBOOK.md / postmortem-template stubs remain.
- **retrofit_cost:** L (the H half ships; runbook markdown is a one-line docs add).
- **pull:** L.
- **is_new:** false. **overlaps:** graceful-shutdown/health ALREADY SHIPPED; remaining stubs overlap nothing of substance.
- **sources:** breadth-nonfunctional.

### accessibility-by-construction-covered — a11y CI gate + reviewer + battery
- **claim:** The high-retrofit a11y seam (a CI gate failing the build on violations) ALREADY SHIPS (`@axe-core/playwright` e2e + ci.yml job + `accessibility` reviewer + battery); only marginal axe-rule/contrast-token niceties remain (see frontend-a11y-static-lint for the one genuine residual).
- **retrofit_cost:** L (high-retrofit seam already shipped).
- **pull:** L.
- **is_new:** false. **overlaps:** ALREADY SHIPPED; the genuine residual (jsx-a11y static lint) is broken out as its own reviewer-enforced row.
- **sources:** breadth-nonfunctional.
