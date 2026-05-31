# Template-audit triage — 2026-05-31 (framework `76d9b65`)

> Subject: the **all-batteries rendered template** (`framework template-render` → 11 batteries:
> age, consumers, graphql, mongodb, pgvector, react, redis, timescaledb, webhooks, websockets,
> workers), reviewed by the full 18-agent **project** roster in snapshot mode.
> **18/18 agents returned — no quota drops.** 58 findings (35 high / 10 medium / 7 low / 6 info).
>
> This is a **template-payload** audit: findings are about `src/framework_cli/template/**` (the code
> rendered into generated projects), located back to source via `path-map.md`. Line numbers in the
> findings are **as-rendered**; Jinja shifts them, so a few security/observability line refs are
> wildly off (e.g. `websockets.py:1547`) — the *function* named in the message is the anchor, not the line.
>
> **Triage lens (per [[offload-architecture-not-delegate]]):** the template should *model* good patterns
> and *pre-empt* antipatterns builders will copy. So a finding is **fix-now** when the template teaches a
> bad pattern or ships a real defect; **defer** when it's a builder-seam decision, a deliberate minimal
> exemplar, or belongs to an already-named roadmap slice; **false-positive** when the agent misread.

## Disposition summary

| Disposition | Count | Theme |
|---|---|---|
| **Fix-now** | 8 findings (5 themes) | Cypher injection, unbounded reads, WS cleanup, silent health probes, tautological dedup test (+ cheap doc/dep cleanups) |
| **Defer — named roadmap slice** | ~22 findings | obs-completeness (obs-db ×14, WS lifecycle, prom/otel scrape), env-parity (worker/beat OTEL), DLQ/webhook PII retention |
| **Defer — document tradeoff** | ~8 findings | WS open-broadcast demo, mongo filter caveat, /metrics + OTLP-insecure, FK semantics, advisory deps/docs |
| **False-positive / inflated** | ~5 findings | contracts ×3 (pact-v4 body wrapper misread), seed KeyError, validation-error echo |

---

## FIX-NOW

These are cheap and the template is actively teaching the wrong thing (or shipping a defect builders inherit).

### 1. Cypher injection in the AGE graph repository — `relate()` + `neighbors()`
- **Agents:** security (high ×2) · **Source:** `src/{{package_name}}/{% if "age" in batteries %}graph{% endif %}/repository.py`
- **Verified:** `src`/`dst`/`kind`/`name` are interpolated into the Cypher text via f-strings (`{name: '{src}'}`, `[\:{kind}]`). The docstring says "pass only trusted, app-controlled values" but nothing enforces it; a single quote breaks out of the literal.
- **Why fix:** a *security-conscious scaffold* must not model raw string-interpolation into a query language — builders copy this verbatim into request-fed paths. AGE's `cypher()` genuinely can't bind params, so the fix is escaping (double single-quotes, reject backslashes/control chars) + constrain `kind` to an allowlist of relationship types. Keep the docstring caveat as defense-in-depth, but enforce it in code.

### 2. Unbounded reads — `list_items()` → GET /items and GraphQL `items`
- **Agents:** performance (high ×2), api-design (high) · **Sources:** `src/{{package_name}}/db/repository.py`, `routes/items.py`, `{% if "graphql" in batteries %}graphql{% endif %}/schema.py`
- **Verified:** `list_items()` is `list(session.scalars(select(Item).order_by(Item.id)))` — full-table materialization; GET /items and the GraphQL `items` field both fan out from it with no bound.
- **Why fix:** same finding the 2-agent probe surfaced (2026-05-31). The scaffold's flagship read path models an unbounded query+allocation+serialize — the canonical antipattern. Add `limit: int = 50, offset: int = 0` (sane default + max cap) to `list_items`, thread through the REST endpoint and the GraphQL field. One change fixes all three findings.

### 3. WebSocket receive loop leaks dead connections
- **Agent:** application-logic (medium) · **Source:** `src/{{package_name}}/routes/{...}websockets.py`
- **Verified:** the loop only catches `WebSocketDisconnect`; any other exception (encode failure, broadcast to a half-open socket) escapes **without** `_manager.disconnect(ws)`, leaving a stale connection registered forever.
- **Why fix:** real resource leak in shipped code. Move cleanup to `finally: _manager.disconnect(ws)` and make `disconnect` idempotent. Small, correct.

