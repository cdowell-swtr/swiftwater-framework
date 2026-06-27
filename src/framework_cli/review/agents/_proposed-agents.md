# Agentic Code Reviewers

## Existing

### Gate # run on *every* push

#### Core engineering

* architecture.md			# Reviews system structure, module boundaries, layering, coupling, cohesion, dependency direction, ownership boundaries, and whether the design will remain understandable as the codebase grows
* application-logic.md			# Reviews whether implemented behavior matches intended application behavior, including control flow, domain flow, branching logic, and user/system state changes
* configuration.md			# Reviews environment variables, config schemas, defaults, validation, fail-fast behavior, feature flags, config drift, secret/config separation, and local/staging/prod behavior
* dependency.md				# Reviews dependency choices, unnecessary packages, version pinning, transitive dependency risk, abandoned libraries, over-heavy dependencies, and dependency hygiene

#### APIs, contracts, and integrations

* contracts.md				# Reviews explicit contracts between modules, services, APIs, consumers, schemas, jobs, events, and external systems, including whether assumptions are testable and documented

#### Data, storage, and persistence

* data-integrity.md			# Reviews correctness, constraints, uniqueness, referential integrity, validation, corruption risk, data loss risk, and whether stored data remains trustworthy over time

#### Security-adjacent and trust

* security.md				# Reviews general application security posture, unsafe patterns, insecure defaults, attack surface, validation gaps, exposure risk, and issues not already owned by a more specialized security panel

#### Testing and quality

* test-quality.md			# Reviews whether tests are meaningful, readable, behavior-focused, maintainable, deterministic, and likely to catch real regressions rather than merely exercise implementation details

#### Change-risk and AI-coding governance

* footgun-sentinel.md			# Reviews code, APIs, defaults, configuration, scripts, tests, and workflows for sharp edges that make accidental misuse likely; flags surprising behavior, dangerous defaults, ambiguous names, unsafe convenience paths, hidden coupling, irreversible actions, misleading abstractions, and places where a future developer could do the obvious thing and cause damage
* semantic-ambiguity.md			# Reviews names, states, flags, comments, and APIs whose meaning is likely to be misunderstood later; flags overloaded terms, vague booleans, misleading function names, unclear ownership, ambiguous status values, and domain language that does not match user/business reality

### Tier 1 # run on *every* release

#### APIs, contracts, and integrations

* api-design.md				# Reviews API shape, resource modeling, naming, consistency, pagination, filtering, status codes, error bodies, versioning, ergonomics, and client expectations
* template-generation.md		# Reviews template rendering, conditional files, Copier variables, generated paths, battery combinations, upgrade compatibility, stale generated artifacts, and whether all supported template permutations remain coherent
#### Documentation and maintainability

* documentation.md			# Reviews README content, inline comments, API docs, setup instructions, architecture notes, decision records, runbooks, examples, and whether documentation matches current behavior

#### Environment, parity, and developer experience

* env-parity.md				# Reviews differences between local, test, staging, CI, and production environments, including config, services, credentials, data, feature flags, dependency versions, and infrastructure assumptions
* local-dev-safety.md			# Reviews dangerous local defaults, accidental production access, destructive scripts, shared credentials, local data handling, and whether dev tooling can cause real-world damage

#### Frontend, UX, and accessibility

* accessibility.md			# Reviews keyboard access, semantic markup, ARIA usage, focus management, screen reader behavior, color contrast, motion, form labels, and inclusive interaction patterns
* usability.md				# Reviews whether flows are understandable, forgiving, efficient, discoverable, consistent, and aligned with user expectations, especially around errors, empty states, and complex actions

#### Observability, operations, and production readiness

