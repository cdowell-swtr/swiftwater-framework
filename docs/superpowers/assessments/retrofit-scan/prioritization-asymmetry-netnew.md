# Retrofit-asymmetry & net-new prioritization — independent architect draft

**Date:** 2026-06-22
**Author role:** independent framework-architect prioritization (a draft for Meridian to respond to).
**Source board:** `docs/superpowers/assessments/2026-06-22-retrofit-cost-horizon-scan.md` (the 76-agent
scan) + the `retrofit-scan/` per-agent files. Code-validated against the live template.
**Primary sort key:** cheap-early-vs-brutal-late asymmetry (the retrofit lens).
**Secondary tiebreak:** rank higher where the early-vs-late asymmetry is largest AND the framework
genuinely owns the seam net-new; discount items already half-covered, owned by an existing
reviewer/CI gate, or consumer-local.

---

## The two lenses I actually sorted by

### Lens 1 (primary) — the two flavors of high retrofit-cost

The single most important distinction on this board, and the one Meridian should push hardest on:
**not all "high-rc" items are high-rc for the same reason.** There are two stories, and they sort
differently:

- **Type-A — embedded-reference / rising migration cost.** The seam gets *monotonically harder to
  add* as data, integrations, and references accumulate. A late add is a coordinated schema +
  reference + client migration. This is the lens's core, and these are the Tier-1 spine.
  *external-id, money, blob-keys, tenant_id, identity-principal, api-versioning namespace,
  time-future-events, cursor envelope, outbound-Idempotency-Key.*
- **Type-B — silent irreversible accumulation.** The seam itself is *cheap to add late*, but the
  **damage incurred in the gap is irrecoverable**: events that were never emitted have no backfill,
  a backup that was silently broken has already lost the data, copyleft contamination is already in
  the tree. The add-cost is low; the *gap-cost* is the asymmetry.
  *license-gate, backup-restore-drill, product-analytics, audit-log, perf-budget.*

Both count (the task explicitly names "irrecoverable precision/identity"). My rule: **a type-B item
ranks below its type-A peers**, because the scaffold's job is to make the decision that is expensive
to *make* later — and type-B decisions are cheap to make later; only the *waiting* is expensive.
The exception is audit-log, which I keep in Tier 1 because it is simultaneously type-B (un-emitted
events don't backfill) *and* a base-model/schema decision (an append-only trail wired at the data
layer is itself an embedded-everywhere seam).

### Lens 2 (the decisive discount) — propagates-via-upgrade ⇒ inherently low primary-rc

This is the cleanest structural sort on the board. **Anything that ships as a reviewer prompt or a
CI gate reaches every consumer later via `framework upgrade` at near-zero cost** (upgrade re-renders
the template payload from the tag — `[[framework-upgrade-fetches-template-from-tag]]`). That means
both arrows point down at once: low primary retrofit-cost (a consumer who upgrades next quarter loses
nothing by not having it today) *and* discounted on the secondary tiebreak (reviewer/CI-owned, not a
net-new seam the scaffold uniquely must decide). This sinks the entire reviewer/CI-enforcement class
to Tier 3 — **not because it's low-value, but because it is the lowest-asymmetry quadrant on the
board.** FWK55 (retrofit-guard reviewers), FWK45/46/47 (maintainer tooling), and FWK48
(consumer-side calibration) all live here. Leverage is not retrofit-cost; "pull H leverage" on FWK55
does not lift it.

---

## TIER 1 — scaffold NOW (highest asymmetry, foundational, base-model/identity-grain)

Each Tier-1 item clears all three secondary-tiebreak tests: framework-owns-net-new **AND**
embedded-everywhere-if-late **AND** only-the-scaffold-is-positioned-to-decide-it.

1. **Composability / identity-principal** (concern; rc H, pull H). The designated-first concern, and
   correctly so: a multi-identity principal at the data layer is the keystone the entire auth cluster
   (authz-spine / api-keys / SSO-SCIM / session-revocation) hangs off. Retrofitting a principal model
   after every table, route, and token assumes a single user identity is the canonical
   forced-rewrite. Type-A, framework-owned, decide-once. **meridian_dependent: false** —
   foundational regardless of roadmap.

