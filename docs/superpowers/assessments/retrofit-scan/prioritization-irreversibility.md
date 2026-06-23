# Retrofit prioritization — the irreversibility & blast-radius lens

**Date:** 2026-06-22
**Author:** independent framework-architect pass (draft for Meridian to respond to)
**Inputs:** the 2026-06-22 retrofit-cost horizon scan (`../2026-06-22-retrofit-cost-horizon-scan.md`),
its `retrofit-scan/SYNTHESIS.md` + `COMPLETENESS.md`, and direct code checks against
`src/framework_cli/template/`.

## The lens, stated so you can argue with the *axis* before the order

**Primary sort key — retrofit asymmetry.** Rank by how *cheap-early-vs-brutal-late* each seam is.
A scaffold's only reason to exist is to bake in the high-asymmetry seams before a builder paints
themselves into a corner. The cost that matters is adding the seam *after* a product has real data
/ content / users / traffic / integrations — coordinated migrations, irrecoverable precision or
identity, references embedded across every surface.

**Secondary tiebreak — irreversibility & blast-radius.** Among retrofit-comparable items, rank
*higher* the ones whose absence becomes **irreversible** (data already lost, identifiers already
leaked, events never emitted) **and spreads widely** (the value is embedded across many surfaces:
IDs, `tenant_id`, timestamps, storage keys, event taxonomy). The "you can never fully fix this
later, and it touches everything" axis.

**The discipline that does the most work: high-stakes ≠ high-retrofit.** The scan already pruned 19
of 29 net-new candidates on exactly this. I apply it *again* to the scan's own H ratings — several
of its H-retrofit items are high-*stakes* but cheaply-addable-late (a contained write-path change, a
forward-looking CI gate), and I demote them relative to the base-model seams that force a coordinated
historical migration. I record the scan's `rc`/`pull` in the fields but **do not** inherit them as
my verdict.

**And the inverse discipline: low pull does not demote a high-retrofit seam.** The scaffold exists
precisely for the high-retrofit / medium-pull quadrant. `money`, `product-analytics`, and `audit-log`
all carry pull=M and all keep an irreversibility-driven rank, because their absence is *non-backfillable*
(you cannot reconstruct precision you discarded, or events you never emitted).

**Convention.** Rank restarts at 1 within each tier (1 = do first in that tier). 31 items total
(A=4, B=13 — sub-letters are separate line items, C=14). `meridian_dependent = true` only where the
*priority* genuinely hinges on Meridian's roadmap timing, not where Meridian merely happens to want it.

---

## Tier 1 — scaffold NOW (the irreversible, embedded-everywhere base-model & identity spine)

These are the seams where the secondary tiebreak bites hardest: each is *both* irreversible-if-late
*and* spreads across every table / URL / integration. This is the cluster a scaffold is *for*.

**1. composability / shapes / shared-auth — identity-principal (C).** `rc H · pull H`. The
designated-first concern, and correctly so: the **identity-principal** decision (one canonical
principal, multi-identity from day 1, a default-deny chokepoint at the data layer) is upstream of the
entire auth cluster — authz-spine, API keys, sessions, SSO/SCIM all hang off it. Retrofitting a
principal abstraction after authorization checks are scattered through routes and queries is a
whole-codebase rewrite of every access decision. Highest blast radius on the board: it touches every
read and write. `meridian_dependent: false` — foundational regardless.

**2. external-id — opaque non-sequential base-model ID (FWK50a).** `rc H · pull H`. Code-confirmed:
`db/models.py:14` ships `id: Mapped[int] = mapped_column(Integer, primary_key=True)` — a bare bigserial
on the base `Item`, and the same pattern repeats on webhooks/vectors/dead-letter models. This is
*verbatim* the task's own blast-radius example: the int leaks into URLs, webhooks, deep-links, exports,
and every FK. Once it's embedded across integrations you cannot recall it — the leaked enumerable IDs
are already in partners' logs and customers' bookmarks. The IDOR/authz half is reviewer-territory and
must stay separate; the *opaque-ID-on-the-base-model* decision is the one-line-now seam. `false`.

