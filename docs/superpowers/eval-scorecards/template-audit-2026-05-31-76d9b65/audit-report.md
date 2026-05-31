# Audit report

## Cost (subagent-dispatched, ~$0)

| Agent | Calls | In tok | Out tok |
|---|---|---|---|
| review-accessibility | 1 | 0 | 0 |
| review-api-design | 1 | 0 | 0 |
| review-application-logic | 1 | 0 | 0 |
| review-architecture | 1 | 0 | 0 |
| review-compliance | 1 | 0 | 0 |
| review-contracts | 1 | 0 | 0 |
| review-data-integrity | 1 | 0 | 0 |
| review-data-lineage | 1 | 0 | 0 |
| review-dependency | 1 | 0 | 0 |
| review-documentation | 1 | 0 | 0 |
| review-observability | 1 | 0 | 0 |
| review-observability-db | 1 | 0 | 0 |
| review-observability-infra | 1 | 0 | 0 |
| review-performance | 1 | 0 | 0 |
| review-privacy | 1 | 0 | 0 |
| review-security | 1 | 0 | 0 |
| review-test-quality | 1 | 0 | 0 |
| review-usability | 1 | 0 | 0 |

## Findings
### review-accessibility
_(no findings)_

### review-api-design
- `src/demo/graphql/schema.py:29` **high** — Unbounded list field: 'items' returns a list[Item] with no pagination (limit/offset, first/after, or cursor-based). As the items table grows, this query could return unbounded results, causing performance and memory issues.

### review-application-logic
- `src/demo/routes/websockets.py:17` **medium** — The receive loop only handles WebSocketDisconnect. Any other exception raised by ws.receive_text() or _manager.broadcast() (e.g. a peer that errors out, a serialization/encode failure, or broadcast to a half-open socket) escapes the try block WITHOUT calling _manager.disconnect(ws), leaving a stale/dead connection registered in the ConnectionManager. Subsequent broadcasts then target a dead socket and the connection is never reaped.
- `src/demo/routes/health.py:41` **low** — The workers/mongo/redis liveness probes each swallow `except Exception` to report `{"alive": False}` but emit NO log, unlike the /metrics DLQ path which logs `dlq_metrics_unavailable`. A dependency that flips to degraded leaves no trace of WHY (connection refused vs auth vs timeout), so operators see 'alive: false' in the report with nothing to diagnose against.

### review-architecture
_(no findings)_

### review-compliance
- `src/demo/routes/webhooks.py:36` **medium** — Inbound webhook processing (handle_event) is a sensitive, externally-triggered state-mutating operation, but it produces no audit log. Outcomes are recorded only as aggregate metric counters (rejected_signature/malformed/duplicate/accepted), which cannot reconstruct which event was processed, when, or under which correlation id. For compliance/audit purposes, externally-triggered mutations should leave a per-event audit record.
- `src/demo/routes/webhooks.py:33` **medium** — The webhook inbox persists a row per inbound event (record(session, key)) with no visible retention or pruning path. Inbound webhook bodies can carry personal data and the dedup/inbox table grows unbounded; there is no documented deletion or retention policy, which is a GDPR retention/storage-limitation gap.
- `src/demo/routes/items.py:27` **low** — Items are persisted (id, name) and only a list endpoint is exposed; there is no deletion / right-to-erasure path. If the 'name' field is ever used to store personal data, this store offers no mechanism to satisfy a deletion request. Demo data here is generic, so this is advisory rather than a clear violation.

### review-contracts
- `pacts/examplewebapp-app.json:19` **high** — Incompatible response shape: pact expects response body wrapped in {"content": [...]}, but provider endpoint GET /items returns list[ItemRead] which serializes directly to [...]. This is an uncompensated breaking change in response structure that will cause verification to fail.
- `pacts/examplewebapp-app.json:20` **high** — Incomplete response expectation: pact only includes one item (id=1, name="alpha") in the response body, but the provider test seeds two items ("alpha" and "beta" at lines 37-38 of test_provider_pact.py). The actual /items endpoint will return both items, causing pact verification to fail due to response mismatch.
- `tests/contract/test_provider_pact.py:11` **info** — Pact not regenerated after provider change: the committed pact (pacts/examplewebapp-app.json) does not match the current provider implementation. The provider's response shape and content differ from what the pact specifies, indicating the consumer-side pact generation needs to be re-run and published.

