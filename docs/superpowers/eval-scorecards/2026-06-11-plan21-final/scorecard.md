# Eval scorecard

## Summary
- Agents: 20
- Calls: 159 (bad: 93, good: 66)
- Total cost (est., USD): $63.46

## Scorecard
| Agent | Recall | FP | Status |
|---|---|---|---|
| review-accessibility | 1.00 | 0.00 | PASS |
| review-api-design | 0.83 | 0.00 | PASS |
| review-application-logic | 1.00 | 0.00 | PASS |
| review-architecture | 0.67 | 0.00 | FAIL (recall 0.67 < 0.90) |
| review-compliance | 1.00 | 1.00 | FAIL (fp 1.00 > 0.10) |
| review-contracts | 0.83 | 0.00 | PASS |
| review-data-integrity | 1.00 | 0.00 | PASS |
| review-data-lineage | 1.00 | 0.00 | PASS |
| review-dependency | 1.00 | 1.00 | PASS |
| review-documentation | 1.00 | 0.67 | PASS |
| review-env-parity | 0.89 | 0.33 | FAIL (recall 0.89 < 0.90; fp 0.33 > 0.10) |
| review-observability | 1.00 | 0.00 | PASS |
| review-observability-db | 1.00 | 0.00 | PASS |
| review-observability-fe | 1.00 | 0.00 | PASS |
| review-observability-infra | 0.50 | 1.00 | FAIL (recall 0.50 < 0.90; fp 1.00 > 0.43) |
| review-performance | 1.00 | 0.00 | PASS |
| review-privacy | 1.00 | 0.00 | PASS |
| review-security | 1.00 | 0.00 | PASS |
| review-test-quality | 1.00 | 0.00 | PASS |
| review-usability | 1.00 | 0.00 | PASS |

## Cost by agent
| Agent | Model | Calls | In tok | Out tok | Cache reads | Est. cost |
|---|---|---|---|---|---|---|
| review-accessibility | claude-sonnet-4-6 | 6 | 18 | 985 | 93458 | $0.17 |
| review-api-design | claude-opus-4-8 | 9 | 19750 | 14077 | 484991 | $3.87 |
| review-application-logic | claude-sonnet-4-6 | 6 | 18 | 15715 | 99822 | $0.36 |
| review-architecture | claude-opus-4-8 | 15 | 32038 | 32603 | 803894 | $7.87 |
| review-compliance | claude-sonnet-4-6 | 6 | 18 | 22245 | 104840 | $0.47 |
| review-contracts | claude-opus-4-8 | 9 | 20533 | 25432 | 759427 | $5.25 |
| review-data-integrity | claude-sonnet-4-6 | 6 | 18 | 13041 | 101514 | $0.32 |
| review-data-lineage | claude-opus-4-8 | 6 | 8944 | 8137 | 300766 | $2.25 |
| review-dependency | claude-sonnet-4-6 | 6 | 18 | 5124 | 95972 | $0.19 |
| review-documentation | claude-sonnet-4-6 | 6 | 18 | 20624 | 142130 | $0.52 |
| review-env-parity | claude-opus-4-8 | 12 | 41435 | 68888 | 1279834 | $17.26 |
| review-observability | claude-sonnet-4-6 | 9 | 27 | 27529 | 181944 | $0.67 |
| review-observability-db | claude-opus-4-8 | 9 | 18155 | 13547 | 575178 | $4.05 |
| review-observability-fe | claude-opus-4-8 | 9 | 17376 | 12250 | 374226 | $3.55 |
| review-observability-infra | claude-opus-4-8 | 9 | 22679 | 45483 | 824340 | $7.98 |
| review-performance | claude-sonnet-4-6 | 6 | 18 | 10706 | 96396 | $0.32 |
| review-privacy | claude-opus-4-8 | 12 | 33624 | 22846 | 582758 | $7.06 |
| review-security | claude-sonnet-4-6 | 6 | 18 | 13170 | 140668 | $0.41 |
| review-test-quality | claude-sonnet-4-6 | 6 | 18 | 26145 | 182606 | $0.69 |
| review-usability | claude-sonnet-4-6 | 6 | 18 | 4171 | 99768 | $0.18 |

## Recall diagnosis (per bad case)
### review-accessibility
- [caught] `img-no-alt-rendered` r0 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `img-no-alt-rendered` r1 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `img-no-alt-rendered` r2 — seeded=`frontend/src/Items.tsx`, other_findings=0

