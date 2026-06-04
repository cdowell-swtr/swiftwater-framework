# Eval scorecard

## Summary
- Agents: 20
- Calls: 159 (bad: 96, good: 63)
- Total cost (est., USD): $0.00

## Scorecard
| Agent | Recall | FP | Status |
|---|---|---|---|
| review-accessibility | 1.00 | 0.00 | PASS |
| review-api-design | 0.83 | 0.00 | PASS |
| review-application-logic | 1.00 | 0.00 | PASS |
| review-architecture | 1.00 | 0.00 | PASS |
| review-compliance | 1.00 | 0.00 | PASS |
| review-contracts | 1.00 | 0.00 | PASS |
| review-data-integrity | 1.00 | 0.00 | PASS |
| review-data-lineage | 0.83 | 0.00 | FAIL (recall 0.83 < 0.90) |
| review-dependency | 1.00 | 1.00 | FAIL (fp 1.00 > 0.43) |
| review-documentation | 1.00 | 1.00 | FAIL (fp 1.00 > 0.10) |
| review-env-parity | 1.00 | 0.00 | PASS |
| review-observability | 1.00 | 0.00 | PASS |
| review-observability-db | 0.83 | 0.00 | FAIL (recall 0.83 < 0.90) |
| review-observability-fe | 1.00 | 0.00 | PASS |
| review-observability-infra | 1.00 | 0.00 | PASS |
| review-performance | 1.00 | 1.00 | FAIL (fp 1.00 > 0.10) |
| review-privacy | 1.00 | 0.00 | PASS |
| review-security | 1.00 | 0.00 | PASS |
| review-test-quality | 1.00 | 0.33 | FAIL (fp 0.33 > 0.10) |
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
| review-env-parity | claude-opus-4-8 | 12 | 0 | 0 | 0 | $0.00 |
| review-observability | claude-sonnet-4-6 | 9 | 0 | 0 | 0 | $0.00 |
| review-observability-db | claude-opus-4-8 | 9 | 0 | 0 | 0 | $0.00 |
| review-observability-fe | claude-opus-4-8 | 12 | 0 | 0 | 0 | $0.00 |
| review-observability-infra | claude-opus-4-8 | 9 | 0 | 0 | 0 | $0.00 |
| review-performance | claude-sonnet-4-6 | 6 | 0 | 0 | 0 | $0.00 |
| review-privacy | claude-opus-4-8 | 12 | 0 | 0 | 0 | $0.00 |
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
  - other: `README.md:96` info — The Endpoints section lists GET /items but does not mention the newly added GET /items/count endpoint. The API spec (README + openapi.json) is now stale.
- [caught] `undocumented-public-function` r1 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `README.md:97` info — The README's 'Endpoints' section lists `GET /items` but does not mention the new `GET /items/count` route added in this diff. The API spec is now stale.
- [caught] `undocumented-public-function` r2 — seeded=`src/demo/routes/items.py`, other_findings=1
  - other: `README.md:96` info — The `## Endpoints` section documents `GET /items` but the newly added `GET /items/count` endpoint is not listed, leaving the README stale.

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
- [caught] `unindexed-unobserved-query` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `unindexed-unobserved-query` r2 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `write-path-no-metric` r0 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `write-path-no-metric` r1 — seeded=`src/demo/db/repository.py`, other_findings=0
- [caught] `write-path-no-metric` r2 — seeded=`src/demo/db/repository.py`, other_findings=0

### review-observability-fe
- [caught] `swallowed-error` r0 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `swallowed-error` r1 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `swallowed-error` r2 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `unbounded-label` r0 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [caught] `unbounded-label` r1 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [caught] `unbounded-label` r2 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [caught] `uninstrumented-view` r0 — seeded=`frontend/src/Dashboard.tsx`, other_findings=0
- [caught] `uninstrumented-view` r1 — seeded=`frontend/src/Dashboard.tsx`, other_findings=0
- [caught] `uninstrumented-view` r2 — seeded=`frontend/src/Dashboard.tsx`, other_findings=0

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
### review-dependency
- `pinned-reputable-dep` r0 → 2 findings:
  - `pyproject.toml:19` info — httpx is a reputable, actively maintained HTTP client (Encode/Tom Christie) with good supply-chain hygiene; the upper bound <1.0 is appropriate to guard against breaking changes in the upcoming stable release.
  - `pyproject.toml:19` low — httpx already appears in [dependency-groups].dev at >=0.28, but the new production constraint allows >=0.27. In practice uv/pip will resolve the intersection, but the floor mismatch could cause confusion — consider aligning the production floor to >=0.28 to match dev.