### review-data-integrity
- `migrations/versions/0004_embeddings.py:25` **high** — embeddings.item_id is a FK to items.id with no ON DELETE behavior. With the default (RESTRICT/NO ACTION), deleting an item with embeddings will fail; if app code expects cleanup it silently leaves orphaned embedding rows. There is also no index on item_id, so the referential-integrity check and any item->embeddings lookup do a full scan.
- `migrations/versions/0005_readings.py:26` **high** — readings.item_id is a FK to items.id with no ON DELETE behavior. Deleting an item with readings will error under the default RESTRICT, and there is no separate index on item_id (the PK is (item_id, time), so the composite PK index covers item_id-prefixed lookups, but the missing ondelete still leaves the deletion/cascade semantics undefined for time-series child rows).
- `src/demo/db/repository.py:11` **high** — create_item accepts any name string and writes it directly; the column is nullable=False but does not reject empty/whitespace-only names, so '' is a valid persisted Item.name. There is no length guard either, so a name longer than the column's String(255) will raise an opaque DB error rather than a validated rejection.
- `src/demo/db/seed.py:18` **high** — seed() reads each row['name'] directly from the JSON file; a malformed seed row (missing 'name', null, or non-string) raises KeyError/TypeError mid-loop AFTER prior rows were added to the session. Because the commit is at the end, the failure aborts the whole transaction, but the error surfaced is an opaque KeyError rather than a clear data-validation message, and a name set to null/empty would be persisted as an invalid Item.

### review-data-lineage
- `src/demo/webhooks/handler.py:21` **high** — Webhook event payload passed to process_async.delay() may contain PII or sensitive user data. If task fails after retries, the full event payload is serialized and stored in dead_letter_tasks.args_json as plain text, creating an undocumented PII storage location.
- `src/demo/tasks/dead_letter.py:23` **high** — Dead-letter queue stores full task arguments (args_json) in plain text with no retention policy, TTL, or cleanup mechanism. PII from failed webhook events will persist indefinitely in the database, violating data minimization and erasure requirements.
- `src/demo/tasks/base.py:46` **high** — Task failure handler unconditionally serializes all task arguments to JSON and stores them in the dead-letter queue. No filtering or redaction is performed, so sensitive webhook payloads (potentially containing customer email, phone, payment info) are persisted unencrypted.
- `src/demo/routes/health.py:82` **medium** — Dead-letter queue metrics are exposed via the public /metrics endpoint (render_dlq_metrics). While the DLQ depth gauge itself is benign, the DLQ table remains queryable by anyone with direct DB access, and no audit trail tracks who accessed PII stored in args_json.
- `src/demo/webhooks/handler.py:15` **medium** — No documentation or contract specifying which fields in the webhook event payload are safe to log/store. Downstream consumers of process_async cannot distinguish between PII and non-sensitive fields, leading to accidental exposure in error handlers, logs, or serialization.

