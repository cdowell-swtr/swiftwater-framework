# Production/Staging Observability (OBS-PROD) — Design Spec

**Date:** 2026-05-26
**Status:** Approved (brainstorm) — not yet planned/implemented
**Plan:** OBS-PROD (a spec-divergence defect fix; prioritized ahead of the remaining Plan 8 battery work). **Supersedes / folds in Plan 8i** (the dev-only postgres-exporter — its content is delivered here, for all environments).
**Builds on:** Plan 4/6 (the observability stack — prometheus/grafana/alertmanager/loki/promtail/tempo/otel-collector; `gen_observability.py`; the `slo_alerts.yml`/`slo.json` baseline; the `LOCKED_TRACKED` set), Plan 8c/8f-1 (the exporter-as-scrape-source pattern; the `base.yml` + env-overlay compose-merge model).

---

## 1. Purpose & scope

**The defect:** the design spec promises the observability stack *"runs identically in every environment … from dev through prod"* (§Observability, §8) — prod = *"Full stack, no dev tooling"* (§10) — with Alertmanager routing breaches to Slack/email/PagerDuty. **The implementation does the opposite:** the entire stack (prometheus, grafana, alertmanager, loki, promtail, tempo, otel-collector, all exporters) lives in `dev.yml` under `profiles: ["dev"]`; `prod.yml`/`staging.yml`/`base.yml` are **app + postgres only**. So **staging and prod run blind** — no scraping, no dashboards, no alerting, no tracing (OTEL is also off there). The `dev:lite` profile was meant to let a developer *opt out* of observability locally (spec §10); the implementation inverted that into "observability is dev-only" — exactly backwards (alerting on a laptop where an engineer can just look, nothing in prod).

**This plan** makes the stack run in staging/prod per the spec, via a shared compose overlay merged into every environment, with environment-appropriate config, persistence, OTEL on, and **alerts that actually reach a destination** in prod. It is a baseline/framework change (LOCKED files), prioritized ahead of the remaining batteries (8f-2/8g/8h) because it restores a headline promise.

**In scope:**
- A new `infra/compose/observability.yml` overlay defining the obs stack once; merged into dev, staging, prod (not test/ci); `dev:lite` omits it.
- The stack moved out of `dev.yml` into the overlay; the postgres-exporter (folded-in 8i) added always-on; the gated `mongodb`/`celery` exporters moved too.
- **Environment-appropriate config** (esp. grafana auth: prod-safe by default, dev conveniences layered back via merge order).
- **Persistence** (named volumes + retention) for prometheus/loki/tempo.
- **OTEL enabled** wherever the overlay runs (an `app:` merge fragment).
- **Minimal real alert routing**: a secret-driven webhook receiver in `alertmanager.yml` (envsubst at startup) + `APP_ALERT_WEBHOOK_URL` in `.env.example`.
- `strategy.sh` merges the overlay at deploy; the `Taskfile` dev/dev:lite targets adjust.
- Tests: render assertions + a `docker compose config` merge-validation that prod+overlay is a valid topology including the stack; integrity green.

**Out of scope (deferred):**
- **The interactive multi-channel alert wizard** (Slack/email/PagerDuty selection at `framework new`) — folded into the **unified configurable `framework new` wizard (`8f-w`)**, built together with the database-paradigm wizard (both are scaffold-time config of the same kind). This slice ships only the secret-driven webhook so alerts route in prod; the channel ergonomics come with `8f-w`.
- **Centralized / external observability** (a dedicated obs host, managed backend) — a builder's later scaling evolution; recorded with the obs-infra-scaling + `review-observability` split-into-inf/db/app/fe follow-up (CLAUDE.md Known follow-ups).
- Any prod hosting model beyond the framework's single-host docker-compose prod (e.g. k8s manifests).

## 2. Architecture — a shared overlay merged everywhere

The compose model is `base.yml` (the app) merged with one env overlay (`dev.yml` adds postgres + obs; `prod.yml`/`staging.yml` are standalone full topologies redefining `app` as the promoted image + postgres). The obs stack currently lives entirely in the `dev.yml` overlay.

**New `infra/compose/observability.yml.jinja`** (LOCKED) defines the obs stack **once**:
- Core (always): `prometheus`, `grafana`, `alertmanager`, `loki`, `promtail`, `tempo`, `otel-collector` — moved out of `dev.yml`.
- `postgres-exporter` (always-on — **folded-in 8i**): `prometheuscommunity/postgres-exporter`, `DATA_SOURCE_NAME=postgresql://app:${POSTGRES_PASSWORD:-app}@postgres:5432/app?sslmode=disable`, scraped via a `postgres` job; plus the always-on `postgres_alerts.yml` (`PostgresDown`) + `postgres.json` dashboard (the 8i deliverables, now in all envs).
- Gated exporters (moved from `dev.yml`, still battery-conditional): `mongodb-exporter`, `celery-exporter`.
- An `app:` **merge fragment** carrying `APP_OTEL_ENABLED: "true"` + `APP_OTEL_EXPORTER_OTLP_ENDPOINT` so the app emits traces wherever the overlay is present (compose deep-merges it onto the app from `base.yml`/`prod.yml`).