2. **Multitenancy — tenant_id on the base model** (concern; rc H, pull H). `tenant_id` everywhere +
   composite keys is the textbook irreversible base-model widening: adding it after rows exist is a
   schema-wide migration + a backfill + a fail-closed context-propagation retrofit on every query.
   Meridian already stubbed logical separation, but the *base-model decision* is foundational and
   does not hinge on their physical-routing timeline. **meridian_dependent: false.**

3. **FWK50a external-id (opaque base-model ID)** (battery/concern; rc H, pull H). Code-confirmed:
   `db/models.py:14` ships `Mapped[int] = mapped_column(Integer, primary_key=True)` — a bare int PK
   that leaks into URLs, webhooks, deep-links, exports, and cross-service FKs. Once those references
   are minted and embedded in partners' systems, swapping the public identifier is a coordinated
   migration across every integration. The cleanest type-A on the board; the IDOR/authz half is
   correctly held to reviewer-territory and not conflated. **meridian_dependent: false.**

4. **FWK49 object/blob storage lifecycle** (battery; rc H, pull H). The scan's one clean whole-domain
   miss — confirmed absent (no boto3/minio/presigned payload). Stored keys/URLs are content
   references embedded in rows, deep-links, webhooks, exports, UIs; a provider-coupled URL or raw
   local path baked into those is `external-id`-for-blobs. The serve-fork (presigned vs
   proxy-through-app) and the quarantine/scan interception point are both structureless to insert
   after bytes flow straight to durable storage. Net-new, framework-owned, decide-before-first-file.
   **meridian_dependent: false** (a rich platform grows a binary surface regardless; pull is H
   structurally, not Meridian-timed).

5. **FWK50b money (int minor-units + ISO-4217)** (battery + reviewer-half; rc H, pull M). Float loses
   precision *irrecoverably* — the canonical irreversible-history loss. A late currency dimension is a
   backfill against history that never recorded which currency a bare `amount` was. The decision is a
   one-line value-type choice on the base model; reversing it is data-archaeology. Pull is only M
   (not every product handles money), but the asymmetry is maximal, which is exactly the
   high-rc/medium-pull quadrant the scaffold exists for. **meridian_dependent: false.**

6. **FWK53a api-versioning /v1 namespace** (concern; rc H, pull H). I deliberately rank the *narrowed*
   item high, not low. The narrowing — "just mount under `/v1`, the enforcement is already
   oasdiff+contracts-owned" — **concentrates** the asymmetry into the literal definition of the
   secondary tiebreak: a cheap one-time scaffold decision, catastrophic to reverse once SDKs/UIs/
   partners consume un-namespaced routes, that only the scaffold is positioned to make at t=0.
   Retrofitting a version namespace onto live consumers is a coordinated breaking change.
   **meridian_dependent: false.**

7. **audit-log / activity-trail** (concern; rc H, pull M). Dual-natured: type-B (an event not
   appended on day 1 has no backfill — the compliance substrate is only as old as the seam) *and* a
   base-model/data-layer decision (an append-only trail wired into the write path is itself
   embedded-everywhere). The combination — irreversible gap *plus* schema-grain — is why it clears
   Tier 1 where pure type-B items don't. **meridian_dependent: false.**

8. **FWK50c time — future-events wall-clock + IANA** (battery + lint; rc H, pull M). `created_at` is
   already `timestamptz` (verified), so the base case is covered; the residual is the genuinely
   irreversible part — a future event stored as pre-converted UTC loses the wall-clock + IANA zone +
   tzdb-version, and a DST-rule change later makes the original intent unrecoverable. Lower in Tier 1
   than money/external-id only because the base timestamp is already handled and the residual is a
   narrower (future-events) slice. **meridian_dependent: false.**

---

## TIER 2 — next (real asymmetry, but localized, type-B, or one notch off the base-model spine)

1. **FWK52 transactional-outbox** (battery; rc H, pull H). The Tier-1/Tier-2 boundary case. It closes
   a dual-write gap the template's *own* `webhooks/handler.py:17-20` documents, and pull is H — but it
   is **localized to the webhooks/workers path**, not embedded-everywhere across the data model. That
   localization is the whole difference from the Tier-1 base-model seams: a consumer who adopts it
   after launch re-plumbs one handler, not every table. Still high on this tier because the
   correctness gap is real and the template already names it. **meridian_dependent: false.**

