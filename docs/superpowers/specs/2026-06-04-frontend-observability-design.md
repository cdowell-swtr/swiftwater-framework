# Frontend Observability Surface + `review-observability-fe` (Plan 16) — Design Spec

**Date:** 2026-06-04
**Status:** Approved (brainstorm) — feeds the Plan 16 implementation plan.
**Roadmap row:** Plan 16 in `docs/superpowers/plans/2026-05-20-meta-plan.md` (*deps: 8g react battery, OBS-COMPLETE, Plan 11*).
**Closes two deferrals:** the react battery (8g) shipped with *"frontend obs deferred"*; OBS-COMPLETE split `review-observability` into app/infra/db but **skipped `fe`** for lack of a frontend-obs surface. This plan builds the surface and the reviewer together.

---

## 1. Purpose & boundary

The react battery currently ships **zero observability** (`BatterySpec.obs == "rides-existing"`): a Vite + TypeScript SPA served by the FastAPI app in prod, with no RUM, error tracking, or metrics. Plan 16 retrofits it to the §5 contract with an **in-process** Real-User-Monitoring surface — Core Web Vitals + JS errors + page-view navigation (with safe query-param attribution) — that rides the app's existing `/metrics`, plus the deferred **`review-observability-fe`** reviewer.

**Why in-process (not a separate exporter):** in prod the SPA is *served by* the FastAPI app (Vite builds to `dist/`, baked into the Python runtime image — one container). Frontend telemetry living on the app's `/metrics` matches the actual deployment topology and reuses the established webhooks / websockets in-process precedent (`docs/superpowers/plans/2026-05-24-webhooks-observability.md`, `2026-05-25-websockets-observability.md`): a thread-safe singleton with `render_prometheus()`, appended to `/metrics` inside a battery-gated block in `health.py`. No new scrape target, exporter, or prod compose service.

**Out of scope** (YAGNI — see §11): no react-router integration; no browser OTEL/trace export; no Sentry / third-party RUM; no backend persistence of RUM events; no broadening of `review-privacy`/`review-security` beyond the one calibration fixture in §9.

## 2. Architecture & data flow

```
Browser
  ├─ web-vitals lib            → onLCP / onCLS / onINP (numeric)
  ├─ window error handlers     → 'error' / 'unhandledrejection' (bounded type only)
  └─ page-view on mount        → pathname (allowlisted query params for attribution)
        │  batched; navigator.sendBeacon('/internal/rum', json)
        │  fire-and-forget; flush on visibilitychange / pagehide
        ▼
FastAPI  POST /internal/rum    → Pydantic-validate → re-apply allowlist → FrontendMetrics singleton
        ▼
GET /metrics   (health.py appends frontend_rum.metrics.render_prometheus(), react-gated)
        ▼
Prometheus scrapes the existing app job → frontend_alerts.yml + grafana/frontend.json
```

The browser is unscrapable, so telemetry must *leave* the browser before it can become a metric. The beacon endpoint is the bridge; everything downstream is the standard in-process pattern.

## 3. Frontend additions (react-gated `frontend/` dir)

- **`web-vitals`** added to `package.json` `dependencies` (tiny, zero transitive deps; the only new runtime dep).
- **`src/observability/rum.ts`** — registers `onLCP/onCLS/onINP`, `window` `error` + `unhandledrejection` handlers, and a page-view emit on load; collects allowlisted query params + referrer-host; batches and flushes via `navigator.sendBeacon` on event + `visibilitychange`/`pagehide`. Initialized once from `main.tsx`.
- **`src/observability/rum.test.ts`** — Vitest unit test: mock `sendBeacon`, assert callbacks wired, payload shape, query-param allowlist applied client-side, flush-on-hide. ESLint + Prettier clean.

## 4. Backend additions (template payload)

