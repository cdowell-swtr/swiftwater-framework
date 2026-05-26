# Production/Staging Observability (OBS-PROD) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the observability stack run in staging/prod (it's currently `dev`-profile only — a spec-divergence defect), via a shared compose overlay merged into every environment, with environment-appropriate config, persistence, OTEL on, and alerts that reach a destination.

**Architecture:** A new `infra/compose/observability.yml` overlay holds the core obs stack (moved out of `dev.yml`) + the always-on postgres-exporter (folded-in 8i) + an `app:` OTEL merge fragment + prod-safe grafana + named volumes. Merged into dev (`task dev`), staging, and prod (the builder's `strategy.sh` place-image hook, guided by the framework); `dev:lite`/test omit it. `prod.yml`/`staging.yml` are untouched.

**Tech Stack:** Docker Compose (multi-file merge), Prometheus/Grafana/Alertmanager/Loki/Promtail/Tempo/OTEL-Collector, `prometheuscommunity/postgres-exporter`, Copier/Jinja, pytest (render + `docker compose config` validation).

**Spec:** `docs/superpowers/specs/2026-05-26-prod-observability-design.md`

---

## Refinements to the spec (decided while planning — the spec flagged these mechanics as "plan pins it")

1. **Overlay carries the CORE stack + postgres-exporter ONLY.** The battery exporters (`mongodb-exporter`/`celery-exporter`) `depends_on` `mongo`/`redis`, which exist only in `dev.yml` — putting them in the overlay would make `docker compose -f prod.yml -f observability.yml config` fail (`depends_on` an undefined service). They **stay in `dev.yml`** (dev-only, as today). Monitoring battery services in prod is gated on those *services* reaching prod — a separate gap, **recorded as a follow-up** (§ Follow-ups). This corrects spec §2's "the gated exporters moved too."
2. **`strategy.sh` is a builder-implemented hook** (`__target_place_image` is a `_todo` stub). OBS-PROD cannot literally merge the overlay; it **updates the hook's guidance comment + the in-comment example + `infra/deploy/README.md`** to merge `-f $DEPLOY_ENV.yml -f observability.yml`, and ships the overlay. The builder's hook does the merge. Refines spec §2/§7.
3. **Alertmanager uses `url_file`** (native since v0.26; the pinned image is v0.27.0) — a mounted file holding the webhook URL — instead of envsubst (the `prom/alertmanager` image is busybox-based, no `envsubst`). Refines spec §6.

## Conventions

- `src/framework_cli/template/` is template payload (framework mypy/ruff EXCLUDE it). Compose/obs-config files are mostly plain or `.jinja`; the overlay is `.jinja` (it has `{{ package_name }}`/conditional bits + `${VAR}` compose interpolation — note `${...}` is shell/compose interpolation, NOT Jinja, so it's safe, but the file is `.jinja` for the package-name/app fragment).
- **LOCKED files:** `dev.yml`, `prod.yml`, `staging.yml`, `base.yml`, all `infra/observability/**`, `strategy.sh`, etc. are `LOCKED_TRACKED`. This plan adds `observability.yml` + `postgres_alerts.yml` + `postgres.json` to that tuple and changes several LOCKED files → a **one-time baseline manifest shift for all projects** (expected). `Taskfile.yml` is HYBRID_TRACKED (its managed section changes).
- Tooling: FROZEN env (`uv run --frozen ...`). Docker IS available (the `docker compose config` validation + integrity render tests run).
- **Commit-gate hook:** `git commit` blocked unless `CLAUDE.md` is staged with its `- **Last updated:** …` line edited. Run `git add … CLAUDE.md` then `git commit` as **separate** Bash calls.
- Render helper: `render_project(dest, {**DATA, "batteries":[...]})`, `DATA={project_name:"Demo",project_slug:"demo",package_name:"demo",python_version:"3.12"}`.

## File Structure

- **Create:** `infra/compose/observability.yml.jinja` (the overlay); `infra/observability/prometheus/alerts/postgres_alerts.yml`; `infra/observability/grafana/dashboards/postgres.json`.
- **Modify:** `infra/compose/dev.yml.jinja` (remove core obs services; add a dev `grafana:` anonymous override); `infra/observability/prometheus/prometheus.yml.jinja` (add the always-on `postgres` scrape job); `infra/observability/alertmanager/alertmanager.yml` (webhook receiver via `url_file`); `Taskfile.yml.jinja` (dev/dev:reset merge `-f observability.yml`; reorder so dev wins); `infra/deploy/strategy.sh` (place-image guidance + example); `infra/deploy/README.md` (deploy-merge guidance); `.env.example.jinja` (`APP_ALERT_WEBHOOK_URL` + `GRAFANA_ADMIN_PASSWORD`); `src/framework_cli/integrity/classes.py` (`LOCKED_TRACKED` += the 3 new files).
- **Tests:** `tests/test_copier_runner.py` (render assertions + `docker compose config` merge validation); `tests/` integrity; update any baseline-pinned compose/obs tests.

---

## Task 1: The `observability.yml` overlay + remove core obs from `dev.yml`

**Files:** Create `infra/compose/observability.yml.jinja`; modify `infra/compose/dev.yml.jinja`; modify `src/framework_cli/integrity/classes.py`. Test: `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render tests**
```python
def test_render_observability_overlay(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # baseline — the overlay is always-on (not battery-gated)
    overlay = dest / "infra" / "compose" / "observability.yml"
    assert overlay.exists()
    text = overlay.read_text()
    for svc in ("prometheus:", "grafana:", "alertmanager:", "loki:", "promtail:", "tempo:",
                "otel-collector:", "postgres-exporter:"):
        assert svc in text
    # prod-safe grafana in the overlay (no anonymous), admin password from env:
    assert "GF_SECURITY_ADMIN_PASSWORD" in text and "GF_AUTH_ANONYMOUS_ENABLED" not in text


def test_render_dev_yml_core_obs_removed(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    # core obs moved to the overlay — dev.yml no longer defines them:
    for svc in ("prometheus:", "loki:", "tempo:", "otel-collector:", "promtail:", "alertmanager:"):
        assert svc not in dev
    # dev keeps a grafana override re-enabling anonymous auth for local convenience:
    assert "GF_AUTH_ANONYMOUS_ENABLED" in dev
    # app + postgres + traefik stay:
    assert "traefik:" in dev and "postgres:" in dev
```
Run `uv run --frozen pytest tests/test_copier_runner.py -q -k "observability_overlay or dev_yml_core_obs"` → FAIL.

- [ ] **Step 2: Create the overlay**
Create `infra/compose/observability.yml.jinja`. Move the seven core obs service blocks **verbatim from `dev.yml.jinja` lines 55–129** (prometheus, grafana, alertmanager, loki, promtail, tempo, otel-collector) — but **remove their `profiles: ["dev"]`** (the overlay only merges when obs is wanted, so no profile gating) — and apply these changes:
  - **grafana:** replace the dev anonymous env with prod-safe auth:
    ```yaml
      grafana:
        image: grafana/grafana:11.3.0
        environment:
          GF_SECURITY_ADMIN_USER: admin
          GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}
        ports:
          - "3000:3000"
        volumes:
          - "../observability/grafana/provisioning:/etc/grafana/provisioning:ro"
          - "../observability/grafana/dashboards:/var/lib/grafana/dashboards:ro"
        depends_on:
          - prometheus
    ```
    (`${GRAFANA_ADMIN_PASSWORD:-admin}` keeps `docker compose config` valid when unset (dev/CI); prod sets the secret. `${...}` is compose interpolation, not Jinja — safe in `.jinja`.)
  - **prometheus/loki/tempo:** add named-volume mounts for persistence (see Task — keep the existing config-file mounts, add a data volume):
    - prometheus: add `- "promdata:/prometheus"` to its volumes, and add `--storage.tsdb.retention.time=15d` to its command list.
    - loki: add `- "lokidata:/loki"`.
    - tempo: add `- "tempodata:/var/tempo"`.
  - Add the **postgres-exporter** (always-on; folded-in 8i):
    ```yaml
      postgres-exporter:
        image: prometheuscommunity/postgres-exporter:v0.16.0
        environment:
          DATA_SOURCE_NAME: "postgresql://app:${POSTGRES_PASSWORD:-app}@postgres:5432/app?sslmode=disable"
        ports:
          - "9187:9187"
        depends_on:
          postgres:
            condition: service_healthy
    ```
  - Add the **app OTEL merge fragment** (deep-merges onto the app from base.yml/prod.yml so the app traces wherever the overlay runs):
    ```yaml
      app:
        environment:
          APP_OTEL_ENABLED: "true"
          APP_OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
    ```
  - Top-level volumes:
    ```yaml
    volumes:
      promdata: {}
      lokidata: {}
      tempodata: {}
    ```
The overlay has **no `profiles:`** on its services (it runs whenever merged). Add a header comment: `# Observability overlay — merged into dev/staging/prod (NOT dev:lite/test). Defines the obs stack once; runs identically in every environment (spec §8).`

- [ ] **Step 3: Remove the core obs services from `dev.yml.jinja`**
Delete the prometheus, grafana, alertmanager, loki, promtail, tempo, otel-collector blocks (current lines 55–129). Leave app, postgres, traefik, and the gated battery blocks (`mongo`/`mongodb-exporter`, `redis`/`worker`/`beat`/`celery-exporter`) and the bottom `volumes:` block untouched. The dev app already sets `APP_OTEL_ENABLED` (line 12-13) — leave it (harmless; the overlay also sets it). Then **add a dev grafana anonymous override** (so local stays frictionless) after the traefik block:
```yaml
  grafana:
    profiles: ["dev"]
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: "Admin"
      GF_AUTH_DISABLE_LOGIN_FORM: "true"
```
This is a partial override merged onto the overlay's grafana. It must **win** in dev — handled by the merge order in Task 3 (`-f base.yml -f observability.yml -f dev.yml`, dev last). (`profiles: ["dev"]` keeps it from affecting staging/prod, which never merge dev.yml.)

- [ ] **Step 4: Add the overlay to `LOCKED_TRACKED`**
In `src/framework_cli/integrity/classes.py`, add `"infra/compose/observability.yml",` to the `LOCKED_TRACKED` tuple (alongside the other compose files).

- [ ] **Step 5: GREEN + gate + commit**
`uv run --frozen pytest tests/test_copier_runner.py -q -k "observability_overlay or dev_yml_core_obs"` → PASS; then full gate. Commit (hook steps). Message: `feat(obs): observability.yml overlay (core stack + postgres-exporter); remove core obs from dev.yml`

---

## Task 2: Postgres scrape job + alerts + dashboard (folded-in 8i)

**Files:** Modify `infra/observability/prometheus/prometheus.yml.jinja`; create `infra/observability/prometheus/alerts/postgres_alerts.yml` + `infra/observability/grafana/dashboards/postgres.json`; modify `classes.py`. Test: `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render tests**
```python
def test_render_postgres_obs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # baseline — postgres is always-on
    prom = (dest / "infra" / "observability" / "prometheus" / "prometheus.yml").read_text()
    assert "job_name: postgres" in prom
    alerts = dest / "infra" / "observability" / "prometheus" / "alerts" / "postgres_alerts.yml"
    dash = dest / "infra" / "observability" / "grafana" / "dashboards" / "postgres.json"
    assert alerts.exists() and dash.exists()
    import yaml as _y, json as _j
    assert _y.safe_load(alerts.read_text())["groups"][0]["name"] == "postgres"
    assert _j.loads(dash.read_text())["uid"] == "postgres"
```
Run → FAIL.

- [ ] **Step 2: Add the always-on `postgres` scrape job**
In `prometheus.yml.jinja`, after the `prometheus` self-scrape job and **before** the `{%- if "workers" %}` block:
```yaml
  - job_name: postgres
    static_configs:
      - targets: ["postgres-exporter:9187"]
```

- [ ] **Step 3: Create `postgres_alerts.yml`** (plain, always-on):
```yaml
groups:
- name: postgres
  rules:
  - alert: PostgresDown
    expr: up{job="postgres"} == 0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: Postgres exporter target is down (postgres unreachable or exporter crashed) — app-specific default; tune or remove
```

- [ ] **Step 4: Create `postgres.json`** — model on `infra/observability/grafana/dashboards/slo.json` (READ it for the exact schema). `uid: "postgres"`, title "Postgres", panels: `up{job="postgres"}` (stat); active connections `pg_stat_database_numbackends{datname="app"}`; commit/rollback rate `rate(pg_stat_database_xact_commit{datname="app"}[5m])` + `..._xact_rollback...`; cache-hit ratio `pg_stat_database_blks_hit{datname="app"} / clamp_min(pg_stat_database_blks_hit{datname="app"} + pg_stat_database_blks_read{datname="app"}, 1)`. Plain/`__auto` legends, valid JSON.

- [ ] **Step 5: `LOCKED_TRACKED`** += `"infra/observability/prometheus/alerts/postgres_alerts.yml"` and `"infra/observability/grafana/dashboards/postgres.json"`.

- [ ] **Step 6: GREEN + gate + commit.** Message: `feat(obs): always-on postgres scrape job + PostgresDown alert + dashboard (folds in 8i)`

---

## Task 3: Merge wiring — Taskfile, strategy.sh, README, .env.example

**Files:** Modify `Taskfile.yml.jinja`, `infra/deploy/strategy.sh`, `infra/deploy/README.md`, `.env.example.jinja`. Test: `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render tests**
```python
def test_render_merge_wiring(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    tf = (dest / "Taskfile.yml").read_text()
    # dev merges the overlay (order: base, observability, dev — dev wins for the grafana override):
    assert "-f infra/compose/observability.yml" in tf
    # dev:lite does NOT merge the overlay — assert its line is overlay-free:
    lite_line = next(ln for ln in tf.splitlines() if "--profile lite" in ln)
    assert "observability.yml" not in lite_line
    env = (dest / ".env.example").read_text()
    assert "APP_ALERT_WEBHOOK_URL" in env and "GRAFANA_ADMIN_PASSWORD" in env
    strat = (dest / "infra" / "deploy" / "strategy.sh").read_text()
    assert "observability.yml" in strat  # the place-image guidance/example references the overlay
```
Run → FAIL.

- [ ] **Step 2: Taskfile** — update the `dev` and `dev:reset` compose commands to include the overlay, ordered `base → observability → dev` (dev last so its grafana override wins):
  - `dev` (line 23): `docker compose -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml --profile dev up --build`
  - `dev:reset` (line 41): `docker compose -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml --profile dev down -v`
  - `dev:lite` (line 33): **unchanged** (`-f base.yml -f dev.yml --profile lite` — no overlay).

- [ ] **Step 3: strategy.sh** — update the `__target_place_image` guidance comment (lines 27–30) so the example merges the overlay:
  - The comment's compose-over-SSH example: `docker compose -f infra/compose/${DEPLOY_ENV}.yml -f infra/compose/observability.yml up -d` (was `-f <env>.yml`).
  - Add a sentence: "Merge the observability overlay (`-f infra/compose/observability.yml`) so staging/prod run the full monitoring stack per the framework's observability contract; provide `GRAFANA_ADMIN_PASSWORD` and the alertmanager webhook file (see README) as target secrets."
  (No logic change — `__target_place_image` stays a `_todo` the builder implements; only the guidance/example changes.)

- [ ] **Step 4: `infra/deploy/README.md`** — add a short "Observability in staging/prod" subsection: the deploy must merge `-f $DEPLOY_ENV.yml -f infra/compose/observability.yml`; set `GRAFANA_ADMIN_PASSWORD`; materialize `APP_ALERT_WEBHOOK_URL` as the alertmanager webhook file (Task 4). (READ the README first to match its style/headers.)

- [ ] **Step 5: `.env.example.jinja`** — add to the managed (`FRAMEWORK:BEGIN/END`) section, unconditional (before `# FRAMEWORK:END`):
```
# Observability (the stack runs in all environments). Grafana admin password (prod/staging);
# alert webhook URL — Alertmanager posts SLO breaches here (materialized as a mounted file on deploy).
GRAFANA_ADMIN_PASSWORD=
APP_ALERT_WEBHOOK_URL=
```

- [ ] **Step 6: GREEN + gate + commit.** Message: `feat(obs): merge the observability overlay in dev + deploy guidance + obs secrets`

---

## Task 4: Alertmanager webhook routing (`url_file`)

**Files:** Modify `infra/observability/alertmanager/alertmanager.yml`; modify the overlay's `alertmanager` service (mount the webhook-url file path). Test: `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render test**
```python
def test_render_alertmanager_webhook(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    am = (dest / "infra" / "observability" / "alertmanager" / "alertmanager.yml").read_text()
    assert "null" not in am                     # no longer the null receiver
    assert "webhook_configs" in am and "url_file" in am
```
Run → FAIL.

- [ ] **Step 2: Rewrite `alertmanager.yml`** — replace the null receiver with a webhook receiver reading the URL from a file (native alertmanager `url_file`, v0.27):
```yaml
route:
  receiver: "default"
  group_by: ["alertname"]
  group_wait: 10s
  group_interval: 1m
  repeat_interval: 1h

receivers:
  - name: "default"
    webhook_configs:
      # The URL is read from a mounted file (the APP_ALERT_WEBHOOK_URL secret, materialized on
      # deploy). Absent file → notifications no-op (e.g. local dev); config still loads.
      - url_file: /etc/alertmanager/webhook_url
        send_resolved: true
```

- [ ] **Step 3: Overlay alertmanager mount** — in `observability.yml.jinja`, the alertmanager service already mounts the config dir; ensure the webhook-url file location is mountable. Add a comment documenting that the deploy mounts the secret at `/etc/alertmanager/webhook_url` (e.g. `- "../observability/alertmanager/webhook_url:/etc/alertmanager/webhook_url:ro"` — a builder-provided file; keep it optional so dev without the file still starts. If a missing bind mount would fail compose, instead document mounting via the deploy and do NOT hard-code the bind in the overlay — the plan implementer verifies which keeps `docker compose config` valid with the file absent; prefer the documented-deploy-mount to avoid a dev failure).

- [ ] **Step 4: GREEN + gate + commit.** Verify: a rendered `alertmanager.yml` loads (optional: `docker run --rm -v .../alertmanager.yml:... prom/alertmanager:v0.27.0 amtool check-config` if cheap; else the render assertion + the merge-validation in Task 5 suffice). Message: `feat(obs): alertmanager routes SLO breaches to a url_file webhook (replaces null receiver)`

---

## Task 5: Integrity + the `docker compose config` merge-validation (the "obs runs in prod" proof)

**Files:** Test `tests/test_copier_runner.py` (+ `tests/acceptance/test_rendered_project.py` if a Docker tier fits); update any baseline-pinned compose/obs tests.

- [ ] **Step 1: The merge-validation test** (the headline proof — runs `docker compose config`, needs docker):
```python
import shutil, subprocess
@pytest.mark.skipif(shutil.which("docker") is None, reason="docker required for compose config")
def test_prod_plus_overlay_merges_with_obs_stack(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    comp = dest / "infra" / "compose"
    # prod + overlay must be a VALID topology including the obs stack + app + postgres:
    r = subprocess.run(
        ["docker", "compose", "-f", str(comp / "prod.yml"), "-f", str(comp / "observability.yml"), "config"],
        capture_output=True, text=True, env={**os.environ, "APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x"},
    )
    assert r.returncode == 0, r.stderr
    for svc in ("prometheus", "grafana", "alertmanager", "postgres-exporter", "app", "postgres"):
        assert svc in r.stdout
    # dev:lite (base+dev, no overlay) must have NO obs services:
    r2 = subprocess.run(
        ["docker", "compose", "-f", str(comp / "base.yml"), "-f", str(comp / "dev.yml"),
         "--profile", "lite", "config"],
        capture_output=True, text=True, env={**os.environ},
    )
    assert r2.returncode == 0 and "prometheus" not in r2.stdout
    # dev (base+overlay+dev) grafana is ANONYMOUS (dev override wins):
    r3 = subprocess.run(
        ["docker", "compose", "-f", str(comp / "base.yml"), "-f", str(comp / "observability.yml"),
         "-f", str(comp / "dev.yml"), "--profile", "dev", "config"],
        capture_output=True, text=True, env={**os.environ},
    )
    assert "GF_AUTH_ANONYMOUS_ENABLED" in r3.stdout
```
Place in the acceptance tier if it needs the `_docker_available()` guard style; otherwise a `skipif(shutil.which("docker") is None)` in `test_copier_runner.py` is fine. **Confirm the grafana-override merge order empirically here** — if `GF_AUTH_ANONYMOUS_ENABLED` is NOT in `r3.stdout`, the merge order is wrong; fix Task 3's `-f` ordering until dev grafana is anonymous AND prod (r) grafana is not.

- [ ] **Step 2: Integrity** — render baseline + a battery combo (e.g. `["mongodb","workers"]`) and run `framework integrity --ci` (or `from framework_cli.integrity.checker import check`): green. The `LOCKED_TRACKED` enumeration test (if any) accounts for the 3 additions. Update any existing test that pinned `dev.yml`/`prometheus.yml`/`alertmanager.yml` content to the new baseline.

- [ ] **Step 3: Full gate** — `uv run --frozen pytest -q && ruff check . && ruff format --check . && mypy src` → PASS.

- [ ] **Step 4: Commit.** Message: `test(obs): docker compose config merge-validation (prod+overlay) + integrity across the restructure`

---

## Final review (after all tasks)

Dispatch a final whole-branch reviewer (opus) that RUNS the tooling: full `pytest` (incl. the merge-validation), `ruff`/`mypy`/`uv lock --check`, `uv build`, `framework integrity --ci` on baseline + a battery combo, and empirically: `docker compose -f prod.yml -f observability.yml config` includes the obs stack; dev grafana anonymous / prod grafana auth-required; `dev:lite` has no obs; `alertmanager.yml` has the webhook (no null). Then use **superpowers:finishing-a-development-branch**.

## Follow-ups (recorded, not in this slice)

- **Battery services + their exporters in prod/staging.** `prod.yml`/`staging.yml` are app+postgres only — a project using `mongodb`/`workers` has no mongo/redis (nor their exporters) in prod. OBS-PROD delivers the core stack + postgres everywhere; battery-service-in-prod (and thus `mongodb-exporter`/`celery-exporter` in prod) is a separate, larger "complete the prod topology for batteries" gap.
- **The unified `8f-w` wizard** — multi-channel alert selection (Slack/email/PagerDuty) + db-paradigm selection, built together (this slice ships only the single `url_file` webhook).
- **Obs-infra scaling + the `review-observability` split (inf/db/app/fe)** — CLAUDE.md Known follow-ups.

## Self-Review

**Spec coverage:** §2 overlay-merged-everywhere → Task 1 + Task 3 (merge wiring) + Task 5 (validation); the battery-exporter refinement is documented. §3 env-appropriate grafana auth → Task 1 (overlay prod-safe + dev override) + Task 5 (empirical merge-order check). §4 persistence → Task 1 (named volumes + retention). §5 OTEL → Task 1 (app fragment). §6 alert routing → Task 4 (`url_file` refinement). §7 integrity/manifest-shift → Tasks 1–2 (`LOCKED_TRACKED`) + Task 5. §8 testing → Task 5 (merge-validation) + render tests throughout. 8i folded → Task 2. Wizard/centralized/battery-services deferred → Follow-ups.

**Placeholder scan:** the `postgres.json` dashboard (Task 2 Step 4) is described by panels+queries (modeled on `slo.json`, which the implementer reads) rather than full JSON — the render test enforces valid JSON + `uid`. The alertmanager webhook-url **mount mechanism** (Task 4 Step 3) is the one item left to the implementer to pin (bind-mount-optional vs documented-deploy-mount) with the invariant: config loads with the file absent (dev), and the deploy materializes it (prod). No literal TODOs.

**Consistency:** the overlay's `postgres-exporter:9187` matches the `postgres` scrape job (Task 2) + the `PostgresDown` `up{job="postgres"}` selector; the merge order (`base → observability → dev`) is consistent across Taskfile (Task 3) and the validation test (Task 5); grafana prod-safe (overlay) vs anonymous (dev override) is asserted empirically; `GRAFANA_ADMIN_PASSWORD`/`APP_ALERT_WEBHOOK_URL` appear in `.env.example` (Task 3) and are consumed by the overlay grafana (Task 1) / alertmanager `url_file` (Task 4).