2. **FWK54b data backup + restore-DRILL** (CI/ops gate; rc H, pull H). Pure type-B and a textbook one:
   a silently-broken backup has *already lost the data* by the time you need it. DATA recovery is
   explicitly out-of-scope today (deploy contract covers only code/schema rollback). The drill itself
   is cheap to add late — which is exactly why it ranks below the type-A spine — but the gap-cost is
   total. Above the other type-B items because the failure mode is irreversible data loss, not
   diligence pain. **meridian_dependent: false.**

3. **outbound-idempotency (PROMOTED from parked)** (concern/battery; rc H by my read, pull H). The
   board parked this as "cheaply addable-late"; I disagree and promote it. The Idempotency-Key
   contract embeds in *every client's retry logic* — reserving the header + a replay/dedup table from
   day 1 is one cheap decision, but retrofitting the *guarantee* after partners have integrated retry
   behavior is a client-coordinated change, and any double-charge/double-effect already incurred in
   the gap is irreversible. Type-A by the embedded-in-every-integration test. Symmetric client-facing
   partner to the outbox. **meridian_dependent: false.**

4. **product-analytics (consent-gated)** (concern; rc H, pull M). Type-B and a clean one: events not
   instrumented from day 1 have **no backfill** — the product's behavioral history simply doesn't
   exist for the un-instrumented window. A different surface from ops observability (which is covered).
   The `track()` seam + consent-records are cheap to add late, so it sits below the type-A spine, but
   the un-emitted-event gap is irrecoverable. **meridian_dependent: false** (any product wants
   day-1 events).

5. **FWK54a license-policy CI gate** (CI gate; rc H, pull M). Type-B: copyleft contamination is
   incurred *silently at first-dep-add* and surfaces only at M&A diligence, where it is
   unrecoverable (the code is already shipped under a tainted license). Net-new axis vs
   gitleaks/dependabot. The gate is one config + one assertion to add late — but the contamination
   accrued before it existed cannot be undone. Ranks below backup-drill because the gap-damage is
   legal/diligence rather than data-loss, and below analytics because it's a narrower trigger.
   **meridian_dependent: false.** *(Note: as a CI gate this propagates via upgrade — it is genuinely
   lower primary-rc than its Tier-2 neighbors; it sits here, not Tier 3, only because the gap-cost is
   irreversible in a way reviewer prompts are not.)*

6. **FWK53b cursor-pagination envelope** (concern; rc M, pull M). Return an opaque cursor envelope
   from day 1 so an offset→keyset swap stays server-internal. Type-A but narrow: the response-shape
   decision is the cheap early seam; the client-facing reshape obligation is correctly held to
   reviewer/Pact territory. rc M (not H) keeps it out of Tier 1, but it is a genuine
   embedded-in-every-client-pager decision. **meridian_dependent: false.**

7. **FWK51a frontend headless a11y/interaction primitive** (battery; rc H, pull H). **My single
   biggest judgment call.** The retrofit story is genuine — swapping the interaction/a11y foundation
   after real screens is a behavior-by-behavior multi-quarter rewrite, and a11y-by-construction is a
   classic FE retrofit horror story. But it sits closest to the consumer-local discount line (the
   consumer picks the component foundation) and the framework already committed to a Vite SPA. I keep
   it Tier 2 rather than Tier 1: it's the most defensible of the three FE items and a real
   asymmetry, but it is not base-model-grain and the consumer has more say here than on a tenant_id
   decision. **meridian_dependent: true** — pull is seeded by Meridian's interactive-UI surface; if
   that surface is thin, this drops.

8. **FWK51c frontend perf-budget CI ratchet** (CI gate; rc H, pull M). Type-B FE: bundle bloat is a
   multi-sprint excavation, but the ceiling is one config + one assertion installable late — the
   asymmetry is the *accumulated* bloat in the gap, not the add-cost. Propagates via upgrade as a CI
   gate (lower primary-rc), which is why it trails the headless primitive despite both being "FE
   foundations." **meridian_dependent: true** (only bites if Meridian ships a real FE bundle).

9. **secrets-backing + rotation/versioning + field-encryption** (concern; rc M-H, pull M). Promoted
   into Tier 2's tail because **field-encryption / crypto-shred is the clean primitive for blob and
   PII erasure** — it's upstream of the erasure story that several Tier-1 items (blob, audit, tenant)
   imply. Retrofitting field-encryption after plaintext PII exists is a re-encrypt-everything
   migration. The rotation/backing-store half is more additive (Tier-3-ish), but the encryption seam
   is type-A. **meridian_dependent: false.**

