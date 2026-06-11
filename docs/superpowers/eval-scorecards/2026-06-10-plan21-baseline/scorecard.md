# Eval scorecard

## Summary
- Agents: 20
- Calls: 159 (bad: 96, good: 63)
- Total cost (est., USD): $74.30

## Scorecard
| Agent | Recall | FP | Status |
|---|---|---|---|
| review-accessibility | 1.00 | 0.00 | PASS |
| review-api-design | 1.00 | 0.00 | PASS |
| review-application-logic | 1.00 | 0.00 | PASS |
| review-architecture | 1.00 | 0.00 | PASS |
| review-compliance | 1.00 | 1.00 | FAIL (fp 1.00 > 0.10) |
| review-contracts | 0.50 | 0.00 | FAIL (recall 0.50 < 0.57) |
| review-data-integrity | 1.00 | 1.00 | FAIL (fp 1.00 > 0.43) |
| review-data-lineage | 0.17 | 0.00 | FAIL (recall 0.17 < 0.73) |
| review-dependency | 1.00 | 1.00 | PASS |
| review-documentation | 1.00 | 1.00 | PASS |
| review-env-parity | 1.00 | 0.67 | FAIL (fp 0.67 > 0.10) |
| review-observability | 1.00 | 0.83 | FAIL (fp 0.83 > 0.10) |
| review-observability-db | 0.00 | 0.00 | FAIL (recall 0.00 < 0.73) |
| review-observability-fe | 0.67 | 0.33 | FAIL (recall 0.67 < 0.90; fp 0.33 > 0.10) |
| review-observability-infra | 1.00 | 0.33 | PASS |
| review-performance | 1.00 | 0.00 | PASS |
| review-privacy | 1.00 | 0.00 | PASS |
| review-security | 1.00 | 0.33 | FAIL (fp 0.33 > 0.10) |
| review-test-quality | 1.00 | 0.33 | FAIL (fp 0.33 > 0.10) |
| review-usability | 1.00 | 0.33 | FAIL (fp 0.33 > 0.10) |

## Cost by agent
| Agent | Model | Calls | In tok | Out tok | Cache reads | Est. cost |
|---|---|---|---|---|---|---|
| review-accessibility | claude-sonnet-4-6 | 6 | 18 | 2397 | 105926 | $0.17 |
| review-api-design | claude-opus-4-8 | 9 | 20384 | 6442 | 171455 | $2.64 |
| review-application-logic | claude-sonnet-4-6 | 6 | 18 | 23777 | 104366 | $0.49 |
| review-architecture | claude-opus-4-8 | 9 | 40764 | 15576 | 330779 | $4.89 |
| review-compliance | claude-sonnet-4-6 | 6 | 18 | 23770 | 109384 | $0.50 |
| review-contracts | claude-opus-4-8 | 9 | 87011 | 34790 | 617057 | $9.39 |
| review-data-integrity | claude-sonnet-4-6 | 6 | 18 | 34010 | 102414 | $0.64 |
| review-data-lineage | claude-opus-4-8 | 9 | 30570 | 11064 | 212964 | $3.42 |
| review-dependency | claude-sonnet-4-6 | 6 | 18 | 11305 | 97936 | $0.29 |
| review-documentation | claude-sonnet-4-6 | 6 | 18 | 19024 | 144810 | $0.50 |
| review-env-parity | claude-opus-4-8 | 12 | 117440 | 42507 | 697901 | $12.66 |
| review-observability | claude-sonnet-4-6 | 9 | 27 | 63621 | 173932 | $1.24 |
| review-observability-db | claude-opus-4-8 | 9 | 61128 | 13022 | 281157 | $5.53 |
| review-observability-fe | claude-opus-4-8 | 12 | 87466 | 39069 | 668671 | $11.05 |
| review-observability-infra | claude-opus-4-8 | 9 | 102703 | 52967 | 737547 | $11.58 |
| review-performance | claude-sonnet-4-6 | 6 | 18 | 18202 | 104548 | $0.41 |
| review-privacy | claude-opus-4-8 | 12 | 66239 | 22036 | 509777 | $7.56 |
| review-security | claude-sonnet-4-6 | 6 | 18 | 14366 | 128699 | $0.46 |
| review-test-quality | claude-sonnet-4-6 | 6 | 18 | 20900 | 185070 | $0.62 |
| review-usability | claude-sonnet-4-6 | 6 | 18 | 9356 | 100912 | $0.26 |

## Recall diagnosis (per bad case)
### review-accessibility
- [caught] `img-no-alt-rendered` r0 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `img-no-alt-rendered` r1 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `img-no-alt-rendered` r2 — seeded=`frontend/src/Items.tsx`, other_findings=0

### review-api-design
- [caught] `graphql-mutation-input-mismatch` r0 — seeded=`src/demo/graphql/schema.py`, other_findings=0
- [caught] `graphql-mutation-input-mismatch` r1 — seeded=`src/demo/graphql/schema.py`, other_findings=0
- [caught] `graphql-mutation-input-mismatch` r2 — seeded=`src/demo/graphql/schema.py`, other_findings=0
- [caught] `graphql-rest-divergence` r0 — seeded=`src/demo/graphql/schema.py`, other_findings=0
- [caught] `graphql-rest-divergence` r1 — seeded=`src/demo/graphql/schema.py`, other_findings=0
- [caught] `graphql-rest-divergence` r2 — seeded=`src/demo/graphql/schema.py`, other_findings=0

### review-application-logic
- [caught] `falsy-none-check` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `falsy-none-check` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `falsy-none-check` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-architecture
- [caught] `duplicate-data-layer` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `duplicate-data-layer` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `duplicate-data-layer` r2 — seeded=`src/demo/routes/items.py`, other_findings=0
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
- [caught] `client-pact-divergence` r0 — seeded=`src/demo/clients/inventory.py`, other_findings=0
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
- [MISSED] `untransformed-write` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [MISSED] `untransformed-write` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [MISSED] `untransformed-write` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-dependency
- [caught] `unpinned-risky-dep` r0 — seeded=`pyproject.toml`, other_findings=0
- [caught] `unpinned-risky-dep` r1 — seeded=`pyproject.toml`, other_findings=0
- [caught] `unpinned-risky-dep` r2 — seeded=`pyproject.toml`, other_findings=0

### review-documentation
- [caught] `undocumented-public-function` r0 — seeded=`src/demo/routes/items.py`, other_findings=2
  - other: `README.md:0` low — The 'Endpoints' section lists `GET /items` but omits the newly added `GET /items/count`. The spec is now stale.
  - other: `README.md:0` info — README advises running `task openapi:export` and committing `openapi.json` after any route change ('CI fails on a stale or breaking spec'). Adding `GET /items/count` requires regenerating that file.
- [caught] `undocumented-public-function` r1 — seeded=`src/demo/routes/items.py`, other_findings=2
  - other: `README.md:0` info — The `## Endpoints` section does not list the new `GET /items/count` route. The section currently ends with `GET /items`.
  - other: `openapi.json:0` info — README.md instructs contributors to run `task openapi:export` and commit the result after any route change; adding `/items/count` will make the committed `openapi.json` stale, and CI's contract-diff job will fail on the next push.
