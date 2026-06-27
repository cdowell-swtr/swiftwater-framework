# Security Panel Stances

## Existing

### Offensive and defensive baseline

* `break-in` - Tries to gain access where no access should exist; focuses on authentication bypass, exposed endpoints, missing guards, weak trust assumptions, unsafe defaults, and unintended entry points

* `harden` - Reviews whether controls are explicit, least-privilege, fail-closed, validated at boundaries, and resistant to known attack paths

* `destroy` - Tries to cause data loss, irreversible state changes, account loss, deleted resources, broken migrations, queue poison, destructive admin actions, or unrecoverable external side effects

* `disrupt` - Tries to degrade availability or normal operation; focuses on denial of service, resource exhaustion, lock contention, queue buildup, slow queries, retry storms, expensive LLM calls, and noisy alerts

* `leak` - Tries to expose data, secrets, metadata, internal state, private behavior, logs, traces, prompts, analytics, exports, or cross-tenant information that should not be visible

## Additional stances to consider

### Offensive

* `escalate` - Tries to turn limited access into broader access; focuses on privilege escalation, role confusion, admin/user boundary failures, tenant boundary failures, confused deputies, and overpowered service accounts

* `impersonate` - Tries to act as another user, tenant, service, worker, admin, or model; focuses on identity binding, token audience, session fixation, actor/subject confusion, forged headers, and delegated authority misuse

* `tamper` - Tries to modify data, decisions, configuration, permissions, prompts, audit records, or state transitions without authorization; focuses on integrity rather than access alone

* `persist` - Tries to keep access after the initial path should have been closed; focuses on refresh tokens, long-lived sessions, stale permissions, orphaned service accounts, cached grants, forgotten webhooks, and undeleted credentials

* `evade` - Tries to avoid detection; focuses on missing audit trails, weak logging, log injection, alert blind spots, ambiguous actors, trace gaps, suspicious behavior that looks normal, and incomplete forensic evidence

### Integrity

* `corrupt` - Looks for ways valid-looking data can become wrong, inconsistent, incomplete, duplicated, orphaned, stale, or semantically invalid

* `forge` - Looks for ways to create fake-but-plausible records, evidence, audit entries, provenance links, signatures, events, model outputs, or system conclusions

* `replay` - Looks for ways old requests, tokens, webhooks, jobs, signed URLs, confirmations, or events can be reused after their intended moment

* `race` - Looks for time-of-check/time-of-use flaws, concurrent updates, double-spend-like behavior, duplicate submissions, session races, role-change races, and state transition races

* `confuse` - Looks for ambiguous identifiers, actor/subject swaps, tenant/product/control-plane confusion, similar names, route ambiguity, and state labels that can be misinterpreted

* `poison` - Looks for ways to contaminate future behavior through training data, eval data, caches, indexes, prompts, fixtures, embeddings, search results, config, or persisted derived state

* `drift` - Looks for permissions, policy, schemas, docs, generated artifacts, secrets, dependencies, or assumptions that become unsafe over time without an obvious breaking point

### Tenancy and authority

* `cross-tenant` - Tries to read, write, infer, enumerate, cache, search, route, provision, or mutate across tenant boundaries

* `cross-plane` - Tries to confuse control-plane, tenant-plane, product-plane, framework-plane, app-plane, worker-plane, or model-plane responsibilities and data

* `confused-deputy` - Looks for trusted internal services, workers, callbacks, agents, admin tools, or background jobs that can be tricked into doing something the original caller could not do directly

* `authority-confusion` - Looks for places where advisory, authoritative, user-provided, model-generated, admin-approved, system-derived, or framework-owned claims are treated as the wrong kind of authority

* `delegation-abuse` - Looks for unsafe delegation through API keys, service accounts, shared sessions, OAuth scopes, signed URLs, webhooks, background jobs, or tool calls

* `revocation-failure` - Looks for access that continues after logout, password reset, role removal, tenant deletion, key rotation, session invalidation, account disablement, or policy change

### LLM and agentic

* `prompt-inject` - Tries to override system intent through user content, retrieved documents, tool outputs, comments, logs, tickets, web pages, emails, or embedded instructions

* `tool-abuse` - Tries to make an agent call tools in unsafe sequences, with unsafe arguments, with excessive authority, or beyond the user’s authority

* `output-smuggle` - Looks for model outputs that carry hidden instructions, unsafe markup, executable payloads, leaked context, malformed structured data, or downstream injection vectors

* `context-poison` - Tries to place misleading, stale, adversarial, or over-salient content into the model’s working context

* `retrieval-poison` - Tries to manipulate RAG/search/indexed content so the model grounds itself on bad, stale, unauthorized, misleading, or adversarial sources

* `overtrust` - Looks for places where model output is trusted without validation, attribution, confidence handling, human approval, policy enforcement, or downstream safety checks

