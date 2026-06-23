# Retrofit Scan — Phase 1.14: Breadth-First Guard (Industries we may have ignored)

**Agent:** `breadth-industries`
**Lens:** high-retrofit-cost architectural seams that fall OUTSIDE every domain already on the candidate board, surfaced by thinking across industries (fintech, healthcare, marketplaces, real-time, IoT/hardware, data platforms). For each: the seam, why-late-is-expensive (with primary-source evidence), retrofit_cost, what early scaffolding concretely looks like, proposed disposition, and overlaps with the current board.

A recurring shape unites the strongest findings: they are all **write-time invariants on a system of record**. Once data has been written without the invariant (mutable money rows, float amounts, un-keyed mutations, a missing tax ID, an unlogged PHI read), you cannot reconstruct the lost information — the cost isn't a code change, it's *irrecoverable history*. That is the precise profile an opinionated scaffold exists to defend.

---

## 1. Fintech — Money is stored as a float (should be integer minor units + decimal, with an explicit currency)

**Domain:** fintech / any product that touches money (a checkout, a balance, a credit, a fee, a refund).

**The seam.** The data type and shape of a monetary value: a float vs. an exact representation (integer minor units, or `Decimal`), *always* paired with an ISO-4217 currency code so the decimal exponent is knowable. This is a one-line decision at the column/model level and a permanent property of every row written thereafter.

**Why late is expensive.** Binary floats cannot represent most decimal fractions exactly. Modern Treasury's engineering writeup gives the canonical failure: `"69.54".to_f * 100` yields `6955`, not `6954` — "the limitations of floating point arithmetic have caused something like 0.0000…1 to be added to 69.54, which manifested itself as a 1p discrepancy." Multiply that by millions of rows and the errors are **already baked into stored data**; you cannot cleanly migrate float→integer because you can no longer tell which stored values were the true amount and which already drifted. Their prescription is to store amounts as integers in the smallest currency unit (`$12.34 → 1234`) and to "store the currency to determine the number of decimal places using the ISO 4217 standard" — because JPY has 0 decimals, USD 2, and some currencies 3. A schema that hardcodes "cents" (×100) silently corrupts every non-2-decimal currency the moment you go international, and you cannot retroactively know whether a stored `1000` meant ¥1000 or ₩10.00. (Modern guidance refines the rule: exact `Decimal` by default, integer minor units when the problem benefits — the failure mode being designed-against is identical.)

**retrofit_cost: H.** Changing the storage type after data exists means a data migration that must *guess at the original intent* of already-drifted or ambiguously-scaled values, plus touching every read/write/serialization/aggregation path. The arithmetic-error class is unrecoverable from stored data alone.

**Early scaffolding concretely.** A `Money` value object / SQLAlchemy type that stores `(amount_minor: int, currency: str)` (or a `Decimal` column with enforced scale), forbids float construction, and derives decimal places from ISO-4217. Ship it as the default monetary primitive the moment any "amount/price/balance" field is scaffolded; a reviewer flags raw `float`/`Float` on money-named columns.

**Evidence/sources.**
- Modern Treasury, "Floats Don't Work For Storing Cents": https://www.moderntreasury.com/journal/floats-dont-work-for-storing-cents (the `6955`/`6954` bug; integer-minor-units + ISO-4217 currency for decimal places).
- "Storing Money as Integer Cents Is Often Over-Engineering" (the `Decimal`-by-default counter-position): https://world.hey.com/otar/storing-money-as-integer-cents-is-often-over-engineering-7238a485
- DZone, "Why You Should Never Use Float and Double for Monetary Calculations": https://dzone.com/articles/never-use-float-and-double-for-monetary-calculatio

**Proposed disposition: battery** ("money/payments primitives" — a `Money` type + currency handling) OR a small **concern** if we want the primitive on by default. Leaning battery: it only matters for money-bearing products, fitting the opt-in model.

**Overlaps with the board.** None directly. Adjacent to the audit-log battery (money movement is auditable) but the *representation* of value is unaddressed anywhere on the board.

---