- [caught] `undocumented-public-function` r2 — seeded=`src/demo/routes/items.py`, other_findings=2
  - other: `README.md:115` low — The Endpoints section lists `GET /items` but does not mention the new `GET /items/count` route. The spec will be stale for anyone reading the README.
  - other: `openapi.json:1` low — README instructs contributors to run `task openapi:export` and commit the updated `openapi.json` after every route change, or CI's `contract` job will fail. The diff adds a new route but shows no corresponding update to `openapi.json`.

### review-env-parity
- [caught] `compose-var-not-declared` r0 — seeded=`infra/compose/base.yml`, other_findings=0
- [caught] `compose-var-not-declared` r1 — seeded=`infra/compose/base.yml`, other_findings=0
- [caught] `compose-var-not-declared` r2 — seeded=`infra/compose/base.yml`, other_findings=0
- [caught] `env-var-consumed-not-declared` r0 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `env-var-consumed-not-declared` r1 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `env-var-consumed-not-declared` r2 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `service-dev-only` r0 — seeded=`infra/compose/dev.yml`, other_findings=0
- [caught] `service-dev-only` r1 — seeded=`infra/compose/dev.yml`, other_findings=0
- [caught] `service-dev-only` r2 — seeded=`infra/compose/dev.yml`, other_findings=0

### review-observability
- [caught] `uninstrumented-route` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `uninstrumented-route` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `uninstrumented-route` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-observability-db
- [MISSED] `unindexed-unobserved-query` r0 — seeded=`src/demo/db/repository.py`, other_findings=0
- [MISSED] `unindexed-unobserved-query` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [MISSED] `unindexed-unobserved-query` r2 — seeded=`src/demo/db/repository.py`, other_findings=0
- [MISSED] `write-path-no-metric` r0 — seeded=`src/demo/db/repository.py`, other_findings=0
- [MISSED] `write-path-no-metric` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [MISSED] `write-path-no-metric` r2 — seeded=`src/demo/db/repository.py`, other_findings=0

### review-observability-fe
- [caught] `swallowed-error` r0 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `swallowed-error` r1 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `swallowed-error` r2 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `unbounded-label` r0 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [caught] `unbounded-label` r1 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [caught] `unbounded-label` r2 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [MISSED] `uninstrumented-view` r0 — seeded=`frontend/src/Dashboard.tsx`, other_findings=0
- [MISSED] `uninstrumented-view` r1 — seeded=`frontend/src/Dashboard.tsx`, other_findings=0
- [MISSED] `uninstrumented-view` r2 — seeded=`frontend/src/Dashboard.tsx`, other_findings=0