### review-api-design
- [caught] `graphql-breaking-field-rename` r0 — seeded=`src/demo/graphql/schema.py`, other_findings=0
- [caught] `graphql-breaking-field-rename` r1 — seeded=`src/demo/graphql/schema.py`, other_findings=0
- [caught] `graphql-breaking-field-rename` r2 — seeded=`src/demo/graphql/schema.py`, other_findings=0
- [caught] `graphql-mutation-input-mismatch` r0 — seeded=`src/demo/graphql/schema.py`, other_findings=0
- [MISSED] `graphql-mutation-input-mismatch` r1 — seeded=`src/demo/graphql/schema.py`, other_findings=0
- [caught] `graphql-mutation-input-mismatch` r2 — seeded=`src/demo/graphql/schema.py`, other_findings=0

### review-application-logic
- [caught] `falsy-none-check` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `falsy-none-check` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `falsy-none-check` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-architecture
- [caught] `duplicate-data-layer` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [MISSED] `duplicate-data-layer` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `duplicate-data-layer` r2 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `heavy-inline-handler` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [MISSED] `heavy-inline-handler` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `heavy-inline-handler` r2 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `layering-violation` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `layering-violation` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `layering-violation` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-compliance
- [caught] `logs-pii-in-handler` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `logs-pii-in-handler` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `logs-pii-in-handler` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-contracts
- [caught] `client-missing-pact-field` r0 — seeded=`src/demo/clients/inventory.py`, other_findings=0
- [caught] `client-missing-pact-field` r1 — seeded=`src/demo/clients/inventory.py`, other_findings=0
- [caught] `client-missing-pact-field` r2 — seeded=`src/demo/clients/inventory.py`, other_findings=0
- [MISSED] `client-pact-divergence` r0 — seeded=`src/demo/clients/inventory.py`, other_findings=0
- [caught] `client-pact-divergence` r1 — seeded=`src/demo/clients/inventory.py`, other_findings=0
- [caught] `client-pact-divergence` r2 — seeded=`src/demo/clients/inventory.py`, other_findings=0

### review-data-integrity
- [caught] `non-atomic-bulk-insert` r0 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `non-atomic-bulk-insert` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `non-atomic-bulk-insert` r2 — seeded=`src/demo/db/repository.py`, other_findings=0

### review-data-lineage
- [caught] `stale-derived-field` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `stale-derived-field` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `stale-derived-field` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-dependency
- [caught] `unpinned-risky-dep` r0 — seeded=`pyproject.toml`, other_findings=0
- [caught] `unpinned-risky-dep` r1 — seeded=`pyproject.toml`, other_findings=0
- [caught] `unpinned-risky-dep` r2 — seeded=`pyproject.toml`, other_findings=0

### review-documentation
- [caught] `undocumented-public-function` r0 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `README.md:72` info — The README Endpoints section does not list the new GET /items/count route; the section explicitly enumerates all four existing endpoints and would be stale after this change.
- [caught] `undocumented-public-function` r1 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `README.md:75` low — The Endpoints section lists GET /items but does not mention the new GET /items/count route, leaving the README stale.
- [caught] `undocumented-public-function` r2 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `README.md:77` low — The ## Endpoints section lists GET /items but does not mention the newly added GET /items/count endpoint, leaving the README stale.

### review-env-parity
- [caught] `compose-var-not-declared` r0 — seeded=`infra/compose/base.yml`, other_findings=0
- [caught] `compose-var-not-declared` r1 — seeded=`infra/compose/base.yml`, other_findings=0
- [caught] `compose-var-not-declared` r2 — seeded=`infra/compose/base.yml`, other_findings=0
- [caught] `env-var-consumed-not-declared` r0 — seeded=`src/demo/config/settings.py`, other_findings=0
- [MISSED] `env-var-consumed-not-declared` r1 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `env-var-consumed-not-declared` r2 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `service-dev-only` r0 — seeded=`infra/compose/dev.yml`, other_findings=0
- [caught] `service-dev-only` r1 — seeded=`infra/compose/dev.yml`, other_findings=0
- [caught] `service-dev-only` r2 — seeded=`infra/compose/dev.yml`, other_findings=0