**3. multitenancy — `tenant_id` on the base model (C).** `rc H · pull H`. `tenant_id`-on-every-table
is the canonical "widen the model after rows exist" migration — a schema-wide change plus a backfill
of every existing row plus a rewrite of every query to be tenant-scoped, all under a fail-closed
invariant you cannot add safely once cross-tenant reads are possible. Meridian already stubbed logical
separation, which *raises* urgency rather than lowering it: the base-model decision (`tenant_id` +
composite keys + context propagation) must land before real tenant data accumulates. The
`resolve_tenant_dsn()` physical-routing promotion is later; the data-model atom is now. `false`
(foundational even though Meridian pulls it — the *priority* doesn't hinge on their timing).

**4. money — int minor-units + ISO-4217 (FWK50b).** `rc H · pull M`. The task's canonical "data already
lost" case. Float on `price/amount/total/balance` discards precision *irrecoverably* — by the time you
notice, the wrong values are already persisted and reconciled against, and a late currency dimension
forces a backfill against ambiguous history (which rows were which currency?). Blast radius is narrower
than IDs/tenant (only money columns), so it sits below them — but on the *irreversibility* axis it is
maximal: there is no migration that recovers discarded precision. Pull=M does **not** demote it; this is
exactly the high-retrofit/medium-pull quadrant the scaffold exists for. `false`.

**5. object/blob storage lifecycle (FWK49).** `rc H · pull H`. The scan's one clean whole-domain MISS,
code-confirmed absent (no boto3/minio/presigned/upload payload anywhere). It earns Tier 1 on the
secondary tiebreak: stored keys/URLs are *content references embedded everywhere* — DB rows, deep-links,
webhooks, exports, client UIs — structurally the same "can't-change-post-integration" class as
external-id, but for blobs. And objects written before the erasure/quarantine seam existed sit in
backups/replicas with no clean delete path (irreversible tail). It ranks just below money because the
*pull* is M–H (a product may never grow a binary-content surface) where IDs/tenant/money are
near-universal — but once a builder ships uploads without the abstraction, the migration is a backfill
of every reference. `meridian_dependent: true` — the *urgency* genuinely hinges on whether Meridian's
roadmap has a documents/exports/avatars surface soon; the seam is high-retrofit regardless but its
*placement this high* is pull-sensitive.

> **Biggest Tier-1 judgment call.** I put the three *first-class concerns* (identity, multitenancy)
> at the very top alongside the net-new base-model seams, rather than treating the FWK49–55 "scaffold-early"
> list as the only Tier-1 candidates. The lens is about the seam's asymmetry, not its ticket status:
> `tenant_id` and identity-principal are the highest-blast-radius, most-irreversible decisions on the
> entire board, and the scan itself calls them foundational. Deferring them because they're "concerns"
> not "batteries" would invert the lens.

---

## Tier 2 — next (high-retrofit but either narrower blast radius, or one-step-removed from the base model)

**1. i18n — string-externalization (ICU catalog) (C).** `rc H · pull H`. The keystone the whole i18n
cluster depends on. Retrofitting `t()` onto authored content and concatenated strings after the UI
exists is a per-string excavation across every screen and template — brutal and pervasive. It sits in
Tier 2 not Tier 1 only because it does *not* corrupt or lose persisted data (you can wrap strings later,
painfully, whereas you cannot un-discard money precision or un-leak an ID). High blast radius, but
recoverable-with-effort rather than irreversible. `meridian_dependent: true` — urgency hinges on whether
Meridian ships localized UI; foundational-shaped but pull-gated.

**2. audit-log / activity-trail (C).** `rc H · pull M`. The non-backfill property puts this above its
pull rating: an append-from-day-1 compliance substrate cannot reconstruct events that were never
recorded. If you add it late, the entire pre-existing history is permanently absent — an irreversible
gap, even if the blast radius (one append path) is narrow. The user has flagged this "huge." `false` —
the irreversibility is intrinsic, not Meridian-timed.

**3. product-analytics — consent-gated `track()` (C).** `rc H · pull M`. Same non-backfill irreversibility
as audit-log: events not instrumented from day 1 are gone forever — no migration reconstructs user
behavior you never captured. A *different surface* from ops observability (consent-gated, server-side,
marketing-CAPI). Ranks just below audit-log because audit-trail is a compliance substrate (legally
load-bearing) where analytics is growth-instrumentation. `false`.

**4. transactional-outbox (FWK52).** `rc H · pull H`. **Demoted from the scan's H-retrofit framing.**
The template's own `webhooks/handler.py.jinja:17-20` documents the exact dual-write gap, so the seam is
real and confirmed-unshipped. But adding it later is a *contained write-path change* plus a relay table —
not a historical-data migration, and not embedded across surfaces. It's the most-irreversible of the
"behavioral" seams (a dual-write that already double-processed cannot be un-processed), which keeps it in
Tier 2, but it is not base-model-irreversible, so it sits below the data-correctness and
non-backfill-event items. `false` — the gap is intrinsic to the architecture, not Meridian-pulled.

**5. AI-agent-harness — durable-agent-state (C).** `rc H · pull H`. Durable-agent-state
(checkpointer/thread_id) is upstream of HITL, eval, memory, and tool-permission — the same
"foundational-within-its-cluster" shape as identity-principal, but scoped to consumers building agents.
Retrofitting durable state after an agent loop exists means re-architecting the loop's persistence
boundary. High-retrofit *for agent-building consumers*, which is why it's Tier 2 not Tier 1: its
universality is conditional. `meridian_dependent: true` — priority hinges on Meridian's agent roadmap.

**6. external-id's frontend twin: typed-frontend-data-layer (FWK51b).** `rc M · pull H`. The react battery
currently *teaches* the `useEffect/useState` fetch antipattern (zero codegen deps confirmed), and every
consumer copies it. The retrofit cost is the scan's M (a refactor, not a data migration), but the *blast
radius* is unusually wide for an M: the antipattern propagates into every screen the moment the battery
ships, so the longer it ships unfixed the more screens inherit it. I rank it in Tier 2 (above the
genuinely-H-rc frontend perf/a11y items it unblocks) because it's the spine the other two FE items
assume, and because "we are actively teaching the wrong pattern" is a leak that compounds with every
consumer. `true` — urgency hinges on FE-heavy Meridian timing.

**7. frontend-headless-primitive — a11y/interaction layer (FWK51a).** `rc H · pull H`. Swapping the
interaction/a11y foundation after real screens exist is a multi-quarter behavior-by-behavior rewrite —
genuinely H-retrofit and high blast radius (every interactive component). It sits below the typed-data
layer only because the data layer is its prerequisite spine and a more universal antipattern-fix; both
are the react battery's missing foundation. `true` — FE-roadmap-gated.

**8. secrets-backing + rotation/versioning + field-encryption (C).** `rc M–H · pull M`. Field-encryption
/ crypto-shred is the clean erasure primitive, and *which* fields are encrypted is a decision that's
expensive to add after the data is written in plaintext (a re-encrypt backfill, and the plaintext sits in
backups). That irreversibility-tail keeps it in Tier 2. Rotation/versioning is more additive. `false` —
the field-encryption-placement decision is intrinsic.

> **Biggest Tier-2 judgment call.** I split the FWK51 frontend cluster across tiers by *which is the
> spine*: typed-data-layer (the antipattern we're actively teaching) and headless-primitive (the
> multi-quarter-rewrite foundation) are Tier 2; perf-budget (Tier 3) is a one-config ceiling that's
> cheap to bolt on whenever. The scan rated perf-budget H-rc; I disagree on *placement* — see Tier 3.

---

## Tier 3 — later but still scaffold-worthy (cheap ceilings, narrow residuals, capability batteries, maintainer tooling)

**1. api-versioning — `/v1` namespace (FWK53a).** `rc H · pull H`. The *enforcement* half (oasdiff +
contracts reviewer) is already owned; the residual seam is just the namespace *decision* — mount under
`/v1` from day 1. That's one line now vs. a coordinated breaking change once SDKs/partners consume the
bare paths. High-retrofit in principle, but the actual scaffold cost is a single routing choice, so it's
a cheap-to-bake Tier-3 do-first. `false`.

**2. frontend-perf-budget — bundle/CWV CI ratchet (FWK51c).** `rc H · pull M`. Clawing back a bloated
bundle *is* a multi-sprint excavation (the scan's H is fair on the *cost of neglect*). But the scaffold
cost is one config + one CI assertion you can add the day you care, and the ratchet only constrains
*future* commits — there's no historical-data migration. High-stakes, low-scaffold-cost → Tier 3, ranked
high within it because the ratchet wants to exist before the bundle bloats. `true` — FE-roadmap-gated.

**3. license-policy-gate — SPDX copyleft CI gate (FWK54a).** `rc H · pull M`. Copyleft contamination is
incurred silently at first-dep-add and surfaces unrecoverably at M&A diligence — a real irreversibility
(you cannot un-ship GPL-linked code already in releases). But the *gate* is an additive CI step that
propagates via upgrade; the cost of adding it late is low even though the cost of the contamination it
catches is high. Net-new axis vs gitleaks/dependabot. Tier 3, ranked high (cheap, catches an
irreversible class). `false`.

**4. cursor-pagination envelope (FWK53b).** `rc M · pull M`. Return an opaque cursor envelope from day 1
so an offset→keyset swap stays server-internal. The response-reshape obligation is reviewer/Pact-owned;
the envelope shape is the cheap early seam. Modest blast radius (paginated endpoints), modest
irreversibility (clients parse the envelope). `false`.

**5. time — future-events wall-clock + IANA (FWK50c).** `rc H · pull M`. **Demoted hard from the
scan's H and from the FWK50 cluster.** The scan itself confirms base `created_at` is *already*
`timestamptz` — so the universal time-correctness seam is shipped. The residual is narrow: future-dated
events stored wall-clock + IANA + tzdb-version (not pre-converted to UTC), plus a naive-`datetime.utcnow()`
lint. Genuinely irreversible *for the apps that store future events* (a recurring-event/scheduling
domain), but most products never hit it. Ranked well below 50a/50b — do not treat "FWK50" as a block.
`true` — only matters if Meridian schedules future events.

**6. data-backup + restore-DRILL (FWK54b).** `rc H · pull H`. **Demoted from the scan's H-retrofit.**
DATA recovery is explicitly out-of-scope today and a silently-broken backup is caught only when needed —
real stakes. But backups are *forward-looking*: adding the drill later loses only the gap-window data,
not a coordinated historical migration, and the drill is a runnable script you can write any time.
High-stakes, low-retrofit-asymmetry → Tier 3. `false`.

**7. AI-retrieval — vector-store / RAG / GraphRAG (C).** `rc M · pull M–H`. Builds on the already-shipped
`pgvector` + `age` + `llm` — so the substrate exists and this is largely additive capability on top.
Real value, low retrofit asymmetry. `true` — pull-gated on Meridian's RAG roadmap.

**8. CMS + admin/CRUD UI (C).** `rc M–H · pull M`. The editor-agnostic *versioned content schema* has a
mild retrofit tail (versioning content after it's authored), but the admin UI itself is additive.
`true` — Meridian-pull-gated.

**9. experimentation / rollout flags + A/B + MVT (C).** `rc M–H · pull M`. The completeness critic
explicitly rated this **L–M, not H** — the textbook high-value/low-retrofit capability: you gate *new*
code forward, you don't retroactively wrap shipped features, and the one irreversible angle
(exposure/experiment logs) collapses into product-analytics. Valuable enabler for parallel build streams,
but the scaffold's lens deprioritizes it. `true`.

**10. FWK48 — audit review-agents shipped INTO rendered projects (A).** Maintainer-origin, but
**consumer-facing** — it calibrates the review agents a `framework new` bakes into generated projects, so
unlike its siblings the retrofit lens applies: mis-calibrated reviewers shipped to consumers compound as
those consumers build. Ranked top of the Section-A block for that reason, but Tier 3 because it's tooling
calibration, not a data/identity seam. `false`.

**11. CDN + static-assets (C).** `rc M · pull M`. Ties to object-storage but is build-time app assets,
additive going forward. `true`.

**12. in-project scaffolding — `framework add route|model` (C).** `rc M · pull M`. The CLI is
lifecycle-only today; this is a DX accelerant, not a retrofit seam — no data or integration is corrupted
by adding it late. `true`.

**13. AI-eval for the builder's own agents (C).** `rc M · pull M`. Ship the framework's reviewer-eval
harness to consumers; extends FWK48. Additive tooling. `true`.

**14. outbound-comms — email/notifications (C).** `rc L–M · pull M`. The completeness critic decomposed
this: the non-backfillable part (consent/opt-out history) lands in product-analytics/consent-records, the
reliable-delivery part in transactional-outbox, and the genuine residual (channel/dispatcher abstraction)
is *low-retrofit* by its own literature ("add a new dispatcher"). Lowest-retrofit concern on the board.
`true`.

**15. FWK55 — retrofit-guard reviewers (B).** `rc M (as enforcement) · pull H (leverage)`. High *leverage*
(i18n / agent-tool-safety / soft-delete-erasure / jsx-a11y / rtl / data-export / tenant-offboarding), but
reviewers *catch* retrofit drift rather than *being* a baked-in seam — they're additive to the reviewer
system at any time, and several depend on the underlying concerns (i18n, tenant) landing first. High value,
low retrofit-asymmetry of the *reviewers themselves*. `false`.

**16–18. FWK45 / FWK46 / FWK47 — reviewer-audit internal tooling (A).** These are **maintainer-facing**
reviewer-audit machinery — the consumer-retrofit lens *barely applies*: no builder paints themselves into
a corner, no product data is lost, nothing is embedded across surfaces. I rank them last and say so
plainly rather than faking a retrofit asymmetry. Order among them follows pipeline-hardening dependency,
not retrofit: **FWK47** (resume-provenance guard — the scan notes it's "best landed before FWK48's larger
run leans on resume") slightly ahead of **FWK46** (unparseable-skeptic retry — a correctness fix that can
flip an outcome) slightly ahead of **FWK45** (apply the deferred tuning remainder — pure maintainer
fixture/prompt work, no release). All `false` (no Meridian dependence; internal tooling).

> **Biggest Tier-3 judgment call.** I deliberately ranked four scan-rated-H items *down* into Tier 3 —
> perf-budget, license-gate, backup-drill, and time-future-events — on the **high-stakes ≠ high-retrofit**
> discipline. Each has a high *cost of neglect* but a *low scaffold-cost-asymmetry*: a CI gate or config or
> script you can add the day you care, constraining only future state, with no coordinated historical
> migration. The scan's rc measures cost-of-neglect; my lens measures cost-of-adding-late. Where they
> diverge, I follow the latter — that's the whole point of the secondary tiebreak. I flag this as the most
> contestable set of calls in the draft, and the place Meridian's response is most useful.

---

## Parked promotions (Section D)

I promote **one** item off the parked list, and explicitly *decline* two tempting ones — the scan's
adversarial filter parked D deliberately, so I promote only where it under-rated *retrofit*, not *stakes*.

**PROMOTE — outbound-idempotency** (client-facing Idempotency-Key replay contract). The scan **self-flagged
this** (pull H, "revisit alongside FWK52") and parked it as "cheaply addable-late" — but the
irreversibility & blast-radius tiebreak says otherwise: an `Idempotency-Key` header contract **embeds in
every client integration**. Adding it after partners/SDKs/mobile clients already call the API forces a
*coordinated change across every consumer* — the same "embedded across integrations, can't change
post-integration" class as external-id and storage keys, which I rank Tier 1. The scan judged it on
*server-side* cost (a dedup table — cheap) and missed the *client-side* blast radius (every caller must
adopt the header). It belongs as a Tier-2-grade companion to FWK52, not parked. *(Promotion confidence:
high — the scan itself left the door open.)*

**DECLINE — frontend-design-tokens** (resolving an internal contradiction). The scan's own domain-9
researcher called late design-system/token adoption "the canonical FE retrofit horror story," yet the
board parked it — a genuine tension. I come down on **parked**, for the framework's specific posture: this
scaffold ships a deliberately *bare* react battery (semantic HTML, no component library), and FWK51a
(headless-primitive) is the foundation that *would* carry a token layer. Tokens are a horror story to
retrofit onto a *mature in-house design system with hundreds of hardcoded values* — but a fresh scaffold
hasn't authored those values yet, and the headless-primitive seam (already Tier 2) is the real
prerequisite. Promote tokens only *after* FWK51a lands, as part of the FE-foundations follow-on, not now.
The contradiction resolves to: the retrofit horror is real, but FWK51a is the seam that addresses it; a
standalone token battery is premature.

**DECLINE — soft-delete-lifecycle** (the parenthetical is correct). Parked as "trap avoided by
construction." Grep-confirmed: the template ships **no** `deleted_at` / `is_deleted` / soft-delete pattern
anywhere. That parenthetical is a *deliberate no-soft-delete-by-default stance* — and that's the right
call: soft-delete-by-default is itself an antipattern (it silently breaks uniqueness constraints, FK
semantics, and "is this really gone?" erasure guarantees). Promoting it would *add* the trap the scaffold
avoided by omission. The erasure obligation it gestures at is already owned by the data-lineage /
compliance / privacy reviewers (per the scan's disposition table). **Stays parked, correctly.**

---

## Summary of the contestable calls (the places Meridian's response is most valuable)

1. **Tier 1 includes the first-class *concerns* (identity, multitenancy), not just the FWK49–55 batteries.**
   The lens ranks by seam asymmetry, not ticket status; `tenant_id` and identity-principal are the
   highest-blast-radius irreversible decisions on the board.
2. **Four scan-rated-H items demoted to Tier 3** (perf-budget, license-gate, backup-drill, time-future-events)
   on high-stakes ≠ high-retrofit. These have high cost-of-neglect but low cost-of-adding-late.
3. **outbound-idempotency promoted off the parked list** to a Tier-2-grade FWK52 companion — the scan
   missed the client-side blast radius.
4. **money and audit-log/product-analytics kept high despite pull=M** — the non-backfill irreversibility
   (discarded precision; never-emitted events) is the scaffold's exact reason to exist.
5. **Section A (FWK45/46/47) ranked last with the lens declared inapplicable** — maintainer tooling, no
   consumer paints into a corner; only FWK48 (ships *into* projects) gets a retrofit-merits ranking.