* deployability.md			# Reviews health checks, readiness/liveness, startup/shutdown behavior, zero-downtime deploys, migration ordering, worker deploys, cron jobs, feature flags, and rollback feasibility
* observability-db.md			# Reviews database metrics, slow queries, connection pools, locks, replication lag, migration visibility, query plans, storage growth, and database-specific operational insight
* observability-fe.md			# Reviews frontend errors, performance metrics, user journey telemetry, client logs, session replay risk, Core Web Vitals-style signals, and visibility into browser-side failures
* observability-infra.md		# Reviews infrastructure metrics, container/node health, autoscaling, network behavior, load balancers, queues, workers, deployment signals, and platform-level visibility
* observability.md			# Reviews logs, metrics, traces, alerts, correlation IDs, dashboards, service-level indicators, error visibility, and whether production behavior can be understood
* performance.md			# Reviews latency, throughput, algorithmic complexity, database access patterns, memory use, caching, frontend performance, startup time, and whether performance fits expected use

#### Security-adjacent and trust

* compliance.md				# Reviews legal/regulatory/process obligations, required controls, evidence, data handling constraints, audit readiness, policy alignment, and jurisdiction- or industry-specific requirements
* privacy.md				# Reviews personal data collection, minimization, consent, exposure, retention, purpose limitation, access controls, logging, analytics, third-party sharing, and user privacy expectations

#### Testing and quality

* coverage-gap.md			# Reviews important untested paths, missing edge cases, untested failure modes, integration gaps, high-risk code without tests, and misleading coverage confidence

### Tier 2 # run periodically

#### Data, storage, and persistence

* data-lineage.md			# Reviews where data comes from, how it is transformed, whether provenance is preserved, whether derived data can be explained, and whether downstream consumers know what they are using

### Tier 3 # run on concerning changes

<!-- No existing agents assigned here yet -->

## Additional agents to consider

### Gate # run on *every* push

#### Core engineering

* business-rules.md			# Reviews whether product, pricing, eligibility, workflow, permissions, and domain-specific rules are represented correctly and explicitly rather than being scattered or implicit
* edge-cases.md				# Reviews boundary conditions, empty states, nulls, missing inputs, duplicates, min/max values, first/last/only cases, malformed data, and unexpected but plausible usage
* error-handling.md			# Reviews exception handling, error classification, user-facing errors, developer-facing errors, context preservation, cleanup paths, and whether failures are visible rather than swallowed
* resource-management.md		# Reviews files, sockets, DB sessions, cursors, locks, transactions, temp files, memory, generators, context managers, cleanup, and leak-prone code paths
* typing.md				# Reviews Python type annotations, Any leakage, Optional/null handling, type checker configuration, runtime validation at boundaries, public interface types, and consistency between models and data

#### Change-risk and AI-coding governance

* ai-agent-safety.md			# Reviews AI-generated changes for agentic failure modes, including fake completion, weakened tests, over-broad edits, fabricated APIs, hidden shortcuts, unsafe automation, and changes outside the user’s intent
* diff-risk.md				# Reviews the actual delta rather than the final files, focusing on removed validation, loosened tests, swallowed errors, changed guarantees, data-shape changes, config changes, and surprising behavioral shifts
* implementation-honesty.md		# Reviews whether the implementation is real rather than stubbed, hardcoded, TODO-driven, test-only, silently degraded, mocked inappropriately, or described by comments that exceed actual behavior
* reviewability.md			# Reviews whether a human can safely review the change, including PR size, coherence, naming, generated-code noise, renames mixed with logic changes, test mapping, risk notes, and verification instructions
* scope-control.md			# Reviews whether the change stayed within the requested scope, avoiding unrelated refactors, formatting churn, dependency upgrades, opportunistic rewrites, and broad “while I was here” edits

### Tier 1 # run on *every* release

#### Core engineering

