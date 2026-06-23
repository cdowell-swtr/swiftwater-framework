# Completeness Critic — Retrofit-Cost Horizon Scan

**Role:** adversarial completeness check on the consolidated candidate board (16 research
agents + synthesis). Question: what whole DOMAIN or NON-FUNCTIONAL AXIS is STILL missing —
a category of high-retrofit-cost seam that NONE of the candidates touch?

**Bar applied to every candidate gap (both must hold):**
1. **No board row touches it** — not as a seam, not decomposed across covered rows.
2. **Retrofit cost is genuinely H** — irreversible-history loss, or a pervasive forced
   rewrite (the property the *whole scan* measures). An item that is high-value-from-day-one
   but cheap-to-add-late is NOT a retrofit miss; filing it as one is the false positive the
   task penalizes as much as a real omission.

---

## VERDICT

The net held remarkably well across the security / data-model / identity / multitenancy /
privacy / i18n / frontend / agents / lifecycle axes. **One genuine whole-domain miss
survives the bar: user-uploaded / generated-content FILE & OBJECT STORAGE (the upload→store→
serve→erase lifecycle).** One additional **H-retrofit facet** is untouched and worth a
flagged secondary: a **content-translation data model** (a translations dimension on content
tables, distinct from the UI-string catalog the i18n rows already cover).

Several plausible-sounding axes were checked and deliberately NOT filed, because they fail
bar (2) — they are additive/low-retrofit (feature flags, server-side caching, full-text
search, green/carbon) — or fail bar (1) — they are decomposed across covered rows
(notifications, optimistic-concurrency). The disciplined accounting of those is below, so the
"net held" claim is auditable rather than assumed.

---

## HEADLINE MISS — File / object storage lifecycle (user-uploaded & generated content)

**Domain:** blob/object storage; file upload, validation, serving, and erasure.
**Retrofit cost:** **H.** **Disposition:** new battery (+ a thin reviewer/erasure obligation).

**The seam.** A new product stores user-uploaded or system-generated binary content
(avatars, attachments, exports, reports, generated documents/images). The high-retrofit
decision is the **storage abstraction + upload lifecycle**, made before the first file lands:

- A `Storage` protocol with a **dev-local backend ↔ S3/GCS/MinIO backend** swap (the
  template ships no upload/object-storage payload at all — verified: no `boto3`/`minio`/
  presigned/upload code anywhere in `src/framework_cli/template/`).
- **Stored keys/URLs are content references** embedded in DB rows, deep links, webhooks,
  exports, and client UIs. A provider-coupled URL or a raw local path baked into those
  references is exactly the "embedded everywhere, can't change post-integration" class the
  board already recognizes for `external-id` — but for blobs.
- **Tenant-scoped prefixes / per-tenant buckets** decided up front, or every object is in a
  flat namespace that later isolation (and `tenant-physical-routing`) can't cleanly carve.
- **Presigned/keyed serving** vs streaming-through-the-app (a security + cost fork that, once
  the app proxies bytes, is re-plumbed under load).
- **Upload validation / size limits / virus-scan-quarantine / content-addressing** — a
  quarantine/scan step is structureless to insert after files flow straight to durable
  storage (same shape as the agent-guardrails "no interception point" argument).
- **Blob erasure + retention** — the GDPR-erasure path for binary content. Crypto-shred
  (`field-encryption`) is the clean primitive, but the blob store has to be a *registered,
  enumerable* surface for `tenant-offboarding` / `data-export-portability` to reach it.

