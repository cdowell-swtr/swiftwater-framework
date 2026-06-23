# Retrofit-lens prioritization — unlock-order ranking

**Date:** 2026-06-22
**Author:** independent framework-architect pass (for Meridian to respond to)
**Inputs:** the 2026-06-22 retrofit-cost horizon scan (`../2026-06-22-retrofit-cost-horizon-scan.md`) + a code re-check of the three load-bearing claims.
**Status:** draft for consumer (Meridian) response. Commits to an order; close calls resolved in-line, not hedged.

## The sort rule (how to read this)

**Primary key — retrofit asymmetry.** Rank by how *cheap-early-vs-brutal-late* each seam is for a real
consumer *product* once it has data / content / users / traffic / integrations. The cost that matters is the
coordinated cross-system migration, the *irrecoverable* precision/identity loss, the reference embedded in
every URL/webhook/FK/export. **High-stakes ≠ high-retrofit** — a valuable capability that is cheaply
addable-late ranks lower (this is the scan's own headline, and it does most of the pruning).

**Secondary key — foundational unlock-order.** Within a retrofit tier, rank a seam HIGHER when it is a
*precondition* for other board items. Building a leaf before its foundation is rework. The keystones:
identity-principal (→ authz-spine/api-keys/SSO/sessions/frontend-auth/tenant-context), external-id +
tenant-data-model (base-model decisions everything assumes), durable-agent-state (→ HITL/agent-eval/
run-history), string-externalization (→ all i18n formatting/resolution).

**The operational top-of-board:** the items that are BOTH high-retrofit AND foundational — the
"decide-once on the base/identity model" cluster. A high-retrofit *leaf* (no downstream unlock) sits
below the double-qualifiers at equal rc. *Irrecoverable* and *embedded-across-integrations* outrank
*merely-expensive-migration*.

**Code re-check (load-bearing claims, verified this pass):**
- `db/models.py` — `Item.id: Mapped[int] = mapped_column(Integer, primary_key=True)` — a bare sequential int PK. external-id (FWK50a) confirmed absent.
- same file — `created_at` is `DateTime(timezone=True)`. FWK50c's "base timestamp already covered; residual is future-events + naive-datetime lint" confirmed.
- `webhooks/handler.py.jinja:17-20` — the template's OWN comment names the dual-write gap and says "for exactly-once, adopt a transactional outbox." FWK52's premise confirmed verbatim.

The scan already code-validated the remaining "confirmed absent" claims against `batteries.py` + the template; not re-audited here.

---

## Tier 1 — scaffold NOW (highest asymmetry AND/OR foundational)

The base-model / identity / keystone decisions. Get these wrong and the fix is a coordinated migration
across data + integrations, or an irrecoverable loss.

1. **composability/shared-auth → identity-principal** (rc H · pull H). The broadest unlock on the board:
   identity-principal is the precondition for authz-spine, api-keys, SSO/SCIM, sessions, frontend-auth-storage
   AND tenant-context. Retrofitting a principal abstraction after auth is wired into every route/middleware is
   the auth-rewrite horror story. Designated-first concern. **#1 by both keys at once.**
2. **multitenancy → tenant-data-model** (rc H · pull H). `tenant_id` on every table + composite keys is a
   base-model decision; adding it after rows exist is a backfill + every-query rewrite + RLS retrofit.
   Tenant-context-propagation depends on identity-principal, so it sits just under it. *Meridian-dependent:*
   Meridian already stubbed logical separation, so the promotion timing genuinely hinges on their roadmap.
3. **FWK50a external-id** (rc H · pull H). A bare `bigserial` PK leaks into URLs, webhooks, deep-links,
   exports, and FKs the moment anything integrates; swapping to an opaque external id later is a coordinated
   cross-integration migration with references already embedded everywhere. Pure-retrofit maximum. Narrower
   *unlock* than identity/tenant (it doesn't gate a cluster) but it IS the base-model decision every
   record-shaped feature assumes → top of the base-model cluster. Keep the IDOR/authz half out (reviewer-territory).
4. **i18n → string-externalization** (rc H · pull H). The ICU-catalog keystone the whole i18n cluster
   (locale-formatting/resolution/RTL/content-translation) depends on. Brutal to retrofit onto *authored*
   content + hardcoded literals scattered through every view; the strings are already written by the time
   you notice. Foundational within its cluster.
5. **AI-agent-harness → durable-agent-state** (rc H · pull H). The checkpointer/thread_id substrate that is
   upstream of HITL interrupts, agent-eval, and run-history. Bolting durable state onto an in-memory agent
   loop after conversations/runs exist is a re-architecture; everything downstream in the harness assumes it.
6. **FWK49 object/blob storage lifecycle** (rc H · pull H). The scan's clean whole-domain miss. Stored
   keys/URLs embed in DB rows, deep-links, webhooks, exports, and client UIs — late introduction of a
   `Storage` abstraction means rewriting every reference + a content migration. Not foundational for *other
   board items*, but maximally embedded-across-integrations, so it tops the non-foundational H·H seams.
7. **FWK50b money — int minor-units + ISO-4217** (rc H · pull M). The one **irrecoverable** seam: float
   loses precision you cannot reconstruct, and late currency means backfilling against ambiguous history.
   Pull is only M, but irrecoverability outranks pull → it earns Tier 1. Battery + the float-on-`price/
   amount/total/balance` reviewer half.

## Tier 2 — next (high-retrofit, but a leaf, or downstream of a Tier-1 keystone)

8. **product-analytics → server-side `track()` seam** (rc H · pull M). Events must be instrumented from
   day 1 — there is no backfill for behavior that wasn't captured. A different surface from ops observability.
   High-retrofit (irrecoverable-by-omission), but independent (gates nothing) → top of Tier 2.
9. **audit-log/activity-trail** (rc H · pull M). Append-from-day-1 compliance substrate; you cannot
   reconstruct an audit trail for the past. Same irrecoverable-by-omission shape as analytics; lower pull.
10. **FWK51a frontend headless a11y/interaction primitive** (rc H · pull H). Swapping the interaction/a11y
    foundation after real screens exist is a multi-quarter, behavior-by-behavior rewrite. The FE analogue of
    a base-model decision. *Meridian-dependent:* their interactive-UI surface seeded this research and sets
    the urgency. (This also largely absorbs the parked `frontend-design-tokens` — see promotions.)
11. **FWK52 transactional-outbox** (rc H · pull H). Closes the dual-write gap the template's own
    `handler.py:17-20` documents. Adding exactly-once after partners depend on your event stream is a
    coordinated change to the publish path + consumer expectations. Folds into webhooks/workers; symmetric
    partner to the shipped inbox. High-retrofit but a contained seam → Tier 2 over the base-model cluster.
12. **FWK51c frontend perf-budget CI ratchet** (rc H · pull M). Bundle bloat is a multi-sprint excavation;
    the ceiling is one config + one assertion installed at commit #1. Classic high-rc / cheap-early ratchet.
13. **FWK53a api-versioning /v1 namespace** (rc H · pull H). Mounting under `/v1` is one line now vs. a
    coordinated breaking change once SDKs/UIs/partners consume unversioned routes. The *enforcement* half is
    already owned (oasdiff + contracts/api-design reviewers) → only the namespace decision is the seam.
14. **secrets-backing → field-encryption / crypto-shred** (rc M-H · pull M). Field-level encryption +
    crypto-shred is the clean erasure primitive; retrofitting encryption onto columns that already hold
    plaintext PII is a data migration + key-management bolt-on. The rotation/versioning half is more
    additive. Ranked here for the field-encryption base-model implication.
15. **FWK54a license-policy CI gate** (rc H · pull M). Copyleft contamination is incurred *silently* at the
    first dep-add and surfaces only at M&A diligence, where it is unrecoverable. Net-new axis vs gitleaks/
    dependabot. A high-rc item that outranks several high-*pull* items precisely because rc leads pull here.
16. **FWK54b data backup + restore-DRILL** (rc H · pull H). DATA recovery is explicitly out-of-scope today
    (the deploy contract covers only code/schema rollback). A silently-broken backup is only discovered when
    you need it; the drill makes that failure cheap-early. High-rc but a standalone ops gate → Tier 2.
17. **multitenancy → tenant-physical-routing (`resolve_tenant_dsn()`)** (rc H · pull H). The literal
    logical→physical promotion seam. Downstream of tenant-data-model (#2); listed separately because it is
    the specific promotion ask Meridian named. *Meridian-dependent.*
18. **AI-agent-harness → agent-tool-permission + cost-budget + guardrails** (rc H · pull H). The safety/
    governance ladder downstream of durable-agent-state; a pre-call $ gate and tool-permission scoping are
    far cheaper designed-in than retrofitted onto a live tool loop. Below durable-state (its precondition).
19. **FWK53b cursor-pagination envelope** (rc M · pull M). Return an opaque cursor envelope from day 1 so an
    offset→keyset swap stays server-internal. The client-facing reshape obligation is reviewer/Pact-territory;
    the envelope shape is the cheap early seam. rc M → below the rc-H seams.
20. **FWK51b typed FE data layer (OpenAPI→TS + query-cache)** (rc M · pull H). **A deliberate inversion:**
    despite pull H, this sits *below* the rc-H FE items (51a/51c). It replaces the useEffect/useState fetch
    antipattern the react battery teaches — a painful but *recoverable* refactor, not an irrecoverable or
    cross-integration migration. High demand, medium retrofit-cost → rc leads.
21. **experimentation/rollout (flags + A/B + MVT)** (rc M-H · pull M). The enabler for parallel
    multi-agent/engineer build streams. Flag plumbing is moderately retrofittable; the A/B assignment-history
    is the stickier part. Mid-board.

## Tier 3 — later, but still scaffold-worthy (or: enforcement that rides `upgrade`)

22. **FWK55 retrofit-guard reviewers** (rc M as enforcement · pull H leverage). High leverage, but a reviewer
    is only useful once the seam it guards exists, and it propagates to every consumer via `upgrade` at any
    time → low cost-of-delay, downstream of its seams. **Each guard should land alongside its seam**
    (i18n-reviewer with string-externalization, agent-tool-safety with tool-permission, soft-delete-erasure
    with the erasure seam, jsx-a11y/rtl with the FE primitive). Not a Tier-1 foundation despite pull H.
23. **FWK50c time future-events (wall-clock + IANA)** (rc H · pull M). Genuinely high-rc *in the abstract*,
    but the base `created_at` is already `timestamptz`, so the residual is narrow: future-events stored
    wall-clock+IANA+tzdb-version (not pre-converted UTC) + a naive-`datetime.utcnow()` lint. Small surface,
    largely lint-enforceable → Tier 3 despite the rc-H tag.
24. **AI-retrieval (vector-store / RAG / GraphRAG)** (rc M · pull M-H). Builds on the existing pgvector + age
    + llm batteries, so the foundation is already present; the retrieval layer itself is additive when pulled.
    rc M.
25. **CMS + admin/CRUD UI** (rc M-H · pull M). The editor-agnostic versioned content schema is the
    higher-rc half (content authored against an unversioned schema is sticky); the admin UI FastAPI lacks is
    additive. Net mid-rc.
26. **CDN + static-assets** (rc M · pull M). Ties to object-storage (FWK49); largely additive once the
    `Storage` abstraction exists. Build-when-pulled-ish but scaffold-worthy as the serving half.
27. **in-project scaffolding (`framework add route|model`)** (rc M · pull M). The CLI is lifecycle-only
    today. Pure DX leverage; near-zero retrofit cost (you can always add the generator later) → low on the
    board, kept only because it compounds every other seam's adoption.
28. **outbound-comms (email/notifications)** (rc L-M · pull M). Low retrofit cost — a drop-in capability when
    a consumer needs it. Scaffold-worthy for consistency, not urgency.
29. **AI-eval for the builder's OWN agents** (rc M · pull M). Ship the framework reviewer-eval harness to
    consumers. Overlaps FWK48; additive consumer tooling, propagates via upgrade.

### Section A — maintainer-facing reviewer-audit tooling (the retrofit lens does NOT apply)

FWK45–48 are **maintainer/internal tooling**, not consumer product seams. There is no product data /
identity / integration to migrate, and reviewer prompts (including FWK48's consumer-facing calibration)
propagate to every project via `framework upgrade` at any time. So the cheap-early-vs-brutal-late lens
is structurally inapplicable — they are **Tier 3 regardless of being "ready" in `Next`** (readiness must
not inflate priority). Their order among *themselves* is **internal-pipeline dependency, not retrofit:**
FWK46 + FWK47 harden the audit pipeline → FWK48 leans on resume/parse-robustness → so 46/47 precede 48;
FWK45 is independent tuning. All `meridian_dependent = false`.

30. **FWK46** reviewer-audit unparseable-skeptic retry — pipeline-correctness; precondition for a reliable FWK48 run.
31. **FWK47** reviewer-audit `--resume` provenance guard — pipeline-correctness; "best landed before FWK48's larger run leans on resume."
32. **FWK48** audit review-agents shipped INTO rendered projects — consumer-facing calibration, but ships via upgrade; downstream of 46/47.
33. **FWK45** apply deferred reviewer edits (eval-gated) — independent maintainer tuning; lowest cost-of-delay.

---

## Parked-promotion calls (Section D)

I promote **two** and explicitly hold the rest (the scan's pruning was mostly right — promoting everything
would defeat the lens).

- **outbound-idempotency → promote (Tier 2, rides with FWK52).** The strongest D candidate: the scan itself
  flagged it `pull H` "for revisit," and it is the client-facing twin of the transactional-outbox
  (Idempotency-Key replay contract). Once partners integrate against your write endpoints, adding an
  idempotency contract is a *breaking* API change — embedded-across-integrations, exactly the retrofit shape
  the scan under-weighted by calling it "cheaply addable-late." Land it with FWK52.
- **frontend-design-tokens → fold into FWK51a, do not promote standalone.** The scan's own FE researcher
  called design-system-adoption-late "the canonical retrofit horror story," then parked tokens as "flat
  adoption cost" — an internal tension. I reconcile it rather than promote: the headless-primitive (FWK51a)
  IS the early seam that absorbs the horror story (it's the interaction/a11y foundation a token layer paints
  onto). A bare token layer without the primitive is genuinely flat-cost to add later, so it stays parked —
  but FWK51a's brainstorm should explicitly carry the token-layer slot so the "horror story" is covered.

Held parked (with the reconciliation):
- **soft-delete-lifecycle** — the scan's counter holds: the erasure obligation is reviewer-enforced (FWK55),
  and a base-model `deleted_at` column is itself cheap to add later (no irrecoverable loss, no embedded
  references). The trap (querying past soft-deleted rows) is a reviewer catch, not a scaffold. Stays parked.
- **read-write-split, realtime-sync/CRDT, ledger, billing, published-sdk, data-backfill-jobs,
  sbom-provenance, test-factories, storybook, data-grid, enum-lookup, micro-frontends, finops,
  structured-output-repair, marketplace-provenance, telemetry-ingest-contract, frontend-rendering-strategy**
  — agree with the scan: real value, but additive-when-pulled / consumer-local / the hard part is a
  consistency problem the seam doesn't solve. No promotion.

---

## My biggest judgment calls (the ones Meridian should push on)

1. **identity-principal #1 over external-id.** Both are base-model decisions with H retrofit cost. I put
   identity first on the *unlock* tiebreak — it gates the entire auth + tenant-context cluster, where
   external-id gates "only" the record surface. If Meridian's near-term is record/integration-heavy but
   single-tenant single-auth, external-id (#3) is the one to pull first; say so and I'll reorder.

2. **money (FWK50b) in Tier 1 at pull M.** I let *irrecoverability* override pull. Float precision loss
   cannot be reconstructed; that asymmetry is stronger than several H-pull items. If Meridian has no money
   surface at all on the roadmap, this is the most defensible single demotion to top-Tier-2 — it's
   meridian-adjacent in a way the foundational seams are not. (I still kept `meridian_dependent=false`
   because the *retrofit logic* holds regardless of Meridian; the only thing their roadmap changes is whether
   the seam is exercised, not whether it's right.)

3. **license-gate (FWK54a, rc H/pull M) above typed-FE-data-layer (FWK51b, rc M/pull H).** The clearest
   "rc leads pull" inversion on the board. Copyleft is silent-at-t0 and unrecoverable at diligence; the FE
   data-layer is high-demand but a recoverable refactor. If the consumer optimizes for *felt* developer pain
   over *latent* legal risk, they'll disagree — but the framework exists to bake the high-asymmetry seam.

4. **FWK55 (reviewers) in Tier 3 despite pull H.** A reviewer is leverage, not a seam: it's only useful once
   its target seam exists and it ships via upgrade with ~zero cost-of-delay. Pull-H tempts a higher rank;
   the retrofit lens says no. The mitigation is sequencing — land each guard *with* its seam, not as a batch.

5. **Section A pinned to Tier 3 wholesale.** The temptation is to rank FWK45–48 by their `Next`-readiness.
   The lens forbids it: maintainer tooling has no product to retrofit. I rank them only by internal pipeline
   dependency. This is the call most likely to read as "burying ready work" — it's deliberate.