### review-dependency
- `pyproject.toml:20` **low** — `httpx>=0.28` is declared in both the runtime `dependencies` array and the `dev` dependency-group with the identical constraint. The dev-group entry is redundant — runtime deps are always installed in the dev environment too. httpx is genuinely used at runtime (src/demo/clients/inventory.py), so the runtime declaration is the correct one; the dev-group copy just creates two places to keep the version bound in sync.
- `pyproject.toml:9` **info** — `psycopg[binary]>=3.2`: the `[binary]` extra ships psycopg's prebuilt C wheels, which the psycopg maintainers explicitly recommend only for development/quick-start and advise against for production (the bundled libpq is not the system one and isn't security-patched with the OS). Justified as a default for a scaffold, but worth flagging that production builds typically pin `psycopg[c]` (compiled against the system libpq) or the pure-Python build.
- `pyproject.toml:19` **info** — `redis>=5` is a direct runtime dependency while `celery[redis]>=5.4` (line 17) also pulls redis transitively. The direct declaration is justified — redis is used directly (src/demo/cache/client.py, repository.py, routes/health.py), so it should not rely on celery's transitive pin. The note is coordination/supply-chain: two declared paths to the same package mean the resolver must keep them compatible, and `redis>=5` is a bare-major lower bound that is looser than every other pin here (which carry a minor, e.g. `>=5.4`, `>=0.28`).

### review-documentation
- `README.md:80` **low** — The README "Endpoints" section lists only /heartbeat, /health, /metrics, and /items, but the rendered project also exposes POST /webhooks (routes/webhooks.py), the /ws WebSocket (routes/websockets.py), and the /graphql endpoint + GraphiQL IDE (routes/graphql.py). These public HTTP/WS surfaces are undocumented here, so the endpoint list is effectively a stale API spec for a full-battery project.
- `src/demo/cache/repository.py:125` **info** — The public cache helpers cache_set/cache_get/cache_delete have no docstrings, unlike the other repository modules (db, mongo, vectors, timeseries, graph) whose public functions document behavior. The TTL semantics (ttl_seconds=None meaning no expiry) and that these operate on the dedicated cache DB (cache/client.py _CACHE_DB=3) are left implicit.
- `src/demo/config/settings.py:201` **info** — graphql_ide_enabled (and mongo_url, redis_url, celery_broker_url, celery_result_backend, webhook_signing_secret, inventory_url) are app config knobs sourced via the APP_ env prefix, but the README does not document them and there is no visible .env.example in the bundled context to confirm they are advertised to project builders. New config vars introduced by batteries should be surfaced so a builder knows they exist and what they default to.
- `src/demo/observability/metrics.py:882` **info** — The module docstring still references "Plan 3a"/"Plan 3b" as the rationale for the unbounded _latencies_ms list and for /metrics scraping. These internal plan references are framework-development artifacts that carry no meaning in a generated project and read as stale context to a downstream builder.

### review-observability-db
- `src/demo/db/repository.py:8` **high** — Query path `list_items()` reads from database with no metric or span around it
- `src/demo/db/repository.py:11` **high** — Write path `create_item()` persists to database with no metric or span around it
- `src/demo/vectors/repository.py:10` **high** — Write path `add_embedding()` persists embedding to database with no metric or span
- `src/demo/vectors/repository.py:19` **high** — Query path `nearest()` executes cosine distance search with no latency metric or span
- `src/demo/mongo/repository.py:10` **high** — MongoDB write path `insert_document()` has no correlation ID in error logs
- `src/demo/mongo/repository.py:14` **high** — MongoDB query path `find_documents()` has no correlation ID in error logs
- `src/demo/mongo/client.py:12` **high** — MongoDB client `get_client()` returns MongoClient with no health check endpoint
- `src/demo/cache/repository.py:4` **high** — Cache write path `cache_set()` has no metric or span around it
- `src/demo/cache/repository.py:10` **high** — Cache read path `cache_get()` has no metric or span around it
- `src/demo/cache/repository.py:14` **high** — Cache delete path `cache_delete()` has no metric or span around it
- `src/demo/cache/client.py:14` **high** — Redis client `get_redis()` returns client with no dedicated health check endpoint
- `src/demo/timeseries/repository.py:19` **high** — Unbounded aggregation query `bucketed_averages()` executes time_bucket GROUP BY without latency metric or row count
- `src/demo/graph/repository.py:12` **high** — Graph write path `relate()` executes Cypher MERGE without metric or span
- `src/demo/graph/repository.py:31` **high** — Graph query path `neighbors()` executes Cypher MATCH without metric or span