### review-observability-infra
- [caught] `exporter-without-scrape` r0 — seeded=`infra/compose/observability.yml`, other_findings=0
- [caught] `exporter-without-scrape` r1 — seeded=`infra/compose/observability.yml`, other_findings=0
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
- [caught] `pii-logged` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-logged` r2 — seeded=`src/demo/routes/items.py`, other_findings=0
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
  - `src/demo/routes/items.py:41` high — user_id is passed as a URL query parameter, so it is recorded verbatim in HTTP access logs, CDN/proxy logs, and browser history — all surfaces outside the application's retention and erasure controls. An opaque integer that singles out a natural person is a pseudonymous personal identifier under GDPR Art. 4(1); embedding it in the URL creates retention obligations that cannot be met for third-party infrastructure logs. The docstring's claim that 'no PII is logged or stored' is therefore incorrect.
  - `src/demo/routes/items.py:51` high — get_logger().info logs user_id (a pseudonymous personal identifier, GDPR Art. 4(1)) with no documented log-retention policy or deletion path. If a data subject exercises the right to erasure (GDPR Art. 17), individual log entries containing user_id cannot be selectively purged from most structured-log backends (ELK, Loki, CloudWatch). There is also no audit trail of what data was returned for this user_id, only that a search occurred.
  - `src/demo/routes/items.py:51` medium — name_filter is logged alongside user_id. If callers pass a person's name, email fragment, or any other identifying string as a search term, this constitutes logging of personal data correlated with a user identity, creating a behavioural profile subject to GDPR Art. 5(1)(e) (storage limitation) and potentially Art. 22 (profiling). No retention limit or erasure path is defined for this event type.
  - `src/demo/routes/items.py:52` high — list_items(session) is called without limit, offset, or the name_filter argument — the filter is accepted from the caller but silently discarded. Every search therefore returns the full, unfiltered, unpaginated item corpus, violating the GDPR data-minimisation principle (Art. 5(1)(c)) and potentially exposing records the requesting user is not entitled to see. This also means the audit log records a filter value that had no effect, making the audit trail misleading.
- `audit-logged-action` r1 → 5 findings:
  - `src/demo/routes/items.py:51` high — `user_id` is a personal identifier under GDPR Art. 4(1). It is written to application logs with no documented retention period, no deletion path, and no right-to-erasure mechanism (GDPR Arts. 5(1)(e) and 17). The docstring's claim that 'no PII is logged or stored' is factually incorrect.
  - `src/demo/routes/items.py:51` medium — `name_filter` (user-supplied search term) is logged alongside `user_id`, producing a behavioural record — what this identified user searched for — with no retention limit or erasure path. Even if the filter value is not PII in isolation, tying it to a `user_id` makes the combined log record personal data under GDPR Art. 4(1).
  - `src/demo/routes/items.py:42` medium — `name_filter` is accepted as a query parameter and persisted in logs (line 51), but is never forwarded to `list_items()` (line 52). Collecting and storing a data element that serves no functional purpose in the request violates the GDPR Art. 5(1)(c) data-minimisation principle.
  - `src/demo/routes/items.py:41` medium — `user_id` is transmitted as a URL query parameter. Query strings are routinely captured in server access logs, reverse-proxy logs, CDN logs, browser history, and HTTP `Referer` headers — creating undocumented secondary personal-data stores with no retention or erasure policy, in violation of GDPR Arts. 5(1)(e) and 32.
  - `src/demo/routes/items.py:52` medium — `list_items(session)` is called without `limit` or `offset`, returning the entire item table. Unlike `GET /items`, this endpoint has no pagination, potentially exposing a disproportionately large data set per request and violating the GDPR Art. 5(1)(c) data-minimisation principle.
- `audit-logged-action` r2 → 5 findings:
  - `src/demo/routes/items.py:51` high — user_id is emitted into application logs with no documented retention period or deletion path. Under GDPR Art. 4(1) a user identifier is personal data, and Art. 5(1)(e) (storage limitation) and Art. 17 (right to erasure) require that log records containing it can be purged on request. Structured log sinks (ELK, CloudWatch, Loki, etc.) rarely support per-field row deletion, making erasure requests practically impossible to fulfil.
  - `src/demo/routes/items.py:41` high — user_id is accepted as a Query parameter on a POST endpoint. Query strings appear verbatim in HTTP access logs on every reverse proxy, CDN, load balancer, and WAF by default—infrastructure logs outside the application's retention or deletion control. This makes Art. 17 erasure requests impossible to fulfil across all log sinks and violates the storage-limitation principle (Art. 5(1)(e)).
  - `src/demo/routes/items.py:51` high — name_filter (a free-text search string) is logged verbatim. Users routinely search by full name, email address, or other PII. Capturing that string in logs with no sanitisation, no retention bound, and no erasure path is a GDPR Art. 5(1)(b) purpose-limitation and Art. 5(1)(e) storage-limitation violation. The docstring's 'no PII is logged' claim is factually incorrect for this field.
  - `src/demo/routes/items.py:42` medium — name_filter is a Query parameter on a POST endpoint. Free-text search strings (which may contain names, email addresses, or other PII) will be written to every HTTP access log in the infrastructure, creating uncontrolled personal-data copies with no retention or deletion path.
  - `src/demo/routes/items.py:52` medium — list_items(session) is called without limit or offset, returning an unbounded result set. The sibling get_items endpoint correctly applies MAX_PAGE_SIZE pagination. Returning more personal data than necessary for the request violates the GDPR data-minimisation principle (Art. 5(1)(c)) and amplifies the blast radius of any downstream logging or caching of the response.

### review-data-integrity
- `atomic-bulk-insert` r0 → 2 findings:
  - `src/demo/db/repository.py:57` high — bulk_create_items returns ORM objects without refreshing server-generated columns. The session factory in engine.py is configured with expire_on_commit=False, so after session.commit() the objects are NOT expired and will not lazy-reload. The created_at column is a server_default (func.now()), meaning its value is never written into the in-memory objects during construction — only the database holds it. Callers that access item.created_at on a closed session (e.g. via FastAPI's get_session() context-manager dependency) will raise DetachedInstanceError; on an open session each access triggers an individual implicit SELECT (N+1). The existing create_item avoids exactly this by calling session.refresh(item) after commit.
  - `src/demo/db/repository.py:46` high — The 1000-row cap is evaluated on the deduplicated cleaned list, not on the raw names input. A caller passing 1 001 names that are all duplicates of one another clears the cap check (cleaned has 1 item) and silently inserts 1 row. More critically: a caller passing exactly 1 001 distinct names is rejected. The docstring describes the cap as protecting against an 'unbounded insert', but the bound is applied after dedup, making the effective cap on caller-visible input non-deterministic. If the intent is to limit input size (DoS protection), the check should be on len(names) before dedup; if the intent is to limit DB rows, the current position is correct but the docstring and error message are misleading ('bulk insert of N exceeds the 1000-row limit' — N is the post-dedup count, not what the caller passed).
- `atomic-bulk-insert` r1 → 3 findings:
  - `src/demo/db/repository.py:59` high — session.commit() is called without any subsequent session.refresh() on the returned Item objects. The session factory in engine.py sets expire_on_commit=False, which prevents post-commit lazy-loading. The created_at column uses server_default=func.now() with no Python-side default, so its value is only set by the database. Whether SQLAlchemy populates it during flush via RETURNING depends on the dialect: PostgreSQL with implicit_returning works, but SQLite and MySQL/MariaDB do not reliably back-fill server_default columns. Returned objects will have created_at=None on those backends despite the column being NOT NULL in the schema, silently misrepresenting persisted state. The sibling function create_item() calls session.refresh(item) for exactly this reason; bulk_create_items removes that safeguard with an incorrect docstring claim ('no per-row refresh') at line 38-40.
  - `src/demo/db/repository.py:55` medium — The 1000-row cap (line 55) is evaluated on the post-deduplication cleaned list, not on the raw names input. A caller may pass an arbitrarily large input (e.g. 10 M near-duplicate names) that deduplicates to fewer than 1000 entries; the entire raw list is iterated and hashed before the guard fires, exhausting memory and CPU. This is a denial-of-service vector against the persistence layer and can cause the hosting process to OOM before any error is raised.
  - `src/demo/db/repository.py:43` medium — The docstring states the function 'propagates sqlalchemy.exc.IntegrityError (e.g. a unique-constraint violation)' and instructs callers to roll back in that case. However, the migration (migrations/versions/0001_initial.py) defines no UNIQUE constraint on items.name. Within-batch duplicates are silently removed by the dedup loop, but duplicate names across separate calls will insert without error, accumulating duplicate rows. The documented IntegrityError contract for uniqueness is unreachable given the actual schema, misleading callers into believing uniqueness is enforced at the database level.
- `atomic-bulk-insert` r2 → 3 findings:
  - `src/demo/db/repository.py:60` high — Returned Item objects will have created_at=None. engine.py configures the sessionmaker with expire_on_commit=False, so SQLAlchemy never expires attributes and lazily re-fetches server-generated values after commit. The created_at column is defined with server_default=func.now() and is never assigned by Python; without eager_defaults=True on the mapper or an explicit session.refresh(), the attribute stays in its ORM-pending state (None) on every returned object. The docstring claim that 'server-assigned ids are populated by the flush inside session.commit()' holds only for the PK (fetched via RETURNING/lastrowid); it does not extend to other server_default columns. By contrast, create_item defensively calls session.refresh(item) for exactly this reason.
  - `src/demo/db/repository.py:58` medium — The items table has no UNIQUE constraint on the name column (migration 0001_initial.py declares only NOT NULL). Within-batch deduplication prevents duplicates inside a single call, but two concurrent bulk_create_items calls with overlapping names will both succeed and silently insert duplicate rows, violating any name-uniqueness invariant the business may rely on. The docstring references sqlalchemy.exc.IntegrityError from 'a unique-constraint violation' as a real runtime concern, but no such constraint exists — that error path is dead code and the documented safety net is absent.
  - `src/demo/db/repository.py:55` medium — The 1000-row cap is evaluated against the de-duplicated count, not the raw input length. A caller supplying 1001 names where any one is a duplicate reduces to 1000 unique entries and silently bypasses the cap, inserting exactly the maximum number of rows the cap was meant to prevent. The intent of the cap ('avoid an unbounded insert') suggests it should apply to the raw request size, not just the unique count after transformation.

### review-dependency
- `pinned-reputable-dep` r0 → 2 findings:
  - `pyproject.toml:0` info — httpx is already declared as a dev dependency (`httpx>=0.28` in [dependency-groups] dev), where it typically serves FastAPI's TestClient. Promoting it to [project] dependencies implies new runtime HTTP-client usage, but this diff contains no source changes to confirm that. If all httpx imports live under tests/, the production pin is unnecessary bloat.
  - `pyproject.toml:0` low — Minor lower-bound inconsistency: the production pin allows >=0.27 while the dev group requires >=0.28. In a combined install the stricter dev constraint wins, but a production-only install (e.g. a slim Docker image built without dev extras) could resolve 0.27.x, which diverges from the version exercised in CI.
- `pinned-reputable-dep` r1 → 4 findings:
  - `pyproject.toml:19` low — Version floor mismatch between production and dev: production allows 'httpx>=0.27' while [dependency-groups].dev already pins 'httpx>=0.28'. This means production could resolve to an older minor than what is exercised in tests, undermining parity.
  - `pyproject.toml:19` low — 'httpx' is already declared in [dependency-groups].dev. Adding it to the production [project].dependencies is only justified if production application code (not just tests or TestClient) makes HTTP calls. The diff contains no accompanying source change to confirm a production use-case.
  - `pyproject.toml:19` info — The '<1.0' upper bound is conservative and correct today (httpx is pre-1.0 as of 0.2x), but will silently block upgrades when httpx 1.0 ships and may cause resolver conflicts downstream.
  - `pyproject.toml:19` info — Supply-chain note (informational): httpx (encode/httpx, Tom Christie) is actively maintained, widely adopted, and has a clean release history. No elevated supply-chain risk identified.
- `pinned-reputable-dep` r2 → 4 findings:
  - `pyproject.toml:0` info — httpx is already declared in [dependency-groups].dev as `httpx>=0.28`. Promoting it to production dependencies is appropriate only if application code (not just tests) now imports it at runtime. The diff touches only pyproject.toml — no source file introducing an httpx import is visible. If the sole consumer is the FastAPI test client or pytest fixtures, the library should remain dev-only.
  - `pyproject.toml:0` info — Version-floor inconsistency: the new production pin allows `>=0.27` while the dev-group pin requires `>=0.28`. A developer environment will always resolve to ≥0.28, but a minimal production install could resolve to 0.27.x, which is one minor behind. The public httpx API is stable across that range, but the asymmetry is surprising and easy to overlook.
  - `pyproject.toml:0` info — The `<1.0` upper bound is appropriate while httpx is pre-1.0 (current latest is 0.28.x), but it will silently block the 1.0 release when it ships. This is a known maintenance cost of capping a pre-release library.
  - `pyproject.toml:0` info — Supply-chain and maintenance health are low-risk. httpx is maintained by the Encode team (also responsible for Starlette/Uvicorn), has a strong release cadence, passes standard audit tools, and has no known high/critical CVEs. No concerns here.

### review-documentation
- `documented-public-function` r0 → 3 findings:
  - `src/demo/routes/items.py:51` low — Docstring claims 'total number of items in the catalogue' but `list_items(session)` is called with no explicit `limit`, so it falls back to `DEFAULT_PAGE_SIZE=50`. The count returned is silently capped at 50 — the docstring is materially misleading for catalogues with more than 50 items.
  - `README.md:78` low — README documents `GET /items/count` as returning 'total items in the catalogue', but the implementation delegates to `list_items` whose default `limit` is `DEFAULT_PAGE_SIZE` (50), not a full COUNT. The documented API contract does not match the implementation.
  - `src/demo/routes/items.py:27` info — `ItemCount` has no field-level docstring or `Field(description=…)` annotation for the `count` field. OpenAPI will emit the field with no description, which weakens the 'typed contract' motivation cited in the endpoint docstring.
- `documented-public-function` r1 → 3 findings:
  - `src/demo/routes/items.py:47` low — Docstring states 'total number of items in the catalogue', but the implementation calls `list_items(session)` with no `limit` argument, so it uses `DEFAULT_PAGE_SIZE` (50). For a catalogue larger than 50 items the count silently under-reports.
  - `README.md:78` info — The endpoint description 'total items in the catalogue' overstates what the route actually returns when the catalogue exceeds DEFAULT_PAGE_SIZE (50), because the implementation is bounded by the repository page cap.
  - `src/demo/routes/items.py:45` low — A new public route `GET /items/count` is added but `openapi.json` does not appear in the diff. The README states 'regenerate openapi.json after changing routes; commit it (CI fails on a stale or breaking spec)'.
- `documented-public-function` r2 → 3 findings:
  - `src/demo/routes/items.py:47` low — Docstring claims to return 'the total number of items in the catalogue', but the implementation calls list_items(session) with no limit override. list_items defaults to DEFAULT_PAGE_SIZE=50 and is hard-capped at MAX_PAGE_SIZE=100, so the count is silently bounded — it is not a true total.
  - `README.md:78` low — Endpoint entry reads '— total items in the catalogue' but the implementation is bounded by list_items' DEFAULT_PAGE_SIZE, so callers relying on this description for a true row count will be misled.
  - `src/demo/routes/items.py:45` info — A new route (GET /items/count) is added but openapi.json does not appear to be updated in this diff. Per the README CI/CD section, CI runs an OpenAPI contract-diff job and fails on a stale or breaking spec.

### review-env-parity
- `parity-preserved` r0 → 1 findings:
  - `infra/compose/base.yml:11` high — APP_WIDGET_API_URL is consumed by the app in ALL environments (settings.py field `widget_api_url`, no env-gating), but its container wiring `APP_WIDGET_API_URL: "${APP_WIDGET_API_URL}"` was added only to base.yml. base.yml is a DEV/TEST-only overlay — the deploy composition is `<env>.yml + services.yml + observability.yml`, and the self-contained staging.yml / prod.yml app definitions enumerate their own `environment:` block (TZ, APP_ENVIRONMENT, APP_DATABASE_URL) without APP_WIDGET_API_URL. Compose only injects vars listed in a service's `environment:`/`env_file:`, so in staging/prod the app never receives APP_WIDGET_API_URL and silently falls back to the settings.py default `http://widget:9000`, making the widget endpoint unconfigurable in the deployed environments. This is the same dev-only-overlay parity gap the service rule guards against, applied to an env-var wiring.
