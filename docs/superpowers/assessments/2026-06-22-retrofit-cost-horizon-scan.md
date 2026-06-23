# Retrofit-cost horizon scan — multi-agent research plan

**Date:** 2026-06-22
**Status:** Research plan (pre-run). Findings appended to this file on execution.
**Origin:** the "what else might be missing from our present vantage" horizon brainstorm.
The composability/shared-auth work is one output of that brainstorm; this is a second —
an *externally-grounded* sweep for high-retrofit-cost seams we haven't named.

## Purpose

Escape our internal vantage. The framework's blind spots are, by definition, the seams we
didn't think to build — so inferring gaps from our own template only finds what we already
half-see. Industry has already paid for the rest in postmortems and "things I'd design in
from day one" retrospectives. This sweep mines that body of experience two ways:

1. **Principle-driven** — the "hard-to-reverse / day-2 / get-this-right-early" canon → a list
   of high-retrofit-cost seams, each with *why adding it late is expensive*.
2. **Comparative** — what mature opinionated scaffolds bake in *by default* → diffed against
   our board. They've absorbed years of retrofit pain into their defaults; the diff is the
   most direct blind-spot finder.

**Deliverable:** an expanded, code-validated candidate board — every item tagged
`pull × retrofit-cost` and given a disposition — deduped against our current board, ready to
triage into PLAN `Next` stubs. Nothing is committed to PLAN by this run; triage is a separate
human step.

## Goals / Non-goals

**Goals**
- Find the high-retrofit-cost seams our domain-by-domain inference misses (esp. via the
  breadth-first guard — see roster).
- Rank the *whole* board by an externally-grounded retrofit-cost estimate, not gut feel.
- Surface what competing scaffolds make first-class that we don't.

**Non-goals**
- No designing of any candidate (each gets its own brainstorm later).
- No PLAN entries written by this run (triage follows).
- No re-litigating already-covered surfaces (deploy contract, obs stack, load/k6, migrations
  + expand-only guard, rate-limiting, compose isolation, Pact contracts, supply-chain) except
  to *confirm* coverage.

## The board we're extending (dedup baseline)

Researchers receive this list and must flag overlaps rather than re-surface these:

- **First-class concerns:** composability/shapes/shared-auth (in flight) · multitenancy
  (logical→physical; Meridian already stubbed) · experimentation/rollout (feature flags +
  A/B + MVT — enables parallel build streams) · product analytics (consent-gated) · i18n/l10n
  · in-project scaffolding · secrets-backing.
- **Batteries:** AI-retrieval (vector-store / RAG / GraphRAG — builds on `pgvector` + `age` +
  `llm`) · CMS + admin/CRUD UI · CDN + blob/static assets · audit-log/activity-trail ·
  outbound-comms (email/notifications).
- **Already-Next:** AI-eval for the builder's own agents (likely extends FWK48).
- **User-emphasized as high-value:** audit trail ("huge") · *versioning of everything*
  (schema / event / API / record) · idempotency (esp. with replication).
- **My predicted-likely hits (for the agents to confirm/deny):** money/decimal/currency ·
  time/UTC/timezone/DST · ID strategy (sequential-exposed vs UUID/ULID) · soft-delete &
  data-lifecycle · event/schema versioning.

## Disposition taxonomy

Every surviving candidate is classified — this is how we avoid scaffolding things better
handled elsewhere:

| Disposition | Meaning | Exemplar |
|---|---|---|
| **battery** | opt-in capability surface that fits today's model | blob storage, FTS |
| **concern** | posture-level; scaffolded early (esp. high-retrofit) | multitenancy, i18n |
| **reviewer-enforced** | better *caught by an agentic reviewer* than scaffolded | **GDPR-erasure → `data-lineage` + `compliance`/`privacy`** (there is no "data-governance" agent; these own it) |
| **park** | real but YAGNI until a consumer pulls | billing, multi-region |
| **reject** | already covered, or not genuinely high-retrofit | (deploy, rate-limit) |

The **reviewer-enforced** row is the key refinement: an implementation-specific obligation
(how *this* app wires erasure) is enforced at review time against real diffs; it doesn't want
a generic scaffold. Agents must consider this disposition, not default everything to battery.

## Agent roster

**Phase 1 — parallel research (web-enabled; each blind to the others).** Tokens are not a
constraint here — prefer depth: each agent does *thorough* search+fetch (multiple angles, real
eng-blog evidence, primary docs), writes its **own findings file**, and returns a structured
summary for synthesis.

*Group A — domain researchers (10).* Each mines the canon + real-world evidence for its domain.

