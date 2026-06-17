# FWK6 — Data-store runtime parity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the hardcoded co-located-container assumption from a generated project's compose stack so any data store can be a co-located container **or** an external endpoint (managed / native / tunneled / proxied), selected by env + overlay membership, without hand-editing locked files or rewriting.

**Architecture:** Two-layer seam. (1) Every `APP_*_URL` **literal** in a compose `environment:` block becomes `${APP_*_URL:-<container-default>}` so the operator's env wins and today's behavior is the fallback. (2) The always-on `postgres` service and the `app → postgres` `depends_on` edge move out of the locked `prod.yml`/`staging.yml` into the operator-merged `services.yml` overlay, so **self-hosted** = merge `services.yml` (already the documented deploy path) and **managed** = omit it + set `APP_DATABASE_URL`. An opt-in `tls-ca.yml` overlay carries an off-by-default CA-bundle mount for `verify-full` to managed stores. `services.yml` (and `tls-ca.yml`) move to `INTENTIONALLY_UNLOCKED` since operators now edit them.

**Tech Stack:** Copier `.jinja` compose templates; `docker compose config` (merge validation); pytest (`tests/test_copier_runner.py` render guards, `tests/integrity/test_classes.py`, `tests/acceptance/test_rendered_project.py` live tier, `tests/runtime_coverage/` FWK29 ratchet); PyYAML.

**Empirically verified before writing (2026-06-17, `docker compose config`) — the implementer may trust these:**
1. `depends_on` long-form maps **merge additively** across `-f` overlays: `base + services` → `app.depends_on.postgres` present; `base` alone → no `depends_on`, no `postgres`.
2. Compose **eagerly** interpolates the `:-` default branch, so a nested `${…:-…${POSTGRES_PASSWORD:?msg}…}` **errors in the managed case even when the override is set**. Therefore the inline default uses plain `${POSTGRES_PASSWORD}` (no `:?`); the `:?` required-guard lives on the `postgres` **service** (self-hosted only).

**Review-model policy (restate per CLAUDE.md / [[subagent-review-model-pattern]]):** implementers → Sonnet (Haiku only for trivial); per-task spec-compliance review → Sonnet; code-quality review → **Opus**; branch-end whole-branch review → **Opus**. Pass `model` explicitly per role.

**Gate cadence (per [[gate-cadence-framework-slices]]):** these are template/infra files — do **not** run the full 18-agent app gate per commit. Use light per-task review + controller skip-marker commits ([[controller-skip-marker-recipe]]), one branch-end Opus review. The commit-gate hook needs `PLAN.md`/`ACTION_LOG.md` staged ([[commit-gate-hook-timing]]: `git add` then `git commit` as **separate** calls; keep the word "commit" out of Bash descriptions).

**Quality gate before merge:** `uv run pytest -q` · `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy src`. Acceptance/live tests need the sandbox disabled + `TMPDIR=/var/tmp`; preflight with `task doctor`.

---

## File Structure

**Template payload (rendered into projects — NOT framework source; mirror via render, do not lint as framework code):**
- `src/framework_cli/template/infra/compose/dev.yml.jinja` — *modify:* wrap the `APP_*_URL` literals (app/worker/beat). Otherwise unchanged (dev keeps its container + `depends_on`).
- `src/framework_cli/template/infra/compose/prod.yml.jinja` — *modify:* wrap `APP_DATABASE_URL` (drop `:?` from the inline default); **remove** the `postgres` service, the app `depends_on`, and the `pgdata` volume (they move to `services.yml`).
- `src/framework_cli/template/infra/compose/staging.yml.jinja` — *modify:* identical treatment to `prod.yml`.
- `src/framework_cli/template/infra/compose/services.yml.jinja` — *modify:* wrap worker/beat `APP_*_URL` literals; **add** the always-on `postgres` service (prod-style, carries the `${POSTGRES_PASSWORD:?…}` guard + `uses_postgres_extension` image/preloads), an `app:` fragment carrying `depends_on: postgres`, and the `pgdata` volume; rewrite the header to the composition-seam contract.
- `src/framework_cli/template/infra/compose/tls-ca.yml.jinja` — *create:* opt-in overlay; `app`/`worker`/`beat` fragments mounting `../tls/ca:/etc/ssl/app-ca:ro`.
- `src/framework_cli/template/infra/tls/ca/.gitkeep` — *create:* empty placeholder so the CA mount source dir ships.
- `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja` — *modify:* doc-comment the precedence (env > compose default-literal > Settings default). No behavior change.
- `src/framework_cli/template/.env.example` — *modify (HYBRID; edit inside the `FRAMEWORK:BEGIN/END` region only):* document the `APP_*_URL` overrides + the CA-mount convention.
- `src/framework_cli/template/infra/deploy/README.md` — *modify:* document self-hosted (`-f <env>.yml -f services.yml`) vs managed (omit `services.yml` + set `APP_*_URL`) + `tls-ca.yml`.

**Framework source:**
- `src/framework_cli/integrity/classes.py` — *modify:* move `infra/compose/services.yml` from `LOCKED_TRACKED` to `INTENTIONALLY_UNLOCKED`; add `infra/compose/tls-ca.yml` to `INTENTIONALLY_UNLOCKED`.