* anti-patterns.md			# Reviews god objects, shotgun surgery, feature envy, primitive obsession, boolean flag soup, temporal coupling, hidden global state, leaky abstractions, excessive indirection, anemic wrappers, and premature generalization
* async-python.md			# Reviews async correctness, missing awaits, blocking I/O inside async code, event loop misuse, task cancellation, timeouts, connection pooling, background task lifecycle, and context propagation
* blast-radius.md			# Reviews how far damage can spread when something fails, misfires, or is misused; flags overly broad permissions, global operations, shared state, all-tenant effects, unbounded jobs, destructive defaults, and missing containment boundaries
* boomerang-risk.md			# Reviews choices that look expedient now but are likely to return as larger future problems; flags shortcuts, deferred decisions, ambiguous ownership, brittle assumptions, and “temporary” compromises with no expiry, owner, or cleanup path
* concurrency.md			# Reviews race conditions, locking, transaction boundaries, concurrent updates, lost updates, double-processing, optimistic/pessimistic locking, and shared mutable state
* coupling-creep.md			# Reviews ways unrelated parts of the system become quietly entangled; flags hidden dependencies, shared globals, cross-layer imports, feature-specific conditionals in generic modules, duplicated assumptions, and changes that make future work require touching too many places
* design-patterns.md			# Reviews whether useful patterns are available where they would reduce complexity, clarify variation, isolate dependencies, or make behavior easier to test and evolve
* false-confidence.md			# Reviews signals that may make the team believe the system is safer than it is; flags weak tests, misleading coverage, shallow mocks, happy-path demos, green CI hiding skipped checks, dashboards without useful alerts, and documentation that overstates guarantees
* idempotency.md			# Reviews retry safety, duplicate submissions, webhook replays, queue redelivery, idempotency keys, repeated job execution, and whether operations can safely run more than once
* invariant-drift.md			# Reviews whether important system invariants can erode over time; flags assumptions not enforced at boundaries, duplicated validation, missing constraints, weak data models, informal conventions, and logic that relies on callers always doing the right thing
* optionality-loss.md			# Reviews choices that unnecessarily close off future paths; flags premature vendor lock-in, irreversible data shapes, over-specific abstractions, hardcoded policy, one-client assumptions, and designs that make likely future changes expensive
* policy-creep.md			# Reviews places where business, product, legal, security, or moderation policy becomes embedded in scattered code instead of explicit rules; flags hardcoded thresholds, duplicated eligibility logic, hidden exceptions, and policy changes that would require risky code archaeology
* resilience.md				# Reviews timeouts, retries, fallbacks, partial failure behavior, degraded modes, circuit-breaker-like patterns, external dependency failures, and survival under non-happy-path conditions
* serialization.md			# Reviews JSON/YAML/Pickle/Pydantic/dataclass serialization, unsafe deserialization, schema evolution, Decimal/datetime handling, encoding, precision loss, and compatibility between versions
* silent-failure.md			# Reviews places where the system can appear healthy while doing the wrong thing; flags swallowed errors, misleading success states, partial writes reported as complete, stale data presented as fresh, degraded fallbacks without visibility, and metrics/logs that would hide the failure
* state-management.md			# Reviews lifecycle transitions, valid/invalid states, state machines, stale state, derived state, recovery after interruption, and whether state can become contradictory
* time.md				# Reviews timezone handling, DST, naive vs aware datetimes, clock skew, expiration, scheduling, ordering by time, “today” boundaries, fiscal/calendar periods, and testability of time-dependent code

#### Change-risk and AI-coding governance

* backwards-compatibility.md		# Reviews compatibility with older clients, existing serialized data, public APIs, database state, config, integrations, contracts, feature flags, and deprecation expectations
* generated-code.md			# Reviews generated files, codegen boundaries, checked-in artifacts, source-of-truth confusion, regeneration instructions, hand-edited generated code, and generated-code noise hiding logic changes
* regression-risk.md			# Reviews what existing behavior could break, whether past bugs could recur, whether compatibility assumptions changed, and what regression tests should exist because this kind of failure is plausible
* release-notes.md			# Reviews whether user-visible changes, migration steps, breaking changes, operational risks, config changes, and known limitations are documented for release or handoff

#### Data, storage, and persistence

* cache-correctness.md			# Reviews cache keys, invalidation, TTLs, permission-aware caching, tenant separation, stale reads, stampedes, consistency assumptions, and whether cached data can become misleading or unsafe
* data-modeling.md			# Reviews schema design, entity relationships, normalization/denormalization, ownership, lifecycle, indexes, constraints, extensibility, and whether the data model matches the domain
* data-retention.md			# Reviews deletion, archival, legal hold, retention windows, soft vs hard delete, backup copies, analytics copies, user deletion requests, and whether data lives longer than intended
* migrations.md				# Reviews database/schema migrations, rollback safety, expand/contract patterns, backfills, default values, nullable transitions, locking risk, idempotency, version skew, and production data volume assumptions