### review-observability
- [caught] `uninstrumented-route` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `uninstrumented-route` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `uninstrumented-route` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-observability-db
- [caught] `db-error-no-correlation-id` r0 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `db-error-no-correlation-id` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `db-error-no-correlation-id` r2 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `raw-connection-bypass` r0 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `raw-connection-bypass` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `raw-connection-bypass` r2 — seeded=`src/demo/db/repository.py`, other_findings=0

### review-observability-fe
- [caught] `swallowed-error` r0 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `swallowed-error` r1 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `swallowed-error` r2 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `unbounded-label` r0 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [caught] `unbounded-label` r1 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [caught] `unbounded-label` r2 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0

### review-observability-infra
- [caught] `exporter-without-scrape` r0 — seeded=`infra/compose/observability.yml`, other_findings=0
- [MISSED] `exporter-without-scrape` r1 — seeded=`infra/compose/observability.yml`, other_findings=0
- [caught] `exporter-without-scrape` r2 — seeded=`infra/compose/observability.yml`, other_findings=0
- [caught] `scrape-without-alert` r0 — seeded=`infra/observability/prometheus/prometheus.yml`, other_findings=0
- [caught] `scrape-without-alert` r1 — seeded=`infra/observability/prometheus/prometheus.yml`, other_findings=0
- [caught] `scrape-without-alert` r2 — seeded=`infra/observability/prometheus/prometheus.yml`, other_findings=0

### review-performance
- [caught] `n-plus-one-query` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `n-plus-one-query` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `n-plus-one-query` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-privacy
- [caught] `pii-in-response` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-in-response` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-in-response` r2 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-logged` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-logged` r1 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `src/demo/db/models.py:0` low — A new PII column (owner_email) is introduced on Item without a documented purpose, retention period, or deletion path. The repository's create_item does not populate it, so as written it adds a PII storage surface with no defined lifecycle. Note the response schema ItemRead correctly omits owner_email (no external echo).
- [caught] `pii-logged` r2 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `src/demo/db/models.py:0` medium — A new owner_email PII column is added to the Item model with no stated retention limit or purpose binding. Since create_item never sets it, the column is currently unused storage for personal data; if wired up later it will retain emails indefinitely alongside item records with no expiry or deletion path defined.
- [caught] `rum-allowlists-pii` r0 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `rum-allowlists-pii` r1 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `rum-allowlists-pii` r2 — seeded=`src/demo/config/settings.py`, other_findings=0

### review-security
- [caught] `hardcoded-secret` r0 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `hardcoded-secret` r1 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `hardcoded-secret` r2 — seeded=`src/demo/config/settings.py`, other_findings=0

### review-test-quality
- [caught] `tautological-assert` r0 — seeded=`tests/unit/test_settings.py`, other_findings=0
- [caught] `tautological-assert` r1 — seeded=`tests/unit/test_settings.py`, other_findings=0
- [caught] `tautological-assert` r2 — seeded=`tests/unit/test_settings.py`, other_findings=0

### review-usability
- [caught] `delete-no-confirm` r0 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `delete-no-confirm` r1 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `delete-no-confirm` r2 — seeded=`frontend/src/Items.tsx`, other_findings=0

## FP diagnosis (findings on good fixtures)
### review-compliance
- `audit-logged-action` r0 → 4 findings:
  - `src/demo/routes/items.py:40` high — user_id is passed as a URL query parameter on a POST endpoint. Query strings appear verbatim in web-server access logs, reverse-proxy logs, and browser history, creating uncontrolled copies of a personal-data identifier (GDPR Art. 4(1)) in infrastructure log stores that have no documented retention limit or erasure path.
  - `src/demo/routes/items.py:50` high — user_id is written to the application log with no retention policy and no deletion path. A numeric user identifier is personal data under GDPR Art. 4(1) because it singles out a natural person. Persisting it in logs without a bounded retention period and without an erasure mechanism violates the storage-limitation principle (Art. 5(1)(e)) and makes right-to-erasure requests (Art. 17) unenforceable.
  - `src/demo/routes/items.py:50` medium — name_filter (a free-text string supplied by the caller) is logged verbatim as `filter=name_filter`. If users search by a person's name — their own or another's — that value constitutes personal data (GDPR Art. 4(1)) persisted in logs with no retention limit or erasure path.
  - `src/demo/routes/items.py:46` medium — The docstring asserts 'no PII is logged or stored', but the same function logs user_id (a personal-data identifier) on line 50 and the user_id appears in the request URI (line 40), which lands in every access log. This false claim will mislead privacy auditors and DPIAs relying on inline documentation as a source of truth.
