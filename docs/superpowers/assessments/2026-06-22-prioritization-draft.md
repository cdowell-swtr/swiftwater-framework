# Retrofit-cost prioritization — DRAFT (for Meridian to respond to)

**Date:** 2026-06-22 · **Status:** draft for Meridian's "local builds" response.
**Inputs:** the retrofit-cost horizon scan (`2026-06-22-retrofit-cost-horizon-scan.md`) + a 3-ranker
panel (`retrofit-scan/prioritization-*.md`) + the inter-item dependency DAG.

## How to read this / how to respond

This is **our draft**, ranked by the **retrofit lens** (cheap-early vs brutal-late) and sequenced by
the **dependency DAG** (a high-retrofit leaf can't precede its foundation). It is deliberately
**Meridian-agnostic** — we don't know your roadmap. **Your turn:** in the right-hand column of each
wave, mark the **local builds** — which items Meridian will actually build, in what order, on what
window — and add any **Meridian-specific dependency edges** we couldn't see (esp. cross-cluster, e.g.
"our multitenancy hard-needs shared-auth first"). Re-rank freely; the waves are a starting point.

## Method (one paragraph)

Three independent rankers each tiered the whole board through the retrofit lens with a distinct
tiebreak — **irreversibility/blast-radius**, **foundational unlock-order**, **scaffold-asymmetry/net-new**.
Where they agree, the tier is confident; where they diverge ≥2 tiers, it's an **open decision** (listed
below). We then overlaid the dependency DAG to turn tiers (rank) into **waves** (build order).

## The dependency DAG (build-order constraints)

Foundations (left) must precede their dependents (right):