- `pinned-reputable-dep` r1 → 2 findings:
  - `pyproject.toml:19` info — httpx is a reputable, actively maintained HTTP client (encode/httpx). The upper bound <1.0 is good practice to guard against breaking changes at the v1 boundary. No supply-chain concerns.
  - `pyproject.toml:19` low — Version floor mismatch: runtime dep allows httpx>=0.27 but the dev dependency-group pins httpx>=0.28. Tests always run against 0.28+, so a production install of 0.27 could expose untested behaviour differences between those minor releases.
- `pinned-reputable-dep` r2 → 2 findings:
  - `pyproject.toml:19` info — httpx added to production dependencies with a lower bound of >=0.27, but the dev group already pins >=0.28. The prod lower bound could allow an older version in production than in development, creating a subtle environment divergence.
  - `pyproject.toml:19` info — httpx is a reputable, well-maintained library (Encode/encode) with no known supply-chain concerns. The <1.0 upper cap is a reasonable guard against a future breaking major release. No existing production dependency covers async HTTP client use, so the addition appears justified.

### review-documentation
- `documented-public-function` r0 → 2 findings:
  - `src/demo/routes/items.py:52` info — count_items calls list_items(session) without a limit, performing a full table scan to count rows. The docstring does not mention this behavior or its scalability implication. Consider noting the scan cost, especially since list_items defaults to MAX_PAGE_SIZE=100 via DEFAULT_PAGE_SIZE — here called with no limit arg so it uses the default, meaning the count will be capped at 100, not the true total.
  - `README.md:78` info — A new route was added but the diff does not include an updated openapi.json. The README and CI configuration both require running `task openapi:export` and committing the updated spec after any route change — CI fails on a stale spec.
- `documented-public-function` r1 → 1 findings:
  - `src/demo/routes/items.py:49` low — The `count_items` docstring claims to return 'the total number of items in the catalogue', but the implementation calls `list_items(session)` with no explicit limit, which defaults to `DEFAULT_PAGE_SIZE=50` and is capped at `MAX_PAGE_SIZE=100`. For catalogues with more than 50 items, the returned count will be silently incorrect.
- `documented-public-function` r2 → 1 findings:
  - `src/demo/routes/items.py:50` low — The docstring says 'total number of items in the catalogue' but `list_items(session)` is called without a `limit` argument, so it uses `DEFAULT_PAGE_SIZE=50` — the count is capped at 50, not the true total. The docstring should document this limitation or the implementation should use a direct `COUNT(*)` query.

### review-performance
- `single-query` r0 → 1 findings:
  - `src/demo/routes/items.py:43` high — Unbounded query: `select(Item.name)` has no LIMIT, so it scans and materializes every row in the `items` table. The existing `get_items` endpoint deliberately caps reads at MAX_PAGE_SIZE=100 via `list_items()`; this endpoint bypasses that guard entirely. As the table grows the response time and memory allocation grow without bound, violating the bounded-read SLO established by the repository layer.
- `single-query` r1 → 1 findings:
  - `src/demo/routes/items.py:43` high — Unbounded query: `select(Item.name)` fetches every row with no LIMIT. The existing `get_items` endpoint clamps results to MAX_PAGE_SIZE (100) via `list_items()`, but this new endpoint bypasses that guard entirely. On a large `items` table this returns an arbitrarily large payload in one request, causing memory pressure, slow DB scans, and potential connection-pool starvation.
- `single-query` r2 → 1 findings:
  - `src/demo/routes/items.py:43` high — Unbounded query: `select(Item.name)` has no LIMIT, so it will load every name in the table into memory and return it all in a single response. The existing `get_items` endpoint caps reads at MAX_PAGE_SIZE=100; this endpoint removes that guard entirely. As the table grows this becomes an OOM and DB-load risk.

