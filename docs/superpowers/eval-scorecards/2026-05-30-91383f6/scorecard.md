# Eval scorecard

## Summary
- Agents: 18
- Calls: 132 (bad: 75, good: 57)
- Total cost (est., USD): $0.00

## Scorecard
| Agent | Recall | FP | Status |
|---|---|---|---|
| review-accessibility | 1.00 | 0.00 | PASS |
| review-api-design | 0.83 | 0.00 | PASS |
| review-application-logic | 1.00 | 0.00 | PASS |
| review-architecture | 1.00 | 0.00 | PASS |
| review-compliance | 1.00 | 0.00 | PASS |
| review-contracts | 0.33 | 0.00 | FAIL (recall 0.33 < 0.67) |
| review-data-integrity | 1.00 | 0.33 | PASS |
| review-data-lineage | 1.00 | 0.00 | PASS |
| review-dependency | 1.00 | 0.33 | PASS |
| review-documentation | 1.00 | 0.67 | FAIL (fp 0.67 > 0.34) |
| review-observability | 1.00 | 0.00 | PASS |
| review-observability-db | 1.00 | 0.00 | PASS |
| review-observability-infra | 1.00 | 0.67 | FAIL (fp 0.67 > 0.34) |
| review-performance | 1.00 | 0.00 | PASS |
| review-privacy | 1.00 | 0.00 | PASS |
| review-security | 1.00 | 0.00 | PASS |
| review-test-quality | 1.00 | 0.00 | PASS |
| review-usability | 1.00 | 0.00 | PASS |

## Cost by agent
| Agent | Model | Calls | In tok | Out tok | Cache reads | Est. cost |
|---|---|---|---|---|---|---|
| review-accessibility | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |
| review-api-design | claude-opus-4-8 | 9 | 0 | 0 | 0 | $0.00 |
| review-application-logic | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |
| review-architecture | claude-opus-4-8 | 9 | 0 | 0 | 0 | $0.00 |
| review-compliance | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |
| review-contracts | claude-opus-4-8 | 9 | 0 | 0 | 0 | $0.00 |
| review-data-integrity | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |
| review-data-lineage | claude-opus-4-8 | 9 | 0 | 0 | 0 | $0.00 |
| review-dependency | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |
| review-documentation | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |
| review-observability | claude-sonnet-4-6 | 9 | 0 | 0 | 0 | $0.00 |
| review-observability-db | claude-opus-4-8 | 9 | 0 | 0 | 0 | $0.00 |
| review-observability-infra | claude-opus-4-8 | 9 | 0 | 0 | 0 | $0.00 |
| review-performance | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |
| review-privacy | claude-opus-4-8 | 9 | 0 | 0 | 0 | $0.00 |
| review-security | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |
| review-test-quality | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |
| review-usability | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |

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
- [MISSED] `client-missing-pact-field` r0 — seeded=`src/demo/clients/inventory.py`, other_findings=3
  - other: `/tmp/claude-1000/evalprep-2an_0z63/fx-contracts-bad-client-missing-pact-field/tests/functional/test_consumer_inventory.py:22` high — Consumer pact assertion is no longer valid: get_stock() now returns dict[str, int] but test asserts equality with integer 5. The assertion will fail because the function now returns {"in_stock": 5, "reserved_count": ...} instead of 5.
  - other: `/tmp/claude-1000/evalprep-2an_0z63/fx-contracts-bad-client-missing-pact-field/tests/functional/test_consumer_inventory.py:19` high — Pact interaction missing required field: The response body in the pact does not include 'reserved_count', but the client implementation at inventory.py:13 expects and accesses this field. This breaks the contract between consumer expectations and provider response.
  - other: `/tmp/claude-1000/evalprep-2an_0z63/fx-contracts-bad-client-missing-pact-field/src/demo/clients/inventory.py:13` high — Client code accesses 'reserved_count' field that is not declared in the consumer pact. The pact interaction at test_consumer_inventory.py:19 only specifies 'in_stock', making this field access incompatible with the committed contract.
- [MISSED] `client-missing-pact-field` r1 — seeded=`src/demo/clients/inventory.py`, other_findings=1
  - other: `/tmp/claude-1000/evalprep-2an_0z63/fx-contracts-bad-client-missing-pact-field/src/demo/clients/inventory.py:13` high — Weakened consumer contract: the client now requires 'reserved_count' field from the response (line 14), but the consumer pact test does not declare this field in the expected response body. The pact interaction only includes 'item_id' and 'in_stock', not 'reserved_count'. This creates a contract mismatch: if the provider delivers only what the pact specifies, the client code will crash with a KeyError when trying to access data['reserved_count'].
- [caught] `client-missing-pact-field` r2 — seeded=`src/demo/clients/inventory.py`, other_findings=2
  - other: `tests/functional/test_consumer_inventory.py:22` high — Consumer pact test assertion is incompatible with the new get_stock() return type. The test asserts get_stock() == 5 (int), but the function now returns dict[str, int]. This weakens the consumer contract and breaks the contract-testable guarantee.
  - other: `tests/functional/test_consumer_inventory.py:19` high — Pact interaction does not declare reserved_count field that the provider is now expected to return. The client code at src/demo/clients/inventory.py:14 requires reserved_count from the response, but the pact mock only provides item_id and in_stock. The pact interaction must be regenerated to include this field.