```
shape-axis / headlessness ────────── workspace-shared-infra · sibling-interface-contracts · (auth-as-service ↔ auth-as-library)
identity-principal (shared-auth) ─┬─ authz-spine ─── api-keys (also needs secrets-backing)
                                  ├─ enterprise-SSO/SCIM
                                  ├─ tenant-context ── tenant-rls / tenant-physical-routing / tenant-fairness
                                  ├─ agent-tool-permission
                                  └─ frontend-auth-storage
tenant-data-model ────────────────── (tenant cluster above; tenant_id is the base-model precondition)
secrets-backing ──────────────────── api-keys · field-encryption
money ────────────────────────────── ledger(parked)
durable-agent-state ──────────────── human-approval(HITL) · genai-trace · agent-eval · agent-memory
transactional-outbox ─────────────── audit-log(reliable) · outbound-comms
audit-log ────────────────────────── admin-CRUD-UI · billing(parked) · healthcare-access
frontend-headless-primitive ──────── design-tokens(fold-in) · data-grid(parked)
string-externalization (i18n) ────── locale-formatting · locale-resolution · RTL · content-translation
object-storage ───────────────────── CDN/static-assets
external-id ───────────────────────── (base-model precondition for every safe external API/webhook/SDK surface)
```
Cross-cluster: tenant-context needs identity-principal · api-keys needs identity+authz+secrets ·
billing needs multitenancy+audit-log+authz+webhook-inbox. **(Meridian: add edges we can't see.)**

---

## Composability / sibling-products — the cross-cutting concern (Meridian's seed)

This is the architectural posture that **started this thread** ("sub-products as isolated composable
components + more parallel building streams"), and the retrofit scan structurally **under-weighted**
it: a seam-hunting scan finds discrete seams, but composability is the *substrate* those seams sit on.
Splitting a web monolith into siblings late is exactly the brutal-retrofit Meridian is facing — so by
the lens's own logic it belongs near the top, not buried as a single auth row. Decomposed:

| Facet | What it is | Status / placement |
|---|---|---|
| **shape axis / headlessness** | `framework new --shape {web\|worker\|library\|cli}`; headless = no app/route/heartbeat. The meta-foundation — a sibling can be a worker, library, CLI, or service. Today `main.py` is unconditional (web-only). | **NEW — Wave 1 *if* going multi-product** |
| **workspace / shared-infra** | N siblings share ONE obs/Traefik/network/canonical-store, not N full 8-service stacks | **NEW — Wave 2 (rides shape-axis + FWK6)** |
| **sibling-interface contracts** | the hard boundary between streams: a published typed client (un-park `published-sdk` here) + Pact `consumers` (exists) + a shared-schema package | **Wave 2** |
| **shared-auth** (service vs library) | the service-vs-library-over-canonical-store decision | **Wave 1** (`identity-principal` + auth cluster) — the open architectural call |
| **shared canonical store** | siblings → one `APP_DATABASE_URL` | **DONE (FWK6)** |
| **parallel-streams enablers** | flag-gated trunk dev (`experimentation`) + api-versioning + Pact + per-sibling CI | **pull together** so incomplete work merges safely |

Build-order: **shape-axis is the root** → workspace + sibling-contracts ride on it → parallel-streams
enablers ride on the contracts. Shared-auth's service-vs-library choice *is itself* a shape-axis choice
(auth-as-service = a headless service sibling; auth-as-library = a library-shape sibling). Tracked as
**FWK56** (promoted from Horizon); gets its own brainstorm — the paused shape-axis → auth-as-service →
auth-as-library sequence.

---

## Wave 1 — Foundations: scaffold FIRST (high-retrofit AND roots; all 3 rankers Tier-1)

| Seam | rc·pull | Why first (retrofit + what it unlocks) | Meridian: build? / when? |
|---|---|---|---|
| **identity-principal** (shared-auth) | H·H | the biggest root — unlocks authz, api-keys, SSO, tenant-context, agent-tool-perm, FE-auth; retrofitting a principal after authz is scattered rewrites every access decision | |
| **external-id** (opaque base-model ID) | H·H | code-confirmed bare `Item.id` int PK leaks into URLs/webhooks/FKs/exports — irrecoverable once integrated; base-model decision | |
| **tenant-data-model** (`tenant_id` everywhere) | H·H | root of the tenant cluster; the canonical widen-after-rows-exist migration; you already stubbed logical separation | |
| **money** (int minor-units + ISO-4217) | H·M | float loses precision irrecoverably; late currency = backfill vs ambiguous history; required by ledger | |
| **object/blob storage lifecycle** | H·H | stored keys/URLs embed everywhere (rows/deep-links/webhooks/exports/UIs); the scan's clean whole-domain miss | |

**Conditional foundations** — Tier-1 *within their cluster*, but the cluster's priority is Meridian's call:
| Seam | rc | Condition | Meridian: in scope? |
|---|---|---|---|
| **string-externalization** (ICU catalog) | H | the i18n keystone everything else depends on — start it first *if* you're localizing | |
| **durable-agent-state** (checkpointer) | H | the agent-harness root (upstream of HITL/eval/memory) — start it first *if* you're building agents | |

## Wave 2 — First dependents + non-backfill accumulation (Tier-2 consensus; unlocked by Wave 1)

| Seam | rc·pull | Depends on / why now | Meridian: build? / when? |
|---|---|---|---|
| **authz-spine** (default-deny chokepoint) | H·H | needs identity-principal; Tier-1-retrofit but **build-order-gated** behind it | |
| **tenant cluster**: context → rls → physical-routing (`resolve_tenant_dsn()`) → fairness | H·H | needs tenant-data-model + identity; the logical→physical ladder | |
| **transactional-outbox** + **outbound-idempotency** *(promoted off parked by all 3)* | H·H | the reliability pair — outbox closes the gap `handler.py:17-20` documents; idempotency is its client-facing twin (both embed in partner integrations) | |
| **audit-log / activity-trail** | H·M | non-backfill — events never recorded can't be reconstructed; best built on the outbox; unlocks admin-UI/billing | |
| **product-analytics** (consent-gated `track()`) | H·M | non-backfill (uninstrumented events gone forever); distinct surface from ops observability | |
| **secrets-backing + field-encryption** (crypto-shred) | M·M | which fields are encrypted is expensive to add after plaintext is written; field-enc needs secrets-backing | |
| **frontend-headless-primitive** (+ fold in design-tokens) | H·H | swapping the a11y/interaction foundation after real screens = multi-quarter rewrite *(Meridian-dependent on FE weight)* | |
| **agent dependents** (tool-permission · HITL · memory · cost-budget · genai-trace) | H·H | need durable-agent-state — *if agents in scope* | |
| **i18n dependents** (formatting · resolution · RTL) | M·H | need string-externalization — *if i18n in scope* | |

## Wave 3 — Leaves, lower-retrofit, conditional, and internal tooling

| Seam | rc·pull | Note | Meridian: build? / when? |
|---|---|---|---|
| **api-versioning** (`/v1` namespace) | H·H | ⚠ open decision (below) — one-line-now vs enforcement-already-owned | |
| **typed-FE-data-layer** (OpenAPI→TS + query-cache) | M·H | replaces the antipattern the react battery teaches *(Meridian-dependent)* | |
| **frontend-perf-budget** · **license-policy-gate** · **data-backup-restore-drill** | H·M | high-stakes but cheap-to-add-late CI/ops gates (propagate via upgrade) | |
| **cursor-pagination** · **time-future-events** | M/H·M | cursor: reviewer-owned reshape; time: narrow residual (base timestamptz covered) ⚠ | |
| **AI-retrieval** · **CMS+admin-UI** · **CDN** · **in-project-scaffolding** · **experimentation** · **AI-eval** · **outbound-comms** | M·M | additive on existing substrate; mostly Meridian-pull-driven | |
| **FWK55 retrofit-guard reviewers** | M·H | a reviewer matters once the surface it guards exists → trails its seams | |
| **FWK45 / 46 / 47 / 48** (reviewer-audit *internal* tooling) | —·— | separate maintainer track; opportunistic, not consumer-facing | |

---

## Open decisions (rankers disagreed ≥2 tiers — your + Meridian's call)

- **api-versioning** (asymmetry=Tier1, irreversibility=Tier3): the `/v1` namespace is *one line now* vs.
  a coordinated breaking change once SDKs/partners consume bare paths — but the additivity *enforcement*
  is already owned (oasdiff + contracts reviewer). **Draft call: do the namespace early (cheap), it's
  effectively a Wave-1 one-liner; everything else is already covered.**
- **time-future-events** (asymmetry=Tier1, others=Tier3): base `created_at` is already `timestamptz`, so
  the residual is narrow (future/recurring events + a naive-`utcnow` lint). **Draft call: Tier 3 unless
  Meridian has scheduling/recurring-event domains.**
- **string-externalization / durable-agent-state**: foundational (unlock-order=Tier1) but
  cluster-conditional (asymmetry=Tier3). **Resolved as "conditional foundations" above** — first *within*
  their cluster, cluster priority is Meridian's.
- **typed-FE-data-layer**: Tier-2 vs Tier-3, Meridian-dependent on how FE-heavy Meridian is.

## Promoted off the parked list
- **outbound-idempotency** — all 3 rankers promoted it (the scan itself flagged pull=H "revisit"). Now in
  Wave 2 alongside the transactional-outbox.

## Parked (build when a consumer pulls — confirmed low retrofit-cost)
ledger · billing · published-sdk · data-backfill-jobs · sbom-provenance · test-factories · storybook ·
data-grid · read-write-split · realtime-sync/CRDT · enum-lookup · micro-frontends · finops ·
structured-output-repair · marketplace-provenance · telemetry-ingest-contract · frontend-rendering-strategy ·
soft-delete-lifecycle. *(frontend-design-tokens → fold into headless-primitive, not standalone.)*

---

## For Meridian — the "local builds" response

Please fill the **"Meridian: build? / when?"** columns above, and answer:
1. **Which Wave-1 foundations are in your near-term path?** (these are the cheap-now/brutal-late ones —
   even a "not building yet" is useful, so we know the scaffold should reserve the seam.)
2. **Are the conditional clusters (i18n, agents) in scope?** — flips string-externalization /
   durable-agent-state into Wave 1.
3. **Cross-cluster edges we can't see** — e.g. does your multitenancy hard-require shared-auth first, or
   are they parallel? Any Meridian seam that hard-blocks another?
4. **Anything mis-ranked for your reality** — a parked item you'd promote, or a Wave-1 item you'd defer.
5. **Sibling / parallel split (your seed — FWK56)** — which sub-products become siblings, and in what
   *shape* (worker / library / cli / service)? Is shared-auth a **service** or a **library over the
   canonical store**? Do you want **workspace/shared-infra** mode (one obs/Traefik/network across
   siblings)? This is the concern the scan under-weighted — your answer here re-weights the whole board.
