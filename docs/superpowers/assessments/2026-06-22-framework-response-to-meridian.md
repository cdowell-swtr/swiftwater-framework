# Framework → Meridian: what's actually coming

**Date:** 2026-06-22 · **Re:** your local-builds response to the retrofit-cost prioritization.
**Read via `gh` (canonical here, framework repo).** Sources on `master`: the integrated draft
(`2026-06-22-prioritization-draft.md`, §"Meridian responded — what changed") + PLAN.md FWK56/FWK57.

## TL;DR — the three things you need to plan around

1. **The de-fork substrate ships in the next 2–3 days — by ~2026-06-25.** We're committing to a date:
   the generic substrate you de-fork onto — **identity · session · tenant-provisioning · physical-routing
   (`resolve_tenant_dsn`, with its per-tenant connection budgeting + plane-aware migrate/deploy/rollback)
   + the authz-spine *mechanism*** — built **as a library over the canonical store** (your lean) to your
   validated shape, lands within 2–3 days (tracked as **FWK58**). Your freeze is therefore *short*: stay
   frozen-but-shippable through the window, then adopt and delete the fork. The Meridian-local parts
   (your RBAC policy + epistemic-governance compartmentalization) you keep — only the generic core moves.
   **This is days, not a brainstorm cycle, so we need you engaged now** — your impl as the extraction
   reference + co-design over the next 48–72h (see "what we need").
2. **We took your boundary, not your product.** The battery scope we'll pursue is **identity · session ·
   tenant-provisioning · physical-routing + the authz-spine *mechanism*** — and *only* that. Your RBAC
   policy and your epistemic-governance / absolute-seal compartmentalization **stay yours**; we are not
   generalizing them. The batteries will ship **multitenant-consumer-shaped, not Meridian-shaped** — if
   they ever start looking Meridian-shaped, that's our bug, flag it.
3. **Your decomposition point became its own concern (FWK57) — general, *referencing* your instrument,
   not adopting it.** We're not shipping your EDR / decision-graph / product-identity lens. We're
   deriving a *general* decomposition discipline (the two purpose-independent principles below); your
   instrument is the worked example, weighed against other purposes — because a different consumer's
   purpose may need different principles.

## What we accepted from you (folded into the board, on `master`)

- **product-vs-substrate** — identity/tenancy/obs are shared *substrate* (the plane siblings sit on),
  not composable peers; the shape-axis applies to genuine product-siblings only. You were right; FWK56
  is corrected.
- **de-fork target** — substrate batteries aim at your validated shape (reference + validation oracle),
  not a speculative scaffold.
- **the three DAG edges you paid for** (off `tenant-physical-routing`): per-tenant connection/pool
  budgeting (MDN47) · plane-aware migrate/deploy/rollback (MDN59/46) · → secrets-backing (per-tenant
  DSNs carry creds). Added.
- **re-weights**: secrets-backing earlier · api-versioning confirmed a Wave-1 one-liner · audit-log
  split (scoped-authz cheap-early vs general activity-trail vs retention/GDPR) · `external-id` stays
  Wave-1 (base-model gap; your routing-around-it ≠ "drop it").
- **the decomposition gap** — promoted to **FWK57**.

## What we held the line on (and why — so there are no surprises)

- **Epistemic-governance stays Meridian-local.** It is not a general framework concern and we're not
  folding it into the auth battery. The only *general* capabilities adjacent to it are already
  represented on their own terms (provenance → the `data-lineage` reviewer + audit-log; decision-records
  → FWK57; isolation → multitenancy).
- **Your decomposition instrument is referenced, not absorbed.** It's your product; the framework's
  version will be lighter and purpose-general (likely: a decomposition guideline + a reviewer that flags
  "substrate treated as a sibling").
- **"Rank us higher" — weighed, partially applied.** A real committed consumer *does* raise priority
  and de-risks the spec (you're the validation oracle), so shared-auth/multitenancy are the
  best-grounded items on the board. But the framework stays general-purpose: the batteries serve any
  multitenant consumer, and we won't re-order the whole board to a single consumer's timeline.

## The honest roadmap status (no over-promising)

Most of this board is stubs and brainstorms (committed-intent + queue position, not dates) — with **one
committed exception**: the **de-fork substrate (FWK58)**, now scheduled for 2–3 days. Everything else
below is honest about being undated.

| Item | Status for you | What it means |
|---|---|---|
| **FWK58** de-fork substrate (identity/session/tenant-provisioning/physical-routing+ops + authz mechanism, library-over-store) | **COMMITTED — ships by ~2026-06-25 (2–3 days)** | built to your validated shape; you adopt + delete your fork. Needs your reference impl + co-design *now*. |
| **FWK56** broader composability (shape-axis for product-siblings · workspace/shared-infra) | brainstorm-next, no date | the *non-substrate* facets; sequenced after the de-fork. |
| **FWK57** decomposition discipline | brainstorm-next, general | you'll recognize the principles; the instrument will be lighter than yours and not yours. |
| **api-versioning** (`/v1` namespace) | a Wave-1 one-liner | cheap; we'll likely land it early. You're the live "didn't namespace, will pay later" example. |
| **external-id**, **per-tenant connection budgeting**, **plane-aware migrate/deploy/rollback** | Wave-1 / new edges | base-model + multitenant-ops seams; relevant when the de-fork runs. |
| **agents** (durable-state · genai-trace · agent-eval) | **reserved, trending** | you flagged these trending-to-foundational (layered-judge panel + traceability sidecar). They re-prioritize **when you signal the pull** — tell us when MDN37/52 move from "coming" to "now." |
| **frontend** (headless-primitive · typed-data-layer · auth-storage) | reserved | you'll pull when MDN38 lands; not before. |
| **money · object-storage · i18n** | **not building** | matches your "reserve, not near-term." We won't scaffold these speculatively. |

## What we need from you — now (a 48–72h window)

1. **Your reference impl, handed over at the *start*** — the auth/session/tenant/physical-routing code we
   extract the generic core *from*. This is the long pole; we need it up front, not at the end.
2. **Confirm the generic/local line before we cut** — does anything you marked generic turn out
   epistemic-governance-coupled (→ stays yours), or vice versa? A wrong line is the one thing that makes
   the battery come out Meridian-shaped.
3. **Co-design availability over the window** — synchronous enough to resolve the service-vs-library edge
   cases and the plane-aware-migration contract as they surface.
4. **Stay freeze-stable through the window** — don't harden the generic parts mid-extraction; park
   changes there until you've adopted.
5. **(after) A pull signal** for the agents/frontend clusters — still the thing that most changes our
   *later* sequence.

## Bottom line

You sharpened the composability story materially — and we're committing to the de-fork on a **date**
(2–3 days, FWK58), because you're a real consumer with a validated shape and a freeze that shouldn't
drag. The guardrails still held: we took your evidence and your boundary-drawing, not your roadmap or
your product, and the battery ships **multitenant-general** (your RBAC + epistemic-governance stay
yours). The ball is now on *both* of us for 48–72h: your reference impl + co-design, our build.

**One scope check before the clock starts:** we've scoped FWK58 as the generic core *plus* the
physical-routing intrinsic ops (connection budgeting + plane-aware migrate/deploy/rollback), since
without them the physical-routing battery isn't a usable de-fork target for you. **secrets-backing**
(externalizing the per-tenant DSN creds) we've left as an *immediate follow* rather than in-window —
you're on env/settings + "never log" today, so it doesn't block adoption. If you need secrets-backing
*inside* the window, say so and we'll fold it in.
