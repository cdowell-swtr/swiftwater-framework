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
| review-contracts | 0.67 | 0.00 | PASS |
| review-data-integrity | 1.00 | 0.00 | PASS |
| review-data-lineage | 1.00 | 0.00 | PASS |
| review-dependency | 1.00 | 0.00 | PASS |
| review-documentation | 1.00 | 0.00 | PASS |
| review-observability | 1.00 | 0.00 | PASS |
| review-observability-db | 1.00 | 0.00 | PASS |
| review-observability-infra | 1.00 | 0.33 | PASS |
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
- [caught] `client-missing-pact-field` r0 — seeded=`src/demo/clients/inventory.py`, other_findings=0
- [caught] `client-missing-pact-field` r1 — seeded=`src/demo/clients/inventory.py`, other_findings=0
- [caught] `client-missing-pact-field` r2 — seeded=`src/demo/clients/inventory.py`, other_findings=0
- [caught] `client-pact-divergence` r0 — seeded=`src/demo/clients/inventory.py`, other_findings=0
- [caught] `client-pact-divergence` r1 — seeded=`src/demo/clients/inventory.py`, other_findings=0
- [caught] `client-pact-divergence` r2 — seeded=`src/demo/clients/inventory.py`, other_findings=1
  - other: `tests/functional/test_consumer_inventory.py:17` info — Pact test expects request to '/inventory/1' with no query parameters, but the client code (src/demo/clients/inventory.py) now sends 'include_location=true'. The pact contract and test are out of sync.

### review-data-integrity
- [caught] `non-atomic-bulk-insert` r0 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `non-atomic-bulk-insert` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `non-atomic-bulk-insert` r2 — seeded=`src/demo/db/repository.py`, other_findings=0

### review-data-lineage
- [caught] `stale-derived-field` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `stale-derived-field` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `stale-derived-field` r2 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `untransformed-write` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `untransformed-write` r1 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `src/demo/db/repository.py:12` medium — Documentation in create_item() docstring warns against direct use with user input, but the function remains public and is called unsafely from routes/items.py post_item() endpoint. The documented safety mechanism (create_item_normalized) is defined but not enforced at the call site.
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
### review-data-lineage
- `normalized-write` r0 → 1 findings:
  - `src/demo/db/repository.py:11` medium — The create_item() function can still be called directly, bypassing the normalization enforced by create_item_normalized(). While a docstring warning exists, Python does not prevent internal code paths or tests from using the raw function, potentially storing un-normalized names and breaking consistency guarantees.
- `normalized-write` r2 → 2 findings:
  - `src/demo/db/repository.py:27` medium — Data normalization (strip/lowercase) in create_item_normalized() performs lossy transformation on user input without recording original value. If the original user-supplied data is ever needed for audit, support, or GDPR requests, it will be unrecoverable.
  - `src/demo/db/repository.py:11` medium — create_item() accepts raw user input without validation or normalization. Although docstring recommends using create_item_normalized() for user-supplied input, there is no enforcement mechanism to prevent misuse (e.g., no private marker or runtime check). Other code paths could inadvertently use the unvalidated function.

### review-observability-infra
- `complete-obs-surface` r1 → 1 findings:
  - `infra/observability/prometheus/prometheus.yml:21` medium — New scrape job 'redis' added with no corresponding alert rule in infra/observability/prometheus/alerts/
- `complete-obs-surface` r2 → 1 findings:
  - `infra/observability/prometheus/prometheus.yml:21` high — New scrape job 'redis' added with no corresponding alert rule file. Prometheus scrape jobs should have matching alert rules defined.

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
  fp_max: 0.43  # observed 0.33
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