1. **Data-model & correctness retrofit** — IDs (sequential-exposed vs UUID/ULID, enumeration
   leakage), money/decimal/currency, time/UTC/tz/DST, soft-delete & data-lifecycle,
   record/schema versioning, nullability/enum evolution.
2. **Distributed-systems & data-flow retrofit** — idempotency (esp. with replication),
   at-least-once vs exactly-once, event/message backbone, outbox/inbox, eventual-consistency
   boundaries, API versioning, pagination/cursoring, read-replica & read/write split.
3. **Identity & access retrofit** — authn, authz (RBAC/ABAC/ReBAC), sessions/tokens, API
   keys, multi-product SSO / shared auth, tenant-scoped permissions.
4. **Multitenancy & data-isolation retrofit** — logical→physical separation, row-level
   security, per-tenant keys/encryption, noisy-neighbor, tenant export/portability/offboarding,
   sharding.
5. **Privacy / compliance / security retrofit** — audit trail/activity log, data residency,
   consent, field-level encryption, PII tokenization, secrets management, key rotation.
   (Classify erasure-type obligations as *reviewer-enforced*, not battery.)
6. **Internationalization & content retrofit** — i18n/l10n (UI + content + DB), number/date/
   currency formatting, RTL, pluralization, CMS, timezone-aware display.
7. **Product / growth / martech retrofit** — product analytics/events, experimentation
   (flags/A·B/MVT), attribution & consent-gated pixels, admin UI, feature management.
   (Flag the privacy tension; resolution is expose-capability-safe-by-default.)
8. **Frontend architecture & rendering retrofit** *(NEW)* — rendering strategy (CSR/SSR/SSG/
   RSC/streaming — brutal to switch late), routing, state management & data-fetching/caching,
   form/validation patterns, bundle/perf budgets, code-splitting, real-time/optimistic-UI &
   collab sync, micro-frontends / module federation (the FE face of composability + parallel
   streams).
9. **Design system & interactive components retrofit** *(NEW)* — adopting a design system /
   token layer late (the canonical FE retrofit horror story), component-library strategy,
   theming/dark-mode, accessibility-by-construction, complex interactive widgets (tables/
   editors/drag-drop/virtualized lists), Storybook/visual-regression, headless-vs-styled.
   Seeded by Meridian's interactive-UI surface.
10. **Agent-framework / harness retrofit** *(NEW)* — what an agent harness must bake in early:
   eval harness, tool-loop observability/tracing, memory/state/conversation persistence, tool
   registry & permissioning, guardrails/safety, multi-agent orchestration, human-in-the-loop
   checkpoints, cost/budget governance, structured-output/contract enforcement, tool-call
   idempotency/retry, prompt/version management. Ties to the `llm`/`agents` batteries, FWK48,
   and the parallel multi-agent-streams thread.

*Group B — comparative scans (3).* Each surveys an ecosystem for what it bakes in *by default*,
then diffs vs our board → a default-feature matrix + implied gaps.

11. **Backend / fullstack scaffolds** — Cookiecutter Django, Ruby on Rails, Phoenix,
   create-t3-app, Encore, Nx/Turborepo (composition angle), SaaS starters (SaaS Pegasus,
   Makerkit, ShipFast).
12. **Frontend-first scaffolds** *(NEW)* — create-next-app/Next.js, Remix, Astro, TanStack
   Start, RedwoodJS, Blitz, Refine, shadcn/ui-based starters, Vite framework templates, and
   design-system/Storybook starters. The FE-default conventions we lack.
13. **Agent frameworks / harnesses** *(NEW)* — LangGraph, CrewAI, AutoGen/AG2, Mastra, Vercel
   AI SDK, LlamaIndex, Claude Agent SDK, OpenAI Agents SDK, Pydantic AI, Letta/MemGPT (memory),
   Dify. What they make first-class that our `agents` battery doesn't.

*Group C — breadth-first guards (3, different seeds — the anti-blind-spot agents).*

14–16. **Outlier / un-enumerated-domain sweep.** Explicitly NOT constrained to Groups A–B.
   Each seeded with the domain list + board, then: "Find high-retrofit-cost architectural
   decisions that fall OUTSIDE every domain above — the categories our taxonomy failed to
   enumerate. Range across industries (fintech, healthcare, marketplaces, real-time/gaming,
   IoT, data platforms, regulated/gov), non-functional axes (accessibility, performance
   budgets, cost/FinOps, disaster-recovery RPO/RTO, data portability, supply-chain, licensing),
   and lifecycle stages we ignore. Name the *domain* we missed and the seam within it." Three
   seeds (with varied framings) widen the net.