---

## TIER 3 — later but still scaffold-worthy (reviewer/CI-propagating, consumer-local, or cheap-late)

Ordered by residual asymmetry. The dividing line: everything here is either (a) reviewer/CI
enforcement that propagates via upgrade at near-zero retrofit-cost, (b) consumer-local (the consumer
picks the foundation), or (c) genuinely cheap to add when pulled.

1. **AI-agent harness — durable-agent-state** (concern; rc H, pull H). The one Tier-3 item with a
   real type-A core: a checkpointer/thread_id is upstream of HITL/memory/eval/history, and bolting
   durable state onto a stateless agent loop later is a rewrite. I keep the *cluster* in Tier 3
   because it hinges hard on whether Meridian builds agents (the harness is dead weight otherwise),
   but durable-agent-state is the piece I'd promote first if they do. **meridian_dependent: true.**

2. **i18n — string-externalization (ICU catalog)** (concern; rc H, pull H). The keystone of the i18n
   ladder, and genuinely H-retrofit onto authored content — but the *enforcement* (hardcoded-string
   rot-guard) is FWK55 reviewer-territory that propagates via upgrade, and the catalog adoption is a
   mechanical refactor a consumer can stage. Real, but the asymmetry is enforced, not scaffolded.
   **meridian_dependent: true** (only bites for a translated product).

3. **FWK51b typed FE data layer (OpenAPI→TS + query-cache)** (battery; rc M, pull H). The pull-H trap.
   The scan itself rates this **rc=M**, and it's a data-fetching *refactor* — a consumer can swap
   useEffect→query-cache later file-by-file. High pull (it replaces the antipattern the react battery
   *teaches*, confirmed: `Items.tsx` uses raw useEffect/useState/fetch) does not make it high-rc.
   Worth shipping, but not a retrofit emergency. **meridian_dependent: true.**

4. **CMS + admin/CRUD UI** (concern; rc M-H, pull M). The structured-content versioned schema has a
   type-A facet (a content model is brutal to re-shape after content exists), but the admin UI is
   additive and the whole thing waits on a content-heavy product. **meridian_dependent: true.**

5. **AI-retrieval (vector-store / RAG / GraphRAG)** (concern; rc M, pull M-H). Builds on
   pgvector+age+llm (already shipped) — the foundation is in place, so the retrofit is additive.
   **meridian_dependent: true.**