## 2. Fintech — No double-entry, immutable, append-only ledger for value movement (distinct from the audit-log battery)

**Domain:** fintech / marketplaces / wallets / credits / any system where balances move between accounts.

**The seam.** A dedicated **ledger** subsystem: every value movement is recorded as balanced double-entry postings (debits == credits per currency) into an **append-only** table; balances are *derived* from postings, never mutated in place; corrections are *new reversing postings*, never edits. This is a structural choice about where the truth of "how much does account X hold" lives.

**Why late is expensive.** Most products start with the balance as a mutable column on an `orders`/`accounts`/`wallets` row and treat updates as `UPDATE balance = ...`. Modern Treasury's "Enforcing Immutability" writeup walks exactly this anti-pattern: when an order amount is modified directly, "the data is irreversibly destroyed and [it] becomes impossible to figure out what changed." Worse, downstream money is already gone: "The payout you've made to the merchant is now incorrect and you have no way to attribute the adjustment to the original payout." Their reconciliation example — "if a merchant had thousands of orders and complained about a $10 discrepancy in their $10,000 payout… it could take days to track this down" — is the day-2 cost of *not* having postings. Their scale series adds the integrity rule: "All money movement must record the source and destination of funds," and shows that without per-currency balancing you can credit "a fraction of ETH (created out of nowhere)." Retrofitting a ledger means reconstructing history that the mutable design *destroyed*, then re-deriving every balance and proving it matches the money that actually moved — frequently impossible without the original events.

**Crucially this is NOT the audit-log battery.** Per the general-ledger vs audit-trail distinction: the ledger records the **"what"** of value movement and holds the official balances; the audit log records the **"who/when/how"** of system events. They are deliberately separate systems — an audit log of "user X edited row Y" does not give you a balanced, reconcilable account of where money is.

**retrofit_cost: H.** Append-only + double-entry is a foundational data model; bolting it onto a product whose balances are mutable columns is a from-scratch rebuild of the money subsystem plus a (often lossy) historical reconstruction.

**Early scaffolding concretely.** An opt-in ledger battery: `accounts` + append-only `postings` (transaction_id, account_id, direction, amount_minor, currency), a per-transaction balance-must-net-to-zero invariant, balance as a derived/materialized read, and a "reverse, don't edit" correction helper. Plus a reviewer that flags mutable balance columns / direct balance `UPDATE`s on money-bearing models.

**Evidence/sources.**
- Modern Treasury, "Enforcing Immutability in your Double-Entry Ledger": https://www.moderntreasury.com/journal/enforcing-immutability-in-your-double-entry-ledger ($10/$10,000 reconciliation story; "irreversibly destroyed"; reversal/difference entries).
- Modern Treasury, "How to Scale a Ledger, Part V: Immutability and Double-Entry": https://www.moderntreasury.com/journal/how-to-scale-a-ledger-part-v ("Immutability is the most important guarantee from a ledger"; "All money movement must record the source and destination"; ETH-from-nowhere).
- General ledger vs audit log distinction: https://www.netsuite.com/portal/resource/articles/accounting/general-ledger.shtml and https://optro.ai/blog/what-is-an-audit-trail