- [MISSED] `client-pact-divergence` r0 — seeded=`src/demo/clients/inventory.py`, other_findings=2
  - other: `/tmp/claude-1000/evalprep-2an_0z63/fx-contracts-bad-client-pact-divergence/src/demo/clients/inventory.py:12` high — Client sends query parameter 'include_location=true' that is not defined in the committed consumer pact (test_consumer_inventory.py line 17 specifies .with_request('GET', '/inventory/1') with no query parameters). The published pact must be regenerated to reflect this change.
  - other: `/tmp/claude-1000/evalprep-2an_0z63/fx-contracts-bad-client-pact-divergence/src/demo/clients/inventory.py:18` high — Client attempts to access 'location' field from response (data.get('location')) which is not defined in the committed consumer pact (test_consumer_inventory.py line 19 specifies response body contains only 'item_id' and 'in_stock' fields). The pact must be regenerated to include this field expectation.
- [MISSED] `client-pact-divergence` r1 — seeded=`src/demo/clients/inventory.py`, other_findings=2
  - other: `/tmp/claude-1000/evalprep-2an_0z63/fx-contracts-bad-client-pact-divergence/src/demo/clients/inventory.py:12` high — Client now sends query parameter 'include_location=true' but the committed consumer pact (test_consumer_inventory.py:17) specifies GET /inventory/1 without query parameters. The Pact mock server will not match this request during contract testing.
  - other: `/tmp/claude-1000/evalprep-2an_0z63/fx-contracts-bad-client-pact-divergence/src/demo/clients/inventory.py:18` high — Client now accesses 'location' field from the response, but the committed consumer pact (test_consumer_inventory.py:19) does not include 'location' in the expected response body. The pact must be updated to reflect this new response field before contract testing will pass.
- [caught] `client-pact-divergence` r2 — seeded=`src/demo/clients/inventory.py`, other_findings=0

### review-data-integrity
- [caught] `non-atomic-bulk-insert` r0 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `non-atomic-bulk-insert` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `non-atomic-bulk-insert` r2 — seeded=`src/demo/db/repository.py`, other_findings=0

### review-data-lineage
- [caught] `stale-derived-field` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `stale-derived-field` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `stale-derived-field` r2 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `untransformed-write` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `untransformed-write` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `untransformed-write` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-dependency
- [caught] `unpinned-risky-dep` r0 — seeded=`pyproject.toml`, other_findings=0
- [caught] `unpinned-risky-dep` r1 — seeded=`pyproject.toml`, other_findings=0
- [caught] `unpinned-risky-dep` r2 — seeded=`pyproject.toml`, other_findings=0

### review-documentation
- [caught] `undocumented-public-function` r0 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `README.md:75` low — The README's `## Endpoints` section lists `/heartbeat`, `/health`, `/metrics`, and `/items` but the diff adds a new public endpoint `GET /items/count` without updating the README — the documented endpoint list is now stale.
- [caught] `undocumented-public-function` r1 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `README.md:60` low — The README's `## Endpoints` section enumerates `/items` but the diff adds a new public endpoint `/items/count` without updating it. The user-facing endpoint list is now stale.
- [caught] `undocumented-public-function` r2 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `README.md:70` low — The README's Endpoints section lists `/items` but does not mention the new `GET /items/count` endpoint, leaving the user-facing API documentation stale relative to this diff.

