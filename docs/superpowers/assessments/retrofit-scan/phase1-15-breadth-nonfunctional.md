# Retrofit Scan — Phase 1.15: Breadth-First Guard (Non-functional axes we may have ignored)

**Agent:** `breadth-nonfunctional`
**Lens:** high-retrofit-cost architectural seams that fall OUTSIDE every functional domain already on the candidate board, surfaced by sweeping the **non-functional axes** an opinionated scaffold tends to under-weight: dependency licensing/compliance, disaster recovery (data restore, not code rollback), supply-chain integrity (SBOM/provenance/signing — the layer *above* gitleaks/dependabot), data portability/export, FinOps/cost budgets, capacity/scaling, and operability (on-call/runbooks). For each: the seam, why-late-is-expensive (with primary-source evidence + URLs), retrofit_cost, what early scaffolding concretely looks like, proposed disposition, and overlaps with the current board.

**The honesty filter applied throughout.** The sibling industries doc (1.14) found the winning shape: the strongest seams are those whose **absence loses something you can never reconstruct** ("irrecoverable history"). I graded retrofit_cost against that test, not against "is this annoying to add later":
- **H** = absence destroys/incurs something unrecoverable — data gone before backups existed; a copyleft *obligation already incurred* across years of integration; provenance lost at compile time.
- **M** = you just do more work later — add a CI job, build an export endpoint, wire a healthcheck.

The result is **not** "everything is High." Two findings are honestly H (licensing; the *lost-data* half of DR). The rest are M, and two collapse to park/reject after a template grep showed the seam already ships. Precision over volume, as the task demands.