Because `observability.yml.jinja` carries the gated battery exporters + the `${POSTGRES_PASSWORD}`-style substitution, it is a templated, LOCKED overlay (battery-aware integrity, the `dev.yml` precedent).

**Merge points:**
| Context | Command |
|---|---|
| `task dev` | `-f base.yml -f dev.yml -f observability.yml` |
| `task dev:lite` | `-f base.yml -f dev.yml` (**no overlay — the opt-out**) |
| staging / prod | `strategy.sh` merges `-f infra/compose/$DEPLOY_ENV.yml -f infra/compose/observability.yml` |
| test / ci | no overlay (no monitoring stack in tests) |

`prod.yml`/`staging.yml` are **not edited** — they pick up the stack purely via the deploy-time merge. Obs services carry **no compose profile** (they run whenever the overlay is merged). Cross-file `depends_on` (e.g. prometheus → app) resolves because compose treats the merged files as one project.

## 3. Environment-appropriate config (the security-relevant split)

The stack is identical everywhere; some **config differs by environment**, and getting this wrong ships an insecure prod:
- **Grafana auth.** Dev runs anonymous-admin, no login form (frictionless local). Shipping that to prod = an open admin console. The **overlay ships prod-safe defaults** (login required; admin password from `GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}`, a deploy secret); **dev re-applies the anonymous conveniences** via a small `grafana:` override that wins in the dev merge (compose is last-wins on scalar env, so the dev override must be ordered after the overlay — the plan pins the exact `-f` ordering / where the dev `grafana:` block lives). **Invariant: prod/staging get auth-required grafana; dev stays anonymous.** The same layering applies to any other dev-only convenience.
- **Retention/footprint** sized for prod in the overlay (see §4); dev can keep shorter windows if it diverges, but the default prod-safe retention is acceptable in dev too (simpler: one value).

## 4. Persistence

Dev's prometheus/loki/tempo have **no named volumes** (ephemeral). The overlay adds named volumes + explicit retention so prod data survives restarts:
- `prometheus`: a `promdata` volume + `--storage.tsdb.retention.time` (a sane default, e.g. 15d).
- `loki`: a `lokidata` volume (its config already sets `retention_period: 168h`).
- `tempo`: a `tempodata` volume + a retention/compaction setting.
These volumes are declared in the overlay's top-level `volumes:`.

## 5. OTEL across environments

The overlay's `app:` fragment sets `APP_OTEL_ENABLED=true` + the collector endpoint, so tracing turns on **iff the overlay is present** (dev full, staging, prod) and stays off for `dev:lite`/test. The app's `/metrics` is exposed regardless (Prometheus scrapes it via an existing `app` job). This removes the current "OTEL off in staging/prod" gap.

## 6. Minimal alert routing

`alertmanager.yml` currently routes to a `null` receiver (drops everything). This slice replaces it with a **single webhook receiver** so SLO breaches reach a destination in prod:
- The receiver URL comes from **`APP_ALERT_WEBHOOK_URL`**, recorded in the `.env.example` managed (`FRAMEWORK:BEGIN/END`) section + set as a deploy secret (GitHub Environment secret → compose env at deploy).
- **Wrinkle:** Alertmanager does not expand env vars in its config natively. So a small **envsubst-at-startup** step renders `alertmanager.yml` from a template using the env var before alertmanager loads it (a tiny entrypoint/command wrapper, or an init container). The plan pins the exact mechanism (likely a `command:`/entrypoint that runs `envsubst` then `alertmanager`). When `APP_ALERT_WEBHOOK_URL` is unset (e.g. local dev), the receiver falls back to a no-op so dev doesn't error.
- The **route** points the default receiver at the webhook (replacing `null`). Grouping/throttling keep the existing `group_wait`/`repeat_interval`.
- The full **multi-channel selection** (Slack vs PagerDuty vs email, with per-channel config + secret ergonomics) is the unified `8f-w` wizard's job — this slice delivers the always-available single-webhook path.

## 7. Integrity & consistency