**Phase 1 output (every agent).** Each agent **writes its own file** —
`docs/superpowers/assessments/retrofit-scan/phase1-NN-<slug>.md` (full human-readable
findings) — *and* returns this structured summary for synthesis:
```
findings: [
  { name, domain,
    claim,              # why adding this late is expensive (the retrofit story)
    retrofit_cost,      # H | M | L  + one-line justification
    early_scaffold,     # what baking it in early concretely looks like
    evidence,           # sources / real-world examples (URLs, eng-blogs, the canon)
    proposed_disposition, # battery | concern | reviewer-enforced | park
    overlaps }          # which board item / existing reviewer it overlaps, or "new"
]
```

**Phase 2 — synthesis + the code-validation guard (single agent + a controller cross-check).**
Reads every `phase1-*.md` + the structured summaries; dedups across findings and against the
board. Then the **hard guard**: every candidate is cross-checked against
`src/framework_cli/batteries.py` + the template *before it lands* — research proposes, our code
disposes. (We have assumed a gap twice and reality had a strength: the deploy contract and
rate-limiting. The guard exists to stop a third.) Writes the merged candidate list to
`retrofit-scan/SYNTHESIS.md`.

**Phase 3 — adversarial disposition filter (parallel; tokens-to-burn → *perspective-diverse*,
2 lenses per *new* candidate, each writing its verdict file).** Lens 1 — "is this *genuinely*
high-retrofit-cost for this framework's consumers, or a generic nice-to-have?" Lens 2 — "is
this already covered, or better-left-to-an-existing-reviewer than scaffolded?" Both default
skeptical. A candidate survives only if neither lens rejects it; the lenses jointly assign the
disposition. Verdicts → `retrofit-scan/phase3-<candidate-slug>.md`.

**Phase 4 — completeness critic (after the merged board exists).** The closing breadth check,
now able to see everything found: "Given this full board, what whole domain or non-functional
axis is STILL missing?" Anything it names is a finding (or a note that the net held). Writes
`retrofit-scan/COMPLETENESS.md`.

## Pipeline shape

```
phase 1: parallel( 10 domain researchers + 3 comparative scans + 3 breadth guards )  # 16, each writes phase1-*.md
phase 2: synthesize + dedup-vs-board + CODE-VALIDATE each candidate     -> SYNTHESIS.md
phase 3: parallel( 2 perspective-diverse skeptics per NEW candidate )   -> phase3-*.md (dispositioned)
phase 4: completeness critic over the dispositioned board              -> COMPLETENESS.md
output:  expanded board, tagged pull × retrofit-cost, deduped -> appended here as Findings
```
Phase 1 is a barrier (synthesis needs all findings to dedup). Phase 3 fans out per candidate.
All artifacts land under `docs/superpowers/assessments/retrofit-scan/`; the final triage-ready
board is appended to *this* file.

## Output shape & tagging

Per-agent files under `retrofit-scan/` (`phase1-*`, `SYNTHESIS.md`, `phase3-*`,
`COMPLETENESS.md`); the consolidated board appended to this file as **Findings**. Each
surviving candidate:
`name · disposition · pull (H/M/L) · retrofit-cost (H/M/L) · one-line claim · evidence · overlaps`.

Ordering falls out of the lens: **retrofit-cost is weighted up** (the scaffold's reason to
exist is the high-retrofit / maybe-low-pull quadrant), so a high-retrofit/medium-pull seam can
outrank a low-retrofit/high-pull battery. The triage step turns the top band into PLAN stubs,
grouped (not one-per-bullet — e.g. one "AI-retrieval" stub that explodes into 3), same pattern
as FWK45–48.

## Sources / starting points (for the researchers)

DDIA (Kleppmann); the 12-factor app; martinfowler.com (evolutionary DB, strangler, CQRS);
the cloud well-architected frameworks (AWS/GCP/Azure); eng blogs with hard-won retrofit
stories (Stripe on idempotency & money, Shopify/GitHub on multitenancy & IDs, Figma/Notion on
data model); OWASP ASVS (auth); GDPR/data-residency retrofit write-ups. Frontend: the rendering
strategy / RSC / design-system-adoption literature, web.dev/Core-Web-Vitals perf budgets, the
WAI-ARIA APG. Agent harnesses: the framework docs above (LangGraph/Mastra/Claude Agent SDK/etc.)
+ agent-eval/observability writing. Plus every scaffold/framework's own docs/READMEs for the
comparative scans. Agents use WebSearch + WebFetch.

## Scale & cost estimate