### review-observability-infra
- `infra/observability/prometheus/prometheus.yml:18` **high** — Prometheus scrape job 'prometheus' (line 18) has no corresponding alert rule to monitor Prometheus itself. Without alerts on prometheus_tsdb_* or prometheus_sd_* metrics, Prometheus failures and service discovery issues may be silent.
- `infra/compose/observability.yml:76` **high** — otel-collector service is deployed (line 76) but has no Prometheus scrape job to monitor it. The collector's health and performance cannot be observed, and failures may go undetected.
- `infra/compose/services.yml:29` **high** — worker service (line 29-50) and beat service (line 51-63) in services.yml (merged for prod/staging) are missing APP_OTEL_ENABLED and APP_OTEL_EXPORTER_OTLP_ENDPOINT environment variables. These runtime surfaces will not send traces to Tempo, creating an observability gap in production workloads.

### review-observability
- `src/demo/routes/websockets.py:13` **high** — The /ws websocket endpoint only meters inbound messages via ws_metrics.message_received() (line 17). The connection lifecycle is unobserved: _manager.connect (line 13), _manager.disconnect (line 20), and _manager.broadcast (line 18) emit no metric, no trace, and no log. Connection counts, broadcast fan-out volume, and disconnects are invisible to /metrics and Prometheus — an entire long-lived code path with no observability signal.
- `src/demo/routes/health.py:33` **high** — The /health dependency probes swallow `except Exception` and downgrade the dependency to {"alive": False} without logging the failure or the correlation id. The workers probe (line 33), the mongo probe (line 43), and the redis probe (line 51) are all silent error paths — a broker/mongo/redis outage produces no log line, so the only signal is the health JSON body. Contrast the /metrics DLQ path (line 86-88) which correctly logs `get_logger().warning("dlq_metrics_unavailable", error=str(_exc))`. An operator inspecting logs sees nothing when a backing store goes down.
- `src/demo/routes/graphql.py:11` **medium** — The GraphQL introspection toggle (`disable_introspection=not _ide`, line 11) and the GraphiQL IDE enablement (line 17) are resolved at import time with no log of the security-relevant decision. When introspection/IDE is enabled (e.g. in a misconfigured prod), nothing records that the schema is exposed, so the configuration drift is unobservable from logs or metrics.
- `src/demo/observability/metrics.py:41` **medium** — MetricsRegistry._latencies_ms is an unbounded list (line 41) that grows by one entry per request (record_request, line 48) and is never trimmed except by an explicit reset(). For a long-running, high-traffic service this is an unbounded memory leak, and render_prometheus / p99 sort the entire history on every /metrics scrape (lines 65, 72), making the scrape cost O(n log n) and grow without limit. The module docstring acknowledges this as a deferred concern, but it remains a real observability-infrastructure risk: the metrics endpoint itself degrades the process it is meant to monitor.

### review-performance
- `src/demo/routes/items.py:28` **high** — GET /items loads the entire items table with no LIMIT/pagination. list_items runs `select(Item).order_by(Item.id)` and materializes every row into a list, then serializes all of them through ItemRead. On an unbounded table this is an unbounded query + unbounded allocation + unbounded serialization on a public read endpoint — a clear latency/memory regression that grows linearly with table size.
- `src/demo/db/repository.py:7` **high** — list_items() does `list(session.scalars(select(Item).order_by(Item.id)))` with no bound — it always fetches and materializes the full table. This is the underlying unbounded-query/allocation hot path behind GET /items; any caller pays O(rows) memory and serialization cost.
- `src/demo/routes/health.py:38` **medium** — The /health probe creates a brand-new redis client via `_redis.Redis.from_url(settings.redis_url)` on every request, which constructs a fresh connection pool, opens a connection to ping liveness, then closes it. Because the probe 'fires continuously' (per the docstring), this churns a new connection pool + TCP connection per probe instead of reusing a cached client — repeated pool setup/teardown in a hot, high-frequency path. Note the mongo and redis checks below already reuse module-level cached clients (get_client/get_redis); only this worker-liveness check pays the per-call pool cost.