- `parity-preserved` r2 → 1 findings:
  - `infra/compose/base.yml:11` high — APP_WIDGET_API_URL is wired into the app's environment only in base.yml, which is a DEV/TEST-only overlay and is NOT part of the staging/prod composition (staging.yml/prod.yml + services.yml + observability.yml). The settings field widget_api_url is consumed by the app in every environment and .env.example documents it as 'set per environment', but staging/prod will never receive ${APP_WIDGET_API_URL} and will silently fall back to the hardcoded default http://widget:9000 — an env-var parity gap that ships to prod unconfigurable.

### review-observability
- `correlation-id-logging` r0 → 4 findings:
  - `src/demo/routes/items.py:59` high — `_log.error('delete_item_failed', item_id=item_id)` is called without `exc_info=True`. The log event carries the structlog-injected correlation_id but contains no exception type, message, or traceback — the error path is effectively unobservable in production because there is no actionable diagnostic information to reconstruct root cause.
  - `src/demo/routes/items.py:42` medium — No application-level counter metric for delete operations. `MetricsRegistry` and `ObservabilityMiddleware` record only fleet-wide HTTP p99 latency and 5xx error rate. A surge in successful or failed deletes is invisible in `/metrics`, `/health`, or any Prometheus alert until it moves the fleet-wide `error_rate_pct` SLO — by which point many deletes may have silently failed.
  - `src/demo/routes/items.py:42` medium — No SLO threshold is defined for the new DELETE endpoint. The existing SLOs in `observability/slo.py` (`request_latency_p99_ms`, `error_rate_pct`) are fleet-wide aggregates that cannot distinguish a degraded delete path from healthy GET traffic. A destructive operation like item deletion warrants its own alertable SLO rather than being diluted into the fleet signal.
  - `src/demo/routes/items.py:50` low — `item_id` is not attached to the active OTel span as a span attribute. `FastAPIInstrumentor` auto-creates a span for the route so the path IS traced, but without a span attribute the trace in Tempo has no discriminating key for the affected item — correlating a failed trace to the specific item requires a separate log join on correlation_id.