**Why it passes bar (1) — no row touches it.** Blobs appear on the board ONLY as a *store to
enumerate for erasure/export*: `tenant-offboarding` ("untracked blobs/search/analytics
accumulate") and the merged-stores language in `data-export-portability`. Both rows
**presuppose a blob store already exists** and ask only "is this diff's new store wired into
erasure?" Neither proposes the storage abstraction, the upload pipeline, the
serving/presign fork, or the key-reference discipline. The seam itself is unaddressed.

**Why it is NOT the CDN/static-assets battery** (referenced at `frontend-rendering-strategy`,
SYNTHESIS ~L359). That axis is **build-time static APP assets** — the JS/CSS/images the app
itself ships, served off a CDN. This is the **runtime user-content lifecycle**: bytes a user
or the app produces *after* deploy, stored durably, referenced from data. Different axis,
different retrofit class.

**Why the cost is H, not additive.** Once files are written to a provider-coupled location
and their keys/URLs are scattered through DB rows + client links + exports, introducing the
abstraction means a backfill/migration of every stored reference and a coordinated client
change — and any object written before the erasure/quarantine seam existed sits in backups
and replicas with no clean delete path. That is both an irreversible-history tail and a
pervasive forced rewrite.

**Pull (Meridian).** **M–H.** A rich multi-product platform with documents/exports/reports/
avatars almost certainly grows a binary-content surface; not guaranteed core, hence not H.

---

## FLAGGED SECONDARY — Content-translation data model (not the UI-string catalog)

**Domain:** i18n/l10n — *translatable content/data*, as opposed to UI chrome.
**Retrofit cost:** **H.** **Disposition:** concern (a translatable-content data-model pattern)
+ reviewer fit. **Confidence: lower than the headline** — see caveat.

The five i18n rows on the board are, on inspection, **all about UI/system text**:
`i18n-string-externalization` (the `t()` catalog), `i18n-locale-formatting` (CLDR numbers/
dates/currency), `i18n-locale-resolution` (request locale middleware), `i18n-encoding`
(UTF-8), and `frontend-direction-rtl`. **None addresses a translations dimension on the
domain DATA model** — translatable fields on content tables, a per-locale row/`translations`
child table, a fallback chain (requested-locale → default-locale → source), and tenant/locale
interaction.

This is genuinely H-retrofit: adding a translations dimension *after* content exists is a
schema-wide change plus a backfill of existing single-language rows into the new structure,
and queries/serializers across the app must learn to resolve the locale fallback. It is the
same irreversibility class as `tenant-data-model` (widen a model after rows exist), just on
the locale axis.

**Caveat (why secondary, not headline).** The framing asks for a *whole missing DOMAIN*.
i18n is a **covered domain** — this is an uncovered *facet within it* (content vs UI text).
It is a real gap the i18n rows do not reach, but it is not a category the scan was blind to,
so it is filed as a clearly-labeled secondary rather than a co-equal headline. **Pull: M**
(only products with translated user-facing content; for an API/dashboard platform, often
not core).

---

## DISCIPLINED ACCOUNTING — axes checked and deliberately NOT filed

Filing a false "you missed X" is as costly as missing a real one. These survived
consideration and were rejected, with the bar each fails:

- **Feature flags / progressive delivery / runtime config — REJECT (fails bar 2).**
  This is the textbook *high-value-from-day-one, LOW-retrofit-cost* capability — the opposite
  of what this scan measures. There is no irrecoverable history (you gate *new* code going
  forward; you don't retroactively wrap shipped features) and no forced rewrite. The cited
  evidence is about flag *debt from having them* (sprawl) and *incremental* adoption, not
  about late addition being expensive. Its one steelman — request-time evaluation context
  (principal/tenant/attributes) — rides plumbing the board already covers
  (`tenant-context-propagation`, `i18n-locale-resolution`, the authz principal); its only
  irreversible angle (exposure/experiment logs) collapses into `product-analytics` (covered).
  Honest rating **L–M**, not H. Recorded here as a deliberate observation, not a miss.

- **Notifications / outbound communications — REJECT as a headline (fails bar 1; decomposed).**
  No row owns the domain, but its H-retrofit sub-seams are netted across covered rows: the
  **non-backfillable** part — notification preferences + opt-out/consent history
  (CAN-SPAM/GDPR) — lands in `consent-records`; reliable delivery → `transactional-outbox`;
  template strings → `i18n-string-externalization`. The genuine residual (channel/dispatcher
  abstraction, template registry, digest/dedup) is **low-retrofit** by its own literature
  ("add a new dispatcher"). Partial/decomposed gap → note, not headline. (Verified: the
  template's `notif`/`smtp` hits are all *deploy/Alertmanager ops* alerting, not an app
  outbound-comms surface.)

- **Server-side caching / invalidation — REJECT (additive, low-retrofit).** The `redis`
  battery already ships the transport ("key/value datastore (cache/sessions)"); a read-through
  cache layer + invalidation is additive going forward. (The board's only "cache" hits are the
  *client-side* TanStack query cache — a different thing — confirming no server-cache seam, but
  none is needed: it's not a retrofit trap.) Held.

- **Full-text / relevance search — REJECT (additive).** `pgvector` covers embedding/vector
  similarity search; a Postgres FTS or external index (Elastic/Meili/Typesense) is additive
  going forward, not an irreversible seam. Held.

- **Optimistic concurrency / lost-update (version column / ETag) — REJECT (fails bar 1).**
  Explicitly named inside `realtime-sync` ("per-entity version/sequence +
  optimistic-concurrency writes"). Touched.

- **Saga / long-running workflow orchestration — REJECT (out-of-scope / building blocks
  covered).** The primitives (`transactional-outbox`, `workers`, idempotency inbox) are on the
  board; general saga/process-orchestration is arguably out of scope for a *single-service*
  scaffold (the same call that parked multi-agent orchestration in `agent-conscious-parks`).
  Borderline → note at most.

- **Multi-region availability / failover (active-active, HA topology) — REJECT (weak for an
  app scaffold).** `data-residency` covers the region *atom* + `resolve_region` indirection;
  `data-backup-restore-drill` covers data recovery. True active-active failover is an
  infra/deploy-topology axis, weak to scaffold from an application template. Note at most.

- **Green / sustainability / carbon-aware compute — REJECT (optimization-shaped, low-retrofit).**
  Emerging concern, but additive/optimization in nature; no irreversible-history or
  pervasive-rewrite property. Consciously set aside.

---

## CONFIDENCE

**High** that **file/object storage** is a genuine whole-domain miss: it is untouched as a
seam (present only as a store-to-enumerate), distinct from the CDN/static-assets axis, and
high-retrofit on both the irreversible-reference and forced-rewrite axes.

**Medium** on the **content-translation data model** secondary: real and H-retrofit, but a
facet within an already-covered domain rather than a category the scan was blind to.

**High** that the remaining commonly-retrofitted axes are either genuinely covered/decomposed
(notifications, optimistic-concurrency) or genuinely low-retrofit/additive (feature flags,
caching, search, sustainability) — i.e., the net held everywhere else, and the two items above
are the honest residue rather than filler.