**Verification done before writing (so reviewers don't bounce these):**
- Grepped `src/framework_cli/template/` for `lifespan|SIGTERM|graceful|/health|/ready|readiness|liveness` → the template **already ships** a `lifespan` that disposes the engine on SIGTERM, `routes/health.py`, `tests/functional/test_graceful_shutdown.py`, `test_health_probes.py`, and compose `healthcheck`s. **Operability's core is covered** → it collapses to runbook stubs (see §7, park).
- Grepped for `backup|restore|pg_dump|RPO|RTO|sbom|cosign|sign|license|SPDX|export` → the only `restore` is `framework restore` (config integrity), the only `export` is OpenAPI schema export, and `rollback` in `infra/deploy/strategy.sh` is **migration-aware *code* rollback**. There is **no data backup/restore, no SBOM, no signing, no license gate**. Gaps confirmed empirically, not assumed.

---

## 1. Dependency LICENSING — no license-policy gate; a copyleft (GPL/AGPL) dep can go load-bearing for years before due diligence forces a rip-out

**Axis:** dependency licensing / OSS compliance (distinct from security CVE scanning).

**The seam.** A **license-policy gate in CI from commit 1**: every dependency (transitively) resolves to an SPDX license, each license is classified `allow` / `review` / `deny` against a policy, and a `deny` (e.g. GPL-3.0, AGPL-3.0) **fails the build** before the dependency is ever merged. The policy file and the gate are a few lines; the property they protect is *which license obligations your codebase has incurred*.

**Why late is expensive — the obligation is already incurred.** This is the cleanest "irrecoverable" non-functional seam, and it isn't about data — it's about *legal obligations baked into shipped code*. A copyleft dependency adopted casually ("it just worked") becomes load-bearing as code is built on top of it, and the obligation propagates: AGPL's network clause "extends this requirement to network-accessible software, meaning that even if you do not distribute the software, you may owe source code access to users who interact with it over a network" — which is exactly a FastAPI service. The bill comes due at **M&A due diligence**, where it is a deal-killer: "Undisclosed strong copyleft usage—especially GPL or AGPL components embedded in proprietary products—can collapse negotiations entirely or trigger significant valuation reductions." A concrete, quantified case: a Series A company "discovered their core analytics engine used an AGPL-licensed component," leaving three options — open-source the platform (destroy the moat), rewrite the engine (**"$800K+ engineering cost, 6-month delay"**), or license commercially (**"$2M+ in licensing fees"**) — and "the discovery led to a **$10M valuation reduction** and nearly killed the deal." The compounding is the trap: "License violations compound over time. Code that violates licenses gets built upon, creating larger compliance costs." Catching it at *adoption* is one rejected PR; catching it at *acquisition* is a forced rewrite of whatever now sits on top of it.

**retrofit_cost: H.** Not because adding the gate is hard (the gate is M), but because **the cost the gate prevents is unrecoverable once incurred**: by the time you discover the AGPL dep, years of proprietary code depend on it, and your options are open-sourcing, a 6-month rewrite, or a six-/seven-figure license. The framework's existing `dependency` reviewer **explicitly does not do license** ("note ... in-manifest justification only ... maintenance health & supply-chain risk ... pin floors"; it never reads license metadata), and dependabot/gitleaks cover *vulnerabilities and secrets*, not license class. This axis is genuinely uncovered.

**Early scaffolding concretely.** Ship a CI license gate in the generated project: a `task licenses:check` (e.g. `uv`-resolved tree → `pip-licenses` / a CycloneDX SBOM → policy eval) wired into the `gate` job, plus a checked-in `licenses.policy.toml` with a sane default allowlist (MIT/BSD/Apache-2.0/ISC/PSF) and a denylist (GPL-*/AGPL-*/SSPL) that **fails the build** on a `deny`, with an explicit per-dependency override list for justified exceptions. Because the framework already pins every prod dep, the gate has a clean manifest to evaluate. A reviewer companion can flag a *newly added* dependency in a manifest diff whose license class is unknown/denied (the `dependency` reviewer's scope would need widening, or a new `license` reviewer — see overlaps).

**Evidence/sources.**
- MindCTO, "The Copyleft Threat: How AGPL License Risk Can Destroy Your Startup's Valuation" (the $10M write-down / $800K rewrite / $2M license case; "cost of prevention is always lower than the cost of remediation"; "violations compound over time"): https://mindcto.com/insights/copyleft-threat-agpl-risk
- Morse Law, "Open Source Issues in Mergers & Acquisitions" (acquirer may have to "release the source code ... under a copyleft license ... reengineer ... remove ... from the market altogether"): https://www.morse.law/news/open-source-issues/
- Wiz Academy, "What Is Copyleft? Definition And Risks For Enterprises" (AGPL viral network clause): https://www.wiz.io/academy/compliance/copyleft
- Snyk, "Open-source license compliance" (CI/CD policy gate: "gate builds and stop 'bad' licenses from entering the codebase early"; SPDX-aligned `allow`/`review`/`deny`): https://docs.snyk.io/scan-with-snyk/snyk-open-source/scan-open-source-libraries-and-licenses/open-source-license-compliance
- FOSSA, "Open Source License Compliance" (runs in CI, PR-comment/Slack on a license issue): https://fossa.com/solutions/oss-license-compliance/

**Proposed disposition: concern** — a CI license-policy gate scaffolded early (posture-level, on by default), with a **reviewer-enforced** backstop for the manifest-diff case. Not the advisory `dependency` reviewer, which explicitly excludes license.

**Overlaps with the board.** Touches **supply-chain (gitleaks/dependabot, already covered)** but is a *different axis* — license class, not CVEs/secrets. Adjacent to the `dependency` advisory reviewer, which by its own prompt does NOT evaluate license. No board item covers it.

---

## 2. Disaster recovery — DATA restore (not code rollback): no backup/restore contract and no tested restore drill

**Axis:** disaster recovery — RPO/RTO, backups, **tested restores**. The framework covers *code* rollback (migration-aware, in `infra/deploy/strategy.sh`); it covers **none** of *data* recovery.

**The seam.** A scaffolded **backup + restore contract** for the project's system-of-record (Postgres, and any Redis/Timescale/Mongo battery state): a scheduled logical/physical backup, an *encrypted, off-host* destination, declared **RPO/RTO targets**, and — the part that actually matters — a **runnable restore drill** (`task db:restore-drill`) that restores into a throwaway environment and asserts success. The seam is the *contract and the drill*, not "we have a backup script."

**Why late is expensive — two halves, graded separately.** The *mechanism* (a backup cron + a restore task) is L/M to add anytime. The half that is **H** is the data lost in the window *before* a working, tested restore existed — that is gone forever. The canonical primary source is the **GitLab January 2017 outage**: an engineer ran a deletion on the primary, and **all five** backup/replication techniques were broken or not enabled. Verbatim from their postmortem: `pg_dump` "failed silently because it was using PostgreSQL 9.2, while GitLab.com runs on PostgreSQL 9.6"; "Azure disk snapshots were not enabled ... as we assumed that our other backup procedures were sufficient"; replication was "primarily used for failover ... and not for disaster recovery." The root cause is the seam this finding is about: **"Why was the backup procedure not tested on a regular basis? — Because there was no ownership, as a result nobody was responsible for testing this procedure."** They permanently lost "at least 5000 projects, 5000 comments, and roughly 700 users." The industry distillation: "you don't have backups until you've successfully restored from them"; "30-40% of organizations that never test their backups discover critical failures only when attempting recovery during an actual disaster." That uncovered window is the irrecoverable cost — and the longer a product runs *without* the seam, the larger the window of permanently-unrecoverable history.

**retrofit_cost: H for the lost data, L/M for the mechanism.** Per the honesty filter: bolting on a backup job and a restore task later is ordinary work (M, arguably L). But every byte written between launch and "first *verified* restore" is unrecoverable if it's lost in that window — and teams routinely discover their untested backups don't restore *at the moment they need them*. Scaffolding the **drill** (not just the backup) from day 1 is what shrinks that irrecoverable window to ~zero. This is explicitly **NOT** the deploy contract / migration-aware rollback the board lists as covered: that restores *code+schema*, never *data* — `strategy.sh` itself notes "Irreversible migrations cannot be restored."

**Early scaffolding concretely.** In `infra/`: an opt-in `db:backup` task (logical dump for Postgres, snapshot hook for managed DBs) writing to an encrypted off-host target; a checked-in `DR.md` runbook declaring **RPO** (acceptable data-loss window) and **RTO** (acceptable downtime) defaults and pointing at the 3-2-1 rule (3 copies, 2 media, 1 off-site); and the load-bearing piece — a `db:restore-drill` task that restores the latest backup into a disposable compose stack and asserts row counts / a smoke query, runnable in CI on a schedule so an undetected `pg_dump`-version-skew failure is caught the way GitLab's wasn't.

**Evidence/sources.**
- GitLab, "Postmortem of database outage of January 31" (silent `pg_dump` version mismatch; snapshots disabled; "nobody was responsible for testing this procedure"; 5000 projects/comments + 700 users lost): https://about.gitlab.com/blog/postmortem-of-database-outage-of-january-31/
- CubePath, "Backup Testing and Restoration: Complete Validation Guide" ("you don't have backups until you've successfully restored from them"; "30-40% ... discover critical failures only when attempting recovery"): https://cubepath.com/docs/backup-recovery/backup-testing-and-restoration
- TechTarget, "Sorry, backups are just not enough to guarantee restoration": https://www.techtarget.com/searchdatabackup/tip/Sorry-backups-are-just-not-enough-to-guarantee-restoration
- Veeam, "RTO vs RPO: What They Mean and How To Set Targets" (RPO = tolerable data loss, RTO = tolerable downtime): https://www.veeam.com/blog/recovery-time-recovery-point-objectives.html

**Proposed disposition: battery** ("disaster-recovery / data backup+restore-drill") — opt-in, fits the battery model, and naturally extends the existing deploy/observability surface. The drill is the differentiator; without it, it's just another backup script.

**Overlaps with the board.** **Distinct from** the **deploy contract + migration-aware rollback (already covered)** — that is *code/schema* recovery; this is *data* recovery. Note that distinction on the board so they aren't conflated. Adjacent to per-tenant restore in the **multitenancy** board item (selective per-tenant restore is a multitenancy concern), but the base backup/restore contract is tenancy-agnostic.

---

## 3. Supply-chain integrity — SBOM + build provenance + artifact signing (the layer ABOVE gitleaks/dependabot)

**Axis:** supply-chain integrity — SBOM (CycloneDX/SPDX), build **provenance/attestation** (SLSA, in-toto), artifact **signing** (Sigstore/cosign). The board lists gitleaks/dependabot as covered; those are *secrets + known-CVE-bumps*. SBOM/provenance/signing is a **strictly higher layer** — "what exactly did we ship, and can a consumer cryptographically prove it came from our pipeline."

**The seam.** Emit a **machine-readable SBOM at build time** (not from a later binary scan), attach **build provenance** (a signed statement of *how* the artifact was built), and **sign the image** with keyless Sigstore/cosign — all wired into the release pipeline from the first build, so every artifact the project has ever shipped carries a verifiable bill of materials and provenance.

**Why late is expensive — regulatory deadline + a provenance-irrecoverability tail.** The dominant pull is **regulatory and dated**: the EU Cyber Resilience Act requires a machine-readable SBOM "covering at least the top-level dependencies of every product with digital elements," with **vulnerability/incident reporting obligations from September 11, 2026** and **full compliance (CE marking, SBOM, conformity assessment) by December 11, 2027**; non-compliance is "up to €15 million or 2.5% of global annual turnover." US procurement was accelerated by EO 14028 (post-SolarWinds/Log4Shell), and SLSA/Sigstore are the now-standard mechanics. There is *also* an irrecoverability tail that nudges this above "pure config": a build-time SBOM "captures the exact components and versions compiled into a specific release," whereas retrofitting from a binary loses fidelity — "provenance information is lost during compilation, making it difficult to trace the origin and history of certain components," and statically-linked versions fall back to "heuristics that don't always work correctly." And "if a consumer needs to audit an old version a decade from now, that specific matching SBOM must be retrievable" — you can't perfectly reconstruct it after the build environment is gone.

**retrofit_cost: M (honest).** The advisor's call holds: this is fundamentally **build-pipeline config you can add to CI at any point** — a `docker buildx` SBOM/attestation flag, a `syft`/CycloneDX step, a `cosign sign` step. The regulatory pull is a *deadline*, not *irrecoverability*; the provenance-loss tail is real but narrow (it degrades fidelity of *old* releases, it doesn't destroy live data). Rating it H would fail the honesty filter. It is M with a near-term regulatory clock, which is exactly why scaffolding it *now* (cheap) beats scrambling against a 2026/2027 deadline (still cheap, but rushed and incomplete on the back-catalog).

**Early scaffolding concretely.** In the release/CI pipeline the framework already owns: emit a CycloneDX or SPDX SBOM at image build (`docker buildx --sbom=true` / a `syft` step), generate a SLSA provenance attestation, and `cosign sign`/`cosign attest` the image keylessly via the OIDC identity of the GitHub Actions run; publish the SBOM as a release artifact. Default it on for the build job so every shipped tag carries it from the first release.

**Evidence/sources.**
- Mend.io, "EU Cyber Resilience Act: 2026 Compliance Guide" + Keysight "One Year Countdown ... September 11, 2026" (Sept 11 2026 reporting; Dec 11 2027 full compliance; €15M / 2.5% penalties; machine-readable SBOM of top-level deps): https://www.mend.io/blog/eu-cyber-resilience-act-compliance-guide/ , https://www.keysight.com/blogs/en/tech/nwvs/2025/09/11/one-year-countdown-to-eu-cra-compliance-september-11-2026-changes-everything
- Anchore, "EU CRA SBOM Requirements": https://anchore.com/sbom/eu-cra/
- Sigstore blog, "cosign Verification of npm Provenance, GitHub Artifact Attestations" (keyless signing/attestation mechanics): https://blog.sigstore.dev/cosign-verify-bundles/
- Kusari, "SLSA — What is it?" (provenance attestation = signed claim of how an artifact was built): https://www.kusari.dev/learning-center/slsa-supply-chain-levels-for-software-artifacts
- RunSafe / Interlynk, "3 SBOM Generation Methods" + "SBOM Strategy & Attestation" (build-time > binary scan; lost provenance at compile time; old SBOMs must remain retrievable): https://runsafesecurity.com/blog/sbom-generation-methods/ , https://www.interlynk.io/resources/sbom-strategy-attestation-model-for-oss-projects
- NIST, "EO 14028 — Improving the Nation's Cybersecurity" (SBOM/SLSA acceleration post-SolarWinds): https://www.nist.gov/itl/executive-order-14028-improving-nations-cybersecurity

**Proposed disposition: concern** — a posture-level build-pipeline default (SBOM + provenance + signing on the release job), scaffolded early. M cost, but the seam *belongs in the pipeline the framework already owns*, so the marginal cost of doing it now is near zero and the CRA clock is running.

**Overlaps with the board.** Extends **supply-chain (gitleaks/dependabot, already covered)** to the *artifact-integrity* layer those don't touch. Name the distinction on the board: gitleaks=secrets, dependabot=CVE bumps, **this**=SBOM/provenance/signing. No board item covers it.

---

## 4. Data portability / export — no machine-readable account/data export seam (GDPR Art. 20 + anti-lock-in)

**Axis:** data portability / export.

**The seam.** A **structured, machine-readable export** of a user's (or tenant's) data — a "Download my data" path that emits JSON/CSV with field labels, mapped from the domain model. The shape decision (what's exportable, in what schema) is cheap when there are a handful of tables and brutal once the model has sprawled.

**Why late is expensive — but recoverable.** GDPR Article 20 grants the right to receive personal data "in a structured, commonly used and machine-readable format," and "eliminates lock-in by preventing businesses from ... making it difficult to export data from their platform." The retrofit pain is real: the export must enumerate *every* store that holds a user's data (the same enumeration problem the erasure-gap reviewer already fights), and a model that grew without an export contract requires hunting down each table/blob/index after the fact, with format constraints ("PDF scans don't comply ... proprietary formats don't comply ... plain text dumps without field labels don't meet the requirement"). **But** — applying the honesty filter — this is **recoverable**: you can always build the export pipeline later against whatever data exists; nothing is *lost*, you just do more archaeology. That makes it M, not H.

**retrofit_cost: M.** More work later (enumerate stores, define a schema, build the endpoint), but no irrecoverable loss — the data is still there to export whenever you build the path.

**Early scaffolding concretely.** A scaffolded `GET /me/export` (and tenant-scoped variant) that serializes the user's owned rows to labeled JSON via the existing Pydantic schemas, with a registry of "exportable models" the builder extends as they add tables — turning a future archaeology project into a one-line registration per model. Pairs naturally with the erasure path (same store-enumeration).

**Evidence/sources.**
- GDPR-info, "Art. 20 GDPR – Right to data portability": https://gdpr-info.eu/art-20-gdpr/
- Legiscope, "GDPR Right to Data Portability (Art. 20): When + Format" (machine-readable; PDF/proprietary/unlabeled fail): https://www.legiscope.com/blog/data-portability-right.html
- Auth0 Docs, "GDPR: Data Portability" (implementation: build export into the app): https://auth0.com/docs/secure/data-privacy-and-compliance/gdpr/gdpr-data-portability

**Proposed disposition: reviewer-enforced** (the `data-lineage` reviewer already owns the store-enumeration / erasure-gap problem — extend it to assert exportability/erasability symmetry), with a thin **battery** option if a self-service export endpoint is wanted. Leaning reviewer-enforced given the M cost and heavy overlap below.

**Overlaps with the board.** Heavy overlap with the **`data-lineage` erasure-gap reviewer** (same "find every store that holds this user's data" problem) and adjacent to the **multitenancy** board item (tenant-level export). Not a standalone high-pull seam; surface it as the export-symmetry of erasure.

---

## 5. FinOps / cost budgets — no per-feature cost attribution or budget guardrails

**Axis:** performance & cost budgets (FinOps).

**The seam.** Cost *attribution* tags + a budget guardrail: emitting a cost/usage dimension (per tenant, per feature, per expensive call — LLM tokens, vector queries, egress) so spend can be attributed, plus an alert/budget threshold. The attribution dimension is the part with any retrofit edge — you can't attribute spend you never tagged.

**Why late is expensive — mostly recoverable, low pull for a single-project scaffold.** The genuinely-irrecoverable sliver is **per-tenant/per-feature cost attribution**: spend that flowed *before* you tagged it can't be retroactively attributed, so you can't answer "which tenant/feature is unprofitable" for the pre-instrumentation period. But for a fresh single-project scaffold, the pull is low: there's no spend yet, the LLM-token-cost case is already implicitly in scope of the **AI batteries**, and the per-tenant-cost case is owned by the **multitenancy** board item. The general budget-alert mechanism is ordinary observability work added anytime.

**retrofit_cost: M (and park-ish).** The attribution dimension has a small irrecoverable edge (un-tagged historical spend), but the overall pull on a single-project scaffold is low and the high-value slices live under batteries/multitenancy already on the board.

**Early scaffolding concretely.** If pursued: a cost/usage label convention on the existing OpenTelemetry surface (tenant_id, feature, model) and a budget-alert stub in alertmanager — but this is better folded into the AI-battery and multitenancy work than scaffolded standalone.

**Evidence/sources.** (Axis is well-established; the seam is low-pull here, so I did not over-invest in sourcing.) FinOps Foundation cost-attribution / showback principles and the general "tag spend at emission, you can't attribute it retroactively" rule.

**Proposed disposition: park** — real axis, low immediate pull for a single-project scaffold; the high-value slices (LLM token cost, per-tenant cost) belong to the AI batteries and the multitenancy board item.

**Overlaps with the board.** Per-tenant cost → **multitenancy** (board). LLM/vector-query cost → **AI-retrieval / agents batteries** (board). No standalone seam left after those.

---

## 6. Accessibility-by-construction — the CI axe gate already ships (park; named so the lead axis is visibly addressed)

**Axis:** accessibility-by-construction (legal/regulatory — ADA, the European Accessibility Act in force June 2025). This is the *first* axis my area description lists, so it gets an explicit verdict rather than silence.

**Finding (verified by template grep, not assumed):** the by-construction seam — a **CI accessibility gate that fails the build on violations** — is **already in the template**. The React battery's `frontend/package.json` pulls `@axe-core/playwright`; `frontend/e2e/items.spec.ts` runs `new AxeBuilder({ page }).analyze()` in a test literally titled *"items page renders and has no axe violations"*; and `.github/workflows/ci.yml.jinja` wires the "Playwright + axe" e2e into the frontend CI job. That is exactly the *proactive* by-construction gate (not just reactive defect-catching) — a sprawled component tree never accumulates axe violations because CI rejects them at the PR. On top of that, the `accessibility` **reviewer** catches per-diff defects (div-onClick, missing alt, broken aria) and there is an `accessibility` **battery**. The genuinely-H-retrofit story for a11y (Domino's ADA suit; retrofitting WCAG into a finished component tree) is the precise pain this scaffolded-from-commit-1 gate prevents — and the framework already prevents it.