- **`{{package_name}}/frontend_rum/metrics.py`** — `FrontendMetrics` singleton mirroring `websockets/metrics.py` (`threading.Lock`, `render_prometheus()` returning hand-rolled Prometheus text):
  - `app_frontend_web_vitals_lcp_milliseconds` / `_inp_milliseconds` / `_cls` — **histograms** (fixed bucket sets) so alerts can compute p75.
  - `app_frontend_js_errors_total{type="error|unhandledrejection"}` — counter.
  - `app_frontend_page_views_total{...attribution labels}` — counter; bounded labels only (see §5/§6).
  - `app_frontend_rum_beacons_total{status="accepted|rejected"}` — ingest self-monitoring.
- **`{{package_name}}/routes/frontend_rum.py`** (react-gated) — `POST /internal/rum`, Pydantic-validated, folds payloads into the singleton.
- **`{{package_name}}/routes/health.py.jinja`** — add a `{% if "react" in batteries %}` block appending `frontend_metrics.render_prometheus()` to `/metrics` (identical pattern to webhooks/websockets/graphql).

## 5. Query-string capture — allowlist capability

Navigation analytics is only half a feature without attribution (search, campaigns, referrers), so Plan 16 exposes a query-param capture **capability** — built the safe way, following the established RUM/analytics pattern (**parameter allowlisting**, as in GA4 URL-parameter config, Sentry data-scrubbing, Datadog RUM): **capture nothing by default; opt in named keys.** Allowlist (fail-closed) is chosen over denylist/scrub (fail-open), which silently leaks any sensitive key nobody remembered to add.