- `correlation-id-logging` r1 → 4 findings:
  - `src/demo/routes/items.py:57` high — `_log.error("delete_item_failed", item_id=item_id)` drops exception details entirely — no type, message, or traceback is captured in the structured log record. The error path emits only `item_id`, making post-incident diagnosis impossible from logs alone without cross-referencing the OTel span.
  - `src/demo/routes/items.py:58` medium — No `session.rollback()` before the bare `raise`. After a failed `session.delete()` or `session.commit()`, the SQLAlchemy session is left in an invalid/dirty state. If the connection-pool reuses the session before the dependency-injection teardown fully closes it, subsequent DB operations will emit confusing errors that are not correlated to the original delete failure, polluting the correlation-ID log stream.
  - `src/demo/routes/items.py:40` medium — No SLO threshold is defined for the new `DELETE /items/{item_id}` endpoint. `slo.py::default_slos()` defines only aggregate fleet-wide metrics (`request_latency_p99_ms`, `error_rate_pct`). A destructive endpoint that begins returning 5xx errors at high volume could stay below the aggregate alert threshold until it degrades a significant fraction of total traffic — the signal is silently absorbed.
  - `src/demo/routes/items.py:56` low — `_log.error(...)` fires inside the `except` block before the bare `raise` propagates to `register_exception_handlers`. If the global exception handler also logs unhandled exceptions (a common pattern for 500-level events), the same failure produces two log entries — one with the structlog-bound correlation ID and one potentially without it — creating split or duplicate correlation chains in log aggregation.
- `correlation-id-logging` r2 → 3 findings:
  - `src/demo/routes/items.py:58` high — `except Exception` re-raises without calling `session.rollback()`. After a failed `session.commit()`, SQLAlchemy marks the session invalid; without an explicit rollback the connection is returned to the pool in a 'needs rollback' state, corrupting subsequent requests that receive the same connection — broken context propagation that can cascade into unrelated 500s with no clear log trail.
  - `src/demo/routes/items.py:59` medium — `_log.error("delete_item_failed", item_id=item_id)` omits `exc_info=True`. The exception type, message, and full stack trace are silently discarded — the only observability signal for a commit failure is the bare event name, making root-cause analysis of production errors impossible even when the correlation ID is present.
  - `src/demo/routes/items.py:42` medium — The new `DELETE /items/{item_id}` endpoint has no per-endpoint SLO threshold in `slo.py` / `provisioning.py`. DELETE is a destructive, potentially lock-contending operation whose latency and error-rate signals are diluted into the global `request_latency_p99_ms` and `error_rate_pct` SLOs shared with `GET /items`. A spike in delete failures or latency may not breach the global threshold until it visibly degrades the entire fleet.
- `instrumented-route` r0 → 5 findings:
  - `src/demo/routes/items.py:49` medium — 404 warning log does not explicitly include a correlation_id. If ObservabilityMiddleware does not bind a request-scoped correlation_id into structlog contextvars before route dispatch, this warning event will be untrackable across service boundaries and the log→trace link is broken for the not-found path.
  - `src/demo/routes/items.py:52` medium — session.commit() failure path is unobserved. If the commit raises (e.g., IntegrityError, stale connection), the exception propagates with no structured log capturing item_id or mutation intent. The registered exception handler will log a generic 500 with no route-level context, making the incident untriageable without a full trace.
  - `src/demo/routes/items.py:40` medium — No SLO threshold is defined for the new archive write endpoint. The fleet-wide request_latency_p99_ms and error_rate_pct in slo.py will absorb archive requests, but POST /items/{item_id}/archive includes a session.commit() and is structurally higher-latency than GET /items. A latency regression on this endpoint can silently inflate the fleet p99 without triggering a targeted alert.
  - `src/demo/routes/items.py:47` medium — item_id is not set as an application-level span attribute on the auto-instrumented trace. FastAPIInstrumentor records http.route and http.target (which includes the raw URL), but there is no app.item_id attribute, so filtering traces for a specific item in Tempo/Jaeger requires full-text URL matching rather than a typed attribute lookup. Log↔trace correlation by item is impossible without it.
  - `src/demo/routes/items.py:51` low — Re-archiving an already-archived item silently produces '[archived] [archived] item_name' with no warning log and no 4xx response. This non-idempotent mutation is invisible in both logs and metrics, making it impossible to detect or alert on repeated archive operations causing data drift.
- `instrumented-route` r1 → 5 findings:
  - `src/demo/routes/items.py:47` high — 404 error path logs 'archive_item_not_found' without a correlation_id or trace_id. The module-level _log carries no request-scoped context. If the ObservabilityMiddleware does not call structlog.contextvars.bind_contextvars(correlation_id=...) before this point, this warning event is unlinked from its OTel request span and cannot be correlated during incident investigation.
  - `src/demo/routes/items.py:55` high — Success path logs 'archive_item_completed' without correlation_id or trace_id for the same reason as line 47. Both structured log events emitted by this endpoint are unlinked from the OTel request span if structlog contextvars are not wired by the middleware.
  - `src/demo/routes/items.py:40` medium — New POST /items/{item_id}/archive endpoint has no SLO threshold defined. slo.py defines only fleet-wide request_latency_p99_ms and error_rate_pct. A commit-bearing mutation endpoint has a materially different latency profile than the read-only GET /items and should either have its own threshold or be explicitly documented as sharing the fleet-wide SLO.
  - `src/demo/routes/items.py:52` medium — session.commit() is unguarded. A DB error at commit time raises an exception that propagates to the global exception handler without this function logging item_id at the point of failure. The handler records the exception but loses the business context (which item was being archived), making root-cause analysis harder.
  - `src/demo/routes/items.py:14` low — _log = get_logger() is bound at module import time with no name argument. If this module is imported before configure_logging() runs (e.g. in unit test fixtures that import the router directly), the logger will not have the expected structlog processors attached, including any contextvar-propagation processor.
- `instrumented-route` r2 → 5 findings:
  - `src/demo/routes/items.py:54` high — session.commit() failure produces an unhandled 500 with no structured log at the call site. The item_id context is lost; only the global exception handler fires, without mutation-specific fields. This is a new unmetered/unlogged error path on a mutating endpoint.
  - `src/demo/routes/items.py:51` medium — _log.warning('archive_item_not_found') logs item_id but no correlation_id. If the structlog pipeline does not auto-bind a request correlation ID via contextvars middleware, this 404 error event cannot be correlated to its originating trace or request in log aggregation.
  - `src/demo/routes/items.py:56` medium — _log.info('archive_item_completed') has the same missing correlation_id as the 404 path — successful mutation events are also unlinked from their originating request in log aggregation, defeating end-to-end trace correlation for the happy path.
  - `src/demo/routes/items.py:42` medium — No SLO threshold is defined in slo.py / default_slos() for the new POST /items/{item_id}/archive endpoint. The global request_latency_p99_ms and error_rate_pct SLOs apply fleet-wide but cannot surface archive-specific degradation (e.g. elevated 404 or commit-failure rates on this path).
  - `src/demo/routes/items.py:55` low — session.refresh() executes after a successful commit. If refresh raises (e.g. row deleted by a concurrent transaction between commit and refresh), the archive mutation DID succeed but archive_item_completed is never logged — creating a silent observability gap where the operation is unrecorded despite having taken effect.

### review-observability-fe
- `capped-label` r0 → 2 findings:
  - `src/demo/frontend_rum/metrics.py:128` high — The new app_frontend_device_class_total signal reads device_class from params.get("device_class", ""), but the route (src/demo/routes/frontend_rum.py) filters params through the fail-closed allowlist (`{k: v ... if k in allow}`) and settings.frontend_rum_allowed_query_params defaults to the UTM set only (utm_source/medium/campaign/term/content) — device_class is never in it. So device_class is stripped server-side before record_page_view ever sees it, and the series will only ever emit device_class="unknown". The signal is structurally incapable of recording its intended dimension: device-class distribution is effectively unobserved despite the metric appearing populated.
  - `src/demo/frontend_rum/metrics.py:206` medium — New RUM signal app_frontend_device_class_total is exposed on /metrics but has no corresponding Grafana dashboard panel (infra/observability/grafana/dashboards/frontend.json defines only vitals, JS errors, page-views-by-route, and beacon ingest) and no alert rule (no prometheus alert files exist under infra/observability). The new signal ships unwatched — operators have no panel to read it and nothing fires on anomalies.
