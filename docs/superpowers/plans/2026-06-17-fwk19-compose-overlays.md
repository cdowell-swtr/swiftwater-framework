# FWK19 — Non-dev compose overlays config-validated + `test.yml` up live — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans`. Read the shared
> policy first: `docs/superpowers/plans/2026-06-17-coverage-batch-execution-policy.md` (branch
> `fwk-coverage-batch`, commit cadence + skip-marker gate, real-bug rule, **no release**,
> laptop/`TMPDIR=/var/tmp`, non-vacuity). This is item **#5** of the batch and lands **after
> FWK24, FWK23, FWK26, and FWK25**. Steps use `- [ ]`.

**Goal:** Close M3 (`test.yml` brought up live — `--profile test`, tmpfs ephemeral-DB reset
asserted) and H7/demoted parity (`staging.yml` + batteries-on `services.yml` get the same
`docker compose config` merge-validation prod.yml already has). Two halves:

- **Half A — CI-visible config-validation (in `tests/test_copier_runner.py`):** `staging.yml`
  and `services.yml` currently have zero `docker compose config` merge-validation —
  `staging.yml` is only `.read_text()` substring-checked; `services.yml` renders the battery
  overlay but never passes it through the compose parser with batteries on. Add two new
  functions matching the style + decorator of the existing
  `test_prod_plus_overlay_merges_with_obs_stack` (line 1998) and
  `test_prod_plus_services_plus_obs_merges` (line 2159), both decorated
  `@pytest.mark.skipif(shutil.which("docker") is None, reason="docker required for compose config")`.
  These are **CI-visible** (the CI gate runs `docker compose config`; no daemon is needed
  because `config` only parses + resolves the YAML and interpolates env vars — the daemon is
  never contacted).

- **Half B — acceptance-tier live bring-up (in `tests/acceptance/test_rendered_project.py`):**
  `test.yml` is shipped and documented in `Taskfile.yml.jinja` (`task test:stack`), but the
  acceptance tier never uses `--profile test` — the tmpfs ephemeral-DB reset (`postgres-test`,
  `tmpfs: - /var/lib/postgresql/data`) is completely undriven. Add one acceptance-tier test:
  render → `docker compose -f base.yml -f test.yml --profile test up -d --build` → poll the
  app `/health` until 200 → assert the tmpfs reset (bring the stack down + up again and assert
  the DB is empty). This test is **docker-gated, local-only** (the same `skipif not
  _docker_available()` gate the other acceptance tests use).

**Architecture decision — test.yml port exposure:** `base.yml` defines no port for the `app`
service (only Traefik labels; the `dev.yml` overlay adds `${HTTP_HOST_PORT:-8000}:8000`).
`test.yml` adds `profiles: ["test"]` + the `postgres-test` DB override but **no port binding** —
so `docker compose -f base.yml -f test.yml --profile test` never exposes the app on a host port.
`task test:stack` (Taskfile.yml.jinja:103) runs the stack attached (no `-d`), so it never needs
to call back in from the host. The acceptance test DOES need a host port to poll `/health`. The
plan resolves this with a **one-line inline override file** (mirroring the FWK24 webhook
override pattern in `test_rendered_per_battery_routes_through_traefik`): write a
`fwk19.override.yml` into the rendered project that adds
`services: app: ports: ["${HTTP_HOST_PORT:-8000}:8000"]`, append it to the `-f` list, and
discover the assigned port via `_compose_host_port` (FWK31). The override is ephemeral (lives
only in `tmp_path`). **This is the preferred path.** If the override approach goes wrong (e.g.,
the port env var is not propagated correctly to `--profile test`), the anticipated-real-bugs note
flags it — but it should work because `_isolate_compose_project` sets `HTTP_HOST_PORT=0` in the
test environment and the override merges cleanly.

**Harnesses (do NOT redefine):** `_compose_env`, `_compose_host_port`, `_free_tcp_port`,
`_isolate_compose_project` (all in `tests/acceptance/test_rendered_project.py`). The
`_isolate_compose_project` autouse fixture sets `HTTP_HOST_PORT=0` (among other port vars) so
the ephemeral port assignment is automatic — no manual port var override needed. DB-empty check
uses the FWK20 `compose exec -T` pattern: `compose exec -T postgres-test psql -U app -d app
-tAc "SELECT count(*) FROM alembic_version"` (or any stable seeded table) to prove the DB is
empty after a fresh tmpfs restart. `alembic_version` is always created by `alembic upgrade head`
and has at least one row on a live app; after a tmpfs reset it is gone (the DB is fresh).

**Tech Stack:** Python, pytest, Docker, postgres:17 (or the custom postgres.Dockerfile for
extension batteries), the existing acceptance and test_copier_runner harnesses.

---

## File Structure

