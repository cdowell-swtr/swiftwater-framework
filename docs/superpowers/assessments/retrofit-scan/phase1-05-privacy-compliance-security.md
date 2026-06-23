# Phase-1 Retrofit Scan — Privacy / Compliance / Security

Agent: `privacy-compliance-security`
Area: audit trail / activity log · data residency · consent management · field-level
encryption · PII tokenization · secrets management · key rotation.
Mandate note: erasure-type (right-to-be-forgotten) obligations are classified
**reviewer-enforced**, not battery — they are owned by the `compliance`, `privacy`,
and `data-lineage` review agents that already exist in this repo.

## Framing: this area already has reviewer enforcement — the gap is the SEAM that makes it satisfiable

The repo already ships four review agents that own the *obligation* side of this domain:
`review-compliance` (audit/retention/erasure on durable stores), `review-privacy` (PII in
logs / over-collection), `review-data-lineage` (PII sinks, deletion gaps across stores),
and `review-security` (authz, injection, leaked secret values). Reading their prompts
(`src/framework_cli/review/agents/{compliance,privacy,data-lineage,security}.md`) shows
they flag a destructive op with no audit entry, personal data with no deletion path, an
erasure that misses a second store, etc. — and explicitly *down-rank hardening to "info"*
because **the template itself omits the mechanism** (`SecretStr`, `min_length`, secret
rotation, retention TTLs are "info at most" today).

That last clause is the whole finding for this area. The reviewers can only ask "does this
diff satisfy erasure?" — they cannot create the **architectural seam** that makes the answer
"yes" possible. A builder who never scaffolds a per-subject key boundary, an append-only
audit table, a region-pinned data atom, or a PII indirection point will be told by the
reviewer "you have no erasure path" *after* PII has already proliferated across tables,
logs, replicas, and backups — exactly when the fix is most expensive. So the high-value
moves here are the **early seams the reviewers presuppose**, not new obligations.

---

## Seam 1 — Per-subject encryption boundary (crypto-shredding-ready field encryption) — THE enabler for reviewer-enforced erasure