* `model-confusion` - Looks for places where different models, prompts, profiles, eval modes, environments, or tool contexts have different authority but are treated interchangeably

* `cost-amplify` - Tries to trigger excessive model calls, huge prompts, recursive tool use, retry loops, fallback cascades, expensive embeddings, or uncontrolled eval runs

### Defensive

* `contain` - Reviews whether damage is scoped, segmented, rate-limited, bounded, reversible, and unable to spread globally

* `detect` - Reviews whether suspicious behavior produces useful logs, metrics, traces, alerts, anomaly signals, and audit trails

* `respond` - Reviews whether operators can identify, isolate, disable, roll back, rotate, revoke, quarantine, or communicate during an incident

* `recover` - Reviews whether data, service, config, secrets, tenants, queues, indexes, caches, generated artifacts, and external state can be restored after failure or compromise

* `prove` - Reviews whether the system can produce evidence that controls worked, including auditability, compliance evidence, security tests, invariants, reproducible checks, and decision records

* `minimize` - Reviews whether the system reduces sensitive data, permissions, attack surface, retention, authority, logging payloads, and blast radius by default

### Abuse

* `enumerate` - Looks for ways to discover users, tenants, resources, slugs, emails, roles, invite status, private IDs, hidden records, feature availability, or internal state

* `spam` - Looks for ways to send unwanted messages, notifications, invites, webhooks, emails, comments, jobs, generated content, or external calls

* `scrape` - Looks for ways to harvest data at scale through allowed endpoints, exports, pagination, search, public pages, timing side channels, or bulk APIs

* `grief` - Looks for ways one user can annoy, block, confuse, overload, or impose costs on another user, tenant, moderator, support team, or operator without classic unauthorized access

* `economic-abuse` - Looks for ways to consume paid resources, LLM tokens, compute, storage, bandwidth, SMS/email sends, support time, third-party quotas, or operational capacity

* `policy-bypass` - Looks for ways to avoid moderation, entitlement, billing, compliance, consent, regional, age, safety, usage, or product-policy restrictions

* `support-bomb` - Looks for technically valid flows that create disproportionate manual support, moderation, cleanup, reconciliation, or operator workload

### Supply chain and framework

* `dependency-confuse` - Looks for package confusion, wrong registry usage, transitive risk, optional dependency surprises, unpinned tools, unsafe install hooks, and unsafe build hooks

* `build-poison` - Looks for compromised generated artifacts, stale lockfiles, malicious build scripts, poisoned Docker layers, CI action drift, and mismatched source/generated outputs

* `template-propagate` - Looks for unsafe defaults or vulnerabilities in templates that will be copied into every generated downstream project

* `upgrade-break` - Looks for framework upgrades that silently weaken security controls, migration safety, authz semantics, observability, generated defaults, or downstream compatibility

* `provenance-break` - Looks for inability to prove where generated code, artifacts, dependencies, decisions, migrations, configs, or model outputs came from

### Forensic

* `attribution-loss` - Looks for actions where you cannot later tell who initiated them, on whose behalf, through which path, and with which authority

* `audit-tamper` - Looks for ways logs, audit records, decision trails, traces, provenance, or security evidence can be altered, omitted, reordered, flooded, or made misleading

* `evidence-gap` - Looks for high-risk actions that lack enough evidence for incident response, compliance, dispute resolution, debugging, or postmortem reconstruction

* `timeline-confusion` - Looks for ordering ambiguity across async jobs, webhooks, migrations, retries, LLM traces, external callbacks, distributed logs, and multi-plane workflows

* `repudiation` - Looks for places where users, admins, services, agents, or models can plausibly deny actions because the system does not bind actor, intent, authority, and effect clearly enough

### Framework, EDR, and reasoning integrity

* `reasoning-regression` - Looks for changes that make the system produce less trustworthy reasoning, findings, judgments, or outcomes while still passing structural tests

* `provenance-fabrication` - Looks for generated claims, findings, references, premises, citations, or grounding links that appear supported but are not actually traceable to evidence

* `premise-drift` - Looks for assumptions, premises, constraints, or decisions that silently change meaning across docs, code, migrations, tests, prompts, and rendered outputs

* `coherence-break` - Looks for contradictions between findings, premises, outcomes, evaluations, decisions, product scope, and rendered explanations

* `self-validation` - Looks for places where the system validates itself too easily, tests against friendly fixtures, accepts its own outputs as proof, or encodes its own mistakes as ground truth

* `adoption-drift` - Looks for divergence between framework behavior, generated repos, adopted repos, conventions, migration expectations, and cross-repo documentation

* `decision-inversion` - Looks for places where a recorded architectural, security, tenancy, or product decision is implemented backwards, weakened, bypassed, or treated as merely advisory

* `semantic-authority` - Looks for places where labels like finding, decision, outcome, premise, evidence, reference, advisory, authoritative, generated, validated, or accepted carry more authority than the system actually proves