- **Settings-driven allowlist.** The framework ships a sane default — the **UTM set** (`utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`) plus **referrer reduced to host/origin** (never the full referring URL). The builder edits one settings list to add/remove keys.
- **Defense in depth.** The frontend captures only allowlisted keys from `location.search`; the **backend re-applies the same allowlist** on ingest — the browser is never trusted.
- **Bounded labels.** Allowlisted params surface as bounded attribution labels on `app_frontend_page_views_total`. High-cardinality members (e.g. `utm_campaign`) get a **distinct-value cap with an `other` overflow bucket** so a campaign explosion can't blow up the series.
- **Search terms: documented seam, off by default.** A builder *can* add their declared search param to the allowlist, but the framework ships with it off and documents the dual tradeoff — search queries are both high-cardinality (belong in logs/events, not a metric label) and PII-prone (`review-privacy`'s concern). The capability exists without shipping a foot-gun. (The framework deliberately does not expose a generic `search` param itself — too many data structures it could reference; it exposes the *observability capability*, leaving the param choice to the builder.)

## 6. Invariants & abuse defense (the public endpoint)

`/internal/rum` is **public + unauthenticated** (browsers hit it pre-login). Hardened invariants:

- **No free-text leaves the browser.** Errors are a counter keyed on a fixed `type` enum — raw `message`/stack/URL are never forwarded and never become labels. Vitals are numeric only. Page-view path is `pathname` only; the backend defensively strips anything after `?`/`#` before applying the allowlist. → PII cannot enter the metric series via text.
- **Only allowlisted query params** (§5) are captured, on both ends.
- Strict Pydantic schema; small max body; malformed → `rum_beacons_total{status="rejected"}`, never 5xx.
- Same dev/prod `/metrics` gating as the rest of the obs surface.
- O(1) ingest work; `sendBeacon` batching + flush-on-hide bound client volume.

## 7. Alerts & dashboard

- **`infra/observability/prometheus/alerts/frontend_alerts.yml`** — `FrontendLCPDegraded` (p75 LCP over budget for N min) + `FrontendErrorSpike` (js-error rate). ~2–3 rules.
- **`infra/observability/grafana/dashboards/frontend.json`** — "Frontend (RUM)" board: vitals percentiles, JS-error rate, page-views by attribution, beacon accept/reject health.

## 8. BatterySpec change + obs-completeness

- React's `BatterySpec.obs` flips `"rides-existing"` → **`"in-process"`** in `batteries.py`.
- `tests/test_obs_completeness.py` is parametrized over batteries: once `obs == "in-process"` and the alerts + dashboard artifacts exist, the existing guard automatically asserts **new alerts + dashboard** and **no** new scrape job / prod service / exporter. No test edit needed — the new obs value drives it.

## 9. Reviewers — correct separation of concerns

Two axes touch the same lines for different reasons; each reviewer owns one:

- **`review-observability-fe`** (NEW) — `src/framework_cli/review/agents/observability-fe.md`. Agentic (rides the Plan 11 spine), `block_threshold` high, sibling to `observability-infra`/`-db`. `active_when="battery"`, added to react's `gates_agents` tuple in `batteries.py` (runs only in projects with the react battery). **Scope: observability + operability** — new frontend components/views/error-boundaries/API calls shipped without RUM/error instrumentation; new views not page-view-tracked; swallowed errors not surfaced to the error counter; and **label-cardinality bounds** on the allowlist (unbounded label → flag). JSON-array output, same schema as siblings. *It does NOT do PII detection* — that would conflate observability with privacy.
- **`review-privacy`** (existing) — owns the PII axis. Its mandate ("collection of PII not needed for the stated purpose; PII logged or echoed") already covers a builder allowlisting a PII-bearing key (`email`/`q`/`token`). Plan 16 adds **one privacy eval fixture** ("allowlists a PII-bearing query param") to calibrate it reliably, accepting the privacy-agent re-eval as the correct cost of clean separation. No prompt rewrite unless the fixture shows a recall gap.

**Eval fixtures (`tests/eval/fixtures/`, calibrated `thresholds.yaml`):** for `review-observability-fe`, **3 bad / 1 good** per the §20 convention. The bad set covers: (a) a new view/component with no RUM/error instrumentation; (b) an error handler that swallows without incrementing the error counter; (c) an unbounded label added to the allowlist (cardinality). The good fixture is a correctly-instrumented change. (The "beacons `location.href`/raw error text" case is a **privacy** fixture, not an obs one — §5/§6 make that a privacy leak, not an observability gap.)

## 10. Tests & guards

- `test_obs_completeness.py` — auto-covers via §8 (no edit).
- Backend unit (singleton math + ingest validation + allowlist re-application + cardinality cap/overflow) and functional (POST `/internal/rum` → series appear on `/metrics`; disallowed param dropped; malformed → `rejected`).
- Frontend Vitest unit for `rum.ts` (§3).
- `tests/test_copier_runner.py` — new files render/interpolate; ruff-format (Python) + Prettier (TS) clean.
- Acceptance — rendered react project still passes first `pre-commit`; integrity manifest regenerates for react upskill (new react-gated files tracked); downskill of react removes the surface cleanly (no `--force` expected).
- Eval scoring for `review-observability-fe` + the new privacy fixture.

## 11. Out of scope (YAGNI)

- No react-router; navigation is `pathname`-based and extends cleanly if a builder adds routing later.
- No browser OTEL / trace export; no Sentry / third-party RUM; no separate exporter service.
- No backend persistence of RUM events (metrics only; events folded and dropped).
- No generic framework-owned `search` param; no broadening of `review-privacy`/`review-security` beyond the §9 fixture.
- The broader "PII in query strings anywhere" concern (backend access logs, API design putting tokens/emails in query params) is **not** Plan 16 — it would mean expanding + re-calibrating privacy/api-design agents on their own. Noted as a candidate follow-up, not built here.

## 12. Implementation details deferred to the plan

These are settled in direction; the implementation plan (`writing-plans`) nails the specifics:

- Exact histogram bucket boundaries for LCP/INP (ms) and CLS (unitless).
- The `app_frontend_page_views_total` label set and the per-label cardinality cap value + overflow handling.
- The Pydantic beacon schema, body-size limit, and batch shape.
- Settings field name + shape for the query-param allowlist (and how the frontend reads it — build-time inject vs served config).
- Alert thresholds (LCP p75 budget, error-rate) and dashboard panel definitions.
- Whether `frontend_rum/` and `routes/frontend_rum.py` are LOCKED vs tracked in the integrity manifest (follow the react battery's existing file-class choices).