### review-security
- `env-sourced-secret` r1 → 1 findings:
  - `src/demo/config/settings.py:36` medium — api_secret_key is typed as plain str rather than pydantic.SecretStr. This means the secret value will appear in plaintext in Settings.__repr__, model_dump(), and any log line that serialises the settings object, which can leak the key to logs or error traces.
- `env-sourced-secret` r2 → 1 findings:
  - `src/demo/config/settings.py:36` medium — api_secret_key is typed as plain str rather than pydantic's SecretStr. A plain str will be revealed in repr(), str(), logs, and any serialization of the Settings object (e.g., debug endpoints, error traces, Sentry breadcrumbs), making accidental secret exposure easy.

### review-test-quality
- `meaningful-assert` r0 → 2 findings:
  - `tests/unit/test_settings.py:48` low — test_slo_request_latency_default_is_reasonable uses a wide range assertion (100–5000) that is strictly weaker than the exact assertion in test_defaults (slo_request_latency_p99_ms == 200.0). The new test adds no safety the existing test does not already provide and could mask a regression if the default drifts to an extreme-but-in-range value.
  - `tests/unit/test_settings.py:57` medium — test_resolved_log_level_production_is_not_debug calls Settings(environment='production') but the canonical production environment string in this codebase is 'prod' (used in test_resolved_log_level_is_info_outside_dev and test_explicit_log_level_overrides_resolution). 'production' is an unrecognised/non-canonical value; because resolved_log_level returns INFO for any string that is not 'dev', the assertion passes trivially on any unknown string. The test provides false confidence: it does not cover the actual production environment.
- `meaningful-assert` r1 → 2 findings:
  - `tests/unit/test_settings.py:57` high — test_resolved_log_level_production_is_not_debug uses environment="production" which is not a recognised environment value (the codebase uses "prod"). Since resolved_log_level returns "INFO" for any environment string that is not "dev", passing any unrecognised string such as "production" trivially satisfies != "DEBUG" — the test cannot fail even if the logic regresses. The guard it purports to add is already provided by the existing parametrise covering "prod".
  - `tests/unit/test_settings.py:48` low — test_slo_request_latency_default_is_reasonable asserts a wide range (100 <= x <= 5000) that overlaps almost entirely with the exact value already pinned in test_defaults (200.0). The range is so wide it would pass even for values that likely violate the intended SLO contract, making it a weak guard. It adds no regression protection beyond what test_defaults already provides.
- `meaningful-assert` r2 → 1 findings:
  - `tests/unit/test_settings.py:59` medium — Weak negative assertion: `assert s.resolved_log_level != "DEBUG"` does not pin the expected value. If `resolved_log_level` returns an unexpected value (e.g. `"WARNING"`, `None`, or empty string) the test still passes, hiding a regression. Additionally, `environment="production"` is not a canonical env in this codebase (the parametrized test uses `"prod"`), so this test exercises an untested alias that happens to return `"INFO"` only because it is not `"dev"`.

## Agentic behavior
### review-api-design
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-architecture
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-contracts
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-data-lineage
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-env-parity
- Calls: 12, avg turns: 1.0, max-cap hits: 0

### review-observability-db
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-observability-fe
- Calls: 12, avg turns: 1.0, max-cap hits: 0

### review-observability-infra
- Calls: 9, avg turns: 1.0, max-cap hits: 0

### review-privacy
- Calls: 12, avg turns: 1.0, max-cap hits: 0

## Drift check
_(no drift detected — all tool calls within the production sandbox)_

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
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
compliance:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
contracts:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
data-integrity:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
data-lineage:
  recall_min: 0.73  # observed 0.83
  fp_max: 0.10  # observed 0.00
dependency:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
documentation:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
env-parity:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability-db:
  recall_min: 0.73  # observed 0.83
  fp_max: 0.10  # observed 0.00
observability-fe:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
observability-infra:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
performance:
  recall_min: 0.90  # observed 1.00
  fp_max: 1.00  # observed 1.00
privacy:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
security:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
test-quality:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.43  # observed 0.33
usability:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
```