**retrofit_cost: L (for the framework — nothing left to do).** The high-retrofit-cost seam is already shipped; only marginal niceties (axe rule tuning, a contrast-token check) remain, all L.

**Evidence/sources.**
- Internal: template grep (above) — `@axe-core/playwright` dep + `AxeBuilder(...).analyze()` e2e + ci.yml "Playwright + axe" job; the `accessibility` reviewer (`src/framework_cli/review/agents/accessibility.md`) and battery.
- Regulatory pull (for context — the seam is covered, so I did not over-source): European Accessibility Act (in force June 28, 2025) and ADA Title III web-accessibility case law (Domino's) are the same regulatory-deadline shape as the CRA finding (#3) — but unlike CRA, this one the framework already answers.

**Proposed disposition: park** — the lead non-functional axis, checked and found **already covered** by the template's CI axe gate + the `accessibility` reviewer + battery. Recorded explicitly so the axis isn't silently dropped; overlaps the design-system assessment (phase1-09).

**Overlaps with the board.** Not on the board, but **already shipped by the framework** (CI axe gate + `accessibility` reviewer + battery) and adjacent to the **design-system / components** assessment (phase1-09). Nothing to add.

---

## 7. Capacity / scaling — already owned by the `performance` reviewer + k6 (reject as a new seam)

**Axis:** capacity / scaling.

**Finding:** the concrete sub-seams here are **already covered**. "Connection-pool exhaustion," "unbounded scan," and "N+1" are *verbatim* the `performance` reviewer's stated domain ("Flag (high) an unbounded scan, an N+1 query, connection-pool exhaustion, or accidentally super-linear work on unbounded input"). Load/capacity testing is **k6 (already covered)**. There is no high-retrofit-cost capacity seam left that the performance reviewer and k6 don't already own.

**retrofit_cost: n/a — reject.** Re-treading covered ground.

**Proposed disposition: park** (effectively reject — kept here only to record that the axis was checked and found covered, per the task's "note overlaps rather than dropping").

**Overlaps with the board.** Fully covered by the **`performance` reviewer** and **k6 load/perf testing** (both already covered). Nothing new.

---

## 8. Operability — graceful shutdown / health probes already ship; only runbook stubs remain (park)

**Axis:** operability — on-call, runbooks, incident response, graceful lifecycle.

**Finding (verified by template grep, not assumed):** the operability *core* is **already in the template**. `src/{{package_name}}/main.py.jinja` ships a `lifespan` whose shutdown hook disposes the DB engine — its own comment: *"On SIGTERM, uvicorn triggers shutdown — we close DB connections."* `tests/functional/test_graceful_shutdown.py.jinja` asserts the engine is disposed on shutdown; `routes/health.py.jinja`, `test_health.py`, and `test_health_probes.py` ship health/readiness; compose files carry `healthcheck`s. So graceful in-flight lifecycle + probes — the parts that are H to retrofit — are done.

What's *not* present is the soft operability glue: a **runbook/incident template** (`RUNBOOK.md`/`docs/runbooks/`), an on-call escalation stub, and an incident-postmortem template. These are **L to retrofit** (drop in a markdown template anytime; no data or contract is at stake) — the opposite of the lens this scan targets.

**retrofit_cost: L.** Markdown stubs added anytime; nothing irrecoverable.

**Early scaffolding concretely.** A `RUNBOOK.md` stub (common ops: restart, scale, drain, rollback pointers) and a `docs/postmortem-template.md` — nice-to-have, low pull. Worth a one-line add when touching docs, not a standalone seam.

**Evidence/sources.** Internal: template grep (above) confirming `lifespan`/SIGTERM/health/graceful-shutdown already ship. The runbook-stub gap is a documentation nicety, not a retrofit risk.

**Proposed disposition: park** — the high-retrofit-cost half (graceful shutdown, probes) is **already covered** by the template; the remaining half (runbook/postmortem stubs) is L-cost and low-pull.

**Overlaps with the board.** Graceful shutdown / health probes are **already shipped by the framework** (not on the board, but in the template — verified). The remaining runbook stubs overlap nothing of substance.

---

## Summary table

| # | Seam | Axis | retrofit_cost | Disposition | Why |
|---|------|------|:---:|------|------|
| 1 | License-policy CI gate (copyleft/GPL/AGPL) | dependency licensing | **H** | concern (+ reviewer) | obligation already incurred; $10M-class M&A rip-out; `dependency` reviewer explicitly excludes license |
| 2 | Data backup/restore **drill** (RPO/RTO) | disaster recovery | **H** (lost data) / L–M (mechanism) | battery | data lost before a *verified* restore is irrecoverable (GitLab 2017); ≠ code rollback |
| 3 | SBOM + provenance + signing | supply-chain integrity | **M** | concern | build-pipeline config, but CRA clock (Sept 2026 / Dec 2027) + provenance-loss tail; layer above gitleaks/dependabot |
| 4 | Machine-readable data export | data portability | **M** | reviewer-enforced (+ thin battery) | recoverable (build it later); heavy overlap with data-lineage erasure-gap |
| 5 | FinOps cost attribution/budgets | performance & cost | **M** | park | low pull for single-project scaffold; slices owned by AI batteries + multitenancy |
| 6 | Accessibility-by-construction | accessibility (ADA/EAA) | **L** | park | CI axe gate + `accessibility` reviewer + battery **already ship**; lead axis, checked |
| 7 | Capacity / scaling | capacity | **L** | park | already owned by `performance` reviewer + k6 |
| 8 | Operability (graceful/health) | operability | **L** | park | core already ships in template; only runbook stubs remain |

**Net:** two honestly-High, uncovered seams to act on — **#1 dependency licensing** (concern + reviewer) and **#2 data restore-drill** (battery). **#3 SBOM/signing** is M but cheap-now against a hard regulatory deadline, and lives in a pipeline the framework already owns, so it's a strong concern. The rest are correctly M/L and fold into existing board items or already-shipped template features.