### review-privacy
- `src/demo/middleware/errors.py:82` **high** — Validation error response includes detailed field error information (errors=jsonable_encoder(exc.errors())), which could expose PII if request schemas contain sensitive fields like email, phone, or SSN. Even with benign current models, validation error details leak information about request structure and failed validation reasons.

### review-security
- `src/demo/graph/repository.py:274` **high** — Cypher injection: `src`, `dst`, and `kind` are interpolated directly into the AGE Cypher text via f-strings wrapped in single quotes (`{name: '{src}'}`, `[\:{kind}]`). A value containing a single quote (or Cypher metacharacters) breaks out of the literal and lets an attacker inject arbitrary Cypher into the MERGE statement. The docstring's 'pass only trusted, app-controlled values' caveat is not enforced in code, so any caller that forwards user input is exploitable. AGE's cypher() cannot bind parameters, but the values must still be sanitized.
- `src/demo/graph/repository.py:292` **high** — Cypher injection: `name` is interpolated unsanitized into the MATCH clause (`{name: '{name}'}`) of the AGE cypher() call. A `name` value containing a single quote escapes the string literal and permits arbitrary Cypher injection. Same root cause as `relate()` — the 'trusted values only' docstring is not enforced.
- `src/demo/routes/websockets.py:1547` **medium** — The /ws WebSocket endpoint accepts every connection with no authentication, authorization, or Origin check, then broadcasts each received message to all connected clients. This allows cross-site WebSocket hijacking (a browser on any origin can open the socket since WebSocket handshakes are not subject to the same-origin policy) and lets any client broadcast arbitrary messages to all others. Broken access control on a public realtime surface.
- `src/demo/mongo/repository.py:778` **medium** — `find_documents` passes the caller-supplied `query` Mapping straight into pymongo's `find()`. If any caller forwards request-derived data into this filter, an attacker can inject MongoDB query operators (e.g. `$where`, `$gt`, `$ne`, `$regex`) for NoSQL injection / auth bypass / DoS. The helper provides no operator stripping or shape validation, so the safety depends entirely on every future caller doing it.
- `src/demo/routes/health.py:1413` **low** — The /metrics endpoint is exposed without any authentication or network restriction and returns internal operational data (request counts, error rates, latency, DLQ depth, circuit-breaker state, webhook/ws/graphql counters). If reachable beyond the trusted scrape network this leaks operational details useful for reconnaissance. Acceptable when bound to an internal network, but the route itself enforces nothing.
- `src/demo/observability/tracing.py:1172` **low** — The OTLP span exporter is configured with `insecure=True`, sending traces over unencrypted gRPC. Trace spans can contain request paths and other potentially sensitive metadata; on an untrusted network this is exposed in cleartext. Fine for an in-cluster collector but should not be the silent default for production wiring.

### review-test-quality
- `tests/functional/test_webhooks.py:55` **high** — test_duplicate_delivery_is_deduped cannot fail if deduplication is broken. Both POSTs send an identical body and the test only asserts each returns status 200. In the route (routes/webhooks.py), a successfully-processed event returns 200 ('accepted') and a deduped redelivery also returns 200 ('duplicate'). So whether the second delivery is correctly deduped or wrongly re-processed, the response is 200 either way — the assertion is satisfied in both cases. The test asserts nothing that distinguishes deduped from not-deduped behaviour, despite its name. (Dedup is in fact covered by test_metrics_count_outcomes, which asserts outcome="duplicate" 1; this test adds no independent guarantee.)
- `tests/unit/test_logging.py:34` **low** — test_get_logger_is_usable has no assertion — it only calls get_logger().info(...) with a 'must not raise' comment. It will pass as long as the call does not raise, but it does not verify the logger emits anything, uses the configured level, or includes structured fields. A regression that silently dropped the log call (or returned a no-op logger) would not be caught.

### review-usability
_(no findings)_

## Drift check
_(no drift detected)_