- `capped-label` r2 → 2 findings:
  - `src/demo/frontend_rum/metrics.py:128` medium — New `device_class` dimension is read from `params`, but the ingest route filters params through the fail-closed allowlist (`frontend_rum_allowed_query_params`, routes/frontend_rum.py:64), which contains only the `utm_*` keys. `device_class` is never in the allowlist, so it is stripped before reaching `record_page_view` and the `app_frontend_device_class_total` series can only ever emit `device_class="unknown"`. The signal is dead-on-arrival: it produces no operable data.
  - `src/demo/frontend_rum/metrics.py:206` medium — New RUM signal `app_frontend_device_class_total` is exposed on /metrics with no corresponding Grafana dashboard panel (infra/observability/grafana/dashboards/frontend.json has panels only for web vitals, js_errors, page_views, rum_beacons) and no alert rule (infra/observability/prometheus/alerts/frontend_alerts.yml covers only LCP and js_errors). The metric is emitted but unobserved by any operator-facing surface.

### review-observability-infra
- `complete-obs-surface` r0 → 1 findings:
  - `infra/compose/dev.yml:68` medium — The new `redis:` block is added at 2-space indent under the `volumes:` mapping (sibling to `pgdata`), not under `services:`. As written it parses as a *volume* named `redis`, and `image`/`profiles`/`healthcheck` are meaningless keys on a volume — so the dev overlay has no redis *service*. The observability overlay's `redis-exporter` (observability.yml) has no `profiles:` so it also loads in the dev overlay, and it declares `depends_on: redis: condition: service_healthy`. With no `redis` service to resolve, dev observability bring-up fails and the `redis` scrape target (redis-exporter -> redis://redis:6379) has nothing behind it in dev. The prod copy in services.yml is correctly placed under `services:`; only the dev definition is malformed.
- `complete-obs-surface` r1 → 2 findings:
  - `infra/observability/prometheus/prometheus.yml:0` high — New prod runtime surface `redis` (added to services.yml for staging/prod) gets a scrape job and a redis-exporter, but has NO alert rule. infra/observability/prometheus/alerts/ contains only postgres.yml, otel-collector.yml, and app.yml. Postgres ships PostgresDown + connection alerts; redis ships nothing — so a prod redis outage fires no alert and silently breaks Celery/cache that depend on it. A new prod data store with zero alerting is a real observability gap.
  - `infra/observability/prometheus/prometheus.yml:0` medium — The new redis scrape job has no matching Grafana dashboard. infra/observability/grafana/dashboards/ contains only postgres.json, otel-collector.json, and app.json — there is no redis.json. The redis surface is now scraped (redis-exporter:9121) but never visualized, so the collected metrics are not usable for operators.
- `complete-obs-surface` r2 → 1 findings:
  - `infra/compose/dev.yml:0` medium — The new dev `redis` block is indented under the `volumes:` mapping (right after `pgdata: {}`), not under `services:`. As written, Compose treats `redis` as a volume definition with bogus keys (`image`, `profiles`, `healthcheck`) rather than a runnable service, so dev gets no redis container. observability.yml (merged into dev) still runs `redis-exporter` pointed at `redis://redis:6379` and prometheus.yml scrapes job `redis` → in dev the scrape target has no backing service, producing a permanent metrics gap and a false-firing `RedisDown` alert. Prod is unaffected (services.yml defines redis correctly under `services:`).

### review-performance
- `single-query` r0 → 1 findings:
  - `src/demo/routes/items.py:46` low — list_items() issues SELECT id, name, created_at FROM items but only the name column is consumed. All ORM columns are hydrated into Item objects and then immediately discarded, transferring ~2× more data than necessary per row.
- `single-query` r1 → 1 findings:
  - `src/demo/routes/items.py:46` low — list_items() fetches full ORM rows (id, name, created_at) but get_item_names() discards every column except name. Two lists are materialised: one of Item objects from the repository, one of bare strings. At the current MAX_PAGE_SIZE=100 cap the waste is small (~1–2 KB of extra column data per request), but the pattern couples this endpoint's cost to future column additions on the Item model without any visible callsite change.
- `single-query` r2 → 1 findings:
  - `src/demo/routes/items.py:46` low — list_items(session) fetches full Item ORM objects (id, name, created_at) but only the name column is consumed. The unused columns are hydrated into Python objects and immediately discarded. Bounded at MAX_PAGE_SIZE=100 so real-world impact is negligible, but it is unnecessary work on every call to this endpoint.

### review-security
- `env-sourced-secret` r0 → 2 findings:
  - `src/demo/config/settings.py:37` medium — api_secret_key is typed as plain `str`, so its value appears in plaintext in `repr(settings)`, `settings.model_dump()`, and any log line that serialises the Settings object. pydantic's `SecretStr` masks the value as `**********` in all of those contexts, preventing accidental leakage into logs, tracebacks, or debug endpoints.
  - `src/demo/config/settings.py:37` low — No minimum-length or format constraint on api_secret_key. A deployer could accidentally set `APP_API_SECRET_KEY=x` (or an empty string after stripping) and the application would start successfully with a trivially weak secret.
- `env-sourced-secret` r1 → 3 findings:
  - `src/demo/config/settings.py:37` high — api_secret_key is typed as plain str. Pydantic's Settings.__repr__() and model_dump() include all str fields in plain text, meaning the secret will appear in structured logs, debug output, error serialization, and any code that calls str(settings) or logs the settings object.
  - `src/demo/config/settings.py:37` medium — No minimum-length or entropy constraint on the secret. An empty-string value (APP_API_SECRET_KEY= in the environment or .env) satisfies Pydantic's required-field check and bypasses the 'fail fast if unset' guarantee described in the comment, silently giving the application a zero-entropy secret key.
  - `src/demo/config/settings.py:37` low — The Settings class is bound to env_file='.env' (line 10). APP_API_SECRET_KEY placed in a .env file is at risk of accidental VCS commit, CI log capture, or Docker build-arg leakage if .env is not in .gitignore and .dockerignore. This risk is amplified now that a high-value secret is expected in that file.
- `env-sourced-secret` r2 → 3 findings:
  - `src/demo/config/settings.py:37` medium — api_secret_key is typed as plain `str` rather than Pydantic's `SecretStr`. A bare `str` field will expose the secret value in plaintext wherever the Settings object is repr'd, str()'d, serialised via model_dump(), or included in a traceback — all common paths to logs and error aggregators.
  - `src/demo/config/settings.py:37` low — The Settings class is cached with @lru_cache (get_settings). Once loaded, api_secret_key is held in the module-level cache for the process lifetime with no rotation path. If the secret is rotated in the environment, the running process will continue using the old value until restarted.
  - `src/demo/config/settings.py:36` info — The comment 'no default so startup fails fast if unset' is correct behaviour, but the field name api_secret_key is generic. If multiple secrets are added in future, distinguishing purpose (e.g. jwt_signing_key, hmac_secret) makes accidental cross-use or scope confusion less likely.