All compose + obs-config files are `LOCKED_TRACKED`. This slice's LOCKED changes:
- **New:** `infra/compose/observability.yml` (add to `LOCKED_TRACKED`); `infra/observability/prometheus/alerts/postgres_alerts.yml` + `infra/observability/grafana/dashboards/postgres.json` (from 8i; add to `LOCKED_TRACKED`); possibly an alertmanager template file if envsubst uses one.
- **Changed:** `dev.yml` (obs services removed → it shrinks); `alertmanager.yml` (webhook receiver); `prometheus.yml` (the always-on `postgres` job — from 8i); `.env.example` (the `APP_ALERT_WEBHOOK_URL` + `GRAFANA_ADMIN_PASSWORD` managed entries); `Taskfile.yml` (dev/dev:lite/deploy merge commands); `infra/deploy/strategy.sh` (merge the overlay).
- **Untouched:** `prod.yml`/`staging.yml` (the overlay is merged at deploy, not edited in) — minimizing the blast radius on the env topologies.
- **Consequence:** a **baseline integrity-manifest shift for all projects** — a one-time framework-version bump (existing projects get it on `framework upskill`; `upskill_project` regenerates the manifest). Same class as 8i, larger. Any existing test pinning a baseline `dev.yml`/`prometheus.yml`/`alertmanager.yml` content/checksum is updated to the new baseline as part of the work.

## 8. Testing

- **Render (`tests/test_copier_runner.py`):** `observability.yml` renders with the full stack (prometheus/grafana/alertmanager/loki/promtail/tempo/otel-collector + postgres-exporter; gated mongodb/celery exporters with those batteries); `dev.yml` **no longer** contains the obs services; the `postgres` scrape job + `postgres_alerts.yml`/`postgres.json` present (baseline); `alertmanager.yml` has the webhook receiver (not `null`); `prod.yml`/`staging.yml` unchanged (no obs services inline); the `Taskfile` dev target merges the overlay and `dev:lite` does not. A render-format/validity guard for the new YAML/JSON.
- **Merge-validation (the "obs runs in prod" proof):** in a rendered project, `docker compose -f infra/compose/prod.yml -f infra/compose/observability.yml config` exits 0 and the parsed output contains the obs services + `app` + `postgres` (and `-f base.yml -f dev.yml -f observability.yml config` for dev; `-f base.yml -f dev.yml config` for dev:lite has **no** obs services). This validates the merge wiring without standing up a live prod (which CI can't do). Runs in the acceptance tier (needs `docker compose`, available).
- **Integrity:** `framework integrity --ci` green on a baseline render (manifest includes the new LOCKED overlay + postgres files + the changed LOCKED files). The `LOCKED_TRACKED` enumeration test accounts for the additions.
- **Alertmanager envsubst:** a focused test that the rendered `alertmanager.yml` (post-envsubst with a sample `APP_ALERT_WEBHOOK_URL`) is valid alertmanager config with the webhook receiver, and that an unset var yields a valid no-op config.
- **No live-stack test:** as with the existing exporters, the running stack is exercised manually (`task dev` locally, the real deploy in staging/prod); CI proves wiring via `docker compose config` + render + integrity.

## 9. Follow-ups (recorded, not in this slice)

- **The unified `8f-w` configurable wizard** — database-paradigm selection **and** alert-channel selection (Slack/email/PagerDuty), built together; the multi-channel alertmanager config + secret ergonomics land there.
- **Observability-infrastructure scaling + the `review-observability` split into inf/db/app/fe** — CLAUDE.md Known follow-ups (the co-located per-host stack is a starting point; a review check should flag when it must graduate to centralized).
- **Centralized/external observability** — a builder's scaling evolution beyond co-located single-host obs.

## 10. Self-review

- **Placeholders:** none material — the overlay contents, merge points, env-config split, persistence, OTEL fragment, alertmanager webhook + envsubst, integrity changes, and test tiers are specified. The one genuinely fiddly item (the grafana dev-override **merge ordering**, §3) is flagged for the plan to pin precisely (the invariant — prod auth-required, dev anonymous — is fixed); likewise the exact envsubst mechanism (§6).
- **Internal consistency:** the overlay is merged identically into every obs-enabled env (delivering "runs identically … dev through prod"); `dev:lite`/test omit it (the intended opt-out); prod/staging topologies stay untouched (overlay at deploy); the alert `up{job="postgres"}`/webhook receiver match the scrape job + secret; 8i is realized here (all-env, not dev-only) and its standalone spec is superseded.
- **Scope:** one cohesive plan — make the existing stack run+persist+trace+alert in staging/prod. The interactive multi-channel wizard (→ `8f-w`), centralized obs, and non-compose hosting are explicitly deferred.
- **Ambiguity:** "runs in prod" pinned to the deploy-time `-f $ENV.yml -f observability.yml` merge (co-located, the approved architecture), not external/managed; "alerting in prod" pinned to a secret-driven single webhook (not the multi-channel wizard); the grafana auth posture pinned (prod-safe default, dev convenience layered) with the merge-ordering detail delegated to the plan.

---

*End of design. Next step: `superpowers:writing-plans` for OBS-PROD.*