~16 Phase-1 agents (10 domain + 3 comparative + 3 breadth) + 1 synthesis + ~2 lenses ×
~20–30 new candidates (~40–60 skeptics) + 1 completeness ≈ **60–80 agents**. Phase-1 agents
are web-heavy and run deep (tokens-to-burn → depth over economy). Order-of-magnitude
**~1–2M tokens**. The user has explicitly chosen better outputs over conservation; this is
sized for coverage, not thrift.

## Risks

- **Generic-listicle drift** — mitigated by the adversarial filter + the "for *this*
  framework's consumers" framing + the code-validation guard.
- **False gaps** — mitigated by the Phase-2 cross-check against `batteries.py` + template.
- **Taxonomy blind spot** — the whole reason for the breadth-first guards + the completeness
  critic; still, two breadth seeds is not a proof of completeness, only a strong sweep.
- **Stale source claims** — evidence is captured per finding so triage can weigh it; we don't
  act on a claim without our own code check.

---

## Findings

**Run:** 76 agents, 3.67M tokens, 727 tool calls, ~47 min (run `wf_93876f54-0ff`). 16/16 Phase-1
agents → 105 findings → **76 deduped candidates** (29 net-new, 47 confirming/decomposing existing
board items) → 58 adversarial verdicts → 1 completeness pass. Per-agent detail:
`retrofit-scan/phase1-*.md`; full deduped board: `retrofit-scan/SYNTHESIS.md`; closing check:
`retrofit-scan/COMPLETENESS.md`. Dispositions cross-checked against `batteries.py` + the template
(controller pass) — survivors below are code-confirmed net-new.

### The headline: the lens pruned as much as it found

The `genuine-high-retrofit` skeptic rejected 19 of 29 new candidates, almost all with the same
correct reasoning — **high-stakes ≠ high-retrofit-cost**. A capability can be important yet
*cheaply addable late* (additive CI step, drop-in utility, consumer-local refactor), which means
it should be **built when a consumer pulls, not scaffolded early**. That separation is the whole
point of the lens, and it reclassifies a chunk of our own board.