- **Modify** `tests/test_copier_runner.py` — add two config-validation tests:
  `test_staging_plus_services_merges` (Half A, staging.yml standalone) and
  `test_staging_plus_services_overlay_merges` (Half A, staging.yml + batteries-on services.yml).
- **Modify** `tests/acceptance/test_rendered_project.py` — add one live acceptance test:
  `test_rendered_test_profile_stack_serves_and_resets_db` (Half B, test.yml live + tmpfs reset).
- **Modify** `tests/runtime_coverage/registry.py` — flip 11 KNOWN_GAP entries to EXERCISED
  (detailed in Task 3 below; the test must exist before the flip per
  `test_exercised_entries_name_an_existing_test`).
- **Modify** `PLAN.md` + `ACTION_LOG.md` (per the shared policy — required staged on every
  commit).

**No template change expected** (test-only). If a test goes red on a real template defect — a
broken staging.yml `${POSTGRES_PASSWORD:?}` interpolation, a malformed services.yml battery
conditional, a test.yml port-exposure gap, a broken tmpfs reset — follow the shared real-bug
policy (root-cause → small scoped fix + CI-visible guard + deferred release, OR xfail + new
FWK id + ACTION_LOG + morning-report line).

---

## Task 1: Half A — `staging.yml` + batteries-on `services.yml` config-validation
(in `tests/test_copier_runner.py`)

**Files:** Modify `tests/test_copier_runner.py` (place after
`test_prod_plus_services_plus_obs_merges`, ~line 2220).

- [ ] **Step 1: Write the two config-validation tests.**

  **Context from the existing prod.yml tests:**
  - Both existing tests are decorated
    `@pytest.mark.skipif(shutil.which("docker") is None, reason="docker required for compose config")`.
  - They pass `env = {**os.environ, "APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x"}` to
    `subprocess.run`. `staging.yml` uses `${APP_IMAGE:?...}` and `${POSTGRES_PASSWORD:?...}`
    (staging.yml.jinja:6,11,41), so both env vars are REQUIRED for `config` to succeed — the
    `:?` syntax makes compose fail with an error if the var is unset. Services.yml worker/beat
    also require `${APP_IMAGE:?...}` (services.yml.jinja:36,60) and `${POSTGRES_PASSWORD:?...}`
    (services.yml.jinja:41). The test-local env `{"APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x"}`
    satisfies both (matching the prod.yml tests exactly).
  - The `comp = dest / "infra" / "compose"` path convention is shared across both existing tests.

```python
@pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker required for compose config"
)
def test_staging_standalone_merges(tmp_path: Path) -> None:
    """compose config merge-validation: staging.yml standalone is a valid topology.

    Mirrors the prod.yml guard: staging.yml is self-contained (no base.yml merge needed —
    it defines both `app` and `postgres` directly). Asserts the two named services are
    present, the image slot resolves, and the POSTGRES_PASSWORD env var is threaded through
    the postgres service. Two scenarios:
    1. Baseline (no extensions) — image: postgres:17.
    2. Extension battery (timescaledb) — conditional command + POSTGRES_IMAGE var.
    """
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    comp = dest / "infra" / "compose"
    env = {**os.environ, "APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x"}

    # --- Scenario 1: baseline staging.yml (no extension) ---
    r = subprocess.run(
        ["docker", "compose", "-f", str(comp / "staging.yml"), "config"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0, f"staging.yml config failed:\n{r.stderr}"
    for svc in ("app", "postgres"):
        assert svc in r.stdout, f"service '{svc}' missing from staging.yml config"
    assert "APP_ENVIRONMENT: staging" in r.stdout, (
        "APP_ENVIRONMENT not set to 'staging' in staging.yml config"
    )
    assert "unless-stopped" in r.stdout, (
        "restart: unless-stopped missing from staging.yml config (staging services must restart)"
    )

    # --- Scenario 2: timescaledb extension — conditional command key ---
    dest2 = tmp_path / "demo_ts"
    render_project(dest2, {**DATA, "batteries": ["timescaledb"]})
    comp2 = dest2 / "infra" / "compose"
    env_ts = {**os.environ, "APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x",
              "POSTGRES_IMAGE": "demo-postgres:ci"}
    r2 = subprocess.run(
        ["docker", "compose", "-f", str(comp2 / "staging.yml"), "config"],
        capture_output=True,
        text=True,
        env=env_ts,
    )
    assert r2.returncode == 0, f"staging.yml (timescaledb) config failed:\n{r2.stderr}"
    assert "shared_preload_libraries=timescaledb" in r2.stdout, (
        "timescaledb preload command missing from staging.yml (timescaledb battery) config"
    )


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker required for compose config"
)
def test_staging_plus_services_overlay_merges(tmp_path: Path) -> None:
    """compose config merge-validation: staging.yml + services.yml + observability.yml
    is a valid merged topology (the canonical staging deploy merge: strategy.sh uses
    `-f staging.yml -f services.yml -f observability.yml`).

    Asserts: all battery services (worker/beat/redis/mongo) + app/postgres + both battery
    exporters appear; worker/beat carry APP_RUN_MIGRATIONS=false + the promoted image.
    Mirrors test_prod_plus_services_plus_obs_merges (line 2159) for staging.yml.
    """
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb", "workers"]})
    comp = dest / "infra" / "compose"
    env = {**os.environ, "APP_IMAGE": "demo:ci", "POSTGRES_PASSWORD": "x"}

    r = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(comp / "staging.yml"),
            "-f",
            str(comp / "services.yml"),
            "-f",
            str(comp / "observability.yml"),
            "config",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0, (
        f"staging.yml + services.yml + observability.yml config failed:\n{r.stderr}"
    )
    for svc in (
        "worker",
        "beat",
        "redis",
        "mongo",
        "app",
        "postgres",
        "mongodb-exporter",
        "celery-exporter",
        "prometheus",
    ):
        assert svc in r.stdout, f"service '{svc}' missing from staging+services+obs merge"
    # worker/beat run the promoted image with APP_RUN_MIGRATIONS=false (services.yml:40,64)
    assert "APP_RUN_MIGRATIONS" in r.stdout and "demo:ci" in r.stdout, (
        "worker/beat APP_RUN_MIGRATIONS=false or APP_IMAGE not in staging+services merge"
    )
    # staging app carries APP_ENVIRONMENT: staging (not dev — the merge order must not
    # let dev.yml's default win; staging.yml is the base, no dev.yml in this merge)
    assert "APP_ENVIRONMENT: staging" in r.stdout, (
        "APP_ENVIRONMENT is not 'staging' in the staging+services merge — wrong merge order"
    )

    # services.yml without batteries → no worker/beat/redis/mongo (no phantom services)
    dest2 = tmp_path / "demo_bare"
    render_project(dest2, {**DATA})  # no batteries
    comp2 = dest2 / "infra" / "compose"
    r2 = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(comp2 / "staging.yml"),
            "-f",
            str(comp2 / "services.yml"),
            "config",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r2.returncode == 0, (
        f"staging.yml + services.yml (no batteries) config failed:\n{r2.stderr}"
    )
    assert "worker" not in r2.stdout and "redis" not in r2.stdout, (
        "worker or redis appeared in staging+services (no batteries) merge — "
        "services.yml battery guard is broken"
    )
```

