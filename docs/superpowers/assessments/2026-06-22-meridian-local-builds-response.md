<!-- Provenance: Meridian's response to the framework's 2026-06-22 prioritization draft, supplied by
the operator on 2026-06-22. Canonical home is Meridian's repo; recorded here verbatim as the framework's
planning input. Integration into our board is tracked via FWK56 + ACTION_LOG. -->

# Meridian — local-builds response to the retrofit-cost prioritization (2026-06-22)

## TL;DR — the three things that should re-weight the board

1. **Meridian is a committed first adopter, not a proof case.** We already hand-built the
   identity / authz / tenant foundation cluster (MDN33/34/36/47) — but it was ~2 days of
   agent-driven dev, so the sunk cost is low. We will **de-fork the *generic* parts onto your
   batteries if you build them to our validated shape.** A battery with a real consumer outranks a
   speculative one — so shared-auth + multitenancy should rank *higher*, with us as the fit target.
2. **You shipped the *mechanics* of composition; you're missing the *discipline* of
   decomposition** — and that discipline (product-identity lens + drift detection + decision
   coherence) is *Meridian's product*. Dogfood it as the decomposition layer of the sibling story.
3. **Two DAG edges are missing, both dependents of `tenant-physical-routing`:** per-tenant
   **connection budgeting** and **plane-aware migrate/deploy/rollback**. We paid both retrofit costs
   in practice (MDN47; MDN59 + the parked MDN46).

---

## Filled status (the "Meridian: build? / when?" columns)

| Seam | Meridian status |
|---|---|
| identity-principal (shared-auth) | **DONE** (MDN34) — `app_user`/`session`, request-path `current_user` (401) |
| authz-spine (default-deny) | **DONE** (MDN34/36) — `guard()` chokepoint + per-product RBAC; adversarially validated |
| tenant-data-model + tenant-context | **DONE** (MDN33/34) — two-plane control+tenant; `active_tenant` (404, leak-safe) |
| tenant-physical-routing (`resolve_tenant_dsn`) | **DONE, past it** (MDN33/47) — **DB-per-tenant** + bounded per-endpoint engine registry. *Reference impl.* |
| tenant-rls | **N/A** — we chose physical routing over RLS (see Q3) |
| external-id | base `Item` still `int` PK (your concern is real at base-model layer); our product surface already uses opaque ids (tenant slugs / product ids / UUIDs) |
| audit-log | **partial** — domain-scoped append-only `authz_event` (MDN34); general activity-trail future; retention/GDPR is live work (MDN48, see below) |
| secrets-backing | **latent gap** — tenant DSNs carry creds (env/settings, "never log"); no secrets backend yet |
| api-versioning | not yet (routes unversioned); want the `/v1` one-liner when the judgment API ships |
| durable-agent-state / agent dependents | **not yet, trending to foundational** (see Q2) |
| object-storage · money · i18n · frontend cluster | **reserve, not near-term** |

---

## Q1 — Wave-1 foundations in our near-term path

The identity/authz/tenant trio is **already built**, so the signal is *validation*: these were exactly
the things we couldn't defer, and retrofitting them later would have been the rewrite you describe.
`external-id`: reserve it (base-model decision); our domain already routes around it. `money`,
`object-storage`: reserve, **not building**.

## Q2 — conditional clusters

- **agents — partial today, trending to Wave-1-for-us.** Now: stateless LLM judge calls, no
  checkpointer. Coming: agentic ingestion (MDN37) and a future *panel of many layered judges* with a
  provenance substrate (our "traceability sidecar", MDN52). So **`durable-agent-state` + `genai-trace`
  + `agent-eval` will become foundational for us** — reserve them; we'll pull them.
- **i18n — out of scope** near-term (single-locale, backend-only).
- **frontend — in scope but deferred** (MDN38). When it lands we'll pull `frontend-headless-primitive`,
  `typed-FE-data-layer`, `frontend-auth-storage`.

## Q3 — cross-cluster edges you can't see

- **multitenancy hard-requires identity first** (confirmed, not parallel): our request chain is
  `current_user (401) → active_tenant (404) → guard (403)`; tenant context is resolved *from* the
  authenticated principal. Your `identity-principal → tenant-context` edge is load-bearing.
- **`tenant-physical-routing` has two expensive dependents your DAG omits:**
  - **→ per-tenant connection/pool budgeting.** DB-per-tenant buys *data* isolation, **not connection**
    isolation — one shared cluster makes `max_connections` a global ceiling, and an unbounded
    per-tenant engine cache exhausts it (we hit this in production-shape — MDN47). Distinct seam from
    "tenant-fairness."
  - **→ plane-aware migrate/deploy/rollback.** With control + per-tenant DBs, a single
    `alembic upgrade head` entrypoint is *wrong* (it applies the app schema to the control DB), and
    rollback must never `downgrade` across the control migration. We just spent MDN59 (boot) on this;
    MDN46 (deploy half) is parked. **Add: physical-routing ⇒ plane-aware migration fan-out +
    rollback-by-image.**