6. **FWK55 retrofit-guard reviewers** (reviewer system; rc M enforcement, pull H leverage). The
   enforcement layer *for* the Tier-1/2 seams (i18n-string, agent-tool-safety, soft-delete-erasure,
   jsx-a11y, rtl, data-export, tenant-offboarding). Genuinely useful — but it is the
   lowest-asymmetry quadrant: a pure reviewer set propagates to every consumer via upgrade at
   near-zero cost, so a consumer loses nothing by not having it today. Leverage ≠ retrofit-cost.
   **meridian_dependent: false** (it's foundational-low regardless).

7. **experimentation / rollout (flags + A/B + MVT)** (concern; rc L by my read, pull M). **I override
   the board's rc M-H tag.** The scan's *own* completeness critic explicitly downgraded this to L-M
   ("you gate new code forward, no irrecoverable history, no forced rewrite; the only irreversible
   facet — exposure logs — collapses into product-analytics, which is covered"). I side with the
   critic over the board tag and record my own **rc=L**. The textbook high-value/low-retrofit
   capability — build when pulled. **meridian_dependent: true.**

8. **in-project scaffolding (`framework add route|model`)** (tooling; rc M, pull M). The CLI is
   lifecycle-only today. Pure developer-velocity tooling — zero retrofit-cost (it generates *new*
   code; nothing embeds). Ships via upgrade. **meridian_dependent: false.**

9. **CDN + static-assets** (battery; rc M, pull M). Ties to object-storage but is build-time app
   assets, not runtime user content; additive going forward. **meridian_dependent: false.**

10. **outbound-comms (email/notifications)** (battery; rc L-M, pull M). The non-backfillable facet
    (consent/opt-out history) lands in product-analytics/consent-records; the residual
    channel/dispatcher abstraction is "add a new dispatcher" low-retrofit. **meridian_dependent:
    false.**

11. **FWK48 audit review-agents shipped INTO rendered projects** (consumer-facing calibration; rc L,
    pull M). Consumer-facing, but still calibration that propagates via upgrade — a consumer's baked-in
    reviewers improve at their next upgrade. The big-brainstorm item, but low on the retrofit lens.
    Above 46/47 only because it's consumer-facing, not maintainer-internal. **meridian_dependent:
    false.**

12. **FWK47 reviewer-audit --resume provenance guard** (maintainer tooling; rc L, pull L).
    Maintainer-facing correctness; not a builder seam at all. Sequencing note: best before FWK48's
    larger run leans on resume. **meridian_dependent: false.**

13. **FWK46 reviewer-audit unparseable-skeptic retry** (maintainer tooling; rc L, pull L).
    Maintainer-facing correctness; a dropped skeptic vote can flip an audit outcome. Not a builder
    seam. **meridian_dependent: false.**

14. **FWK45 apply deferred reviewer edits (eval-gated)** (maintainer tooling; rc L, pull L). Pure
    maintainer reviewer-tuning; no consumer-facing seam, no retrofit dimension. Tier-3 floor.
    **meridian_dependent: false.**

---

## Section D — parked-promotion calls

- **PROMOTE: outbound-idempotency** → Tier 2 (see Tier-2 #3). The board flagged it "pull H, revisit"
  and parked it as cheaply-late; I disagree on the retrofit classification. The Idempotency-Key
  contract embeds in every client's retry logic, so the *guarantee* is client-coordinated to
  retrofit and any duplicate effect incurred in the gap is irreversible — type-A, not parkable.
- **Considered, left parked: soft-delete-lifecycle.** The scan parked it as "trap avoided by
  construction," and I agree — hard-delete + an erasure/audit obligation (FWK55 reviewer-territory)
  is the safer posture; a soft-delete column added late is additive, not a forced rewrite.
- **Considered, left parked: frontend-rendering-strategy (CSR/SSR/SSG/RSC).** Genuinely H-retrofit in
  the abstract, but the framework has *already committed to a Vite SPA* — it's both consumer-local
  (the consumer owns this foundation) and foundation-locked (changing it is a different scaffold,
  not a seam this one adds). Out of scope by construction, not by under-rating.
- **Considered, left parked: the rest** (ledger, billing, published-sdk, data-backfill-jobs,
  sbom-provenance, test-factories, storybook, data-grid, read-write-split, realtime-sync/CRDT,
  enum-lookup, micro-frontends, finops, structured-output-repair, marketplace-provenance,
  telemetry-ingest-contract, frontend-design-tokens). The scan's headline reasoning holds for all of
  them — real value, but additive/drop-in/consumer-local, i.e. the low-retrofit quadrant. No
  promotion.

---

## My biggest judgment calls (where Meridian should push)

1. **Type-B items rank below their type-A peers** (license-gate, backup-drill, analytics, perf-budget
   in Tier 2; not Tier 1) even though several carry an rc-H tag. The scaffold's job is the decision
   that's expensive to *make* late; type-B decisions are cheap to make late — only the *waiting*
   costs. If Meridian weights "irreversible gap-damage" above "rising add-cost," backup-drill and
   analytics move up.
2. **Reviewer/CI-enforcement is the lowest-asymmetry quadrant** (FWK55, FWK45-48 → Tier 3) because it
   propagates via `framework upgrade` at near-zero retrofit-cost. This is the call most likely to
   feel wrong to a leverage-minded reader — I am ranking by *retrofit asymmetry*, not by value or
   reach.
3. **FWK51a headless-primitive in Tier 2, not Tier 1.** Real asymmetry, but consumer-local and not
   base-model-grain. The closest FE item to the discount line; if Meridian's UI surface is rich and
   interaction-heavy, promote it.
4. **I override the board on experimentation (rc M-H → my rc L)**, siding with the scan's own
   completeness critic that already retracted the higher tag.
5. **api-versioning (53a) is Tier 1, not a demoted scrap**, precisely *because* it was narrowed — the
   narrowing concentrates the asymmetry into the cleanest instance of the secondary tiebreak.
6. **outbox (52) is the Tier-1/2 boundary** — pull-H and template-documented, but localized to the
   webhooks/workers path rather than embedded-everywhere, so it leads Tier 2 rather than closing
   Tier 1.