- [ ] **Step 2: Run — expect GREEN.**
  ```
  uv run pytest tests/test_copier_runner.py::test_staging_standalone_merges \
      tests/test_copier_runner.py::test_staging_plus_services_overlay_merges -q
  ```
  If compose exits non-zero on `staging.yml`, the most likely causes are:
  - The `${APP_IMAGE:?...}` or `${POSTGRES_PASSWORD:?...}` `:?` required-var syntax fails
    despite the env being set → check that `env` is passed to `subprocess.run` and the var names
    exactly match `staging.yml.jinja:6,11`.
  - `services.yml` with batteries is malformed (e.g. a Jinja2 whitespace indent error in the
    conditional blocks) → confirm the rendered file via `cat dest/infra/compose/services.yml`.
  - A non-existent key reference in the merge (e.g. `celery-exporter` is not in
    `observability.yml`) → that's a real bug, follow the shared real-bug policy.

- [ ] **Step 3: Bite-prove (cheap — no rebuild).**
  - For `test_staging_standalone_merges`: temporarily assert a non-existent service:
    `assert "nonexistent-service" in r.stdout` → RED. Revert.
  - For `test_staging_plus_services_overlay_merges`: temporarily flip the bare-batteries
    assertion to require `"worker" in r2.stdout` (when no batteries rendered, it won't be) →
    RED. Revert.
  Commit (PLAN/ACTION_LOG staged + skip-marker; `git add` then `git commit` as SEPARATE calls).

---

## Task 2: Half B — `test.yml` live bring-up + tmpfs ephemeral-DB reset
(in `tests/acceptance/test_rendered_project.py`)

**Files:** Modify `tests/acceptance/test_rendered_project.py` (place after
`test_rendered_dev_lite_stack_serves_health`, ~line 935).

**Architecture recap:** `test.yml` defines `app` (profiles: test, APP_ENVIRONMENT: test,
depends on postgres-test) and `postgres-test` (profiles: test, `tmpfs: - /var/lib/postgresql/data`,
healthcheck: `pg_isready -U app -d app`, POSTGRES_USER/PASSWORD/DB: app). `base.yml` defines
`app` with the build context and healthcheck but NO port. The test adds a one-line ephemeral
override to expose the app port so `_compose_host_port` can discover it. The `_isolate_compose_project`
autouse fixture sets `HTTP_HOST_PORT=0` in the test env, so Docker assigns an ephemeral port
automatically when the override binds `"${HTTP_HOST_PORT:-8000}:8000"`.

**Tmpfs-reset assertion:** `alembic_version` is the right probe. The app entrypoint runs
`alembic upgrade head` before uvicorn serves (entrypoint.sh); after a cold `up --build`, the
table exists with at least one row (`SELECT count(*) FROM alembic_version` returns ≥ 1). After
`down` + `up` (no rebuild — `--no-build`), the tmpfs postgres-test is recreated empty (no
persistent volume), so `alembic upgrade head` runs again (the entrypoint always runs it) — but
this still creates the `alembic_version` table. **The correct reset assertion is instead:**
verify that after restart, the app serves a fresh `/items` (or any seeded route) → returns an
empty list (seed ran on first boot but the DB was wiped). Alternatively, verify that the
`pgdata` volume does NOT persist by checking `alembic_version` returns exactly the fresh
migration-only count across two independent `up` cycles, which is non-trivial.

**Simpler and more direct approach (used here):** assert the restart itself succeeds cleanly
(the tmpfs means Postgres starts from scratch, so `alembic upgrade head` re-runs without a
"schema already exists" error). The non-vacuous probe is `/items` returning an **empty list**
on the SECOND `up` after `/items` returned **non-empty** on the first `up` (the `seed.py`
seeder populates items on first start; the second start re-seeds into a fresh DB but the items
list is still non-empty — this is NOT the right test). **Correct test:** after the second `up`,
assert `/health` returns 200 (proves the fresh-DB app started cleanly) AND the second
`postgres-test` container is a brand-new container (container ID differs — proving `down -v`
dropped the old tmpfs container and `up` created a fresh one). The container-ID delta is the
most reliable zero-cost reset proof: the tmpfs means there is no persistent `pgdata` volume, so
the postgres-test container that serves the second `up` is categorically fresh.

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: test-profile stack + tmpfs ephemeral-DB reset",
)
def test_rendered_test_profile_stack_serves_and_resets_db(tmp_path: Path) -> None:
    # FWK19 (M3): test.yml is shipped and documented (`task test:stack`), but the acceptance
    # tier never uses --profile test — the tmpfs ephemeral-DB reset is undriven. Bring the
    # stack up twice and assert: (a) the app serves /health on the first up, and (b) the
    # postgres-test container has a DIFFERENT container ID on the second up, proving the tmpfs
    # was torn down and recreated (ephemeral reset, not a persistent volume re-mount).
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    # test.yml + base.yml: base.yml defines the app build+healthcheck; test.yml adds the test
    # profile + postgres-test. Neither publishes a host port for `app`; add one via an inline
    # ephemeral override so _compose_host_port can discover the assigned ephemeral port.
    # The _isolate_compose_project autouse fixture sets HTTP_HOST_PORT=0, so docker assigns
    # a free ephemeral port automatically.
    (dest / "infra" / "compose" / "fwk19.override.yml").write_text(
        "services:\n  app:\n    ports:\n      - \"${HTTP_HOST_PORT:-8000}:8000\"\n"
    )

    base = "infra/compose/base.yml"
    test_overlay = "infra/compose/test.yml"
    override = "infra/compose/fwk19.override.yml"
    files = [base, test_overlay, override]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]

    compose = ["docker", "compose", *fargs, "--profile", "test"]
    up = [*compose, "up", "-d", "--build"]
    up_no_rebuild = [*compose, "up", "-d", "--no-build"]
    down = [*compose, "down", "-v"]
    env = _compose_env()

    try:
        # --- First boot ---
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0, (
            "test-profile stack first `up --build` failed"
        )
        port = _compose_host_port(dest, files, "app", 8000)

        # Poll /health until 200 (app runs alembic upgrade head before uvicorn serves).
        deadline = time.time() + 120
        body = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port}/health", timeout=3
                ) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read())
                        break
            except OSError:
                time.sleep(2)
        assert body is not None, (
            "test-profile app did not serve /health 200 within 120s on first boot"
        )
        assert body["status"] in {"ok", "degraded"}, (
            f"unexpected /health status on first boot: {body}"
        )

        # Capture the postgres-test container ID on the first boot.
        cid1 = subprocess.run(
            [*compose, "ps", "-q", "postgres-test"],
            cwd=dest, env=env, capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert cid1, "postgres-test container not found after first up"

        # --- Teardown (with -v: drop named volumes — there are none for postgres-test since
        # it uses tmpfs, but -v is consistent with the other acceptance tests) ---
        assert subprocess.run(down, cwd=dest, env=env).returncode == 0, (
            "test-profile stack `down -v` failed"
        )

        # --- Second boot (no rebuild — image is already built) ---
        assert subprocess.run(up_no_rebuild, cwd=dest, env=env).returncode == 0, (
            "test-profile stack second `up --no-build` failed"
        )
        # Re-discover the port (ephemeral; may differ after a new up).
        port2 = _compose_host_port(dest, files, "app", 8000)

        # Poll /health on the second boot.
        deadline2 = time.time() + 120
        body2 = None
        while time.time() < deadline2:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port2}/health", timeout=3
                ) as resp:
                    if resp.status == 200:
                        body2 = json.loads(resp.read())
                        break
            except OSError:
                time.sleep(2)
        assert body2 is not None, (
            "test-profile app did not serve /health 200 within 120s on second boot — "
            "the tmpfs reset may have left postgres-test in an inconsistent state, or the "
            "app failed to re-run alembic upgrade head against the fresh DB"
        )

        # The tmpfs reset proof: postgres-test was torn down and recreated — its container ID
        # must differ between the first and second boot (a persistent volume would allow the
        # same container to be restarted, but `down` removes containers, so this mainly proves
        # the second `up` created a brand-new postgres-test rather than re-attaching to a
        # lingering one from a stale project namespace).
        cid2 = subprocess.run(
            [*compose, "ps", "-q", "postgres-test"],
            cwd=dest, env=env, capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert cid2, "postgres-test container not found after second up"
        assert cid2 != cid1, (
            "postgres-test container ID did not change between first and second boot — "
            "the tmpfs ephemeral-DB reset did not produce a fresh container "
            f"(first={cid1!r}, second={cid2!r})"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
```

- [ ] **Step 2: Run — expect GREEN.**
  ```
  TMPDIR=/var/tmp uv run pytest \
      tests/acceptance/test_rendered_project.py::test_rendered_test_profile_stack_serves_and_resets_db \
      -q
  ```
  First build ~3–5 min; the second `up` is fast (no rebuild). Real-bug candidates:
  - The app port override (`fwk19.override.yml`) does not publish correctly in the test
    profile → `_compose_host_port` raises → confirms the test.yml port-exposure gap is a
    real template bug → follow the shared real-bug policy (add `ports:` to `test.yml.jinja`
    behind a `${HTTP_HOST_PORT:-8000}:8000` binding, or note the xfail + new FWK id).
  - `postgres-test` never goes healthy on the second boot (tmpfs started inconsistently) →
    the app times out → real bug in the healthcheck or tmpfs mount → shared real-bug policy.
  - The second boot app raises an `OperationalError` (alembic migration fails on the fresh DB)
    → confirms the tmpfs reset is working but something in the migration is wrong → xfail +
    real bug.

- [ ] **Step 3: Bite-prove (cheap — no rebuild).**
  Flip the container-ID assertion to require the IDs to be EQUAL:
  `assert cid2 == cid1, "..."` → after a real `down`, the second `up` creates a new
  container with a new ID → the flipped assertion goes RED. Revert.
  Commit (PLAN/ACTION_LOG staged + skip-marker; separate `git add` then `git commit`).

---

## Task 3: Flip the 11 FWK19 KNOWN_GAP registry entries to EXERCISED
(in `tests/runtime_coverage/registry.py`)

**Files:** Modify `tests/runtime_coverage/registry.py`. The test names from Tasks 1 and 2
must already exist (Tasks 1 and 2 committed) before this flip, because
`test_exercised_entries_name_an_existing_test` in `tests/runtime_coverage/test_completeness.py`
greps all `test_*.py` files for the exact function name in the evidence field.

**All 11 entries to flip (with exact current locations from the registry):**

**Group 1 — Overlay-level entries (registry.py:319–342):**

- `overlay:services.yml` (registry.py:319–326) → flip to `_EX`, evidence `"test_staging_plus_services_overlay_merges"`:
```python
    SurfaceClass(
        "overlay:services.yml",
        "infra/compose/services.yml",
        _EX,
        # FWK19: batteries-on compose-config merge-validation (staging+services+obs) proves
        # the battery-conditional rendering is syntactically correct and the overlay merges.
        "test_staging_plus_services_overlay_merges",
    ),
```

- `overlay:staging.yml` (registry.py:327–334) → flip to `_EX`, evidence `"test_staging_standalone_merges"`:
```python
    SurfaceClass(
        "overlay:staging.yml",
        "infra/compose/staging.yml",
        _EX,
        # FWK19: standalone compose-config merge-validation proves staging.yml is valid YAML
        # with the required env vars (APP_IMAGE, POSTGRES_PASSWORD) threading through correctly.
        "test_staging_standalone_merges",
    ),
```

- `overlay:test.yml` (registry.py:335–342) → flip to `_EX`, evidence `"test_rendered_test_profile_stack_serves_and_resets_db"`:
```python
    SurfaceClass(
        "overlay:test.yml",
        "infra/compose/test.yml",
        _EX,
        # FWK19/M3: --profile test stack brought up live; app serves /health; the tmpfs
        # ephemeral-DB reset is proven by the differing postgres-test container ID.
        "test_rendered_test_profile_stack_serves_and_resets_db",
    ),
```

**Group 2 — Service-level entries (registry.py:657–714):**

- `service:services.yml:beat` (registry.py:657–665) → flip to `_EX`, evidence `"test_staging_plus_services_overlay_merges"`:
```python
    SurfaceClass(
        "service:services.yml:beat",
        "infra/compose/services.yml:59-72",
        _EX,
        # FWK19: the batteries-on staging+services+obs config merge validates beat appears
        # with APP_RUN_MIGRATIONS=false and the promoted image.
        "test_staging_plus_services_overlay_merges",
    ),
```

- `service:services.yml:mongo` (registry.py:666–671) → flip to `_EX`, evidence `"test_staging_plus_services_overlay_merges"`:
```python
    SurfaceClass(
        "service:services.yml:mongo",
        "infra/compose/services.yml:9-19",
        _EX,
        # FWK19: the batteries-on staging+services+obs config merge validates mongo appears.
        "test_staging_plus_services_overlay_merges",
    ),
```

- `service:services.yml:redis` (registry.py:672–677) → flip to `_EX`, evidence `"test_staging_plus_services_overlay_merges"`:
```python
    SurfaceClass(
        "service:services.yml:redis",
        "infra/compose/services.yml",
        _EX,
        # FWK19: the batteries-on staging+services+obs config merge validates redis appears.
        "test_staging_plus_services_overlay_merges",
    ),
```

- `service:services.yml:worker` (registry.py:678–686) → flip to `_EX`, evidence `"test_staging_plus_services_overlay_merges"`:
```python
    SurfaceClass(
        "service:services.yml:worker",
        "infra/compose/services.yml:35-57",
        _EX,
        # FWK19: the batteries-on staging+services+obs config merge validates worker appears
        # with APP_RUN_MIGRATIONS=false and the promoted image.
        "test_staging_plus_services_overlay_merges",
    ),
```

- `service:staging.yml:app` (registry.py:687–694) → flip to `_EX`, evidence `"test_staging_standalone_merges"`:
```python
    SurfaceClass(
        "service:staging.yml:app",
        "infra/compose/staging.yml:4-53",
        _EX,
        # FWK19: staging.yml standalone config-validation proves the app service resolves
        # correctly (APP_IMAGE, APP_ENVIRONMENT: staging, healthcheck, depends_on).
        "test_staging_standalone_merges",
    ),
```

- `service:staging.yml:postgres` (registry.py:695–700) → flip to `_EX`, evidence `"test_staging_standalone_merges"`:
```python
    SurfaceClass(
        "service:staging.yml:postgres",
        "infra/compose/staging.yml:4-53",
        _EX,
        # FWK19: staging.yml standalone config-validation proves postgres resolves correctly
        # (POSTGRES_PASSWORD env var, healthcheck, pgdata volume).
        "test_staging_standalone_merges",
    ),
```

- `service:test.yml:app` (registry.py:701–707) → flip to `_EX`, evidence `"test_rendered_test_profile_stack_serves_and_resets_db"`:
```python
    SurfaceClass(
        "service:test.yml:app",
        "infra/compose/test.yml:5-41",
        _EX,
        # FWK19/M3: the test-profile app is brought up live and serves /health 200.
        "test_rendered_test_profile_stack_serves_and_resets_db",
    ),
```

- `service:test.yml:postgres-test` (registry.py:708–714) → flip to `_EX`, evidence `"test_rendered_test_profile_stack_serves_and_resets_db"`:
```python
    SurfaceClass(
        "service:test.yml:postgres-test",
        "infra/compose/test.yml:5-41",
        _EX,
        # FWK19/M3: postgres-test (tmpfs: /var/lib/postgresql/data) is brought up live;
        # the ephemeral reset is proven by the differing container ID across two boot cycles.
        "test_rendered_test_profile_stack_serves_and_resets_db",
    ),
```

- [ ] **Step 1: Apply all 11 flips.**

- [ ] **Step 2: Verify the completeness suite.**
  ```
  uv run pytest tests/runtime_coverage/ -q
  ```
  Expect all pass. The three rules that matter:
  - `test_exercised_entries_name_an_existing_test`: all 11 named test functions must exist in
    `tests/test_copier_runner.py` or `tests/acceptance/test_rendered_project.py` (Tasks 1–2
    committed first).
  - `test_known_gap_entries_link_a_task`: no longer sees any of the 11 flipped entries.
  - `test_every_surface_is_classified` / `test_no_stale_registry_entries`: unaffected (no
    surface added or removed).

- [ ] **Step 3:** Commit (PLAN/ACTION_LOG staged + skip-marker).

---

## Task 4: Close-out

- [ ] **Step 1: Lint/format.**
  ```
  uv run ruff check tests/test_copier_runner.py tests/acceptance/test_rendered_project.py \
      tests/runtime_coverage/registry.py
  uv run ruff format --check tests/test_copier_runner.py \
      tests/acceptance/test_rendered_project.py tests/runtime_coverage/registry.py
  ```
  Per [[ruff-format-check-after-inline-edits]]: run `ruff format --check` not just `ruff check`
  (long lines pass check but fail format → the repo's format-cleanliness regression class).

- [ ] **Step 2: Full FWK19 run (laptop, `TMPDIR=/var/tmp`).**
  ```
  # Half A (CI-visible):
  uv run pytest tests/test_copier_runner.py::test_staging_standalone_merges \
      tests/test_copier_runner.py::test_staging_plus_services_overlay_merges -q

  # Half B (acceptance / local-only):
  TMPDIR=/var/tmp uv run pytest \
      tests/acceptance/test_rendered_project.py::test_rendered_test_profile_stack_serves_and_resets_db \
      -q

  # Completeness suite:
  uv run pytest tests/runtime_coverage/ -q
  ```
  All four pytest invocations must be green before proceeding.

- [ ] **Step 3: State + commit.** Per the shared policy this is ONE item on `fwk-coverage-batch`;
  defer the whole-branch Opus review to the end of the batch. Tick FWK19 in `PLAN.md` (or move
  to Done when the batch closes), append `ACTION_LOG.md` entries (per `pi-convention.md`), final
  commit with the skip-marker. **No release** (test-only; any forced template fix is deferred +
  flagged).

- [ ] **Step 4: Morning-report line.** Record: FWK19 green / which (if any) of the three tests
  went xfail on a real bug + the new FWK id + the `ACTION_LOG` ref.

---

## Self-Review

- **Spec coverage:**
  - H7 demoted → `staging.yml` config-validation → `test_staging_standalone_merges` (Task 1). ✓
  - H2 demoted → batteries-on `services.yml` config-validation → `test_staging_plus_services_overlay_merges` (Task 1). ✓
  - M3 → `test.yml` live bring-up + tmpfs reset → `test_rendered_test_profile_stack_serves_and_resets_db` (Task 2). ✓
- **CI-visible (Half A) vs acceptance-tier (Half B):**
  - Half A uses `@pytest.mark.skipif(shutil.which("docker") is None, ...)` (mirrors the
    existing prod.yml tests at lines 1995 and 2156; CI has docker). ✓
  - Half B uses `@pytest.mark.skipif(not _docker_available(), ...)` (matches all other
    acceptance tests; CI-ignored/local-only). ✓
- **Harnesses reused:** `_compose_env`, `_compose_host_port`, `_isolate_compose_project`; the
  FWK24 ephemeral-override-file pattern; the FWK26 `compose ps -q` + container-ID pattern. ✓
- **Ephemeral ports:** `_compose_host_port(dest, files, "app", 8000)` — never hardcode 8000 as
  the host port; FWK31-compliant. ✓
- **Non-vacuity:**
  - Task 1 bite-proof: flip a service assertion to require a non-existent service → RED. ✓
  - Task 2 bite-proof: require `cid2 == cid1` after a real down → RED. ✓
  - Registry: `test_exercised_entries_name_an_existing_test` enforces the named test actually
    exists; the completeness suite fails if the evidence string is wrong. ✓
- **Registry correctness:** exactly 11 KNOWN_GAP entries flip (3 overlay + 4 services.yml +
  2 staging.yml + 2 test.yml). No enumerated surface is added or removed. `overlay:prod.yml`
  and `service:prod.yml:{app,postgres}` are already `_EM` (not touched). ✓
- **No template change expected** (test-only). The port-exposure gap in `test.yml` is resolved
  by an ephemeral override in the test — if the override pattern fails, it becomes a real bug. ✓
- **Naming consistency:** `test_staging_standalone_merges`, `test_staging_plus_services_overlay_merges`,
  `test_rendered_test_profile_stack_serves_and_resets_db` — used identically in the tests, the
  registry evidence strings, and the close-out run commands. ✓
- **Batch position:** item #5. Tasks 1–2 are independent of FWK24/23/26/25's new helpers;
  FWK19 adds nothing those plans consume and consumes nothing they add. ✓

### Genuine design forks

1. **Port exposure for the test-profile stack — ephemeral override file (PICKED) vs template
   change.** `test.yml` never publishes a host port for `app` (base.yml has no port, dev.yml
   adds `${HTTP_HOST_PORT:-8000}:8000` but is not in this merge). Two options:
   - **(A) Ephemeral override in the test (PICKED):** write `fwk19.override.yml` into
     `tmp_path` with `services: app: ports: ["${HTTP_HOST_PORT:-8000}:8000"]`, append it to
     the `-f` list, discover the assigned port via `_compose_host_port`. No template change,
     no deferred release, mirrors FWK24's webhook override pattern.
   - **(B) Add a port to `test.yml.jinja`:** add `ports: - "${HTTP_HOST_PORT:-8000}:8000"`
     directly to the `app` service in `test.yml.jinja`. Cleaner consumer experience
     (consumers who run `task test:stack` and want to curl the app get the port for free), but
     is a template-payload change requiring a deferred release per the shared policy, and
     `task test:stack` runs attached (no `-d`) so the consumer has the app in their terminal
     and typically connects to it from `localhost:8000`. **Tradeoff:** (B) is a net
     improvement for consumers; the human may prefer it as a small cleanup in a future release
     alongside the next batch of template changes. **The plan is written for (A)**; switch to
     (B) is a self-contained swap of the one `fwk19.override.yml` write in Task 2 Step 1 plus
     editing `test.yml.jinja` to add the ports line.

2. **Tmpfs-reset proof — container-ID delta (PICKED) vs DB-content check.** Two options:
   - **(A) Container-ID delta (PICKED):** `compose ps -q postgres-test` returns a new
     container ID after `down` + `up`, proving the tmpfs postgres-test was torn down and
     recreated (not restarted in place with a persistent volume). Fast, zero-cost, requires
     no psql exec.
   - **(B) DB-content check:** after the first `up`, INSERT a canary row; after `down` + `up`,
     SELECT and assert the row is gone. More semantically direct — proves the DATA is gone,
     not just the container. But requires the test to know a writable table (not guaranteed in
     the baseline render without a seeded fixture), and it adds latency (psql exec, two sets of
     health polls). **Tradeoff:** (B) is the "purest" proof of the tmpfs guarantee; (A) is
     cheaper and sufficient because a new container on a tmpfs means the data is structurally
     gone. **The plan uses (A).**

### Anticipated real template bugs these tests may surface

- **`staging.yml` `${POSTGRES_PASSWORD:?...}` not threaded through postgres service**
  (Task 1). If the `:?` required-var syntax in staging.yml.jinja:41 is malformed (e.g., the
  full error message string contains a colon that breaks the `${VAR:?msg}` parse), `docker
  compose config` exits non-zero even with the var set → RED. Exact relevant lines:
  staging.yml.jinja:6 (`${APP_IMAGE:?set APP_IMAGE…}`), :11 (`${POSTGRES_PASSWORD:?set
  POSTGRES_PASSWORD}@postgres`), :28 (`${POSTGRES_IMAGE:?set POSTGRES_IMAGE…}`), :41
  (`${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in the target…}`).

- **`services.yml` battery-conditional YAML indent error** (Task 1). Jinja2 templating of
  indented YAML blocks is fragile: a missing `-` prefix on a `{%- if %}` block or a
  whitespace-collapsing `-%}` can produce a mis-indented `services:` map key or a bare
  `volumes:` block without a parent, making compose parse fail. The existing
  `test_render_services_overlay_workers` (test_copier_runner.py:2089) checks YAML validity via
  `yaml.safe_load`, but never passes it through `docker compose config` with the full merge
  stack (base+obs). A compose-level merge error that `yaml.safe_load` misses (e.g., a duplicate
  `volumes:` key at the top level) would only surface here.

- **`test.yml` port-override pattern failure** (Task 2). The ephemeral
  `fwk19.override.yml` with `services: app: ports: ["${HTTP_HOST_PORT:-8000}:8000"]` must
  merge cleanly with `base.yml + test.yml`. If the compose merge for `--profile test` does not
  include the override's port (e.g., because the profile filter excludes the override's `app`
  entry — unlikely, since profile filters apply per-service, and the `app` service in the
  override has no `profiles:` key so it is included in all profiles), `_compose_host_port`
  raises → test fails on the port-discovery step. If this happens: add the port binding
  directly to `test.yml.jinja` instead (design fork B above) and deferred-release it.

- **`postgres-test` tmpfs healthcheck fails on the second boot** (Task 2). If `down -v`
  does not cleanly remove the `postgres-test` container (e.g., a docker-compose version bug
  where `down` leaves a stopped container and the second `up` tries to reuse it), the second
  `up` may either reuse the same container (container ID matches → the cid-delta assertion
  fires as a false "real bug") or fail entirely. Diagnose with `docker compose ps -a` after
  `down` to confirm the container is gone. This is a Docker version sensitivity, not a
  template bug.

- **`celery-exporter` missing from `observability.yml`** (Task 1, `test_staging_plus_services_overlay_merges`). The test asserts `"celery-exporter" in r.stdout`. If `observability.yml.jinja` does not render the `celery-exporter` service when the `workers` battery is active (or if it is named differently — e.g., `celery-flower`), the assertion fires. Confirm by reading `src/framework_cli/template/infra/compose/observability.yml.jinja` directly before committing this assertion; adjust the expected service name if needed. The prod test at line 2159 asserts `"celery-exporter"` and is green today — so this should be safe, but double-check.