**Tests:**
- `tests/test_copier_runner.py` — *modify:* URL-seam render guards; update `test_render_staging_prod_compose` (postgres gone from prod/staging) + `test_render_services_overlay_empty_is_valid` (postgres now always present); add the managed-vs-self-hosted `docker compose config` merge test; add the `tls-ca.yml` render + merge test; doc-string guards.
- `tests/integrity/test_classes.py` — *modify:* assert `services.yml` + `tls-ca.yml` are unlocked, not locked.
- `tests/acceptance/test_rendered_project.py` — *create test:* `test_rendered_project_managed_db_boots_without_colocated_postgres` (live: app boots against an out-of-stack postgres via injected URL, no co-located container).
- `tests/runtime_coverage/registry.py` — *modify:* classify the new `tls-ca.yml` overlay + the relocated postgres surface (EXERCISED via the live test).

---

## Task 1: URL seam — `dev.yml`

**Files:**
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_dev_compose_urls_are_env_overridable(tmp_path: Path):
    """Every APP_*_URL literal in dev.yml is wrapped so the operator's env wins
    (the FWK6 seam), with today's container DSN as the default fallback."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    # app: database URL is overridable, default unchanged
    assert (
        'APP_DATABASE_URL: "${APP_DATABASE_URL:-postgresql+psycopg://app:app@postgres:5432/app}"'
        in dev
    )
    # worker + beat: redis/celery URLs overridable
    for var, default in (
        ("APP_REDIS_URL", "redis://redis:6379/0"),
        ("APP_CELERY_BROKER_URL", "redis://redis:6379/0"),
        ("APP_CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
    ):
        assert f'{var}: "${{{var}:-{default}}}"' in dev, f"{var} not env-overridable in dev.yml"
    # no bare literal APP_*_URL remains (every one is wrapped in ${...:-...})
    import re
    for m in re.finditer(r'^\s*(APP_\w*_URL):\s*"([^"]*)"', dev, re.MULTILINE):
        assert m.group(2).startswith("${"), f"{m.group(1)} still a bare literal: {m.group(2)}"
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_copier_runner.py::test_dev_compose_urls_are_env_overridable -q`
Expected: FAIL (literals are bare, e.g. `APP_DATABASE_URL: "postgresql+psycopg://…"`).

- [ ] **Step 3: Implement — wrap the literals in `dev.yml.jinja`**

In `src/framework_cli/template/infra/compose/dev.yml.jinja`, replace each `APP_*_URL` literal with the `${VAR:-default}` form. The app service:

```yaml
      APP_DATABASE_URL: "${APP_DATABASE_URL:-postgresql+psycopg://app:app@postgres:5432/app}"
```

The `worker` service block:

```yaml
      APP_REDIS_URL: "${APP_REDIS_URL:-redis://redis:6379/0}"
      APP_CELERY_BROKER_URL: "${APP_CELERY_BROKER_URL:-redis://redis:6379/0}"
      APP_CELERY_RESULT_BACKEND: "${APP_CELERY_RESULT_BACKEND:-redis://redis:6379/1}"
      APP_DATABASE_URL: "${APP_DATABASE_URL:-postgresql+psycopg://app:app@postgres:5432/app}"
```

The `beat` service block:

```yaml
      APP_REDIS_URL: "${APP_REDIS_URL:-redis://redis:6379/0}"
      APP_CELERY_BROKER_URL: "${APP_CELERY_BROKER_URL:-redis://redis:6379/0}"
      APP_CELERY_RESULT_BACKEND: "${APP_CELERY_RESULT_BACKEND:-redis://redis:6379/1}"
```

Leave everything else (the `postgres`/`redis`/`mongo` services, `depends_on`, profiles, ports) unchanged — dev keeps its co-located containers.

- [ ] **Step 4: Run it — expect PASS**

Run: `uv run pytest tests/test_copier_runner.py::test_dev_compose_urls_are_env_overridable -q`
Expected: PASS.

- [ ] **Step 5: Regression — the existing dev/compose render tests still pass**

Run: `uv run pytest tests/test_copier_runner.py -q -k "compose or dev or render"`
Expected: PASS (defaults are byte-identical, so structural tests are unaffected).

- [ ] **Step 6: Commit**

Stage `PLAN.md`/`ACTION_LOG.md` (tick + log this task) plus the changed files, then commit (separate `git add` and `git commit` calls):

```bash
git add src/framework_cli/template/infra/compose/dev.yml.jinja tests/test_copier_runner.py PLAN.md ACTION_LOG.md
git commit -m "FWK6: env-overridable APP_*_URL in dev.yml (seam, defaults unchanged)"
```

---

## Task 2: URL seam — `prod.yml`, `staging.yml`, `services.yml`

**Files:**
- Modify: `src/framework_cli/template/infra/compose/prod.yml.jinja`
- Modify: `src/framework_cli/template/infra/compose/staging.yml.jinja`
- Modify: `src/framework_cli/template/infra/compose/services.yml.jinja`
- Test: `tests/test_copier_runner.py`

Note: the inline default for `APP_DATABASE_URL` drops the `:?` guard on the password (`${POSTGRES_PASSWORD}`, not `${POSTGRES_PASSWORD:?…}`) — the empirically-verified fix (eager `:-` interpolation). The `:?` enforcement stays on the `postgres` service (relocated in Task 3).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_production_compose_urls_are_env_overridable(tmp_path: Path):
    """prod/staging app DATABASE_URL and services.yml worker/beat URLs are env-overridable.
    The inline default drops the :? password guard (compose eagerly interpolates the :- branch,
    so a nested :? would break the managed override) — the guard lives on the postgres service."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    comp = dest / "infra" / "compose"
    for env in ("prod", "staging"):
        text = (comp / f"{env}.yml").read_text()
        assert (
            'APP_DATABASE_URL: "${APP_DATABASE_URL:-postgresql+psycopg://app:${POSTGRES_PASSWORD}@postgres:5432/app}"'
            in text
        ), f"{env}.yml APP_DATABASE_URL not env-overridable / still uses :? in default"
        assert "POSTGRES_PASSWORD:?" not in text.split("APP_DATABASE_URL")[1].split("\n")[0], (
            f"{env}.yml inline DSN default must not use the :? guard (breaks managed override)"
        )
    svc = (comp / "services.yml").read_text()
    for var, default in (
        ("APP_REDIS_URL", "redis://redis:6379/0"),
        ("APP_CELERY_BROKER_URL", "redis://redis:6379/0"),
        ("APP_CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
    ):
        assert f'{var}: "${{{var}:-{default}}}"' in svc, f"{var} not env-overridable in services.yml"
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_copier_runner.py::test_production_compose_urls_are_env_overridable -q`
Expected: FAIL.

- [ ] **Step 3: Implement — `prod.yml.jinja` + `staging.yml.jinja`**

In both files, change the app `APP_DATABASE_URL` line from the bare literal to:

```yaml
      APP_DATABASE_URL: "${APP_DATABASE_URL:-postgresql+psycopg://app:${POSTGRES_PASSWORD}@postgres:5432/app}"
```

(Do **not** touch the `postgres` service yet — that move is Task 3.)

- [ ] **Step 4: Implement — `services.yml.jinja` worker/beat URLs**

In `services.yml.jinja`, wrap the worker `APP_REDIS_URL`/`APP_CELERY_BROKER_URL`/`APP_CELERY_RESULT_BACKEND`/`APP_DATABASE_URL` and the beat `APP_REDIS_URL`/`APP_CELERY_BROKER_URL`/`APP_CELERY_RESULT_BACKEND` in the `${VAR:-default}` form. The worker `APP_DATABASE_URL`:

```yaml
      APP_DATABASE_URL: "${APP_DATABASE_URL:-postgresql+psycopg://app:${POSTGRES_PASSWORD}@postgres:5432/app}"
```

and the redis/celery vars exactly as in Task 1 Step 3.

- [ ] **Step 5: Run it — expect PASS**

Run: `uv run pytest tests/test_copier_runner.py::test_production_compose_urls_are_env_overridable -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/infra/compose/prod.yml.jinja src/framework_cli/template/infra/compose/staging.yml.jinja src/framework_cli/template/infra/compose/services.yml.jinja tests/test_copier_runner.py PLAN.md ACTION_LOG.md
git commit -m "FWK6: env-overridable APP_*_URL in prod/staging/services compose"
```

---

## Task 3: Relocate `postgres` + `app → postgres` `depends_on` into `services.yml` (the section-B core)

**Files:**
- Modify: `src/framework_cli/template/infra/compose/prod.yml.jinja` (remove postgres + depends_on + pgdata volume)
- Modify: `src/framework_cli/template/infra/compose/staging.yml.jinja` (same)
- Modify: `src/framework_cli/template/infra/compose/services.yml.jinja` (add postgres + app fragment + pgdata volume)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_copier_runner.py` (and update the two existing tests named in Steps 5–6):

```python
@pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker required for compose config"
)
def test_managed_db_topology_drops_postgres_and_depends_on(tmp_path: Path):
    """FWK6 section B: prod.yml ALONE (managed) has no co-located postgres and the app has
    no dangling depends_on; merging services.yml (self-hosted) restores both — proving the
    overlay seam. Mirrors the empirically-verified depends_on additive-merge behaviour."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # no batteries: postgres is always-on
    comp = dest / "infra" / "compose"
    env = {**os.environ, "APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x"}

    # managed: prod.yml alone (override the DB url so no POSTGRES_PASSWORD is needed)
    managed_env = {**os.environ, "APP_IMAGE": "demo:ci",
                   "APP_DATABASE_URL": "postgresql+psycopg://u:p@managed.example:5432/db"}
    r = subprocess.run(["docker", "compose", "-f", str(comp / "prod.yml"), "config"],
                       capture_output=True, text=True, env=managed_env)
    assert r.returncode == 0, r.stderr
    cfg = yaml.safe_load(r.stdout)
    assert "postgres" not in cfg["services"], "managed prod.yml must not define postgres"
    assert "depends_on" not in cfg["services"]["app"], "managed app must have no depends_on"
    assert "managed.example" in r.stdout, "injected APP_DATABASE_URL must win"

    # self-hosted: prod.yml + services.yml restores postgres + the depends_on edge
    r2 = subprocess.run(
        ["docker", "compose", "-f", str(comp / "prod.yml"), "-f", str(comp / "services.yml"), "config"],
        capture_output=True, text=True, env=env,
    )
    assert r2.returncode == 0, r2.stderr
    cfg2 = yaml.safe_load(r2.stdout)
    assert "postgres" in cfg2["services"], "self-hosted merge must define postgres"
    assert cfg2["services"]["app"]["depends_on"]["postgres"]["condition"] == "service_healthy"
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_copier_runner.py::test_managed_db_topology_drops_postgres_and_depends_on -q`
Expected: FAIL (today `postgres` is still in `prod.yml`, so the managed assertion fails).

- [ ] **Step 3: Implement — remove postgres from `prod.yml.jinja` and `staging.yml.jinja`**

In **both** files: delete the entire `postgres:` service block, the app's `depends_on:` block, and the trailing `volumes:`/`pgdata` block. After the edit, `prod.yml.jinja` is:

```yaml
# Production topology — the SAME registry image promoted from staging (no rebuild), run
# against this definition by the configured deploy strategy. Secrets from the target env.
# The co-located postgres + its depends_on live in services.yml (the self-hosted overlay):
# self-hosted = `-f prod.yml -f services.yml`; managed = omit services.yml + set APP_DATABASE_URL.
services:
  app:
    image: ${APP_IMAGE:?set APP_IMAGE to the promoted registry tag}
    restart: unless-stopped
    environment:
      TZ: UTC
      APP_ENVIRONMENT: prod
      APP_DATABASE_URL: "${APP_DATABASE_URL:-postgresql+psycopg://app:${POSTGRES_PASSWORD}@postgres:5432/app}"
    ports:
      - "8000:8000"
    # Liveness so `restart: unless-stopped` can recover a wedged app. start_period covers
    # migrate+seed on first start (the image entrypoint runs them before uvicorn serves).
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/heartbeat').status==200 else 1)"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 30s
```

`staging.yml.jinja` is the same with `APP_ENVIRONMENT: staging` and its existing header wording (keep its "production-equivalent" comment; append the same self-hosted/managed note).

- [ ] **Step 4: Implement — add postgres + app fragment + volume to `services.yml.jinja`**

The relocated `postgres` block uses the **prod-style** image (the `${POSTGRES_IMAGE}` / `postgres:17` conditional + preloads, identical to what `prod.yml` had) and keeps the `${POSTGRES_PASSWORD:?…}` guard. It is **always** present (postgres is always-on, not battery-gated), so it goes *outside* the battery `{% if %}` that wraps mongo/redis/worker/beat.

Restructure `services.yml.jinja` so its top is always-on and the battery block follows. The new top (replacing the current `{%- if "mongodb" … %}\nservices:` opener with an always-on `services:`):

```jinja
# Self-hosted data-store + worker overlay for staging/prod, merged by the deploy
# (infra/deploy/strategy.sh) alongside observability.yml:
#   -f $DEPLOY_ENV.yml -f services.yml -f observability.yml
# This file is a COMPOSITION SEAM (intentionally unlocked) — edit it for your topology:
#   * Self-hosted stores: keep the services below (the default).
#   * Managed stores (RDS / ElastiCache / Atlas / native / tunneled): delete the store
#     service(s) you are externalising and set the matching APP_*_URL in the target env;
#     the app/worker/beat depends_on edges for a removed store go with it. The DSN is
#     opaque — put multi-host failover strings or ?sslmode=verify-full&sslrootcert=… in it.
#   * TLS verify-full to a managed store: also merge -f tls-ca.yml and drop your CA bundle
#     in infra/tls/ca/ (see that file).
services:
  # Always-on relational store (self-hosted). Remove this + set APP_DATABASE_URL for managed PG.
  postgres:
{%- if uses_postgres_extension %}
    image: ${POSTGRES_IMAGE:?set POSTGRES_IMAGE to the built+pushed custom Postgres tag (extensions baked in)}
{%- else %}
    image: postgres:17
{%- endif %}
{%- set _preloads = [] %}
{%- if "timescaledb" in batteries %}{% set _ = _preloads.append("timescaledb") %}{% endif %}
{%- if "age" in batteries %}{% set _ = _preloads.append("age") %}{% endif %}
{%- if _preloads %}
    command: ["postgres", "-c", "shared_preload_libraries={{ _preloads | join(',') }}"]
{%- endif %}
    restart: unless-stopped
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in the target environment}
      POSTGRES_DB: app
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
    volumes:
      - "pgdata:/var/lib/postgresql/data"

  # depends_on fragment: merged onto prod.yml/staging.yml's app so it waits for the
  # co-located postgres. Dropped automatically in the managed case (this file omitted).
  app:
    depends_on:
      postgres:
        condition: service_healthy
```

Then the existing `{%- if "mongodb" … %}` battery block (mongo/redis/worker/beat) follows **unchanged except** it must no longer re-open `services:` (it is now under the always-on `services:` above — remove its `services:` line). Finally the `volumes:` section must always declare `pgdata` (and conditionally the battery volumes):

```jinja
volumes:
  pgdata: {}
{%- if "mongodb" in batteries %}
  mongodata: {}
{%- endif %}
{%- if "workers" in batteries or "redis" in batteries %}
  redisdata: {}
{%- endif %}
```

- [ ] **Step 5: Update `test_render_staging_prod_compose`**

The relocated postgres means prod/staging no longer define it. Change the loop body (was asserting `compose["services"]["postgres"]`):

```python
def test_render_staging_prod_compose(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    for env in ("staging", "prod"):
        path = dest / "infra" / "compose" / f"{env}.yml"
        assert path.is_file(), f"{env}.yml missing"
        compose = yaml.safe_load(path.read_text())
        app = compose["services"]["app"]
        assert "build" not in app, f"{env} must run the pushed image, not build"
        assert "${APP_IMAGE" in app["image"]
        assert app["environment"]["APP_ENVIRONMENT"] == env
        assert app["restart"] == "unless-stopped"
        # FWK6: postgres + depends_on now live in services.yml (the self-hosted overlay)
        assert "postgres" not in compose["services"], f"{env}.yml must not define postgres (moved to services.yml)"
        assert "depends_on" not in app, f"{env}.yml app must have no inline depends_on (moved to services.yml)"
```

- [ ] **Step 6: Update `test_render_services_overlay_empty_is_valid`**

postgres is now always in services.yml, so the "no-battery → no services" assertion is wrong. Replace it:

```python
def test_render_services_overlay_always_has_postgres(tmp_path: Path):
    """FWK6: services.yml is the self-hosted store overlay; postgres (always-on) is present
    even with no battery, and the app fragment carries the depends_on edge."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # no batteries
    cfg = yaml.safe_load((dest / "infra" / "compose" / "services.yml").read_text())
    assert "postgres" in cfg["services"]
    assert cfg["services"]["app"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert "pgdata" in cfg["volumes"]
    # battery stores still absent without their batteries
    assert "mongo" not in cfg["services"] and "redis" not in cfg["services"]
```

- [ ] **Step 7: Run the affected render tests — expect PASS**

Run: `uv run pytest tests/test_copier_runner.py -q -k "managed_db_topology or staging_prod_compose or services_overlay or prod_plus_services or dev_and_services_images"`
Expected: PASS. (`test_prod_plus_services_plus_obs_merges` still passes — postgres now comes from services.yml in that merge.)

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/template/infra/compose/prod.yml.jinja src/framework_cli/template/infra/compose/staging.yml.jinja src/framework_cli/template/infra/compose/services.yml.jinja tests/test_copier_runner.py PLAN.md ACTION_LOG.md
git commit -m "FWK6: relocate postgres + depends_on to services.yml (managed = omit overlay)"
```

---

## Task 4: `services.yml` → `INTENTIONALLY_UNLOCKED` (section D)

**Files:**
- Modify: `src/framework_cli/integrity/classes.py`
- Test: `tests/integrity/test_classes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/integrity/test_classes.py`:

```python
def test_services_overlay_is_a_composition_seam_not_locked():
    """FWK6: services.yml is now operator-edited (managed URLs, omit stores), so it is an
    intentional composition seam, not a checksummed locked file."""
    from framework_cli.integrity.classes import INTENTIONALLY_UNLOCKED, LOCKED_TRACKED

    assert "infra/compose/services.yml" in INTENTIONALLY_UNLOCKED
    assert "infra/compose/services.yml" not in LOCKED_TRACKED
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/integrity/test_classes.py::test_services_overlay_is_a_composition_seam_not_locked -q`
Expected: FAIL (`services.yml` is in `LOCKED_TRACKED`).

- [ ] **Step 3: Implement**

In `src/framework_cli/integrity/classes.py`: remove `"infra/compose/services.yml",` from `LOCKED_TRACKED` (line ~36), and add to `INTENTIONALLY_UNLOCKED`:

```python
    "infra/compose/services.yml",  # FWK6: self-hosted store overlay — operators edit it (managed URLs / omit stores)
```

- [ ] **Step 4: Run it + the full integrity suite — expect PASS**

Run: `uv run pytest tests/integrity/ -q`
Expected: PASS (no stale-entry / coverage failures — the rendered file still exists; it is just no longer checksummed).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/classes.py tests/integrity/test_classes.py PLAN.md ACTION_LOG.md
git commit -m "FWK6: services.yml is a composition seam (INTENTIONALLY_UNLOCKED)"
```

---

## Task 5: Opt-in CA-bundle overlay `tls-ca.yml` (section C)

**Files:**
- Create: `src/framework_cli/template/infra/compose/tls-ca.yml.jinja`
- Create: `src/framework_cli/template/infra/tls/ca/.gitkeep`
- Modify: `src/framework_cli/integrity/classes.py` (add `infra/compose/tls-ca.yml` to `INTENTIONALLY_UNLOCKED`)
- Test: `tests/test_copier_runner.py`, `tests/integrity/test_classes.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_copier_runner.py`:

```python
def test_tls_ca_overlay_renders_off_by_default(tmp_path: Path):
    """FWK6 section C: an opt-in CA-bundle overlay ships with an (empty) mount dir, so it is
    inert until the operator drops a bundle and merges it. No effect on the default topology."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    comp = dest / "infra" / "compose"
    overlay = comp / "tls-ca.yml"
    assert overlay.is_file()
    cfg = yaml.safe_load(overlay.read_text())
    # mounts the conventional CA path read-only onto each store client
    for svc in ("app", "worker", "beat"):
        vols = cfg["services"][svc]["volumes"]
        assert any("/etc/ssl/app-ca" in v for v in vols), f"{svc} missing CA mount"
    # the mount source dir ships (empty placeholder)
    assert (dest / "infra" / "tls" / "ca" / ".gitkeep").is_file()


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker required for compose config"
)
def test_prod_plus_tls_ca_merges(tmp_path: Path):
    """prod.yml + services.yml + tls-ca.yml is a valid merge and the app gains the CA mount."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    comp = dest / "infra" / "compose"
    env = {**os.environ, "APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x"}
    r = subprocess.run(
        ["docker", "compose", "-f", str(comp / "prod.yml"), "-f", str(comp / "services.yml"),
         "-f", str(comp / "tls-ca.yml"), "config"],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, r.stderr
    assert "/etc/ssl/app-ca" in r.stdout
```

Add to `tests/integrity/test_classes.py`:

```python
def test_tls_ca_overlay_is_intentionally_unlocked():
    from framework_cli.integrity.classes import INTENTIONALLY_UNLOCKED
    assert "infra/compose/tls-ca.yml" in INTENTIONALLY_UNLOCKED
```

- [ ] **Step 2: Run them — expect FAIL**

Run: `uv run pytest tests/test_copier_runner.py::test_tls_ca_overlay_renders_off_by_default tests/integrity/test_classes.py::test_tls_ca_overlay_is_intentionally_unlocked -q`
Expected: FAIL (files/classification absent).

- [ ] **Step 3: Create `tls-ca.yml.jinja`**

`src/framework_cli/template/infra/compose/tls-ca.yml.jinja`:

```jinja
# Opt-in TLS CA-bundle overlay (FWK6). Merge this when the app/worker/beat connect to a
# managed data store that requires verify-full TLS:
#   -f prod.yml -f services.yml -f tls-ca.yml   (omit services.yml if the store is managed)
# Drop your CA bundle at infra/tls/ca/<name>.pem (the dir ships empty) and reference it in
# the opaque DSN, e.g. APP_DATABASE_URL=...?sslmode=verify-full&sslrootcert=/etc/ssl/app-ca/<name>.pem
# Off by default: nothing references the mounted path unless your DSN does.
services:
  app:
    volumes:
      - "../tls/ca:/etc/ssl/app-ca:ro"
{%- if "workers" in batteries %}
  worker:
    volumes:
      - "../tls/ca:/etc/ssl/app-ca:ro"
  beat:
    volumes:
      - "../tls/ca:/etc/ssl/app-ca:ro"
{%- endif %}
```

- [ ] **Step 4: Create the placeholder dir**

Create `src/framework_cli/template/infra/tls/ca/.gitkeep` with content:

```
# FWK6: drop a managed-store CA bundle here (e.g. rds-ca.pem) and merge -f tls-ca.yml.
# This dir ships empty; the read-only mount of an empty dir is inert.
```

- [ ] **Step 5: Classify in integrity**

In `src/framework_cli/integrity/classes.py`, add to `INTENTIONALLY_UNLOCKED`:

```python
    "infra/compose/tls-ca.yml",  # FWK6: opt-in CA-bundle TLS overlay — operator-supplied bundle + DSN param
```

- [ ] **Step 6: Run them — expect PASS**

Run: `uv run pytest tests/test_copier_runner.py -q -k "tls_ca" && uv run pytest tests/integrity/ -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/infra/compose/tls-ca.yml.jinja src/framework_cli/template/infra/tls/ca/.gitkeep src/framework_cli/integrity/classes.py tests/test_copier_runner.py tests/integrity/test_classes.py PLAN.md ACTION_LOG.md
git commit -m "FWK6: opt-in tls-ca.yml CA-bundle overlay (off by default)"
```

---

## Task 6: Docs — Settings precedence, `.env.example`, deploy README

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja`
- Modify: `src/framework_cli/template/.env.example` (HYBRID — edit **inside** the `FRAMEWORK:BEGIN/END` region)
- Modify: `src/framework_cli/template/infra/deploy/README.md`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_datastore_runtime_docs_present(tmp_path: Path):
    """FWK6: the managed/self-hosted runtime contract is documented where operators look."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    env_example = (dest / ".env.example").read_text()
    assert "APP_DATABASE_URL" in env_example and "managed" in env_example.lower()
    readme = (dest / "infra" / "deploy" / "README.md").read_text()
    assert "services.yml" in readme and "managed" in readme.lower()
    # the managed contract: omit services.yml + set the URL
    assert "tls-ca.yml" in readme
    settings = (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "APP_DATABASE_URL" in settings  # precedence note references the env var
```

(Adjust `demo` to the rendered package dir if `DATA`'s slug differs; match the existing tests' convention in the file.)

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_copier_runner.py::test_datastore_runtime_docs_present -q`
Expected: FAIL.

- [ ] **Step 3: Settings precedence comment**

In `settings.py.jinja`, above the `database_url` field, extend the existing comment to state precedence (no code change):

```python
    # Database connection (SQLAlchemy URL). Resolution precedence: APP_DATABASE_URL in the
    # environment (set by the operator for a managed/external store) > the compose file's
    # ${APP_DATABASE_URL:-…} default (the co-located container DSN) > this Settings default
    # (out-of-compose fallback for host tooling / tests). The DSN is opaque — failover hosts
    # and ?sslmode=verify-full&sslrootcert=… all go here.
    database_url: str = "postgresql+psycopg://app:app@postgres:5432/app"
```

- [ ] **Step 4: `.env.example` (inside the FRAMEWORK region)**

Add, **between** the existing `# FRAMEWORK:BEGIN` and `# FRAMEWORK:END` markers (do not add the token in prose — see [[hybrid-region-marker-token-in-prose]]; refer to "the closing marker"):

```bash
# Data-store runtime (FWK6): leave unset to use the co-located container; set to point at a
# managed / native / tunneled store (the value is an opaque DSN — failover hosts, TLS params
# all allowed). For a managed deploy, omit services.yml from the compose merge and set these.
# APP_DATABASE_URL=postgresql+psycopg://USER:PASS@managed-host:5432/db?sslmode=verify-full&sslrootcert=/etc/ssl/app-ca/ca.pem
# APP_REDIS_URL=redis://managed-host:6379/0
# APP_MONGO_URL=mongodb://managed-host:27017/app
```

- [ ] **Step 5: Deploy README**

In `infra/deploy/README.md`, add a `## Data-store runtime (self-hosted vs managed)` section documenting: self-hosted = `docker compose -f <env>.yml -f services.yml -f observability.yml up -d` (postgres + worker/beat run locally); managed = omit `services.yml`, set `APP_DATABASE_URL`/`APP_REDIS_URL`/`APP_MONGO_URL` in the target env; TLS verify-full = also `-f tls-ca.yml` + drop the CA bundle in `infra/tls/ca/`.

- [ ] **Step 6: Run it — expect PASS**

Run: `uv run pytest tests/test_copier_runner.py::test_datastore_runtime_docs_present -q`
Expected: PASS.

- [ ] **Step 7: Verify the hybrid region still validates + rendered format is clean**

Run: `uv run pytest tests/test_copier_runner.py -q -k "hybrid or env_example or integrity"` then render once and `uv run ruff format --check` the rendered `settings.py` ([[ruff-format-check-after-inline-edits]]).
Expected: PASS / clean.

- [ ] **Step 8: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja" src/framework_cli/template/.env.example src/framework_cli/template/infra/deploy/README.md tests/test_copier_runner.py PLAN.md ACTION_LOG.md
git commit -m "FWK6: document the managed/self-hosted data-store runtime contract"
```

---

## Task 7: Live acceptance test — app boots against an out-of-stack DB

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`

This is the real end-to-end proof a render diff can't give (per the FWK20/FWK24 pattern): the app, in the **managed** topology, reaches a postgres that is **not** in its compose stack and is **not** depended-on. Read the existing `_run_image_serving` helper (FWK21) and `_compose_env`/`_free_tcp_port` before writing; reuse them.

- [ ] **Step 1: Write the failing test**

Add to `tests/acceptance/test_rendered_project.py` (adapt names to the helpers actually present):

```python
@pytest.mark.skipif(shutil.which("docker") is None, reason="docker required")
def test_rendered_project_managed_db_boots_without_colocated_postgres(tmp_path: Path):
    """FWK6: prove the managed seam live. Start a standalone postgres OUTSIDE the project's
    stack, render + build the project image, run it from prod.yml ALONE (no services.yml ->
    no co-located postgres, no depends_on) with APP_DATABASE_URL injected at the standalone
    DB, and assert /heartbeat 200 (the app booted + migrated against the external store)."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    pg_port = _free_tcp_port()
    pg_name = f"fwk6-extpg-{pg_port}"
    # 1) standalone postgres, not part of the project compose stack
    subprocess.run(
        ["docker", "run", "-d", "--name", pg_name, "-e", "POSTGRES_USER=app",
         "-e", "POSTGRES_PASSWORD=app", "-e", "POSTGRES_DB=app",
         "-p", f"{pg_port}:5432", "postgres:17"],
        check=True, capture_output=True, text=True,
    )
    try:
        # 2) build the project image
        subprocess.run(["docker", "build", "-f", "infra/docker/Dockerfile", "-t", "fwk6-managed:ci", "."],
                       cwd=dest, check=True, capture_output=True, text=True)
        app_port = _free_tcp_port()
        ext_url = f"postgresql+psycopg://app:app@host.docker.internal:{pg_port}/app"
        # 3) run the image (managed topology: prod.yml's app, no co-located postgres)
        cname = f"fwk6-managed-{app_port}"
        subprocess.run(
            ["docker", "run", "-d", "--name", cname,
             "--add-host", "host.docker.internal:host-gateway",
             "-e", "APP_ENVIRONMENT=prod", "-e", f"APP_DATABASE_URL={ext_url}",
             "-p", f"{app_port}:8000", "fwk6-managed:ci"],
            check=True, capture_output=True, text=True,
        )
        try:
            _poll_until_200(f"http://127.0.0.1:{app_port}/heartbeat", timeout=60)
        finally:
            subprocess.run(["docker", "logs", cname], capture_output=True, text=True)
            subprocess.run(["docker", "rm", "-f", cname], capture_output=True, text=True)
    finally:
        subprocess.run(["docker", "rm", "-f", pg_name], capture_output=True, text=True)
```

Use the file's existing readiness poller (e.g. the helper `_run_image_serving` uses); if none is exposed, inline a `urllib`-based poll mirroring the app healthcheck. Confirm the entrypoint runs migrations against `APP_DATABASE_URL` (it does — `scripts/entrypoint.sh`), so `/heartbeat` 200 proves the external DB was reachable and migrated.

- [ ] **Step 2: Run it — expect FAIL (or RED for the right reason)**

Run (sandbox disabled, `TMPDIR=/var/tmp`): `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_managed_db_boots_without_colocated_postgres -q`
Expected: with the Task-3 changes already in, this should PASS; to bite-prove it, temporarily inject the literal `APP_DATABASE_URL` back into `prod.yml` (or point `ext_url` at a dead port) and confirm it FAILS — then revert. Record the bite in the commit message.

- [ ] **Step 3: Confirm GREEN + classify the run**

Run: same command → PASS. Capture the container `/heartbeat` 200 as the proof.

- [ ] **Step 4: Commit**

```bash
git add tests/acceptance/test_rendered_project.py PLAN.md ACTION_LOG.md
git commit -m "FWK6: live acceptance — managed-topology app boots against out-of-stack DB"
```

---

## Task 8: FWK29 runtime-coverage classification + branch-end gate

**Files:**
- Modify: `tests/runtime_coverage/registry.py`
- Test: `tests/runtime_coverage/` (the `gate`-tier `test_every_surface_is_classified`)

- [ ] **Step 1: Run the completeness check to surface the new unclassified surfaces**

Run: `uv run pytest tests/runtime_coverage/ -q`
Expected: FAIL — `test_every_surface_is_classified` reports the new `tls-ca.yml` overlay (and possibly the relocated postgres/`app` fragment surface in `services.yml`) as unclassified. Read the failure to get the exact surface keys ([[fwk29-coverage-registry-gate]]).

- [ ] **Step 2: Classify the new surfaces**

In `tests/runtime_coverage/registry.py`, add entries for the surfaces the failure names. The `tls-ca.yml` overlay + the relocated postgres are **EXERCISED** by Task 7's live test (managed boot) and the Task-3/Task-5 `docker compose config` merge tests. Use the existing entry style in that file (match the surrounding `EXERCISED(...)`/reason format exactly):

```python
    # FWK6: data-store runtime parity
    "overlay:tls-ca.yml": EXERCISED("test_prod_plus_tls_ca_merges + tls-ca off-by-default render guard"),
    # postgres relocated dev->services overlay; managed-omit path proven live
    # (adjust the key to the one enumerate.py emits for the services.yml postgres service)
```

If `enumerate.py` emits a different key for the relocated postgres (e.g. `service:services.yml:postgres`), classify that exact key as `EXERCISED("test_rendered_project_managed_db_boots_without_colocated_postgres + test_managed_db_topology_drops_postgres_and_depends_on")` and re-point any now-stale `dev.yml` postgres KNOWN_GAP/EXEMPT entry.

- [ ] **Step 3: Run it — expect PASS**

Run: `uv run pytest tests/runtime_coverage/ -q`
Expected: PASS (set-equality + reference-integrity green).

- [ ] **Step 4: Commit**

```bash
git add tests/runtime_coverage/registry.py PLAN.md ACTION_LOG.md
git commit -m "FWK6: classify tls-ca overlay + relocated postgres surfaces (FWK29)"
```

- [ ] **Step 5: Branch-end quality gate + reviews**

Run the framework gate:

```bash
uv run pytest -q -k "not acceptance"   # or the gate-tier set
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Then the two branch-end reviews (per the review-model policy): a **spec-compliance** review (Sonnet) against this plan + the spec, and a **code-quality / whole-branch** review (**Opus**). Address findings; re-run the gate.

- [ ] **Step 6: Update state + open the PR**

Move FWK6 to `Done` in `PLAN.md`; final `ACTION_LOG.md` entry. Confirm the release note: template-payload change, defaults byte-identical, **release-deferred** (batches with FWK36/FWK37). Open the PR against `master` (required checks: `gate` + `build` + `render-complete`; [[render-matrix-dockerhub-flake-triage]] if render-matrix is red on an unrelated combo).

---

## Self-Review (completed during authoring)

**Spec coverage:** §A (URL seam) → Tasks 1–2. §B (conditional container/depends_on) → Task 3 (empirically pre-verified). §C (CA mount) → Task 5. §D (services.yml unlock) → Task 4. Testing (render + merge + live + env-override) → Tasks 1–3, 5, 7. FWK29 → Task 8. Docs/precedence → Task 6. Release framing → Task 8 Step 6. **No gaps.**

**Placeholder scan:** every code step carries concrete content; the two "adjust to the exact key the enumerator emits" notes in Task 8 are deliberate (the FWK29 key string is generated, read at red-time) and bounded with the fallback spelled out — not a TODO.

**Type/name consistency:** test names, the `${APP_*_URL:-…}` form, the `${POSTGRES_PASSWORD}` (no `:?`) inline-default decision, and `services.yml`/`tls-ca.yml` paths are consistent across tasks and match the verified compose behaviour. `INTENTIONALLY_UNLOCKED` / `LOCKED_TRACKED` symbol names match `integrity/classes.py`.