### 4. Silent `/health` dependency probes (no log on degrade)
- **Agents:** observability (high), application-logic (low) · **Source:** `src/{{package_name}}/routes/health.py.jinja`
- **Verified:** the workers/mongo/redis probes each `except Exception:` → `{"alive": False}` with **no log**, while the very same file's `/metrics` DLQ path correctly logs `dlq_metrics_unavailable`. The inconsistency *is* the tell.
- **Why fix:** an outage of a backing store leaves zero log trace — operators see `alive:false` with nothing to diagnose. Add `get_logger().warning("health_probe_failed", dependency=..., error=str(exc))` in each except (capture `as exc`). Preserves the never-500 behavior. Cheap consistency fix.

### 5. Tautological webhook dedup test
- **Agent:** test-quality (high) · **Source:** `tests/functional/{...}test_webhooks.py`
- **Verified:** `test_duplicate_delivery_is_deduped` sends two identical bodies and asserts only `status == 200` on each. But accepted→200 and deduped→200, so the test passes whether or not dedup works — it cannot fail. (Real dedup coverage lives in `test_metrics_count_outcomes`.)
- **Why fix:** a framework-shipped test that gives false confidence is worse than no test. Assert an observable dedup signal — the `duplicate` webhook metric incremented, or exactly one inbox row for the key.