#### APIs, contracts, and integrations

* cli-admin-tools.md			# Reviews one-off scripts, admin commands, backfills, maintenance tools, dry-run modes, confirmation prompts, logging, idempotency, and whether internal tools are production-safe
* events-messaging.md			# Reviews queues, topics, event schemas, ordering, delivery semantics, poison messages, retries, dead letters, consumers, producers, and assumptions about exactly-once behavior
* file-handling.md			# Reviews uploads, downloads, content types, file size limits, scanning hooks, storage paths, metadata, lifecycle, access control handoff, and safe file parsing
* pagination-filtering-sorting.md	# Reviews list endpoints, stable ordering, cursor correctness, offset risks, filter semantics, sort edge cases, duplicate/missing rows across pages, and performance implications
* rate-limits-quotas.md			# Reviews API limits, user limits, internal throttling, retry-after behavior, quota exhaustion, fair-use controls, burst behavior, model/API spend limits, and backpressure
* third-party-integrations.md		# Reviews external API usage, timeouts, retries, auth, quotas, schema drift, SDK behavior, degraded mode, sandbox/prod differences, and mock fidelity
* webhooks.md				# Reviews webhook signatures, replay protection, ordering, retries, idempotency, event versioning, dead-letter handling, observability, and consumer/provider compatibility

#### Testing and quality

* accessibility-testing.md		# Reviews whether accessibility is tested with automated checks, keyboard flows, screen reader assumptions, focus management, semantic markup, color contrast, and manual verification where needed
* determinism.md			# Reviews flaky tests, unstable snapshots, time/random/network/order dependence, hidden global state, concurrency nondeterminism, and test behavior that changes across environments
* e2e-testing.md			# Reviews end-to-end user journeys, critical workflows, browser/API paths, happy and unhappy paths, test brittleness, setup cost, and whether E2E tests cover the right thin slice
* integration-testing.md		# Reviews cross-module/service/database/API behavior, realistic test boundaries, environment setup, external dependency substitutes, and whether integration risk is actually covered
* mocking.md				# Reviews mocks, fakes, stubs, monkeypatches, contract fidelity, over-mocking, unrealistic external behavior, and whether tests still exercise meaningful code paths
* mutation-testing.md			# Reviews whether tests would fail if logic were meaningfully changed, identifying assertions that are too weak, tests that only check execution, and logic branches with no behavioral pressure
* performance-testing.md		# Reviews load, stress, soak, benchmark, and regression testing for speed, memory, concurrency, database load, queue depth, and realistic traffic patterns
* test-fixtures.md			# Reviews fixture realism, isolation, determinism, over-broad fixtures, hidden production assumptions, data leakage, fixture reuse, and whether fixtures make tests too forgiving

#### Security-adjacent and trust

* abuse-prevention.md			# Reviews product abuse by legitimate-looking users, including spam, scraping, enumeration, trial abuse, bulk actions, cost amplification, fake accounts, griefing, and resource exhaustion
* auditability.md			# Reviews whether important actions answer who/what/when/where/why/how, including admin actions, system actions, agent actions, before/after state, correlation IDs, and forensic usefulness
* input-validation.md			# Reviews untrusted input handling, normalization, parsing, allowlists, encoding, SQL/NoSQL injection, command injection, path traversal, SSRF, unsafe deserialization, and file parsing
* secure-defaults.md			# Reviews default-deny behavior, least privilege defaults, safe local/dev defaults, debug settings, secure headers, TLS assumptions, production config, and whether unsafe behavior requires explicit opt-in
* supply-chain.md			# Reviews package provenance, lockfiles, transitive dependencies, package confusion, build scripts, CI actions, container bases, generated artifacts, maintainer risk, and tool/model dependencies
* threat-model.md			# Reviews assets, actors, entry points, trust boundaries, attack paths, likely abuse cases, high-impact failures, and whether mitigations match realistic threats
* trust-boundaries.md			# Reviews boundaries between users, tenants, services, workers, queues, webhooks, models, tools, admin paths, and “internal” systems that may be trusted too much

#### Observability, operations, and production readiness