## Q4 — mis-rankings for our reality

- **audit-log** — your "non-backfill, build early" call is right (we built `authz_event` in the first
  auth cut). But split the ranking: a *scoped* audit (authz grants) is much cheaper early than a
  *general* activity-trail; retention/GDPR coherence is a real follow-on cost.
- **api-versioning** — agree it's a Wave-1 one-liner. We're a live example of "didn't namespace, will
  pay the coordination cost when the consumer API ships."
- **secrets-backing** — slightly under-ranked for a multitenant story: the moment you do DB-per-tenant
  you store per-tenant DSNs-with-creds, which wants a secrets backend earlier than M·M / Wave 2.

## Q5 — sibling / parallel split, shapes, shared-auth, workspace

**Posture (pending a sibling EDR, framed by our existing `EDR-0001` "consume-not-fork" rule):** freeze
the bespoke auth/tenancy at "runs fine," declare **intent-to-adopt the generic parts**, and stop
piling dependents on it. We can't de-fork onto a battery that doesn't exist yet — so the live decision
is *freeze vs keep-hardening*, and we're choosing freeze.

**Proposed sibling map + shapes** (candidates — gated on validating the decomposition first; see
below):

| Unit | Sibling? | Shape | Notes |
|---|---|---|---|
| Judgment / Coherence engine | **yes** | **service** | our core value prop; today a back-office batch job (MDN55/G1 gives it a surface) — prime sibling |
| EDR / Decision-graph kernel | maybe | **library** | the domain foundation, consumed by Judgment + Registry |
| App-Product registry | maybe | service or library | entangled with the kernel ("a Product *is* a root `edr_product`"); needs our decomposition brainstorm (MDN54/MDN60) first |
| Agentic ingestion (MDN37) | yes (later) | **worker** | when built |
| Frontend (MDN38) | yes (later) | **service (web)** | when built |
| **Identity/Access + Tenant-provisioning + Observability** | **NO** | **shared substrate** | the plane every sibling sits on — *not* composable peers (see missed-point #2) |

- **shared-auth: service vs library** — our lean is **library over the canonical store** for the
  *generic* parts (identity / sessions / tenant-provisioning / physical-routing), because we already
  have the canonical control store (FWK6) and a two-plane model, and auth-as-service adds a network
  hop + an availability dependency to every request's 401/404/403 chain. **But we KEEP** per-product
  RBAC + the absolute-seal compartmentalization (MDN36) in-product — those are tied to our
  epistemic-governance model and can't be a generic battery. (This is the open architectural call; we'd
  co-design it as the FWK56 brainstorm.)
- **workspace / shared-infra: yes** — we already run one obs/Traefik/network/canonical-store; we want
  that mode, not N full 8-service stacks.

---

## What the updated draft still misses (decomposition + parallel-engineering)

The composability section added the mechanics (shapes, workspace, contracts, parallel enablers). Four
things it still doesn't capture:

1. **Decomposition needs a principle, not just shapes.** "Which become siblings?" is asked as an
   *input* — but identifying genuine boundaries vs shared substrate vs tangles is the hard problem, and
   it has a method: the product-identity lens (a real sub-product is a strict specialization on
   **boundary ⊊ / ontology ⊊ / telos**; coextensive ⇒ not a distinct product). Without it, teams split
   along convenient file lines and call them siblings.
2. **Product vs substrate is a category the section blurs — not everything can be a sibling.** Shared
   substrate (identity, tenancy, obs) is the *plane every sibling sits on*; you choose how to *share*
   it, you don't *compose* it as a peer. Listing `shared-auth` as a sibling-via-shape-axis conflates
   "how do we share substrate" with "this is a distinct product" — that conflation is how you get a
   distributed monolith.
3. **Parallel engineering's binding constraint is decision/interface *stability*, not serial "waves."**
   Under agent-driven dev the build cost is cheap, so coordination dominates: reframe "waves" as
   "**what must be frozen before streams fork.**" And you have *interface* contracts (Pact) but no
   *decision* contracts — streams stay coherent only where their decisions are independent. Your DAG is
   a build/interface DAG; the missing one is a **decision-dependency graph** (which choices constrain
   which). That graph is exactly Meridian's `deps:` edges + `decisions/` (EDR) — i.e. our product.
4. **Sound decomposition must precede parallelism, and boundaries erode.** Build-order should be
   `validate-decomposition → shape-axis → workspace → contracts → parallel` (parallelizing on the wrong
   seams multiplies the fix cost across N streams). And boundaries rot into tangles as code accretes —
   re-establishing an eroded sibling boundary across N streams is the brutal-late retrofit. Drift
   detection (the decomposer as an ongoing check) belongs in the picture; it's not a one-time scaffold.

**Synthesis:** the relationship is bidirectional. Meridian *consumes* your composition **mechanics**;
your composability story is *missing the decomposition discipline* — and that discipline is what
Meridian builds. The highest-leverage move isn't another column entry: it's to treat
**decompose-correctly + keep-streams-coherent** as a first-class framework concern and dogfood
Meridian's lens for it.