### review-test-quality
- `meaningful-assert` r0 → 2 findings:
  - `tests/unit/test_settings.py:56` high — test_resolved_log_level_prod_is_info is a verbatim duplicate of an existing parametrized case. test_resolved_log_level_is_info_outside_dev is already parametrized over ["staging", "prod", "ci"] and asserts the identical expression `Settings(environment="prod").resolved_log_level == "INFO"`. The new test cannot fail in any scenario where the existing parametrized test passes; it adds zero coverage and will never catch a regression that the suite does not already catch.
  - `tests/unit/test_settings.py:50` low — test_slo_request_latency_p99_env_override exercises the same Pydantic-settings env-override mechanism already proven by test_env_vars_override (which covers APP_SLO_ERROR_RATE_PCT). The new test does cover a distinct field name, so it is not a pure duplicate, but the marginal confidence gained is low: a bug that silently ignores APP_SLO_REQUEST_LATENCY_P99_MS would be the only new failure mode caught, and that scenario is already guarded by test_defaults asserting the default value. Consider whether this test pulls its weight.
- `meaningful-assert` r1 → 1 findings:
  - `tests/unit/test_settings.py:56` low — test_resolved_log_level_prod_is_info is a strict duplicate of an existing parametrized case. test_resolved_log_level_is_info_outside_dev already parametrizes over ["staging", "prod", "ci"] and executes the identical assertion — Settings(environment="prod").resolved_log_level == "INFO" — as one of its three invocations. The new test adds zero coverage and creates a maintenance hazard: the two assertions can silently diverge if the parametrized set is later changed.
- `meaningful-assert` r2 → 2 findings:
  - `tests/unit/test_settings.py:55` medium — `test_resolved_log_level_prod_is_info` is an exact duplicate of the existing parametrized case `test_resolved_log_level_is_info_outside_dev[prod]` (line 17–19 in the full file). Both call `Settings(environment="prod").resolved_log_level` and assert `== "INFO"`. They are fully coupled: any regression that breaks one breaks the other, so the new test contributes zero additive coverage. The 'data-leak' comment does not change the code path exercised.
  - `tests/unit/test_settings.py:49` low — `test_slo_request_latency_p99_env_override` exercises the same mechanism already covered by `test_env_vars_override` (which already asserts a `float` field — `slo_error_rate_pct` — is overridden from env). pydantic-settings applies the same coercion uniformly to every scalar field; a second single-field float override test adds no new failure mode. The only distinct value would be verifying the exact env-var-name-to-attribute mapping for this specific field.

### review-usability
- `delete-with-confirm` r1 → 3 findings:
  - `frontend/src/Items.tsx:56` info — No success feedback after deletion: onDeleted() is called on success, but there is no in-component confirmation (e.g. a brief 'Item deleted' message). The user receives no positive acknowledgment — the item simply disappears, which can feel jarring or ambiguous if the list re-render is slow.
  - `frontend/src/Items.tsx:44` info — window.confirm is a blocking, browser-native dialog with no custom styling and inconsistent behavior across environments (blocked in iframes, absent in some mobile browsers). It also interrupts the user with a modal for a potentially low-stakes action.
  - `frontend/src/Items.tsx:64` info — The error message is rendered inline with no dismiss affordance. Once shown, it persists indefinitely (until the next delete attempt), which can confuse users who navigate away and return, or who take other actions.

## Agentic behavior
### review-api-design
- Calls: 9, avg turns: 1.1, max-cap hits: 0
- Tools: read_file×1
- Top paths/patterns: `src/demo/graphql/schema.py`×1

### review-architecture
- Calls: 9, avg turns: 1.8, max-cap hits: 0
- Tools: read_file×13, glob×2, grep×2
- Top paths/patterns: `src/demo/routes/items.py`×6, `src/demo/db/repository.py`×5, `src/demo/db/engine.py`×3, `src/demo/db/*.py`×1, `src/demo/db/item_service.py`×1

### review-contracts
- Calls: 9, avg turns: 2.4, max-cap hits: 0
- Tools: grep×13, glob×12, read_file×7
- Top paths/patterns: `tests/functional/test_consumer_inventory.py`×4, `**/*pact*`×3, `**/*inventory*`×2, `in_stock`×2, `in_stock|reserved_count|inventory`×2

### review-data-lineage
- Calls: 9, avg turns: 1.3, max-cap hits: 0
- Tools: read_file×6, grep×2
- Top paths/patterns: `src/demo/db/models.py`×3, `src/demo/db/repository.py`×2, `src/demo`×2, `delete|erase|remove`×1, `class Item`×1

### review-env-parity
- Calls: 12, avg turns: 2.5, max-cap hits: 0
- Tools: read_file×31, glob×17, grep×8
- Top paths/patterns: `.env.example`×7, `infra/compose/*.yml`×6, `infra/compose/staging.yml`×4, `**/.env.example`×4, `src/demo/config/settings.py`×4

### review-observability-db
- Calls: 9, avg turns: 2.0, max-cap hits: 0
- Tools: grep×11, glob×7, read_file×2
- Top paths/patterns: `src/demo/**/*.py`×4, `src/demo`×3, `src/demo/db/repository.py`×3, `SQLAlchemyInstrumentor`×3, `SQLAlchemyInstrumentor|Instrumentor|instrument`×1

### review-observability-fe
- Calls: 12, avg turns: 1.9, max-cap hits: 0
- Tools: grep×13, read_file×10, glob×6
- Top paths/patterns: `src/demo/frontend_rum`×7, `src/demo/frontend_rum/metrics.py`×3, `record_raw_path|raw_path|full_path`×2, `src/demo/frontend_rum/**`×2, `src/demo/routes/frontend_rum.py`×2

### review-observability-infra
- Calls: 9, avg turns: 2.7, max-cap hits: 0
- Tools: glob×25, read_file×15, grep×9
- Top paths/patterns: `redis`×7, `infra`×5, `infra/compose/services.yml`×4, `infra/compose/*.yml`×4, `infra/observability/prometheus/prometheus.yml`×3

### review-privacy
- Calls: 12, avg turns: 2.1, max-cap hits: 0
- Tools: read_file×13, grep×6, glob×5
- Top paths/patterns: `src/demo/db/repository.py`×8, `src/demo/routes/items.py`×4, `def create_item`×3, `src/demo/config/settings.py`×3, `owner_email`×2