**Proposed disposition: battery** (a "ledger / double-entry" battery, naturally `requires` the Money primitive from #1).

**Overlaps with the board.** Adjacent to but **distinct from** the **audit-log/activity-trail battery** (system events ≠ value movement) — name that item in the board so the two aren't conflated. Could share the immutable-append-only machinery with audit-log.

---

## 3. Fintech / marketplaces — No idempotency keys on mutating & outbound money-moving requests (the inbox battery only covers *inbound* webhooks)

**Domain:** fintech / marketplaces / any API that performs a side-effecting, non-naturally-idempotent operation (charge, transfer, payout, order-create, send-notification).

**The seam.** A first-class **idempotency-key** contract on `POST`/mutation endpoints and on outbound calls to payment processors: the client supplies a stable key, the server records `(key → first-result)` and returns the stored result on any replay, so retries/double-clicks/at-least-once delivery cannot double-execute.

**Why late is expensive.** "Connections drop, responses time out, requests can get lost or duplicated, and people click the same button more than once." In a money system this becomes a double charge or a duplicate payout. The key property the literature stresses is that the **key must be generated before the first attempt**, so "every attempt of the same operation uses the same key" — meaning the *clients and the API contract* must be designed for it up front. Retrofitting is brutal because (a) you must add and thread a key through every caller and every endpoint, (b) you must build the dedupe store and decide its semantics (in-flight vs. completed, response replay, key TTL), and (c) until it exists you have **no way to retroactively de-duplicate the double charges that already happened** — you can only refund. Distributed payment flows (auth → gateway → fraud → ledger, interacting asynchronously with retries) make at-least-once delivery the norm, so the absence of idempotency is not a rare edge — it is a steady leak of duplicate money operations.

**retrofit_cost: H.** Touches the public API contract and every client, plus a new store and replay semantics; the financial damage accrued before it exists is unrecoverable except by manual reversal.

**Early scaffolding concretely.** A scaffolded idempotency-key middleware/dependency for FastAPI mutations (header `Idempotency-Key`, a keyed result store with TTL, response replay, and an in-flight lock), and an outbound-idempotency helper for processor calls. A reviewer flags side-effecting `POST` money endpoints with no idempotency contract.

**Evidence/sources.**
- Modern Treasury, "What is Idempotency and Why It Matters in Payments": https://www.moderntreasury.com/journal/why-idempotency-matters-in-payments
- IEEE Computer Society, "Why Idempotency Matters In Payment Processing Architectures": https://www.computer.org/publications/tech-news/trends/idempotency-in-payment-processing-architecture (auth/gateway/fraud/ledger asynchronous interaction → duplicate processing without safeguards).
- Stripe-style "key created before the first request, reused on every retry": https://nxtbanking.com/idempotency-keys-payment-api-design/

**Proposed disposition: concern** scaffolded early (an idempotency seam on mutating endpoints) for money-bearing products, with reviewer enforcement.

**Overlaps with the board.** **Partial overlap with the existing `webhooks` battery**, which already ships "an idempotent **inbox**" — but that is *inbound* webhook dedupe only. This seam is the *reciprocal*: idempotency on the project's own *outbound/mutating* requests. The board should note the inbox covers only one direction.

---

## 4. Marketplaces — Compliance/payout provenance not captured at write-time (KYC, tax ID, gross-vs-net) — the reporting window closes and you cannot backfill

**Domain:** marketplaces / payouts / two-sided platforms / anything that pays third parties.

**The seam.** Capturing, **at the moment each transaction and onboarding happens**, the fields a future payout/tax/dispute process will need: the seller's verified identity / tax ID, the **gross** transaction amount (not just net-of-fees), per-payout attribution of fees/refunds/adjustments, and the consent/agreement state. These are write-time facts that a later feature *cannot reconstruct*.

**Why late is expensive — the window literally closes.** IRS 1099-K rules are unambiguous and time-boxed: the platform reports **gross** payments, "not amounts net of processing fees or refunds," and — the killer constraint — "The Tax ID used on your Form 1099-K must be updated **prior to or during the year that corresponds with the sales being reported**… tax ID updates submitted in 2024 for Form 1099-K filing reporting 2023 sales **are not accepted**." If you didn't capture verified seller identity and gross amounts during the reporting year, you are non-compliant and there is *no backfill* — the data needed never existed in a usable form. The same shape applies to KYC ("not a once-off burden… requires regular maintenance") and to dispute evidence: if you stored only net post-fee amounts and never recorded fee/refund attribution per payout, you cannot reconstruct gross figures or defend a chargeback after the fact.

**retrofit_cost: H.** This is the purest "irrecoverable history" seam — the cost of retrofitting is regulatory exposure plus a backfill that is *impossible* because the source facts were never recorded at the time they existed.

**Early scaffolding concretely.** When a payouts/marketplace battery is selected, scaffold the transaction model to record gross amount + itemized fees/refunds (so net is derived, never the only stored figure), a seller-identity/tax-profile model captured at onboarding with effective-dated fields, and per-payout line attribution. A reviewer flags money flowing to third parties without captured payee-identity / gross-amount provenance.

**Evidence/sources.**
- IRS, "Understanding your Form 1099-K": https://www.irs.gov/businesses/understanding-your-form-1099-k
- Trolley, "IRS 1099-K…" (marketplaces' reporting obligations; gross not net): https://trolley.com/learning-center/irs-1099-k-payment-card-third-party-network-transactions/
- Walmart Marketplace, "Retrieve Form 1099-K" (Tax ID must be updated in the reporting year; later updates "not accepted"): https://marketplacelearn.walmart.com/guides/Taxes%20%26%20payments/Tax%20information/Retrieve-form-1099-K

**Proposed disposition: battery** (the payouts/marketplace battery should scaffold provenance-complete transaction + payee-identity models) with a **reviewer-enforced** guard ("third-party money movement must carry captured payee identity + gross provenance").

**Overlaps with the board.** None directly; the audit-log battery records system events but not *business/compliance provenance fields*. Closest neighbor is consent (board has consent-gated analytics) but this is financial-record provenance, a different axis.

---

## 5. Healthcare — Access is not consent-gated / purpose-of-use-aware / break-glass-capable (an authorization *shape*, distinct from multitenancy)

**Domain:** healthcare / regulated data / any product where *who may read which record* depends on consent, purpose, and emergency context — not just role.

**The seam.** An authorization model where each sensitive read is checked against (a) the subject's **consent state at the time of access**, (b) the requester's **purpose-of-use**, and (c) an explicit **break-glass / emergency override** path that elevates access *temporarily*, *minimally*, and *always with a recorded justification*. Plus the mandatory companion: a real-time **PHI access log** of who read what, when, and why (HIPAA §164.312(b)).

**Why late is expensive.** HIPAA requires "audit controls… that record and examine activity in information systems that contain or use ePHI" on "all systems and applications that access, store, or transmit ePHI," with logs capturing "search queries that returned patient data, bulk reads/exports, and consent captures and revocations… recording consent state at the time of access." If the app was built with plain RBAC and read paths that don't log, you cannot retroactively produce who-read-what — that history never existed, and HIPAA mandates **6-year retention** of it. Break-glass is structurally hard to bolt on: a correct implementation is "tied to urgent clinical risk, not convenience; temporary; transparent (records who did what and why); and reviewable" — i.e., it must wrap the *same authorization chokepoint* every read already flows through. If reads scatter across the codebase without a single enforcement seam, adding consent-gating + purpose + break-glass + per-read logging means rewriting every data-access path.

**retrofit_cost: H.** Requires a single authorization chokepoint and a per-read logging seam to already exist; scattering reads first makes this a whole-app refactor, and the missing access history is unrecoverable.

**Early scaffolding concretely.** A policy-decision seam (an ABAC-style `authorize(subject, action, resource, purpose, context)` chokepoint) that all sensitive reads route through; a consent model with effective-dated state; a break-glass path that elevates with a mandatory reason and emits a high-severity log; and an append-only access-log of every sensitive read. A reviewer flags sensitive-resource reads that bypass the chokepoint or aren't logged.

**Evidence/sources.**
- Kiteworks, "HIPAA Audit Log Requirements" (§164.312(b); log all ePHI systems; consent state at time of access; 6-year retention): https://www.kiteworks.com/hipaa-compliance/hipaa-audit-log-requirements/
- Yale HIPAA, "Break Glass Procedure": https://hipaa.yale.edu/security/break-glass-procedure-granting-emergency-access-critical-ephi-systems
- "Did You Break the Glass Properly? A Policy Compliance Framework" (break-glass as policy-checked, reviewable override): https://www.scitepress.org/Papers/2025/135270/135270.pdf
- Solum Health glossary, break-glass four-part definition (urgent/temporary/transparent/reviewable): https://getsolum.com/glossary/break-glass-access-emergency

**Proposed disposition: concern** (an authorization-chokepoint + consent/purpose seam scaffolded early) reinforced by **reviewer-enforced** checks (sensitive reads must route through the chokepoint and be logged). The break-glass + consent specifics can be a regulated-data battery.

**Overlaps with the board.** **multitenancy** (board) is a *different axis* — tenant isolation, not consent/purpose-of-use. Touches the **audit-log battery** (PHI read logging would ride it) and shared-auth (in flight) — name those, but the consent/purpose/break-glass *shape* is unaddressed.

---

## 6. Real-time — No sync/conflict-resolution semantics above the WebSocket transport (the `websockets` battery is transport, not sync)

**Domain:** real-time / collaborative / offline-capable apps (collaboration tools, gaming presence/state, anything multi-writer over a live connection).

**The seam.** The data-model decision for concurrent edits and presence: per-entity version/sequence numbers (and the choice between server-authoritative OT, CRDTs, or explicit version-vector merge) plus a separation of **ephemeral presence/awareness** state (cursors, who's-online) from **persisted** state. This is a property of how every mutable shared entity is modeled and written.

**Why late is expensive.** Teams default to **last-write-wins on a timestamp**, which "might discard important changes" silently. Moving to a real conflict-free model later is not additive: "Replacing custom WebSocket conflict resolution with a CRDT library means **rewriting an entire collaboration layer**," because "the fundamental architectural differences make retrofitting offline capabilities a substantial undertaking compared to building them in from the start." The presence/persistence split is also structural: Yjs uses a separate "awareness system for sharing ephemeral state… without persisting to the CRDT document" — get that wrong early and ephemeral cursor spam pollutes your persisted document model. The retrofit cost is high because the conflict model is woven into every shared-entity write path and the client sync protocol.

**retrofit_cost: M–H.** High for genuinely collaborative/offline-first products (full collaboration-layer rewrite); lower for apps that are merely "live-updating reads" where server-authoritative state suffices. Honest rating: H if multi-writer concurrency is in the product's future, M otherwise.

**Early scaffolding concretely.** If the realtime/collab battery is selected: per-entity version/sequence columns + an optimistic-concurrency write helper (reject stale writes), a clear presence channel separate from persisted entities, and a documented upgrade path to CRDT (e.g., Yjs) for true co-editing. A reviewer flags shared-entity writes that silently last-write-wins without a version check.

**Evidence/sources.**
- Fordel Studios, "Real-Time Data Sync: CRDTs, OT, and What Actually Works" (LWW discards changes; replacing custom resolution = rewriting the collaboration layer): https://fordelstudios.com/research/real-time-data-sync-patterns
- "Deep Dive into Y.js CRDTs" (separate awareness/presence system, not the persisted doc): https://dev.to/ebendttl/deep-dive-into-yjs-crdts-for-real-time-multiplayer-editors-5b33
- Adalo, "Offline vs. Real-Time Sync: Managing Data Conflicts" (CRDTs / version vectors vs LWW tradeoffs): https://www.adalo.com/posts/offline-vs-real-time-sync-managing-data-conflicts

**Proposed disposition: park** (or a thin **battery** extension on top of `websockets`). Real but lower immediate pull, and only High-cost for the collaborative-app subset.

**Overlaps with the board.** **Partial overlap with the existing `websockets` battery** (FastAPI WebSocket routes + connection manager) — but that is *transport only*; it ships no conflict/version/presence-vs-persistence semantics. The board should note the gap above the transport.

---

## 7. Data platforms — No telemetry/event-ingest contract (schema + retention + downsampling) at the front door (the `timescaledb` battery is the storage engine, not the ingest discipline)

**Domain:** data platforms / IoT telemetry / analytics event pipelines / anything ingesting high-volume time-stamped events.

**The seam.** A typed **ingest contract** at the boundary where events/readings arrive: an enforced schema (with explicit evolution rules), a deliberate **retention + downsampling/rollup policy**, and cardinality discipline on tag/label dimensions — decided *before* the firehose is pointed at the table.

**Why late is expensive.** Time-series and telemetry stores are governed by the trio "schema evolution and semantic consistency," "high cardinality and volume constraints [that] need sampling and aggregation," and "cost constraints [that] drive retention, downsampling, and rollups." Once raw events stream in under an ad-hoc schema with unbounded-cardinality tags, three things are hard to undo: (a) the **schema is now load-bearing** for every consumer, so changing it is a breaking change across the platform — the data-contracts literature is explicit that "a schema defined as a contract protects every downstream consumer," and absent that, breaking changes "propagate as silent failures"; (b) you cannot reclaim storage/cost from data you *kept at full granularity forever* because you never set a retention/downsampling policy; and (c) high-cardinality tags chosen carelessly degrade the store and can't be un-ingested. Retrofitting a contract + retention onto a live firehose means migrating historical data and renegotiating with every consumer.

**retrofit_cost: M.** Real and load-bearing, but more recoverable than the money/PHI seams (you can introduce a contract going forward and downsample retroactively); rated M honestly, not H.

**Early scaffolding concretely.** On top of the `timescaledb` battery: a Pydantic-typed ingest endpoint/contract for readings, a default retention + continuous-aggregate/downsampling policy (raw N days → rollups), and a documented cardinality budget for tag columns. A reviewer flags ingest endpoints that accept untyped/unbounded-cardinality payloads or hypertables with no retention policy.

**Evidence/sources.**
- SRE School, "What is Telemetry?" (schema evolution + cardinality + cost/retention/downsampling trio): https://sreschool.com/blog/telemetry/
- IIoT-World, "Long-Term Data Retention in IIoT with Time Series Databases" (retention + downsampling as a design decision): https://www.iiot-world.com/predictive-analytics/predictive-maintenance/long-term-iiot-data-retention-with-time-series-databases/
- Soda, "The Definitive Guide to Data Contracts" / dataskew "Stop Breaking Downstream Pipelines" (schema-as-contract protects every consumer; breaking changes propagate silently): https://soda.io/blog/guide-to-data-contracts and https://dataskew.io/blog/data-contracts-for-data-engineers/

**Proposed disposition: battery** extension to `timescaledb` (ingest-contract + retention scaffolding) with a reviewer guard.

**Overlaps with the board.** **Partial overlap with the existing `timescaledb` battery** (TimescaleDB extension + readings hypertable) — that ships the storage engine but no ingest contract / retention / cardinality discipline. Also adjacent to the framework's **already-covered Pact CDC** — but Pact is *API-level* consumer-driven contracts; this is a *data/ingest-level* contract, a different layer.

---

## Summary table

| # | Domain | Seam | retrofit_cost | Disposition | Board overlap |
|---|--------|------|---------------|-------------|---------------|
| 1 | fintech | Money as float vs integer-minor-units/decimal + currency | H | battery (Money primitive) | none |
| 2 | fintech | Double-entry immutable append-only ledger | H | battery (ledger) | distinct from audit-log battery |
| 3 | fintech/marketplaces | Idempotency keys on mutating/outbound requests | H | concern + reviewer | partial: webhooks inbox is inbound-only |
| 4 | marketplaces | Write-time compliance/payout provenance (KYC, tax ID, gross) | H | battery + reviewer | none (audit-log ≠ compliance fields) |
| 5 | healthcare | Consent-gated / purpose-of-use / break-glass authz + PHI read log | H | concern + reviewer (battery for specifics) | distinct from multitenancy; rides audit-log |
| 6 | real-time | Sync/conflict semantics above the transport | M–H | park / websockets-battery ext | partial: websockets is transport-only |
| 7 | data platforms | Telemetry ingest contract + retention/downsampling | M | timescaledb-battery ext + reviewer | partial: timescaledb is storage-only; ≠ Pact (API-level) |

**Highest-signal trio (cheap-to-scaffold, brutal-to-retrofit, off-board):** #1 Money representation, #2 double-entry ledger, #4 write-time compliance provenance — all three share the "irrecoverable history" profile and all three are absent from the board. #3 idempotency and #5 consent/break-glass are close behind and only partially shadowed by existing batteries.