### review-observability
- [caught] `uninstrumented-route` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `uninstrumented-route` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `uninstrumented-route` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-observability-db
- [caught] `unindexed-unobserved-query` r0 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `unindexed-unobserved-query` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `unindexed-unobserved-query` r2 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `write-path-no-metric` r0 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `write-path-no-metric` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `write-path-no-metric` r2 — seeded=`src/demo/db/repository.py`, other_findings=0

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
- [caught] `pii-logged` r0 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `src/demo/db/models.py:17` high — Collection of owner_email PII without clear retention purpose. The field is collected but the primary usage (logging on line 47 of items.py) violates the stated PII protection policy. The necessity of collecting and storing owner_email is not evident from the current codebase structure.
- [caught] `pii-logged` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-logged` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

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
### review-contracts
- `client-pact-covered` r2 → 1 findings:
  - `tests/functional/test_consumer_inventory.py:24` info — Consumer pact generated by pact.write_file(Path("pacts")) is not committed to the repository; the demo-inventory pact is ephemeral and not available for provider verification. The provider test only verifies against pacts/examplewebapp-app.json, leaving this contract unverified.

### review-data-integrity
- `atomic-bulk-insert` r0 → 1 findings:
  - `src/demo/db/repository.py:28` high — The bulk_create_items function body is truncated/incomplete — the diff ends with `for item in created:` with no loop body. As written this is a SyntaxError and the function cannot execute. If the intent was to call `session.refresh(item)` (mirroring create_item), the returned Items will otherwise be missing server-populated fields (id, created_at) after commit when expire_on_commit=False.

### review-data-lineage
- `normalized-write` r1 → 2 findings:
  - `/tmp/claude-1000/evalprep-2an_0z63/fx-data-lineage-good-normalized-write/src/demo/db/seed.py:19` medium — Seed data bypasses create_item_normalized() normalization when creating Item records. Seeds inject raw names directly without stripping/lowercasing, creating inconsistent data provenance across writes.
  - `/tmp/claude-1000/evalprep-2an_0z63/fx-data-lineage-good-normalized-write/tests/functional/test_items_route.py:12` low — Test setup uses create_item() without normalization when testing the GET endpoint, creating test data inconsistent with POST endpoint behavior which uses create_item_normalized().

### review-dependency
- `pinned-reputable-dep` r0 → 1 findings:
  - `pyproject.toml:18` info — Adding httpx>=0.27,<1.0 as a production dependency is justified: httpx is a reputable, actively maintained async-capable HTTP client (Encode, the FastAPI/Starlette maintainers), aligns with the FastAPI/Pydantic stack already in use, and is correctly constrained with a sane upper bound to guard against a future 1.0 breaking change. Note: httpx is also listed in the dev group (>=0.28) where FastAPI's TestClient pulls it in transitively; promoting it to production is appropriate now that it's used at runtime, but consider aligning the floors (dev >=0.28 vs prod >=0.27) so dev and prod resolve to the same major/minor band.

### review-documentation
- `documented-public-function` r0 → 2 findings:
  - `README.md:64` low — New public endpoint GET /items/count is added but the README's 'Endpoints' section is not updated to list it, leaving user-facing docs incomplete.
  - `src/demo/routes/items.py:32` low — The new route changes the API surface; per README, `openapi.json` must be regenerated after route changes (CI fails on a stale spec). The diff does not include a regenerated `openapi.json`, which will likely render the committed API spec stale.
- `documented-public-function` r2 → 2 findings:
  - `src/demo/routes/items.py:32` low — New public endpoint GET /items/count is added but the README's 'Endpoints' section (which explicitly enumerates /heartbeat, /health, /metrics, /items) is not updated to list it. The endpoint catalogue in README.md will be stale once this lands.
  - `src/demo/routes/items.py:33` info — The route uses an untyped `dict` return annotation rather than a Pydantic response model. The README notes `task openapi:export` must be re-run after route changes and CI fails on a stale or breaking spec; a bare `dict` produces a weaker OpenAPI schema (no documented `count` field/type) than the `response_model=...` pattern used by `get_items` (ItemRead).

### review-observability-infra
- `complete-obs-surface` r0 → 1 findings:
  - `infra/compose/observability.yml:100` high — redis-exporter service depends on undefined 'redis' service. The service reference 'redis' in depends_on and REDIS_ADDR environment variable has no corresponding service definition in any compose file (dev.yml, staging.yml, prod.yml, services.yml, or base.yml).
- `complete-obs-surface` r1 → 1 findings:
  - `infra/observability/prometheus/alerts/postgres_alerts.yml:11` info — Redis alert rule is defined in 'postgres_alerts.yml' which is named after a different service. While the wildcard loading in prometheus.yml will find this, consider moving the redis alert rule to a dedicated 'redis_alerts.yml' file for clarity and maintainability.
- `complete-obs-surface` r2 → 1 findings:
  - `infra/compose/observability.yml:100` high — redis-exporter depends on 'redis' service which is not defined in any compose file (base.yml, dev.yml, services.yml, prod.yml, staging.yml, test.yml). The scrape target 'redis://redis:6379' will fail to connect at runtime.

### review-privacy
- `pii-excluded` r0 → 1 findings:
  - `src/demo/routes/items.py:44` medium — ItemCreate schema accepts owner_email but post_item endpoint discards it: create_item() is called with only payload.name, not payload.owner_email. This creates a silent data loss pattern where clients submit PII that is never persisted.
- `pii-excluded` r1 → 1 findings:
  - `src/demo/routes/items.py:43` medium — Post endpoint accepts owner_email in ItemCreate schema but does not store it - unnecessary PII collection violates data minimization principle
- `pii-excluded` r2 → 1 findings:
  - `src/demo/routes/items.py:45` medium — Docstring claims 'owner_email stored' but the actual implementation at line 46 calls create_item(session, payload.name) without passing owner_email, so it is not stored. This is a documentation-code mismatch.

## Agentic behavior
### review-api-design
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-architecture
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-contracts
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-data-lineage
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-observability-db
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-observability-infra
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-privacy
- Calls: 9, avg turns: 1.0, max-cap hits: 0

## Drift check
_(no drift detected — all tool calls within the production sandbox)_

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
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
compliance:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
contracts:
  recall_min: 0.23  # observed 0.33
  fp_max: 0.10  # observed 0.00
data-integrity:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.43  # observed 0.33
data-lineage:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
dependency:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.43  # observed 0.33
documentation:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.77  # observed 0.67
observability:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability-db:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability-infra:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.77  # observed 0.67
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