### The seam
A designated, opt-in surface where sensitive fields are encrypted at the application layer
with a **per-subject Data Encryption Key (DEK)** — `Ks` unique to data-subject `s`, wrapped
by a KEK in a KMS/Vault, with the DEK addressable as `{subject_type}:{subject_id}`. Erasure
of subject `s` then means **destroying `Ks`**, not deleting rows: the ciphertext stays in
every table, replica, and backup but becomes computationally unrecoverable
([VeritasChain](https://veritaschain.org/blog/posts/2026-01-18-crypto-shredding-gdpr-mifid-ii-reconciliation/),
[Granit](https://granit-fx.dev/blog/crypto-shredding-gdpr-erasure-without-deleting-rows/)).

### Why late is expensive (the retrofit story, with evidence)
The primary sources are unusually blunt that this is a *pre-architecture* decision, not a
later feature:

- VeritasChain states the requirement directly: *"this separation must be designed before
  data is written — you cannot retrofit crypto-shredding into existing plaintext systems"*
  and lists "Pre-architecture requirement" as a hard limitation
  ([VeritasChain](https://veritaschain.org/blog/posts/2026-01-18-crypto-shredding-gdpr-mifid-ii-reconciliation/)).
- The reason it *can't* be retrofitted cleanly: GDPR Art. 17 erasure (30 days) collides with
  immutable retention regimes (MiFID II / SOC2 / HIPAA 6-year). You cannot just `DELETE`:
  deleting a row "breaks the hash chain and creates gaps in the audit trail that regulators
  detect," and a soft-delete leaves plaintext that admins (and backups) still read. Without
  the per-subject DEK seam your only erasure tools are row-deletion (breaks immutability +
  misses backups/replicas) or pseudonymization (still personal data under GDPR)
  ([VeritasChain](https://veritaschain.org/blog/posts/2026-01-18-crypto-shredding-gdpr-mifid-ii-reconciliation/)).
- The crypto math is the seam: `Hchain = H(Hprev || C)` over **ciphertext** survives key
  destruction, where `Hchain = H(Hprev || P)` over plaintext does not — so the encryption
  boundary has to exist before the first write for the chain to be erasure-safe.
- Regulatory backing exists, which raises this from "nice idea" to "recognized mechanism":
  EDPB **Guidelines 02/2025** — *"Where personal data has been encrypted using state of the
  art encryption … and the encryption key has been securely destroyed, the encrypted data
  may be considered to have been erased."*
- Cossack Labs' CTO (InfoQ): *"Encryption starts from the design"* and *"Unless well-defined,
  the task for application-level encryption is frequently underestimated, poorly implemented,
  and results in haphazard architectural compromises."* Retrofitting application-level
  encryption onto existing plaintext means redesigning data flows, standing up key
  infrastructure, and **re-encrypting historical data as a blocking operation with
  availability implications**
  ([InfoQ ALE](https://www.infoq.com/articles/ale-software-architects/)).

The queryability tax is the second half of why this must be early, not bolted on: you cannot
`WHERE`, `ORDER BY`, or `JOIN` on an encrypted column. The mitigations — **deterministic
encryption** (enables equality search but leaks frequency), **blind indexing** (store a
separate HMAC token for equality lookup), **searchable encryption** (CryptDB / SQL Always
Encrypted / MongoDB CSFLE, each with access-pattern leakage or performance caveats) — all
change the **schema and the read paths**, so deciding *which* fields are encrypted-and-how is
a data-model decision, not a column you flip later
([InfoQ ALE](https://www.infoq.com/articles/ale-software-architects/),
[Cossack/Acra](https://github.com/cossacklabs/acra)).

### retrofit_cost: **H**
Adding per-subject encryption after PII exists requires: a key-hierarchy + KMS/Vault you
didn't have, an interceptor seam in the ORM (EF Core's value converters famously *can't* see
the entity id, forcing save/materialization interceptors —
[Granit](https://granit-fx.dev/blog/crypto-shredding-gdpr-erasure-without-deleting-rows/)),
a blind-index column for every field you still need to query, and a one-shot re-encryption of
all historical rows *plus every backup and replica*. The reviewers will already be flagging
the missing erasure path while this multi-quarter migration is in flight.

### What early scaffolding looks like
A `field-encryption` (or `pii-vault`) battery that wires: (a) a KMS/Vault-backed envelope
key hierarchy (master KEK in KMS → per-subject DEK), reusing the existing `secrets-backing`
concern; (b) a SQLAlchemy `TypeDecorator` / declarative mixin (`EncryptedStr`) so a builder
marks a column `encrypted=True` and gets AES-256-GCM + per-subject DEK lookup for free;
(c) an optional blind-index sibling column + helper for equality search; (d) an
`erase_subject(subject_id)` hook that destroys the DEK and emits an **erasure certificate**
(subject-hash + key-id + affected-event count) — which is exactly the artifact
`review-compliance` looks for. The framework already has the observability + migration-aware
contract to make the re-encryption path operable.

### Proposed disposition: **battery** (the seam) + reviewer-enforced (the obligation)
The capability is an opt-in battery (`field-encryption`); the *use of it on the right fields*
stays reviewer-enforced by `compliance`/`privacy`/`data-lineage`. The reviewer prompts even
encode the workaround they want today — "hash the identifier (HMAC-SHA256 with a rotating
secret) so records cannot be re-identified after key rotation" appears verbatim in the
`compliance/good/audit-logged-action` scorecard — i.e. they are *asking* for a key-rotation /
crypto-shredding primitive that no battery currently provides.

### Overlaps
Erasure obligation = the board's **reviewer-enforced** row (`data-lineage` + `compliance`/
`privacy`). The KMS/Vault layer = the **secrets-backing** first-class concern. Per-tenant
keys are the multitenant cousin of this (board's **multitenancy** concern + Agent-4's
per-tenant-encryption); this is the **per-subject** cut, which is what erasure needs.

---

## Seam 2 — Append-only audit / activity trail (table shape + same-transaction write)

### The seam
A first-class, append-only `audit_events` table written **inside the same DB transaction** as
the operation it records, with a typed schema rather than a free-text `jsonb` blob.

### Why late is expensive (the retrofit story, with evidence)
- The canonical retrofit quote:
  *"By the time you are retrofitting it, you are working around an existing schema, an
  existing permission model, and existing client code that was never designed with
  observability in mind … It cannot answer the questions auditors actually ask, it cannot be
  queried efficiently at scale, and it provides no protection against tampering."*
  ([hoop.dev](https://hoop.dev/blog/immutable-audit-logs-the-key-to-soc-2-compliance-and-trust),
  [letsbuildsolutions](https://letsbuildsolutions.com/blog/system-design/designing-an-audit-log-system-immutable-events-efficient-querying-and-compliance-at-scale/)).
- The shape is load-bearing and hard to backfill: `occurred_at`, `actor_type/actor_id/
  actor_email`, `action` (dotted, e.g. `record.deleted`), `resource_type/resource_id`,
  `before`/`after` (JSONB) + `changed_fields[]`, context (`tenant_id`, `request_id`,
  `ip_address`), and tamper-evidence (`prev_hash`, `row_hash`) — plus a `retention_class`.
  The common anti-pattern, "a generic jsonb column with inconsistent action strings, cannot
  be efficiently queried at scale"
  ([letsbuildsolutions](https://letsbuildsolutions.com/blog/system-design/designing-an-audit-log-system-immutable-events-efficient-querying-and-compliance-at-scale/)).
- **Atomicity is the part a late library can't fix:** *"Audit events must be written within
  the same database transaction as the operation being recorded. Post-commit async writes
  risk silent loss on process crash."* Retrofitting audit into a codebase whose write paths
  already commit independently means re-plumbing every mutating path.
- The questions auditors ask are concrete: SOC2 wants privileged-action monitoring; HIPAA
  (45 CFR §164.312(b)) mandates logging all PHI **reads** with 6-year retention and on-demand
  sample production. A log not designed for "actor + resource + time-range" indexing literally
  cannot produce those samples.
- Tamper-evidence (`prev_hash`/`row_hash` hash chain, periodic root hash to WORM object
  storage) and month-range partitioning (so `DROP TABLE audit_events_2024_01` is a
  millisecond retention op) are schema commitments — both painful to add to a populated table.

### retrofit_cost: **H**
Schema + index design is mechanical (the cheap half), but the **same-transaction write** has to
thread through every mutating endpoint, and you can't reconstruct history you never captured —
you can only go forward, so backfilling `before`/`after` for past events is impossible. The
non-backfillable history plus the cross-cutting re-plumb of every write path put this at H, even
though the table itself is trivial.

### What early scaffolding looks like
An `audit-log`/`activity-trail` battery: the typed migration (with the index set
`(tenant_id, occurred_at DESC)`, `(tenant_id, resource_type, resource_id, occurred_at DESC)`,
`GIN(changed_fields)`), a `record_audit(...)` helper that participates in the request's
SQLAlchemy session/transaction, an optional `prev_hash`/`row_hash` chain + a verifier, and
month-partitioning + `retention_class` tiers (standard 365d / security 1095d / compliance
2555d / legal-hold). Reuses the existing OpenTelemetry `request_id` plumbing.

### Proposed disposition: **battery** (confirms a board item)
This is already on the candidate board as the `audit-log/activity-trail` battery and was
user-emphasized ("audit trail = huge"). This finding **confirms** it and supplies the concrete
shape: typed schema, same-transaction write, hash-chain, partitioned retention. Keep it a
battery; `review-compliance` already enforces "destructive op with no audit entry," so the
reviewer + battery pair is exactly right.

### Overlaps
Board battery **audit-log/activity-trail** (direct). Tamper-evidence hash chain overlaps Seam 1
(crypto-shredding computes the same chain over ciphertext). Atomicity overlaps Agent-1/2's
**idempotency** + transactional-outbox work. `retention_class` overlaps the reviewer-enforced
retention obligation.

---

## Seam 3 — Data residency: the "region atom" routing key

### The seam
A single early decision: the **atomic unit of residency** (the indivisible thing — a tenant /
org / user — whose data must live entirely in one region) and the **routing key** that maps a
request to its region. Everything downstream (DB placement, replication, request routing) is a
consequence of this one key.

### Why late is expensive (the retrofit story, with evidence)
- Alation (fetched) is blunt on cost and timing: *"Retrofitting data residency into existing
  systems costs far more than building it correctly from the start,"* and *"Smart SaaS
  companies treat data residency as a core architectural decision rather than a feature they'll
  add later."* The penalty side is real money, not theory: *"Meta alone faced a $1.3 billion
  penalty in 2023 for improper data transfers between the EU and the US,"* against a GDPR
  ceiling of *"4% of global revenue or €20 million, whichever is higher"*
  ([Alation](https://www.alation.com/blog/data-residency-by-design-global-compliance/)).
- The early decision is explicit (InfoQ, fetched): *"defining this atomic unit is essential in
  determining the source of truth for your multi-region deployment."* A single-region app bakes
  in three assumptions — synchronous local reads/writes, a shared database, global data access —
  that are *"fundamentally incompatible"* with region boundaries; converting "requires
  rebuilding consistency models, introducing asynchronous patterns, and redesigning all data
  flow"
  ([InfoQ multi-region](https://www.infoq.com/articles/understanding-architectures-multiregion-data-residency/)).
- The design principle that has to be there from day one: *"Do the same thing every time"* —
  asymmetric per-region behavior "creates unpredictable bugs impossible to test thoroughly."
  You cannot sprinkle region-awareness in later without this invariant.
- Named patterns the scaffold should presuppose: **cell-based architecture** (region as an
  encapsulated onion of edge/app/db), gateway routing on an embedded atom-id, region-pinned
  storage.

### retrofit_cost: **H** (but lower immediate pull)
Genuinely brutal to retrofit — it touches routing, the schema's tenant/region column, the
connection-pool/DB topology, and every "global" read. But most early products are single
region and the pull only arrives at the first EU/regulated enterprise deal.

### What early scaffolding looks like
NOT a full multi-region stack. The cheap early seam is a **`region` column on the residency
atom + a `resolve_region(subject)` indirection** that's hardwired to the single home region on
day one, so no code ever assumes "the database" — it asks for "this atom's database." Document
the atom choice in the scaffold. That single indirection is the difference between a
config-change later and a re-architecture.

### Proposed disposition: **concern (park the full build)**
The *seam* (residency-atom + region indirection) is a cheap posture-level **concern** worth
scaffolding as a no-op indirection; the full multi-region data plane is **park** until a
consumer pulls (consistent with the board listing "multi-region" under park).

### Overlaps
Tightly bound to the board's **multitenancy** concern (the residency atom is usually the
tenant; logical→physical separation is the same axis). The async/consistency rework overlaps
Agent-2's distributed-systems retrofit. "Region as a column you can't add later" rhymes with
Agent-1's ID-strategy finding.

---

## Seam 4 — Consent / lawful-basis records (purpose-tagged collection)

### The seam
A `consents` record store (subject, purpose, lawful-basis, method, timestamp, evidence,
policy-version) **plus** the discipline that every PII-collecting/processing path carries a
`purpose` so downstream systems can enforce purpose-limitation.

### Why late is expensive (the retrofit story, with evidence)
- The split-brain failure mode is the load-bearing one, and DataGrail names it (fetched):
  *"When consent states live in multiple tools that do not stay in sync, enforcement gaps
  appear."* You can collect consent and still never wire it to the code that acts on the data —
  the *enforcement* substrate is what's missing, and it's the hard part to backfill
  ([DataGrail](https://www.datagrail.io/glossary/what-is-consent-management/)).
- The record shape DataGrail prescribes (fetched): capture *"the timestamp, source,
  jurisdiction, specific purposes selected, and the policy version displayed,"* and consent
  must be *"freely given, specific, informed, and unambiguous"* with *"clear purpose
  limitation."* The non-backfillable retrofit pain: you can't reconstruct *why* (under what
  basis / which policy version) you collected data you already hold — there is no backfill for
  lawful basis, so pre-consent data is permanently questionable.
- Purpose-limitation only works if `purpose` rides along at collection time; bolting it on
  means re-tagging every existing collection path and every downstream consumer.

### retrofit_cost: **M**
The `consents` table is easy; the hard, non-backfillable parts are (a) lawful basis for data
already collected and (b) threading `purpose` through existing pipelines. Not H because most
early apps have few processing purposes and the table can be added without re-encrypting data.

### What early scaffolding looks like
A small `consents` model + migration (subject_id, purpose, lawful_basis, method, granted_at,
revoked_at, evidence, policy_version) and a `has_consent(subject, purpose)` gate helper, so
the *evidence trail* exists from day one and analytics/comms paths can gate on it. This is the
enforcement substrate the board's "product analytics (consent-gated)" item presupposes.

### Proposed disposition: **concern** (lean; overlaps board)
A posture-level **concern** — scaffold the lean consent-record substrate. The *over-collection*
and *retention-beyond-purpose* judgments stay **reviewer-enforced** (`review-privacy` already
owns "collection of PII not needed for the stated purpose, and retention beyond purpose").

### Overlaps
Directly under the board's **product-analytics (consent-gated)** concern and Agent-7's
attribution/consent-gated-pixels thread; the over-collection/retention call is already
`review-privacy`'s lane.

---

## Seam 5 — PII vault / tokenization indirection (store a reference, not the PII)

### The seam
A single point of indirection where PII is replaced by an opaque token / reference ID, and
operational tables, logs, analytics, and caches hold only the reference — the actual PII lives
in one vault behind an API.

### Why late is expensive (the retrofit story, with evidence)
- The core driver is **PII proliferation**: *"As enterprise data moves across applications,
  databases, and analytics pipelines, uncontrolled proliferation of PII increases compliance
  risk and a potential breach."* Once email/SSN/phone are copied into N tables, M log
  streams, analytics warehouses, replicas, and backups, *finding* every copy to encrypt or
  erase it is the expensive part
  ([Protecto](https://www.protecto.ai/blog/enterprise-pii-protection-approaches-to-limit-data-proliferation/)).
- The indirection seam (Centralized Profile / vault model), Protecto (fetched):
  *"Applications now hold only reference IDs, not actual PII. Any request for personal data
  must go through Vault APIs"* — which *"simplifies privacy operations such as Data Subject
  Requests (DSRs), including deletion or 'Right to Forget.'"* Erasure becomes a single vault
  delete instead of an N-store hunt.
- Tokens are designed to be non-reversible without the vault: *"Tokens are generated using
  entropy-based true random numbers, ensuring they're pattern-less and impossible to
  reverse-engineer"* — so the operational stores leak nothing even if breached
  ([Protecto](https://www.protecto.ai/blog/enterprise-pii-protection-approaches-to-limit-data-proliferation/)).
  (Note: the surveyed vendor pages assert the proliferation problem strongly but do not publish
  concrete build-cost numbers; the retrofit-cost claim below rests on the same
  proliferation/re-plumb mechanics as Seam 1, which the fetched ALE source documents directly.)

### retrofit_cost: **H**
Same root cause as Seam 1 — once PII has proliferated, retrofitting any indirection means
finding and rewriting every read/write site plus scrubbing logs/replicas/backups. The whole
value of the vault is that it *prevents* proliferation, which is only possible before it
happens.

### What early scaffolding looks like
This is the heavier sibling of Seam 1 and likely the **same battery's** "vault" mode: a
`pii_vault` table/service + `tokenize(value, type) -> token` / `detokenize(token)` helpers, a
`TokenRef` column type, and an `erase_subject` that deletes the vault rows. For most projects
Seam 1's per-subject field encryption is the lighter answer; the vault model is the option for
heavy cross-system PII or test-data needs.

### Proposed disposition: **battery** (mode of Seam 1's battery)
Folds into the `field-encryption`/`pii-vault` battery as its "vault/tokenization" mode; offer
field-encryption as the default and centralized-vault as the heavyweight option.

### Overlaps
Same battery as Seam 1; erasure obligation = the **reviewer-enforced** row. Token-as-reference
echoes Agent-1's "don't expose raw identifiers" ID-strategy finding.

---

## Seam 6 — Secrets management + key rotation (rotation as the un-retrofittable habit)

### The seam
Secrets sourced from an external store at runtime (12-factor config), **never** hardcoded, and
— the part that's actually hard — a key-rotation path that is **automatic by construction**,
including envelope key rotation (KEK roll + re-wrap) for the encryption seams above.

### Why late is expensive (the retrofit story, with evidence)
- The static-secret retrofit is a known disaster class. Cycode (fetched): *"10% of GitHub
  authors pushed secrets in 2022"*; *"96% of organizations have secrets scattered across their
  infrastructure, creating near infinite exposure points"*; *"Over 1.7 billion records were
  exposed in 2024 breaches that utilized stolen credentials as their initial access vector"*;
  credential-stuffing breaches average $4.8M and *"take 292 days, on average, to identify and
  contain"* ([Cycode](https://cycode.com/blog/secrets-management-best-practices/)).
- The honest framing of what's actually hard, verbatim from the rotation reference (fetched):
  *"The hard part was never the rotation mechanics — those are solved. The hard part is making
  rotation automatic enough that it happens even when no one is watching."* Rotation that
  requires a human ritual decays to never-rotated; this is a *design habit*, not a library,
  which is why it's retrofit-resistant
  ([digitalapplied](https://www.digitalapplied.com/blog/secrets-management-api-key-rotation-2026-engineering-reference)).
- 12-factor env-var secrets have a sharp edge that affects the encryption seams: a process
  reads its environment at startup, so an env-var-only secrets posture means a rotated secret
  is only picked up on restart — fine for a credential, but it forces a re-plumb if you later
  want *dynamic* (no-restart) rotation of the encryption KEKs the seams above depend on. The
  defensive posture is an external runtime fetch rather than baking secrets into the env
  ([OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)).
- For the encryption seams, **key rolling** (multiple active keys flagged read-vs-write, so you
  rotate without a full re-encrypt) is itself a schema/design decision — DEKs must carry a
  `key_id` from the first write (the crypto-shredding event example stores
  `"key_id": "KEY-TRADER-001-..."`), or you can never roll keys without re-encrypting
  everything ([InfoQ ALE](https://www.infoq.com/articles/ale-software-architects/)).

### retrofit_cost: **M**
Externalizing secrets is mechanical (the repo already has `gitleaks`/dependabot and
SecretStr-shaped fields). What's genuinely hard to add later is *versioned keys with rotation*
— if DEKs/secrets weren't `key_id`-tagged from day one, rotation forces a re-encrypt of all
historical ciphertext. So: externalization L, rotation-readiness M.

### What early scaffolding looks like
Largely the existing **`secrets-backing`** concern — finish it so a builder gets a
KMS/Vault-backed secrets source and a documented rotation runbook, and ensure every DEK/secret
the encryption seams mint is **`key_id`-versioned** so rotation never implies a global
re-encrypt. A `rotate_keys` management command + a guard against env-var-only secrets for the
encryption keys completes it.

### Proposed disposition: **concern** (extends a board concern)
Extends the board's **secrets-backing** first-class concern with the *rotation/versioning*
dimension. The "leaked secret VALUE on a changed line" case stays **reviewer-enforced**
(`review-security` already owns it).

### Overlaps
Board's **secrets-backing** concern (direct). The KEK/DEK hierarchy is the key-management layer
Seam 1 + Seam 5 consume. `gitleaks`/dependabot already cover the supply-chain leak-detection
half (board: already-covered).

---

## Summary table

| # | Seam | retrofit_cost | Disposition | Primary board overlap |
|---|---|---|---|---|
| 1 | Per-subject field encryption (crypto-shredding seam) | **H** | battery (+ reviewer-enforced obligation) | reviewer-enforced erasure; secrets-backing |
| 2 | Append-only audit / activity trail | H | battery (confirms board item) | **audit-log/activity-trail** battery |
| 3 | Data-residency region atom | H | concern (park full build) | **multitenancy** concern; multi-region (park) |
| 4 | Consent / lawful-basis records | M | concern (lean) | **product-analytics consent-gated** concern |
| 5 | PII vault / tokenization indirection | H | battery (mode of #1) | reviewer-enforced erasure |
| 6 | Secrets mgmt + key rotation/versioning | M | concern (extends board) | **secrets-backing** concern |

**The through-line:** this repo already *reviews for* erasure, audit, retention, and leaked
secrets — but the reviewers explicitly down-rank the fixes to "info" because the template
offers no mechanism. The highest-leverage move is to scaffold the **seams the reviewers
presuppose** — most of all the per-subject encryption boundary (Seam 1), which is the one the
sources unanimously say *cannot* be retrofitted and which turns "you have no erasure path" from
an unfixable finding into a `key_id` delete.