- `audit-logged-action` r1 → 5 findings:
  - `src/demo/routes/items.py:49` high — user_id is written to structured logs with no retention limit or deletion path. A numeric user ID is a persistent personal-data identifier under GDPR Art. 4(1) — it links unambiguously to a natural person. Log records containing user_id cannot be selectively purged in response to an Art. 17 erasure request without manual log scrubbing, creating an undischargeable right-to-erasure obligation.
  - `src/demo/routes/items.py:49` high — name_filter is logged verbatim. Callers are likely to pass names or partial names (their own or others') as the filter string, making this a free-text PII sink in the audit log. There is no retention limit, no erasure path, and no masking — a clear GDPR Art. 5(1)(c) data-minimisation and Art. 17 erasure gap.
  - `src/demo/routes/items.py:45` high — The docstring asserts 'no PII is logged or stored', which is factually incorrect: user_id and name_filter are both written to the log on line 49. This false assurance will cause compliance reviewers and DPO audits to skip this endpoint, turning a discoverable gap into a hidden one.
  - `src/demo/routes/items.py:50` high — name_filter is accepted and logged but silently ignored — list_items(session) is called without passing limit, offset, or name_filter, returning the full unfiltered item set. Under GDPR Art. 5(1)(c) (data minimisation), returning more personal data than the caller requested is a principle violation. It also means the logged filter value has no relationship to the data actually disclosed, breaking audit-trail integrity.
  - `src/demo/routes/items.py:49` medium — The audit log records the search actor (user_id) and filter but not the result set, making it impossible to reconstruct which personal data records were disclosed in response to a given search. This gap impedes GDPR Art. 15 subject-access responses and Art. 33/34 breach-notification impact assessments.
- `audit-logged-action` r2 → 4 findings:
  - `src/demo/routes/items.py:50` high — user_id is written to the application log with no documented retention limit or erasure path. A user identifier that can be linked back to a natural person is personal data under GDPR Art. 4(1). Without a defined retention policy and a deletion mechanism, this log entry violates the storage-limitation principle (Art. 5(1)(e)) and leaves the right to erasure (Art. 17) unaddressed. The docstring's claim that 'no PII is logged' is therefore incorrect.
  - `src/demo/routes/items.py:50` medium — name_filter (a free-text name prefix) is logged alongside user_id. Users routinely search by their own name or another person's name, making this field a potential personal-data carrier under GDPR Art. 4(1). There is no retention limit or erasure path for this log field.
  - `src/demo/routes/items.py:51` high — name_filter is accepted, logged, and passed to the audit trail, but is silently ignored by list_items(session) — the full item corpus is returned regardless of the filter value. This violates the GDPR data-minimisation principle (Art. 5(1)(c)): more personal data is transmitted to the caller than the stated processing purpose (a filtered search) requires.
  - `src/demo/routes/items.py:40` medium — user_id is placed in a URL query parameter on a POST endpoint. Query parameters are captured verbatim in web-server access logs, browser history, and HTTP Referer headers, multiplying the surfaces on which the identifier is retained without explicit retention controls — each surface becomes an independent GDPR Art. 5(1)(e) exposure.

### review-dependency
- `pinned-reputable-dep` r0 → 2 findings:
  - `pyproject.toml:19` info — httpx>=0.28 is added as a production dependency. The dev dependency group already declares httpx>=0.28, so this promotes an existing dev-only dependency to production. This is justified if the production code now directly uses httpx (e.g. as an HTTP client), but no call-site evidence is visible from the manifest alone.
  - `pyproject.toml:19` info — httpx>=0.28 is now declared in both [project.dependencies] (line 19) and [dependency-groups].dev (line 24), creating a redundant double-declaration. The dev group inherits the production dependency automatically, so the dev-group pin is now redundant.
- `pinned-reputable-dep` r1 → 2 findings:
  - `pyproject.toml:19` info — `httpx>=0.28` is added as a production dependency. `httpx>=0.28` already appears in the `[dependency-groups] dev` group (line 28). The production addition is justified if application code (not just tests) makes HTTP calls, but reviewers cannot confirm call sites from the manifest alone.
  - `pyproject.toml:19` info — The pin floor `>=0.28` matches the existing dev-group floor (`httpx>=0.28` at line 28), which is consistent with the project's bare-`>=`-floor convention. No convention violation.
- `pinned-reputable-dep` r2 → 1 findings:
  - `pyproject.toml:19` info — httpx>=0.28 is added as a production dependency. It already appears in the [dependency-groups] dev section (httpx>=0.28), so the floor is consistent. The production justification is not visible from the manifest alone — confirm httpx is used in production (e.g. as an HTTP client in application code) and not solely as a test transport.

### review-documentation
- `documented-public-function` r0 → 1 findings:
  - `README.md:78` info — The parenthetical '(typed response)' does not communicate the endpoint's meaningful behavioural characteristic — that it returns the unbounded total, independent of the list endpoint's page-size cap. The adjacent '/items' entry uses its parenthetical to call out the pagination behaviour; this one's annotation adds no equivalent signal.
- `documented-public-function` r2 → 1 findings:
  - `README.md:78` info — The parenthetical '(typed response)' is uninformative as written: every endpoint in this file uses a typed/schema-backed response, yet none of the others carry that note. Readers gain no actionable information from it.

### review-env-parity
- `parity-preserved` r0 → 1 findings:
  - `.env.example:19` high — APP_WIDGET_API_URL defaults to http://widget:9000, and the var is injected into prod-reaching services (app in staging.yml/prod.yml, worker in services.yml). But the `widget` service it names is defined ONLY in infra/compose/dev.yml (reached by dev via Taskfile, NOT by staging/prod). dev.yml is a dev-only overlay; staging/prod compose <env>.yml + services.yml + observability.yml only. So in staging/prod the app and worker will resolve http://widget:9000 to a non-existent host — the widget dependency silently fails to ship to prod. `widgetcorp/widget:1.4` is an upstream app dependency, not local-developer tooling (mail catcher / TLS / DB UI), so it cannot be excused as dev-only.

### review-observability
- `correlation-id-logging` r0 → 1 findings:
  - `src/demo/routes/items.py:58` low — The `_log.error('delete_item_failed', ...)` call omits `exc_info=True`, so the structured log event carries no exception class, message, or traceback. The exception is re-raised and the ObservabilityMiddleware will record the resulting 5xx, but the log event itself is non-diagnostic: when triaging a production commit or delete failure you must cross-correlate via `correlation_id` across a second log entry (the exception handler) rather than reading one self-contained structured event.
- `correlation-id-logging` r1 → 1 findings:
  - `src/demo/routes/items.py:59` low — _log.error("delete_item_failed") is called without exc_info=True, so the exception type, message, and traceback are not captured in the structured log event. The item_id-keyed business log and the exception detail end up in separate, unlinked records: the former carries item_id but no exception context; the latter (emitted by FastAPI's unhandled-exception handler) carries the traceback but no item_id. Correlating the two during an incident requires manual cross-referencing.
- `correlation-id-logging` r2 → 1 findings:
  - `src/demo/routes/items.py:55` medium — The `except Exception:` block logs `delete_item_failed` without capturing or emitting exception details. The structured event identifies the affected item but carries no information about what went wrong (exception type, message, traceback). When this fires in production, root-cause analysis requires correlating the structlog event against a separate unhandled-exception trace or uvicorn stderr — the structured log alone is a dead end.
- `instrumented-route` r1 → 1 findings:
  - `src/demo/routes/items.py:54` low — archive_item_completed is logged after session.refresh(), not after session.commit(). If session.refresh() raises (e.g., a transient connection drop) after a successful commit(), the mutation is durable in the DB but the structured completion event is never emitted. A consumer tracing archive operations by this event would see a gap for the item even though it was actually archived.

### review-observability-infra
- `complete-obs-surface` r0 → 3 findings:
  - `infra/observability/prometheus/prometheus.yml:0` high — Redis is added as a new prod runtime surface (services.yml redis + redis-exporter + this scrape job) but ships with NO alert rule and NO Grafana dashboard. Its sibling data store postgres has both: alerts PostgresDown/PostgresTooManyConnections in rules/alerts.yml and a postgres.json dashboard. The new redis surface is scraped into Prometheus but nothing pages on it being down or on memory/eviction/connection saturation, and there is no panel to view it.
  - `infra/compose/dev.yml:0` medium — The new dev redis block is indented under the top-level `volumes:` mapping (same level as `pgdata:`), not under `services:`. As written it is a malformed volume entry carrying service keys (image/profiles/healthcheck), so the dev redis container never starts — yet dev api sets APP_REDIS_URL: redis://redis:6379/0 and does not depend_on redis. The dev-side observability/runtime surface this diff intends to add is effectively absent, while prod (services.yml) gets a real redis service.
  - `infra/compose/observability.yml:0` low — Note (non-blocking): the observability stack continues to co-locate Prometheus, Loki, Grafana, Alertmanager and now a fourth exporter (redis-exporter) plus the data stores on a single compose host. Each added scrape target (postgres, otel-collector, now redis) increases the single-host blast radius; if the obs host or its profiles grow further this co-located layout will outgrow one host.
- `complete-obs-surface` r1 → 2 findings:
  - `infra/observability/prometheus/prometheus.yml:21` high — New `redis` scrape job (targets redis-exporter:9121) instruments a new prod runtime surface — the `redis` service added to services.yml (prod), restart: unless-stopped, persistent redisdata volume — but there is NO matching alert rule. alerts.yml has only app-alerts and postgres-alerts groups; the postgres precedent (PostgresDown / PostgresTooManyConnections off pg_up & pg_stat_activity_count) establishes the expected pattern. A prod data store scraped with no alerting is silent on outage.
  - `infra/observability/compose/observability.yml:94` medium — New `redis-exporter` + redis scrape job add metrics for the redis surface, but there is no Grafana dashboard for it. dashboards/ contains only app.json and postgres.json; the postgres path ships exporter + scrape + alerts + postgres.json together. Redis metrics will be scraped but never visualized, breaking the per-surface dashboard parity.
- `complete-obs-surface` r2 → 3 findings:
  - `infra/observability/prometheus/prometheus.yml:21` high — New `redis` scrape job (and the new prod `redis` service in services.yml) ships with no matching alert rule. infra/observability/prometheus/alerts.yml only defines groups for `app`, `postgres`, and `otel` — there is no `redis` group, so a prod Redis outage or saturation will never page. Redis is a new prod runtime surface with metrics collected but no alerting.
  - `infra/observability/prometheus/prometheus.yml:21` medium — The new `redis` scrape target has no Grafana dashboard. infra/observability/grafana/dashboards/ contains only postgres.json, app.json, and otel-collector.json — every other scraped surface has a dashboard panel, but Redis does not, leaving the redis-exporter metrics unvisualized.
  - `infra/compose/observability.yml:94` low — Non-blocking: redis-exporter is added to the already co-located single-host observability stack (prometheus, loki, grafana, alertmanager, otel-collector, postgres-exporter) which now also colocates with the prod redis/postgres data stores on the same host. Each added exporter compounds the single-host blast radius.

### review-privacy
- `pii-excluded` r0 → 1 findings:
  - `src/demo/db/models.py:16` medium — owner_email (PII) is added and persisted for the stated purpose of 'outreach', but no retention bound or deletion/erasure path is introduced. Stored indefinitely, this is retention beyond the stated purpose and leaves no mechanism to honor data-subject deletion requests.
- `pii-excluded` r1 → 1 findings:
  - `src/demo/db/models.py:16` medium — owner_email (PII) is persisted indefinitely with no retention bound or deletion mechanism. The diff handles exposure well — excluded from ItemRead, validated as EmailStr, and confirmed absent from the observability request log — but the stated purpose ('outreach') is open-ended and the column is added with no TTL, purge job, or delete endpoint, so addresses accumulate beyond the point of use (storage-limitation gap).

### review-test-quality
- `meaningful-assert` r0 → 2 findings:
  - `tests/unit/test_settings.py:56` medium — test_resolved_log_level_prod_is_info is an exact subset of the existing parametrized test test_resolved_log_level_is_info_outside_dev (line 18–20), which already covers environment='prod'. Any regression this test catches will simultaneously be caught by the parametrized variant; it contributes zero independent signal and will never fail while that parametrized test passes.
  - `tests/unit/test_settings.py:50` low — test_slo_request_latency_p99_env_override exercises the same pydantic-settings APP_ prefix env-override mechanism already covered by test_env_vars_override (line 27–32), which tests APP_SLO_ERROR_RATE_PCT. The only incremental coverage is field-existence for slo_request_latency_p99_ms, which is already asserted in test_defaults (line 10).
- `meaningful-assert` r1 → 2 findings:
  - `tests/unit/test_settings.py:59` low — Exact duplicate of the existing parametrised case `test_resolved_log_level_is_info_outside_dev[prod]` (line 20). The assertion `Settings(environment='prod').resolved_log_level == 'INFO'` is already enforced for all non-dev environments including 'prod'; this test adds zero incremental coverage and will silently stay green even if the duplicate is deleted.
  - `tests/unit/test_settings.py:52` low — Happy-path only: no coverage for an invalid env-var value (e.g. APP_SLO_REQUEST_LATENCY_P99_MS=not-a-number). Pydantic-settings should raise a ValidationError at Settings() construction time when the value cannot be coerced to float; without an unhappy-path assertion the rejection guard is untested.
- `meaningful-assert` r2 → 2 findings:
  - `tests/unit/test_settings.py:57` medium — test_resolved_log_level_prod_is_info is a complete duplicate of the 'prod' case already exercised by the existing parametrized test test_resolved_log_level_is_info_outside_dev (which iterates ["staging", "prod", "ci"] and asserts the identical expression). This new test will always pass or fail in lockstep with that parametrized case and provides zero incremental signal.
  - `tests/unit/test_settings.py:51` low — test_slo_request_latency_p99_env_override exercises the same pydantic-settings env-prefix mechanism (APP_ prefix, string-to-float coercion) already proven by the existing test_env_vars_override, which covers APP_SLO_ERROR_RATE_PCT — a structurally identical float field. Because pydantic-settings applies the prefix uniformly across all fields, a second float-field env-override test adds no discriminating coverage; it is testing the library, not project logic.

## Agentic behavior
### review-api-design
- Calls: 9, avg turns: 1.3, max-cap hits: 0
- Tools: read_file×3, glob×1, grep×1
- Top paths/patterns: `src/demo/graphql/schema.py`×2, `src/demo/**/*.py`×1, `src/demo/db/repository.py`×1, `src/demo`×1, `def create_item`×1

### review-architecture
- Calls: 15, avg turns: 1.4, max-cap hits: 0
- Tools: read_file×9, glob×4, grep×1
- Top paths/patterns: `src/demo/db/repository.py`×5, `src/demo/db/item_service.py`×2, `src/demo/routes/items.py`×2, `src/demo/db/*.py`×1, `**/db/*.py`×1

### review-contracts
- Calls: 9, avg turns: 1.3, max-cap hits: 0
- Tools: grep×2, read_file×2
- Top paths/patterns: `reserved_count|in_stock`×1, `get_stock`×1, `tests/eval/fixtures/contracts/bad/client-pact-divergence/pacts/inventory.json`×1, `tests/functional/test_consumer_inventory.py`×1

### review-data-lineage
- Calls: 6, avg turns: 1.2, max-cap hits: 0
- Tools: read_file×2, grep×1
- Top paths/patterns: `src/demo/db/models.py`×1, `src/demo/db/repository.py`×1, `src/demo`×1, `slug|normaliz|create_item|name`×1

### review-env-parity
- Calls: 12, avg turns: 1.8, max-cap hits: 0
- Tools: read_file×21, glob×10, grep×5
- Top paths/patterns: `.env.example`×5, `infra/compose/prod.yml`×3, `infra/compose/*.yml`×2, `WIDGET`×2, `infra/compose/staging.yml`×2

### review-observability-db
- Calls: 9, avg turns: 1.3, max-cap hits: 0
- Tools: read_file×3, grep×2, glob×1
- Top paths/patterns: `src/demo/observability.py`×2, `get_logger|structlog|logging`×1, `src/demo/db/session.py`×1, `src/demo`×1, `SQLAlchemyInstrumentor|create_engine|instrument`×1

### review-observability-fe
- Calls: 9, avg turns: 1.3, max-cap hits: 0
- Tools: read_file×3
- Top paths/patterns: `src/demo/frontend_rum/metrics.py`×2, `frontend/src/Items.tsx`×1

### review-observability-infra
- Calls: 9, avg turns: 1.4, max-cap hits: 0
- Tools: glob×5, read_file×2, grep×2
- Top paths/patterns: `infra`×2, `redis`×2, `infra/**`×1, `infra/observability/prometheus/prometheus.yml`×1, `infra/observability/prometheus/alerts/*`×1

### review-privacy
- Calls: 12, avg turns: 1.8, max-cap hits: 0
- Tools: read_file×10, glob×4, grep×2
- Top paths/patterns: `src/demo/routes/items.py`×3, `src/demo/db/repository.py`×2, `src/demo/config/settings.py`×2, `src/demo/middleware/observability.py`×2, `src/demo`×1

## Drift check
- ⚠ `api-design` / `graphql-mutation-input-mismatch` r1 — disallowed tools: glob×1, read_file×2
- ⚠ `api-design` / `graphql-mutation-input-mismatch` r2 — disallowed tools: grep×1, read_file×1
- ⚠ `architecture` / `duplicate-data-layer` r0 — disallowed tools: glob×1, read_file×2
- ⚠ `architecture` / `duplicate-data-layer` r2 — disallowed tools: glob×3, read_file×3
- ⚠ `architecture` / `layering-violation` r2 — disallowed tools: read_file×3
- ⚠ `architecture` / `lightweight-inline-handler` r0 — disallowed tools: read_file×1
- ⚠ `architecture` / `lightweight-inline-handler` r2 — disallowed tools: grep×1
- ⚠ `contracts` / `client-missing-pact-field` r2 — disallowed tools: grep×2
- ⚠ `contracts` / `client-pact-divergence` r1 — disallowed tools: read_file×1
- ⚠ `contracts` / `client-pact-covered` r1 — disallowed tools: read_file×1
- ⚠ `data-lineage` / `normalized-write` r2 — disallowed tools: grep×1, read_file×2
- ⚠ `env-parity` / `compose-var-not-declared` r0 — disallowed tools: glob×1, grep×2, read_file×3
- ⚠ `env-parity` / `compose-var-not-declared` r2 — disallowed tools: glob×4, read_file×11
- ⚠ `env-parity` / `env-var-consumed-not-declared` r0 — disallowed tools: glob×2, grep×1, read_file×2
- ⚠ `env-parity` / `service-dev-only` r1 — disallowed tools: glob×1, grep×1, read_file×5
- ⚠ `env-parity` / `parity-preserved` r2 — disallowed tools: glob×2, grep×1
- ⚠ `observability-db` / `db-error-no-correlation-id` r2 — disallowed tools: grep×1, read_file×2
- ⚠ `observability-db` / `raw-connection-bypass` r0 — disallowed tools: glob×1, grep×1
- ⚠ `observability-db` / `observed-query` r2 — disallowed tools: read_file×1
- ⚠ `observability-fe` / `swallowed-error` r0 — disallowed tools: read_file×1
- ⚠ `observability-fe` / `capped-label` r1 — disallowed tools: read_file×1
- ⚠ `observability-fe` / `capped-label` r2 — disallowed tools: read_file×1
- ⚠ `observability-infra` / `exporter-without-scrape` r2 — disallowed tools: glob×3, grep×1, read_file×2
- ⚠ `observability-infra` / `scrape-without-alert` r2 — disallowed tools: glob×2, grep×1
- ⚠ `privacy` / `pii-in-response` r1 — disallowed tools: grep×1, read_file×2
- ⚠ `privacy` / `pii-logged` r2 — disallowed tools: read_file×2
- ⚠ `privacy` / `rum-allowlists-pii` r0 — disallowed tools: read_file×1
- ⚠ `privacy` / `rum-allowlists-pii` r2 — disallowed tools: read_file×2
- ⚠ `privacy` / `pii-excluded` r1 — disallowed tools: glob×3, read_file×2
- ⚠ `privacy` / `pii-excluded` r2 — disallowed tools: glob×1, grep×1, read_file×1

## Acknowledged (covered by decisions)
_(none)_

## Proposed thresholds.yaml
```yaml
accessibility:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
api-design:
  recall_min: 0.73  # observed 0.83
  fp_max: 0.10  # observed 0.00
application-logic:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
architecture:
  recall_min: 0.57  # observed 0.67
  fp_max: 0.10  # observed 0.00
compliance:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
contracts:
  recall_min: 0.73  # observed 0.83
  fp_max: 0.10  # observed 0.00
data-integrity:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
data-lineage:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
dependency:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
documentation:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.77  # observed 0.67
env-parity:
  recall_min: 0.79  # observed 0.89
  fp_max: 0.43  # observed 0.33
observability:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability-db:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability-fe:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability-infra:
  recall_min: 0.40  # observed 0.50
  fp_max: 1.00  # observed 1.00
performance:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
privacy:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
security:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
test-quality:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
usability:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
```