* background-jobs.md			# Reviews scheduled jobs, workers, queues, retries, dead letters, idempotency, observability, concurrency, locking, backfills, and operational behavior outside request/response paths
* build-release.md			# Reviews packaging, reproducible builds, CI/CD, Docker hygiene, artifacts, versioning, changelogs, release sequencing, signing/checksums where relevant, and deployment coordination
* cost.md				# Reviews cloud spend, database spend, logging/tracing volume, LLM/API cost, storage growth, CI minutes, expensive defaults, inefficient queries, and avoidable operational waste
* incident-readiness.md			# Reviews runbooks, alert ownership, escalation, rollback plans, kill switches, dashboards, support communication, postmortem hooks, and whether the team could respond under pressure
* operational-surprise.md		# Reviews changes that may surprise operators in production; flags new background load, new alert noise, hidden dependencies, changed runbooks, new failure modes, unusual deployment ordering, maintenance burden, and behavior that differs from established operational expectations

#### Frontend, UX, and accessibility

* browser-compatibility.md		# Reviews browser support assumptions, APIs, polyfills, CSS compatibility, mobile browser behavior, and graceful degradation
* content-quality.md			# Reviews labels, helper text, empty states, confirmation copy, destructive-action warnings, error messages, onboarding text, and whether interface language reduces confusion
* design-system.md			# Reviews component reuse, visual consistency, responsive behavior, spacing, tokens, theming, variants, and whether new UI creates design drift
* forms-validation.md			# Reviews client/server validation parity, error placement, required fields, partial submits, dirty state, input masks, recovery paths, and whether invalid data can sneak through
* frontend-state.md			# Reviews loading states, optimistic updates, stale queries, racey interactions, cache invalidation, offline/slow network behavior, double clicks, and form state consistency
* localization.md			# Reviews dates, times, numbers, currencies, pluralization, address formats, Unicode, sorting, translations, text expansion, right-to-left readiness, and locale-sensitive assumptions
* responsive-design.md			# Reviews behavior across screen sizes, touch targets, mobile layouts, overflow, scrolling, breakpoints, and whether functionality remains usable on constrained screens

#### Documentation and maintainability

* code-organization.md			# Reviews file layout, naming conventions, module boundaries, import structure, circular dependencies, public/private interfaces, and discoverability
* comments-intent.md			# Reviews whether comments explain why rather than restating what, whether comments are stale, and whether important business or safety intent is preserved near the code
* maintainability.md			# Reviews readability, naming, decomposition, complexity, duplication, abstraction quality, local reasoning, comments, and whether future maintainers can safely modify the code

#### Environment, parity, and developer experience

* ci-cd.md				# Reviews pipeline correctness, required checks, caching, parallelism, secrets handling, test selection, artifact handling, deploy gates, and whether CI reflects real release risk

### Tier 2 # run periodically

#### Core engineering

* dependency-upgrade-risk.md		# Reviews breaking changes from dependency upgrades, Python version compatibility, lockfile changes, migration notes, transitive version shifts, and hidden behavior changes

#### Data, storage, and persistence

* analytics-integrity.md		# Reviews event tracking, metrics definitions, funnel correctness, duplicate events, missing events, identity stitching, attribution, data drift, and whether product/business analytics can be trusted
* backup-restore.md			# Reviews backup coverage, restore testing, RPO/RTO assumptions, disaster recovery, seed data, recovery runbooks, and whether the system can actually be restored under pressure
* import-export.md			# Reviews CSV/JSON/file import and export flows, encoding, escaping, partial failures, large files, duplicate rows, schema changes, user-visible errors, and data leakage through exports
* search-indexing.md			# Reviews indexing pipelines, reindexing, stale search results, permission filtering, query escaping, ranking, multilingual search, indexing latency, and mismatch between source data and search data

#### Observability, operations, and production readiness

* capacity-planning.md			# Reviews expected traffic, burst behavior, queue depth, DB connections, CPU, memory, storage, model/API capacity, growth assumptions, and bottlenecks before they become incidents
* disaster-recovery.md			# Reviews catastrophic failure scenarios, region/service outages, restore paths, manual recovery steps, dependencies, RPO/RTO, and whether recovery has actually been rehearsed
* scalability.md			# Reviews growth behavior, horizontal/vertical scaling assumptions, sharding/partitioning needs, async/background work, data volume, tenant growth, and scaling limits

