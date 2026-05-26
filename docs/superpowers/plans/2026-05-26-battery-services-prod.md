# Battery Services in Staging/Prod (SVC-PROD) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Get the battery services (`mongo`, `redis`) + processes (`worker`, `beat`) into staging/prod (they're `dev.yml`-only), so a battery-using project actually works when deployed — and move the battery exporters into the obs overlay so they run in prod too.

**Architecture:** A new prod/staging-only `infra/compose/services.yml` overlay (gated mongo/redis with persistence + worker/beat as `image:${APP_IMAGE}` + celery command + `APP_RUN_MIGRATIONS:false`, no compose profiles), merged at deploy by `strategy.sh` alongside `observability.yml`. `dev.yml` keeps its dev battery blocks unchanged (the dev/prod definition split mirrors the app's own `base.yml`-build vs `prod.yml`-image split). The `mongodb-exporter`/`celery-exporter` relocate from `dev.yml` into `observability.yml` (gated) so they run wherever obs runs.

**Tech Stack:** Docker Compose (multi-file merge), mongo/redis, Celery worker/beat on the app image, Copier/Jinja, pytest (render + `docker compose config` validation).

**Spec:** `docs/superpowers/specs/2026-05-26-battery-services-prod-design.md`

---

## Conventions
- `src/framework_cli/template/` is template payload (framework ruff/mypy EXCLUDE it). `services.yml.jinja` has `{{ package_name }}` + `${VAR}` compose interpolation (`${...}` is compose, NOT Jinja — safe).
- **LOCKED files:** `dev.yml`, `observability.yml`, `prod.yml`, `staging.yml`, `strategy.sh`, `README.md` are `LOCKED_TRACKED`; this plan adds `infra/compose/services.yml` to that tuple and changes `dev.yml`/`observability.yml`/`strategy.sh`/`README.md` → a **one-time baseline manifest shift** (expected; the OBS-PROD precedent). `prod.yml`/`staging.yml` are **untouched** (the overlay merges at deploy).
- Tooling: FROZEN env (`uv run --frozen ...`). Docker available (the `docker compose config` merge-validation runs).
- **Commit-gate hook:** `git commit` blocked unless `CLAUDE.md` is staged with its `- **Last updated:** …` line edited. Run `git add … CLAUDE.md` and `git commit` as **separate** Bash calls.
- Render helper: `render_project(dest, {**DATA, "batteries":[...]})`, `DATA={project_name:"Demo",project_slug:"demo",package_name:"demo",python_version:"3.12"}`.

## File Structure
- **Create:** `infra/compose/services.yml.jinja`.
- **Modify:** `infra/compose/dev.yml.jinja` (remove the two exporter blocks), `infra/compose/observability.yml.jinja` (add the two exporters, gated), `infra/deploy/strategy.sh` (merge guidance), `infra/deploy/README.md` (services + managed-escape-hatch note), `src/framework_cli/integrity/classes.py` (`LOCKED_TRACKED += services.yml`).
- **Tests:** `tests/test_copier_runner.py` (render + image-drift guard + `docker compose config` merge-validation).

---

## Task 1: The `services.yml` overlay (prod/staging battery services)

**Files:** Create `infra/compose/services.yml.jinja`; modify `src/framework_cli/integrity/classes.py`. Test: `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render tests**
```python
def test_render_services_overlay_workers(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    svc = (dest / "infra" / "compose" / "services.yml").read_text()
    import yaml as _y
    cfg = _y.safe_load(svc)
    assert "redis" in cfg["services"] and "worker" in cfg["services"] and "beat" in cfg["services"]
    assert "${APP_IMAGE" in svc and 'APP_RUN_MIGRATIONS: "false"' in svc
    assert "celery" in svc and "redisdata" in cfg["volumes"]


def test_render_services_overlay_mongodb(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})
    cfg = __import__("yaml").safe_load((dest / "infra" / "compose" / "services.yml").read_text())
    assert "mongo" in cfg["services"] and "mongodata" in cfg["volumes"]


def test_render_services_overlay_empty_is_valid(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # no battery → valid YAML no-op (comment only)
    svc = (dest / "infra" / "compose" / "services.yml").read_text()
    parsed = __import__("yaml").safe_load(svc)  # must not raise
    assert not (parsed or {}).get("services")  # no battery services
```
Run `uv run --frozen pytest tests/test_copier_runner.py -q -k services_overlay` → FAIL.

- [ ] **Step 2: Create `infra/compose/services.yml.jinja`**
Gate the WHOLE `services:`/`volumes:` structure on a relevant battery being present, so a no-battery render is a **comment-only file** (valid YAML, merges to nothing):
```jinja
# Battery-service overlay for staging/prod — merged by the deploy (infra/deploy/strategy.sh)
# alongside observability.yml: `-f $DEPLOY_ENV.yml -f services.yml -f observability.yml`. Defines
# the battery data stores + worker/beat for prod/staging (dev keeps its own build-based, profiled
# copies in dev.yml). Managed alternative: point APP_MONGO_URL / APP_REDIS_URL / APP_CELERY_* at a
# managed instance and omit the data-store services here (worker/beat stay self-hosted).
{%- if "mongodb" in batteries or "workers" in batteries %}
services:
{%- if "mongodb" in batteries %}
  mongo:
    image: mongo:7
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "mongosh --quiet --eval \"db.adminCommand('ping').ok\" | grep -q 1"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
    volumes:
      - "mongodata:/data/db"
{%- endif %}
{%- if "workers" in batteries %}
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - "redisdata:/data"

  worker:
    image: ${APP_IMAGE:?set APP_IMAGE to the promoted registry tag}
    restart: unless-stopped
    command: ["celery", "-A", "{{ package_name }}.tasks.app", "worker", "--loglevel=info"]
    environment:
      APP_RUN_MIGRATIONS: "false"
      APP_DATABASE_URL: "postgresql+psycopg://app:${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}@postgres:5432/app"
      APP_REDIS_URL: "redis://redis:6379/0"
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
    healthcheck:
      test: ["CMD", "celery", "-A", "{{ package_name }}.tasks.app", "inspect", "ping"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 20s
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy

  beat:
    image: ${APP_IMAGE:?set APP_IMAGE to the promoted registry tag}
    restart: unless-stopped
    command: ["celery", "-A", "{{ package_name }}.tasks.app", "beat", "--loglevel=info"]
    environment:
      APP_RUN_MIGRATIONS: "false"
      APP_REDIS_URL: "redis://redis:6379/0"
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
    depends_on:
      redis:
        condition: service_healthy
{%- endif %}

volumes:
{%- if "mongodb" in batteries %}
  mongodata: {}
{%- endif %}
{%- if "workers" in batteries %}
  redisdata: {}
{%- endif %}
{%- endif %}
```
> The implementer pins the exact `{%- %}` whitespace so EVERY combo renders valid YAML: `["workers"]`, `["mongodb"]`, `["mongodb","workers"]`, and **none** (comment-only). Verify each parses (Step 4). `worker`/`beat` use `image:${APP_IMAGE}` (the promoted image, same `:?` validation as `prod.yml`'s app), the celery command overriding the entrypoint's uvicorn, `APP_RUN_MIGRATIONS:"false"` (the `entrypoint.sh` gate — they never migrate). No published `ports` (in-network only). No `profiles:`.

- [ ] **Step 3: `LOCKED_TRACKED`** — add `"infra/compose/services.yml",` to the tuple in `src/framework_cli/integrity/classes.py` (next to the other `infra/compose/*.yml`).

- [ ] **Step 4: GREEN + validate all combos**
`uv run --frozen pytest tests/test_copier_runner.py -q -k services_overlay` → PASS. Then render each combo + parse:
```
for b in '[]' '["workers"]' '["mongodb"]' '["mongodb","workers"]'; do
  rm -rf /tmp/sv && uv run --frozen python -c "
import yaml; from framework_cli.copier_runner import render_project
render_project('/tmp/sv', {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12','batteries':$b})
yaml.safe_load(open('/tmp/sv/infra/compose/services.yml').read()); print('$b services.yml valid')
"; done
```

- [ ] **Step 5: Full gate + commit** (hook steps). Message: `feat(svc): services.yml overlay — battery data stores + worker/beat for staging/prod`

---

## Task 2: Relocate the exporters (`dev.yml` → `observability.yml`)

**Files:** Modify `infra/compose/dev.yml.jinja` (remove exporters), `infra/compose/observability.yml.jinja` (add them, gated). Test: `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render tests**
```python
def test_render_exporters_in_observability_overlay(tmp_path: Path):
    for batteries, exporter in (["workers"], "celery-exporter"), (["mongodb"], "mongodb-exporter"):
        dest = tmp_path / ("e_" + exporter)
        render_project(dest, {**DATA, "batteries": batteries})
        obs = (dest / "infra" / "compose" / "observability.yml").read_text()
        dev = (dest / "infra" / "compose" / "dev.yml").read_text()
        assert exporter in obs           # now in the obs overlay (runs in all obs envs)
        assert exporter not in dev       # gone from dev.yml
```
Run → FAIL.

- [ ] **Step 2: Remove the exporters from `dev.yml.jinja`**
In the `{%- if "mongodb" %}` block, delete the `mongodb-exporter:` service (keep `mongo:`). In the `{%- if "workers" %}` block, delete the `celery-exporter:` service (keep `redis:`/`worker:`/`beat:`). Preserve clean whitespace + the gated-block structure.

- [ ] **Step 3: Add the exporters to `observability.yml.jinja`** (gated, NO profiles — the overlay convention). Place after the core obs services (before the top-level `volumes:`):
```jinja
{%- if "mongodb" in batteries %}

  mongodb-exporter:
    image: percona/mongodb_exporter:0.43
    command: ["--mongodb.uri=mongodb://mongo:27017", "--collect-all"]
    ports:
      - "9216:9216"
    depends_on:
      mongo:
        condition: service_healthy
{%- endif %}
{%- if "workers" in batteries %}

  celery-exporter:
    image: danihodovic/celery-exporter:0.10.5
    command: ["--broker-url=redis://redis:6379/0"]
    ports:
      - "9808:9808"
    depends_on:
      redis:
        condition: service_healthy
{%- endif %}
```
> Their `depends_on` mongo/redis resolves in every env that merges `observability.yml`: dev (mongo/redis from `dev.yml`), staging/prod (from `services.yml`). `dev:lite` merges no obs overlay → no exporters (unchanged from today). The `prometheus.yml` `celery`/`mongodb` scrape jobs already exist (gated) — no scrape change.

- [ ] **Step 4: GREEN + sanity** — `uv run --frozen pytest tests/test_copier_runner.py -q -k "exporters_in_observability"` → PASS. Render `["mongodb","workers"]` + confirm `observability.yml` has both exporters and `dev.yml` has neither, both valid YAML.

- [ ] **Step 5: Full gate + commit.** Message: `feat(svc): relocate mongodb/celery exporters into observability.yml (run in prod too)`

---

## Task 3: Merge wiring — `strategy.sh` + deploy README

**Files:** Modify `infra/deploy/strategy.sh`, `infra/deploy/README.md`. Test: `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render test**
```python
def test_render_services_deploy_guidance(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    strat = (dest / "infra" / "deploy" / "strategy.sh").read_text()
    assert "services.yml" in strat   # place-image guidance merges the services overlay
    readme = (dest / "infra" / "deploy" / "README.md").read_text()
    assert "services.yml" in readme and "managed" in readme.lower()
```
Run → FAIL.

- [ ] **Step 2: `strategy.sh` guidance** — the `__target_place_image` comment currently merges `-f $DEPLOY_ENV.yml -f infra/compose/observability.yml` (from OBS-PROD). Add `services.yml` to the merge example + a sentence: the example becomes `... docker compose -f <env>.yml -f infra/compose/services.yml -f infra/compose/observability.yml up -d`, and note "merge `services.yml` so a battery-using project's data stores + worker/beat run in staging/prod (set `APP_IMAGE`/`POSTGRES_PASSWORD`; for a managed data store instead, set `APP_MONGO_URL`/`APP_REDIS_URL`/`APP_CELERY_*` and omit the data-store services — see README)." No logic change (still the `_todo` builder hook).

- [ ] **Step 3: `infra/deploy/README.md`** — READ it (match style). Extend the OBS-PROD "Observability in staging/prod" guidance (or add a sibling "Battery services in staging/prod" subsection): the deploy merges `-f services.yml`; worker/beat run the promoted `${APP_IMAGE}` with `APP_RUN_MIGRATIONS=false` (the app/pre-roll migrates once); **managed escape hatch** — point the `APP_*_URL`s at a managed store + omit the data-store services (worker/beat stay self-hosted). Concise.

- [ ] **Step 4: GREEN + full gate + commit.** Message: `feat(svc): deploy guidance merges services.yml; document the managed-store escape hatch`

---

## Task 4: Integrity + `docker compose config` merge-validation + image-drift guard

**Files:** Test `tests/test_copier_runner.py`.

- [ ] **Step 1: Image-drift guard** (cheap, hermetic) — assert the dev/prod parallel definitions use the same images:
```python
def test_dev_and_services_images_match(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb", "workers"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    svc = (dest / "infra" / "compose" / "services.yml").read_text()
    for image in ("mongo:7", "redis:7-alpine"):
        assert image in dev and image in svc, f"{image} drifted between dev.yml and services.yml"
```

- [ ] **Step 2: The merge-validation** (the headline proof — docker available):
```python
import os, shutil, subprocess
@pytest.mark.skipif(shutil.which("docker") is None, reason="docker required for compose config")
def test_prod_plus_services_plus_obs_merges(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb", "workers"]})
    comp = dest / "infra" / "compose"
    env = {**os.environ, "APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x"}
    r = subprocess.run(
        ["docker", "compose", "-f", str(comp / "prod.yml"), "-f", str(comp / "services.yml"),
         "-f", str(comp / "observability.yml"), "config"],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, r.stderr
    for svc in ("worker", "beat", "redis", "mongo", "app", "postgres",
                "mongodb-exporter", "celery-exporter", "prometheus"):
        assert svc in r.stdout
    assert "APP_RUN_MIGRATIONS" in r.stdout and "demo:ci" in r.stdout  # worker/beat on the promoted image
    # dev:lite (no overlays) still has its data stores + NO worker/beat/exporters:
    r2 = subprocess.run(
        ["docker", "compose", "-f", str(comp / "base.yml"), "-f", str(comp / "dev.yml"),
         "--profile", "lite", "config"],
        capture_output=True, text=True, env={**os.environ},
    )
    assert r2.returncode == 0 and "redis" in r2.stdout and "worker" not in r2.stdout
```
Run it. If the prod merge fails, read `r.stderr` (likely a `depends_on` to a service not present, or a YAML issue in `services.yml`) and fix the root cause.

- [ ] **Step 3: Integrity** — render baseline + `--with mongodb,workers`; `write_manifest` then `check(..., ci=True)` → both green; confirm `LOCKED_TRACKED` includes `services.yml`. Update any baseline-pinned compose test broken by the exporter relocation (explain each).

- [ ] **Step 4: Full gate** — `uv run --frozen pytest -q && ruff check . && ruff format --check . && mypy src` → PASS.

- [ ] **Step 5: Commit.** Message: `test(svc): prod+services+obs merge-validation + image-drift guard + integrity`

---

## Final review (after all tasks)

Dispatch a final whole-branch reviewer (opus) that RUNS the tooling: full `pytest` (incl. the merge-validation), `ruff`/`mypy`/`uv lock --check`, `uv build`, `framework integrity --ci` on baseline + `--with mongodb,workers`, and empirically: `docker compose -f prod.yml -f services.yml -f observability.yml config` includes worker/beat (on `${APP_IMAGE}`, `APP_RUN_MIGRATIONS=false`) + mongo/redis + both exporters; `dev:lite` still has its data stores and no worker/beat/exporters; `dev.yml` no longer defines the exporters. **Crucially, have it check the live-stack acceptance tests** (the gap that slipped in OBS-PROD): the dev workers/mongodb acceptance variants must still pass (they exercise `dev.yml`'s worker/beat — unchanged here, but confirm). Then use **superpowers:finishing-a-development-branch**.

## Follow-ups (recorded)
- The unified **`8f-w`** wizard (db-paradigm + alert-channel selection).
- **HA/clustering** of the self-hosted prod data stores (single-host compose; builder owns backups — same posture as prod postgres).
- The obs-completeness review check + obs-infra-scaling + the inf/db/app/fe `review-observability` split (Known follow-ups).

## Self-Review

**Spec coverage:** §2 services.yml overlay (prod/staging-only, dev.yml untouched) → Task 1. §3 contents (mongo/redis persistent + worker/beat image+celery+RUN_MIGRATIONS=false) → Task 1. §4 exporters → observability.yml → Task 2. §5 migration discipline → Task 1 (`APP_RUN_MIGRATIONS:false`). §6 managed escape hatch → Task 3 (README). §7 dev/lite unchanged + drift guard → Task 2 (dev only loses exporters) + Task 4 (drift test). §8 integrity/manifest shift → Tasks 1-2 (LOCKED) + Task 4. §9 testing → Task 4 (merge-validation) + render tests throughout. HA/wizard deferred → Follow-ups.

**Placeholder scan:** the `services.yml` whitespace control for the four battery combos (esp. the comment-only no-battery render) is the one implementer-pinned detail (Task 1 Step 2/4), with the invariant stated (every combo valid YAML) + a test for it. No literal TODOs.

**Consistency:** `worker`/`beat` `image:${APP_IMAGE}` + `${POSTGRES_PASSWORD}` match `prod.yml`'s conventions; `APP_RUN_MIGRATIONS:false` matches `entrypoint.sh` + the dev blocks; the exporters' `depends_on` mongo/redis are satisfied in every obs env (dev.yml in dev, services.yml in prod); the merge order `$ENV.yml → services.yml → observability.yml` is consistent across `strategy.sh` (Task 3) and the validation test (Task 4); the drift guard pins `mongo:7`/`redis:7-alpine` identical across `dev.yml` and `services.yml`.
