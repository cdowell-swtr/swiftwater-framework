# Eval scorecard

## Summary
- Agents: 18
- Calls: 132 (bad: 75, good: 57)
- Total cost (est., USD): $0.00

## Scorecard
| Agent | Recall | FP | Status |
|---|---|---|---|
| review-accessibility | 1.00 | 0.00 | PASS |
| review-api-design | 1.00 | 0.00 | PASS |
| review-application-logic | 1.00 | 0.00 | PASS |
| review-architecture | 1.00 | 0.00 | PASS |
| review-compliance | 1.00 | 0.00 | PASS |
| review-contracts | 0.67 | 0.00 | PASS |
| review-data-integrity | 1.00 | 0.00 | PASS |
| review-data-lineage | 1.00 | 0.00 | PASS |
| review-dependency | 1.00 | 0.00 | PASS |
| review-documentation | 1.00 | 0.00 | PASS |
| review-observability | 1.00 | 0.00 | PASS |
| review-observability-db | 1.00 | 0.00 | PASS |
| review-observability-infra | 1.00 | 1.00 | FAIL (fp 1.00 > 0.34) |
| review-performance | 1.00 | 0.00 | PASS |
| review-privacy | 1.00 | 1.00 | FAIL (fp 1.00 > 0.10) |
| review-security | 1.00 | 0.00 | PASS |
| review-test-quality | 1.00 | 0.00 | PASS |
| review-usability | 1.00 | 0.33 | FAIL (fp 0.33 > 0.10) |

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
- [caught] `client-missing-pact-field` r0 — seeded=`src/demo/clients/inventory.py`, other_findings=1
  - other: `tests/functional/test_consumer_inventory.py:22` high — Consumer test assertion broken by incompatible change: the test asserts `get_stock(...) == 5` (returns int), but the implementation (src/demo/clients/inventory.py:14) now returns a dict. This assertion will fail at runtime, indicating a weakened consumer contract.
- [MISSED] `client-missing-pact-field` r1 — seeded=`src/demo/clients/inventory.py`, other_findings=2
  - other: `tests/functional/test_consumer_inventory.py:19` high — Pact contract missing required field: 'reserved_count' field is accessed by the client (src/demo/clients/inventory.py:14) but not declared in the pact interaction. The response body must include 'reserved_count' with a matching rule, and the assertion on line 22 must be updated to match the new dict return type.
  - other: `tests/functional/test_consumer_inventory.py:22` high — Consumer assertion no longer matches function return type: get_stock() now returns dict[str, int] but the assertion expects int. This will cause the test to fail and the pact not to be regenerated, leaving the contract broken.
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
- [caught] `untransformed-write` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `untransformed-write` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `untransformed-write` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

### review-dependency
- [caught] `unpinned-risky-dep` r0 — seeded=`pyproject.toml`, other_findings=0
- [caught] `unpinned-risky-dep` r1 — seeded=`pyproject.toml`, other_findings=0
- [caught] `unpinned-risky-dep` r2 — seeded=`pyproject.toml`, other_findings=0

### review-documentation
- [caught] `undocumented-public-function` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `undocumented-public-function` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `undocumented-public-function` r2 — seeded=`src/demo/routes/items.py`, other_findings=0

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
- [caught] `exporter-without-scrape` r0 — seeded=`infra/compose/observability.yml`, other_findings=1
  - other: `infra/observability/prometheus/prometheus.yml:24` high — No scrape job defined for redis-exporter service. The redis-exporter was added to observability.yml but no corresponding scrape configuration exists in prometheus.yml to collect its metrics.
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
### review-observability-infra
- `complete-obs-surface` r0 → 1 findings:
  - `infra/observability/prometheus/prometheus.yml:21` high — New Prometheus scrape job 'redis' has no corresponding alert rules file. Dashboard exists (redis.json) but no alerts defined for redis-exporter metrics.
- `complete-obs-surface` r1 → 1 findings:
  - `infra/compose/observability.yml:94` high — redis-exporter service is defined in observability.yml (merged into all environments) but Redis service only exists in dev.yml (dev/lite profiles). In staging/prod environments, redis-exporter will fail to start due to missing service_healthy dependency.
- `complete-obs-surface` r2 → 1 findings:
  - `infra/compose/observability.yml:94` high — redis-exporter service added with hard dependency on redis:6379, but redis service is only defined in dev.yml (profiles: ["dev", "lite"]). When observability.yml is merged into staging/prod via deploy strategy, redis-exporter will fail to start because redis service does not exist in those environments.

### review-privacy
- `pii-excluded` r0 → 1 findings:
  - `src/demo/routes/items.py:45` high — Misleading docstring: states 'owner_email stored but not returned or logged', but implementation does not store owner_email (not passed to create_item). This docstring-code mismatch could lead developers to incorrectly assume PII retention.
- `pii-excluded` r1 → 2 findings:
  - `migrations/versions/0001_initial.py:20` critical — Database migration is missing the owner_email column. The ORM model in src/demo/db/models.py adds owner_email (line 17), but the Alembic migration does not include this column in the create_table statement. This will cause runtime errors when the application tries to access or store owner_email.
  - `src/demo/routes/items.py:46` medium — The post_item function receives owner_email in the ItemCreate payload but does not pass it to create_item(). The repository function signature create_item(session, name) does not accept owner_email as a parameter, so any owner_email provided by the client is silently discarded.
- `pii-excluded` r2 → 1 findings:
  - `src/demo/routes/items.py:46` high — post_item function docstring claims 'owner_email stored' but the implementation discards the owner_email from payload. The create_item(session, payload.name) call does not pass payload.owner_email, so user-provided PII is silently dropped.

### review-usability
- `delete-with-confirm` r1 → 1 findings:
  - `frontend/src/Items.tsx:34` info — DeleteButton has no error feedback: if the DELETE fetch rejects or returns a non-2xx response, the catch path is absent and onDeleted() still won't be called, leaving the user with no signal that the action failed. Consider surfacing an error state (e.g., a message or toast) when the request fails.

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
  fp_max: 0.10  # observed 0.00
contracts:
  recall_min: 0.57  # observed 0.67
  fp_max: 0.10  # observed 0.00
data-integrity:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
data-lineage:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
dependency:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
documentation:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability-db:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability-infra:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
performance:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
privacy:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
security:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
test-quality:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
usability:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.43  # observed 0.33
```