## Drift check
- ⚠ `api-design` / `graphql-rest-divergence` r2 — disallowed tools: read_file×1
- ⚠ `architecture` / `duplicate-data-layer` r0 — disallowed tools: glob×1, read_file×3
- ⚠ `architecture` / `duplicate-data-layer` r1 — disallowed tools: glob×1, read_file×1
- ⚠ `architecture` / `layering-violation` r0 — disallowed tools: read_file×3
- ⚠ `architecture` / `layering-violation` r1 — disallowed tools: read_file×3
- ⚠ `architecture` / `layering-violation` r2 — disallowed tools: read_file×3
- ⚠ `architecture` / `clean-layering` r1 — disallowed tools: grep×2
- ⚠ `contracts` / `client-missing-pact-field` r0 — disallowed tools: glob×1, grep×2, read_file×1
- ⚠ `contracts` / `client-missing-pact-field` r1 — disallowed tools: grep×1, read_file×1
- ⚠ `contracts` / `client-missing-pact-field` r2 — disallowed tools: glob×1, grep×1, read_file×2
- ⚠ `contracts` / `client-pact-divergence` r0 — disallowed tools: glob×1, grep×3
- ⚠ `contracts` / `client-pact-divergence` r1 — disallowed tools: glob×2, grep×1
- ⚠ `contracts` / `client-pact-divergence` r2 — disallowed tools: glob×3, grep×1, read_file×2
- ⚠ `contracts` / `client-pact-covered` r1 — disallowed tools: glob×1, grep×2
- ⚠ `contracts` / `client-pact-covered` r2 — disallowed tools: glob×3, grep×2, read_file×1
- ⚠ `data-lineage` / `untransformed-write` r2 — disallowed tools: grep×1, read_file×2
- ⚠ `data-lineage` / `normalized-write` r0 — disallowed tools: grep×1, read_file×1
- ⚠ `data-lineage` / `normalized-write` r2 — disallowed tools: read_file×3
- ⚠ `env-parity` / `compose-var-not-declared` r0 — disallowed tools: glob×2, grep×2, read_file×3
- ⚠ `env-parity` / `compose-var-not-declared` r1 — disallowed tools: glob×3, grep×3, read_file×1
- ⚠ `env-parity` / `env-var-consumed-not-declared` r0 — disallowed tools: glob×2, grep×1, read_file×1
- ⚠ `env-parity` / `env-var-consumed-not-declared` r1 — disallowed tools: glob×1, read_file×2
- ⚠ `env-parity` / `env-var-consumed-not-declared` r2 — disallowed tools: glob×1, read_file×2
- ⚠ `env-parity` / `service-dev-only` r0 — disallowed tools: glob×2, grep×1, read_file×3
- ⚠ `env-parity` / `service-dev-only` r1 — disallowed tools: glob×2, grep×1, read_file×2
- ⚠ `env-parity` / `service-dev-only` r2 — disallowed tools: glob×1, read_file×2
- ⚠ `env-parity` / `parity-preserved` r0 — disallowed tools: read_file×8
- ⚠ `env-parity` / `parity-preserved` r1 — disallowed tools: glob×1, read_file×6
- ⚠ `env-parity` / `parity-preserved` r2 — disallowed tools: glob×2, read_file×1
- ⚠ `observability-db` / `unindexed-unobserved-query` r0 — disallowed tools: glob×1, grep×1, read_file×1
- ⚠ `observability-db` / `unindexed-unobserved-query` r1 — disallowed tools: glob×1, grep×1
- ⚠ `observability-db` / `unindexed-unobserved-query` r2 — disallowed tools: glob×1, grep×1
- ⚠ `observability-db` / `write-path-no-metric` r0 — disallowed tools: glob×1, grep×1, read_file×1
- ⚠ `observability-db` / `write-path-no-metric` r1 — disallowed tools: glob×1, grep×1
- ⚠ `observability-db` / `write-path-no-metric` r2 — disallowed tools: glob×1, grep×1
- ⚠ `observability-db` / `observed-query` r0 — disallowed tools: glob×1, grep×1
- ⚠ `observability-db` / `observed-query` r1 — disallowed tools: grep×2
- ⚠ `observability-db` / `observed-query` r2 — disallowed tools: grep×2
- ⚠ `observability-fe` / `swallowed-error` r2 — disallowed tools: glob×1, grep×1
- ⚠ `observability-fe` / `unbounded-label` r0 — disallowed tools: grep×2, read_file×1
- ⚠ `observability-fe` / `unbounded-label` r1 — disallowed tools: glob×1, grep×1
- ⚠ `observability-fe` / `unbounded-label` r2 — disallowed tools: glob×1, grep×2
- ⚠ `observability-fe` / `capped-label` r0 — disallowed tools: glob×1, grep×3, read_file×6
- ⚠ `observability-fe` / `capped-label` r1 — disallowed tools: glob×1, grep×1
- ⚠ `observability-fe` / `capped-label` r2 — disallowed tools: glob×1, grep×3, read_file×3
- ⚠ `observability-infra` / `exporter-without-scrape` r0 — disallowed tools: glob×6, grep×3, read_file×4
- ⚠ `observability-infra` / `exporter-without-scrape` r1 — disallowed tools: glob×1, grep×1
- ⚠ `observability-infra` / `exporter-without-scrape` r2 — disallowed tools: glob×4, grep×2, read_file×1
- ⚠ `observability-infra` / `scrape-without-alert` r0 — disallowed tools: glob×3, grep×1, read_file×2
- ⚠ `observability-infra` / `scrape-without-alert` r1 — disallowed tools: glob×2
- ⚠ `observability-infra` / `scrape-without-alert` r2 — disallowed tools: glob×3, grep×2, read_file×2
- ⚠ `observability-infra` / `complete-obs-surface` r0 — disallowed tools: glob×2
- ⚠ `observability-infra` / `complete-obs-surface` r1 — disallowed tools: glob×2
- ⚠ `observability-infra` / `complete-obs-surface` r2 — disallowed tools: glob×2, read_file×6
- ⚠ `privacy` / `pii-in-response` r0 — disallowed tools: grep×2, read_file×1
- ⚠ `privacy` / `pii-in-response` r1 — disallowed tools: grep×1, read_file×1
- ⚠ `privacy` / `pii-in-response` r2 — disallowed tools: grep×1, read_file×1
- ⚠ `privacy` / `pii-logged` r0 — disallowed tools: read_file×2
- ⚠ `privacy` / `pii-logged` r1 — disallowed tools: read_file×2
- ⚠ `privacy` / `pii-logged` r2 — disallowed tools: grep×1, read_file×1
- ⚠ `privacy` / `rum-allowlists-pii` r0 — disallowed tools: read_file×1
- ⚠ `privacy` / `rum-allowlists-pii` r1 — disallowed tools: read_file×1
- ⚠ `privacy` / `rum-allowlists-pii` r2 — disallowed tools: read_file×1
- ⚠ `privacy` / `pii-excluded` r0 — disallowed tools: glob×2, grep×1
- ⚠ `privacy` / `pii-excluded` r1 — disallowed tools: glob×1, read_file×1
- ⚠ `privacy` / `pii-excluded` r2 — disallowed tools: glob×2, read_file×1

## Acknowledged (covered by decisions)
_(none)_

## Proposed thresholds.yaml
```yaml
accessibility:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
api-design:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
application-logic:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
architecture:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
compliance:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
contracts:
  recall_min: 0.40  # observed 0.50
  fp_max: 0.10  # observed 0.00
data-integrity:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
data-lineage:
  recall_min: 0.07  # observed 0.17
  fp_max: 0.10  # observed 0.00
dependency:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
documentation:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
env-parity:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.77  # observed 0.67
observability:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.93  # observed 0.83
observability-db:
  recall_min: 0.00  # observed 0.00
  fp_max: 0.10  # observed 0.00
observability-fe:
  recall_min: 0.57  # observed 0.67
  fp_max: 0.43  # observed 0.33
observability-infra:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.43  # observed 0.33
performance:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
privacy:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
security:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.43  # observed 0.33
test-quality:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.43  # observed 0.33
usability:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.43  # observed 0.33
```