**Build-later (real, but LOW retrofit-cost → do NOT scaffold early):** `ledger`, `billing`
(Stripe, vendor-locked business domain), `published-sdk` (the committed `openapi.json` seam
already exists), `data-backfill-jobs` (drop-in when you hit your first big table), `sbom-provenance`
(additive CI, propagates via upgrade), `test-factories` (file-local test refactor),
`storybook-vrt` (flat adoption cost), `data-grid`, `read-write-split` (the hard part is a
consistency problem the split doesn't solve), `realtime-sync`/CRDT (niche local-first identity).
These stay **parked**; the value is real but the urgency the scaffold exists to capture is not.

### A. New scaffold-early seams that SURVIVED adversarial (code-confirmed net-new)

These are genuinely-high-retrofit AND not covered — the real additions:

| Seam | rc·pull | Why early-only | Status |
|---|---|---|---|
| **external-id** — opaque non-seq ID on base model, separate from the authz check | H·H | bigserial leaks into URLs/webhooks/deep-links/FKs; the IDOR half is reviewer-territory (do not conflate) | base `Item` exposes a bare int PK |
| **transactional-outbox** | H·H | the template's *own* `handler.py:17-20` names this exact dual-write gap | confirmed unshipped |
| **money** — int minor-units + ISO-4217 value type | H·M | float loses precision irrecoverably; late currency = backfill vs ambiguous history. Battery + reviewer-half (float on `price/amount/total`) | none today |
| **frontend-headless-primitive** — React-Aria/Base-UI a11y layer | H·H | swapping the interaction/a11y foundation after real screens = multi-quarter rewrite | react battery is bare `div`/semantic HTML |
| **typed-frontend-data-layer** — OpenAPI→TS client + query cache | M·H | the react battery currently *teaches* the `useEffect/useState` fetch antipattern every consumer copies | zero codegen deps confirmed |
| **frontend-perf-budget** — bundle/CWV CI ratchet | H·M | clawing back a bloated bundle is a multi-sprint excavation; the ceiling is one config + one assertion | only runtime RUM, no build budget |
| **license-policy-gate** — SPDX copyleft CI gate | H·M | copyleft contamination is incurred silently at t=0, surfaces at M&A diligence; net-new axis vs gitleaks/dependabot | confirmed none |
| **api-versioning** (NARROWED) — the `/v1` namespace + compat posture | H·H | the additivity-*enforcement* half is already owned (oasdiff + `contracts` reviewer); only the namespace decision is the seam | — |
| **data-backup-restore-drill** — runnable restore DRILL (RPO/RTO) | H·H | deploy contract covers code/schema rollback; DATA recovery is explicitly out-of-scope today | confirmed unshipped |
| **cursor-pagination** (PARTIAL) — opaque cursor envelope from day 1 | M·M | the response-reshape obligation is reviewer-territory (Pact/`contracts`); the envelope-shape is the cheap early seam | — |

### B. The completeness MISS — a genuine whole-domain gap our taxonomy lacked

- **Object / blob storage lifecycle** (H·H) — upload → validate/scan → store → serve(presigned/keyed)
  → erase, behind a `Storage` abstraction (dev-local ↔ S3/GCS/MinIO). The board had blobs ONLY as
  "a store to enumerate for erasure," never as a seam. **Confirmed absent** (no boto3/minio/presigned/
  upload payload). Distinct from the CDN/static-assets battery. *This is the clean catch the breadth
  guards + completeness critic existed for.*
- **(secondary, med-confidence)** content-translation **data** model — a translations dimension on
  domain data, distinct from the UI-string `t()` catalog. Fold into the i18n concern.

### C. Existing board items — CONFIRMED + decomposed (47 overlaps)

The scan didn't just confirm the board — it gave each item its internal seam-ladder, ready for
when each gets its own brainstorm:

- **Multitenancy (logical→physical):** tenant-data-model (`tenant_id` everywhere + composite keys) ·
  tenant-context-propagation (auth→request→DB contextvar, fail-closed) · tenant-rls (Postgres RLS
  defense-in-depth) · **tenant-physical-routing** (`resolve_tenant_dsn()` — the literal board ask) ·
  tenant-fairness · tenant-offboarding(reviewer) · data-residency. A complete promotion ladder.
- **Shared-auth / composability:** identity-principal (multi-identity from day 1) · **authz-spine**
  (default-deny chokepoint at the data layer) · session-revocation · api-keys (machine principals) ·
  enterprise-sso-scim (deprovisioning is the under-appreciated half) · frontend-auth-storage.
- **AI-agents (a real harness roadmap):** durable-agent-state (checkpointer/thread_id) · agent-memory ·
  agent-tool-permission · human-approval (HITL interrupts) · agent-guardrails · agent-cost-budget
  (pre-call $ gate) · genai-trace-schema (OTel `gen_ai.*` spans — gap *inside* covered observability).
- **i18n:** string-externalization (ICU catalog — the keystone) · locale-formatting · locale-resolution ·
  encoding · direction-rtl.
- **product-analytics:** server-side `track()` seam · marketing-capi · consent-records.
- **secrets:** rotation/versioning · field-encryption (crypto-shred = the clean erasure primitive).
- **CMS/admin:** structured-content (editor-agnostic versioned schema) · admin-crud-ui.

### D. Reviewer-enforced (extend the reviewer system, don't scaffold)

i18n-reviewer (hardcoded-string/naive-datetime/float-money rot-guard) · agent-tool-safety-reviewer ·
soft-delete-erasure-policy · tenant-offboarding obligation · data-export-portability · rum-trace-correlation ·
frontend-a11y-static-lint (jsx-a11y) · frontend-direction-rtl. (GDPR-erasure confirmed already owned by
`data-lineage`/`compliance`/`privacy` — the disposition taxonomy held.)

### E. Proposed triage → PLAN stubs (for sign-off)

Grouped, exploding-later (the FWK45–48 pattern), ordered by retrofit-cost × pull:

1. **Object/blob storage lifecycle** — the completeness miss; clean new battery+concern. *(new stub)*
2. **Data-correctness base-model seams** — external-id + money + time-future-events: the "decide once on
   the base model" cluster. *(new stub, explodes to 3)*
3. **Frontend foundations** — headless-primitive + typed-data-layer + perf-budget: the react battery's
   missing spine. *(new stub, explodes to 3)*
4. **transactional-outbox** — closes the gap the template already documents; folds into webhooks/workers. *(new stub)*
5. **license-policy-gate** + **data-backup-restore-drill** — two standalone CI/ops gates. *(new stub(s))*
6. **Retrofit-guard reviewers** — i18n-reviewer + agent-tool-safety + soft-delete-erasure + cursor/api-version
   obligations: extend the reviewer system. *(new stub)*
7. **Existing board items** (multitenancy, shared-auth, i18n, AI-agents, product-analytics, secrets, CMS) —
   no new stubs; their `Next`/brainstorm entries inherit the decomposition in §C.
8. **Parked** (build-later, §headline) — recorded here, not stubbed.