#### Documentation and maintainability

* decision-records.md			# Reviews architectural/product/technical decisions, tradeoffs, alternatives considered, consequences, expiry conditions, and whether important decisions are captured outside code
* deprecation-cleanup.md		# Reviews old paths, deprecated APIs, dead feature flags, stale migrations, unused configs, obsolete docs, and whether cleanup is safe and intentional
* onboarding.md				# Reviews whether a new developer can set up, run, test, understand, and safely contribute to the project without hidden knowledge

#### Environment, parity, and developer experience

* developer-experience.md		# Reviews setup friction, commands, local workflows, test speed, error clarity, Makefile/scripts, docs, dependency install, and whether contributors can work efficiently
* notebooks-scripts-cli.md		# Reviews notebooks, scripts, and command-line tools for reproducibility, parameter safety, logging, dry-run support, cleanup, dependency assumptions, and production-adjacent risk
* repo-hygiene.md			# Reviews ignored files, generated files, repo size, binary artifacts, naming, stale branches/configs, checked-in outputs, and whether the repository remains clean and navigable

### Tier 3 # run on concerning changes

#### Change-risk and AI-coding governance

* human-process-risk.md			# Reviews places where safety depends on humans remembering the right manual step; flags undocumented procedures, copy/paste commands, manual sequencing, tribal knowledge, missing checklists, risky admin workflows, and operations that should have guardrails
* irreversibility.md			# Reviews actions that cannot easily be undone; flags hard deletes, destructive migrations, lossy transforms, external side effects, irreversible user notifications, one-way state transitions, and operations without backup, preview, dry-run, or recovery paths
* migration-shadow.md			# Reviews hidden aftermath from migrations, refactors, or compatibility layers; flags old paths left alive, dual-write drift, read/write asymmetry, stale backfills, partially migrated records, legacy assumptions, and cleanup work that is easy to forget
* socio-technical-risk.md		# Reviews how code changes may create support burden, user confusion, team ownership gaps, moderation load, manual ops work, or incentives for harmful behavior; flags outcomes that are technically correct but organizationally expensive

#### LLM, RAG, and agentic product behavior

* agent-tool-use.md			# Reviews tool permissions, tool schemas, hidden parameters, destructive capabilities, confirmation gates, external side effects, audit logs, and whether agents can exceed intended authority
* ai-output-validation.md		# Reviews validation of model outputs before execution, storage, display, downstream API calls, database writes, code execution, user communication, or privileged workflow actions
* eval-data-integrity.md		# Reviews train/dev/eval separation, leakage, representative examples, adversarial examples, privacy-safe eval data, versioning, and whether evaluation results are trustworthy
* human-in-the-loop.md			# Reviews approval gates, escalation, confidence thresholds, review queues, override behavior, accountability, user consent, and when automation should stop and ask a person
* llm-cost-latency.md			# Reviews token budgets, model choice, caching, batching, retries, rate limits, streaming, fallback models, timeout behavior, and runaway model/API cost risk
* llm-security.md			# Reviews prompt injection, insecure tool use, output handling, data leakage, model/tool permissions, sandboxing, allowlists, destructive actions, and AI-specific security boundaries
* model-evaluation.md			# Reviews eval sets, acceptance thresholds, regression tests, false positives/negatives, adversarial cases, drift, human review, and whether model behavior is measured credibly
* model-observability.md		# Reviews traces, prompts, completions, redaction, token/cost metrics, model versions, tool calls, evaluation telemetry, user feedback loops, and privacy-safe debugging
* prompt-quality.md			# Reviews prompt clarity, instruction hierarchy, examples, brittle formatting, ambiguity, injection resistance, prompt versioning, evaluation cases, and whether prompts are maintainable
* rag-quality.md			# Reviews retrieval quality, chunking, ranking, source attribution, stale documents, permission-aware retrieval, hallucination containment, source trust, and answer grounding