### 6–8. Cheap hygiene (bundle with the above)
- **documentation (info)** — `observability/metrics.py` docstring still cites "Plan 3a/3b" (framework-internal plan refs leaking into generated projects). Reword in builder-facing terms.
- **documentation (low)** — `README.md.jinja` "Endpoints" lists only `/heartbeat /health /metrics /items`; omits `/webhooks`, `/ws`, `/graphql`. Add them (note they're battery-gated).
- **dependency (low)** — `pyproject.toml.jinja` declares `httpx>=0.28` in **both** runtime `dependencies` and the `dev` group. It's a genuine runtime dep; drop the redundant dev-group copy.

---

## DEFER — belongs to an already-named roadmap slice

These are real but map onto follow-ups already tracked in `CLAUDE.md` (Known follow-ups). Folding them in there keeps the triage honest rather than scope-creeping this pass.

### A. Observability-completeness (the §5-contract-per-surface reviewer follow-up)
- **obs-db (high ×14):** no metric/span around *any* repository call — db, vectors, mongo, cache, timeseries, graph — plus "no health()` on mongo/redis clients." The repos are intentionally **minimal exemplars**; instrumenting every call is a design decision. **Recommendation:** ship a `record_query`/span helper *used in the baseline `db/repository.py`* as the exemplar pattern builders extend, rather than hand-instrumenting 6 batteries. → obs-completeness slice.
- **observability (high):** `/ws` meters only inbound messages; `_manager.connect/disconnect/broadcast` emit no metric/trace/log — yet the websockets battery ships a dashboard + alerts. **Strongest of this cluster** (the battery advertises obs it doesn't fully deliver); elevate within the slice.
- **observability-infra (high ×2):** Prometheus has no self-scrape **alert** (`up{job="prometheus"}==0`); `otel-collector` is deployed with **no scrape job**. → obs-infra completeness/scaling (already named).
- **observability (medium):** `/metrics` `_latencies_ms` unbounded list + O(n log n) p99 per scrape. Known/acknowledged in the docstring; cap with a fixed deque/reservoir. → same slice. (Also flagged by the probe.)
- **observability (medium):** GraphQL introspection/IDE toggle resolved with no log of the security-relevant decision. Add an `info` log at router construction. → same slice (cheap; could also ride fix-now if touching graphql).

### B. Environment parity (dev→ci→stage→prod reviewer follow-up)
- **observability-infra (high):** `worker`/`beat` in `infra/compose/services.yml` (prod/staging overlay) lack `APP_OTEL_ENABLED` / `APP_OTEL_EXPORTER_OTLP_ENDPOINT` — prod workers won't export traces. This is exactly the **dev-only-not-prod / divergent-overlay** class the env-parity reviewer is meant to catch. **Concrete + cheap** — verify against how the `app` service wires OTEL, then add the two env vars to worker+beat. → env-parity slice (or a quick standalone fix).

### C. DLQ / webhook PII + retention (builder-seam + data-governance)
- **data-lineage (high ×3, medium ×2), compliance (medium ×2):** failed webhook events serialize their full payload into `dead_letter_tasks.args_json` (plain text, no TTL/retention); the webhook inbox row has no pruning path; no audit log on inbound webhook processing.
- **Verified:** `webhooks/handler.py` is explicitly a **builder seam** ("REPLACE THIS with your logic") and `process_async.delay(event)` enqueues the raw event. PII redaction/retention is a *builder* responsibility, but the template should **document** these as PII-bearing stores and offer a retention-job seam. → document in DLQ/webhook docs + a commented pruning seam; not a behavior change in the demo.

### D. Schema hygiene — FK `ondelete` + index (design call)
- **data-integrity (high ×2):** `embeddings.item_id` / `readings.item_id` FKs declare no `ondelete` and no index. Builders copy migration patterns, so modeling explicit `ondelete=` + an index is good scaffold hygiene — **but** CASCADE-vs-RESTRICT is a deliberate data-lifecycle decision the template should make intentionally. → decide semantics, then a cheap migration edit. (Lean toward fixing once the semantics call is made.)

---

## DEFER — document the intentional tradeoff (no behavior change)

- **security (medium):** `/ws` accepts every connection with no auth/origin check and broadcasts to all. This is the **intentional open broadcast-echo demo**. Document that builders must add handshake auth + an `Origin` allowlist before exposing it.
- **security (medium):** `mongo.find_documents` forwards the caller's `query` Mapping straight to `find()` (NoSQL-operator injection if caller-fed untrusted input). It's a helper; mirror the graph repo's "trusted, app-controlled values only" docstring caveat. (Optional: reject `$`-prefixed keys.)
- **security (low ×2):** `/metrics` unauthenticated (deployment-topology tradeoff — document the internal-network requirement); OTLP exporter `insecure=True` (make it a settings flag defaulting to secure outside dev — small, could ride fix-now).
- **compliance (low):** items have no erasure path — advisory; demo `name` data is generic.
- **dependency (info ×2):** `psycopg[binary]` is the dev-convenience extra (note prod should consider `psycopg[c]`); `redis>=5` is a looser bound than the rest of the manifest (tighten to a minor). Advisory comments.
- **documentation (info ×2):** cache helpers lack docstrings; battery-introduced `APP_*` settings undocumented in README/.env.example. Nice-to-have.

---

## FALSE-POSITIVE / inflated severity

- **contracts (high ×2, info ×1) — pact-v4 body-wrapper misread.** The agent read the pact response `body` as `{"content": [...], "contentType": "application/json", "encoded": false}` and concluded the provider (which returns a bare `list[ItemRead]`) is incompatible. **This is wrong:** `{content, contentType, encoded}` is **pact-v4's body-encoding wrapper**, not a literal expected shape. The `matchingRules` anchored at `$[*].id` / `$[*].name` with `match: type` confirm the body is matched as an **array**, and a `type` matcher matches *N* elements from a single example (so seeding two items still verifies). The shipped `test_provider_pact.py` runs the real app and verifies this pact **green** in the acceptance tier. → **No action.** *(Agent-calibration note: the `contracts` agent does not understand pact-4 body serialization — worth a fixture in `reviewers:tune` if this recurs. Cross-ref [[check-agent-prompt-fit-before-adding-to-target]].)*
- **data-integrity (high) — `seed.py` KeyError on malformed row.** `seeds.json` is a **framework-controlled fixture**, not untrusted input. Real-world risk ≈ 0; severity inflated. → defer-low (a guard is harmless but unnecessary).
- **privacy (high) — validation-error field echo.** FastAPI's 422 echoes `exc.errors()` (field names + invalid input) back **to the client that submitted it**. The handler already returns a generic `detail` and never leaks internal exception text. Echoing a submitter's own input to themselves is low real risk; "high" is inflated. → defer-low (optionally redact known-sensitive field names later).
- **data-lineage (medium) — `/metrics` DLQ audit trail.** Overlaps cluster C; the agent concedes the DLQ depth gauge itself is benign. → defer-low.

---

## Notes for next time
- Mechanism worked end-to-end: 18/18 agents, no drops, `meta.json` `git_sha` correctly stamped as the framework HEAD (`76d9b65`), `path-map.md` resolved most paths (the `*/repository.py` basenames land as 6-way `candidates` because every battery has one — the agent message disambiguates).
- `path-map.md` line numbers are as-rendered; trust the function name in the message over the line for the Jinja-heavy files (`health.py.jinja`, route files).
- The same `_latencies_ms` / unbounded-`items` findings recur from the 2-agent probe — confirms they're stable, real, and overdue for the fix-now batch above.
