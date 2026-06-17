# FWK26 — Dev-loop / service-health live exercise — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans`. Read the shared
> policy first: `docs/superpowers/plans/2026-06-17-coverage-batch-execution-policy.md` (branch
> `fwk-coverage-batch`, commit cadence + skip-marker gate, real-bug rule, **no release**,
> laptop/`TMPDIR=/var/tmp`, non-vacuity). This is item **#3** of the batch and lands **after FWK24
> and FWK23**. FWK24 already added the shared helpers `_traefik_request`, `_traefik_ws_upgrade`,
> `_mkcert_ssl_context`; FWK23 already added `_poll_json` — **this plan assumes all four exist and
> does NOT redefine them** (M1 reuses `_mkcert_ssl_context` only for the host name; the :80 probe is
> raw plaintext and needs no TLS helper). Steps use `- [ ]`.

**Goal:** Close the four dev-loop / service-health med gaps that ship to a consumer unexercised:

- **M1** — the Traefik `web` (:80) entrypoint actually **redirects HTTP → HTTPS** (web → websecure).
  Today the only through-Traefik test connects to :443; nothing connects to :80, so a removed/broken
  redirect (a dev/staging behavior break) passes silently.
- **M2** — the **mongo compose SERVICE** (`mongo:7`, the mongosh-ping healthcheck quoting, the
  `mongodata` volume, the `27017` mapping) is brought up and **reports `healthy`** and a client can
  connect. The mongo data-store round-trip is tested via testcontainers (`mongo/repository.py` 100%),
  but the `mongo:` compose block itself is never `compose up`-ed — a broken healthcheck quote or volume
  mount means a consumer's mongo never goes healthy and blocks dependents, masked by app coverage.
- **M4** — **hot-reload** works on the bind mount: `--reload` + `WATCHFILES_FORCE_POLLING=true` pick up
  a source edit. Every dev/lite test runs uvicorn with reload, but none edits a file post-startup and
  asserts the new response — so a reload regression (env removed, inotify dead on the WSL bind mount)
  breaks the core dev inner-loop silently.
- **M14** — the DB engine **pool lifecycle**: `pool_pre_ping=True` recovers the **real module-level
  engine** after the underlying Postgres connection drops, and `dispose_engine()` **actually disposes
  the pool** (real pool state), not a monkeypatched stub. The functional suite builds a *separate* test
  engine (conftest `build_engine(pg_url)`), and the graceful-shutdown test monkeypatches
  `dispose_engine` — so neither pre-ping recovery nor real disposal of the shipped module-level engine
  is asserted anywhere.

**Architecture:** Four independent tests, chosen to bound cost:

- **Test A — M1 + M2 folded into ONE `--profile dev` bring-up.** Render `mongodb` (so the `mongo:`
  service renders) and bring up `app + postgres + traefik + mongo` under `-f base -f observability -f
  dev --profile dev` (the same merge `test_rendered_project_dev_stack_routes_through_traefik` uses —
  `observability.yml` is required so `--profile dev` config-validation accepts grafana's image-less
  dev override; we do not `up` the obs containers). Against this ONE stack: (M1) a raw plaintext GET to
  Traefik's **:80** ephemeral host port asserts a 30x + `Location: https://…`; (M2) poll
  `docker inspect` on the `mongo` container until `Health.Status == healthy`, then `compose exec -T
  mongo mongosh …ping` to prove a client connects. **Justification:** M1 and M2 are both read-only
  probes of one already-running dev stack; the Traefik redirect and the mongo health are orthogonal
  surfaces but share the boot cost. Splitting them would double the (heavy) dev-stack bring-up for no
  extra signal. M1 needs Traefik (so does the existing :443 test); M2 needs the `mongo` service (only
  rendered under the `mongodb` battery) — rendering `mongodb` and adding `mongo` to the up-list
  satisfies both in one stack. `task certs` is **not** needed (M1's :80 probe is plaintext; we do not
  hit :443), which also drops the `mkcert`/`task` skip preconditions from this test.
- **Test B — M4 hot-reload (dev:lite, app-only, cheapest reload-capable stack).** Bring up the
  `lite` profile (`app + postgres`, no Traefik/obs — the smallest stack that still runs uvicorn with
  `--reload` + `WATCHFILES_FORCE_POLLING` and bind-mounts `../../src:/app/src`). GET `/heartbeat`
  (plaintext `"OK"`) through the app's ephemeral host port; then **edit the rendered
  `src/demo/routes/health.py` `heartbeat()` body** to return a sentinel string; poll `/heartbeat`
  until the sentinel appears within a timeout, proving the bind-mounted reload fired. The `app` service
  runs as the host UID (`user: "${UID:-1000}:${GID:-1000}"`, dev.yml.jinja:8) **and the edit is made
  on the host to a host-owned file** — so no root-owned residue is created by this test and **no
  chown-reclaim is needed** (uvicorn only writes `__pycache__`, already covered by the no-root lite
  test; we still defensively reclaim in `finally`, see Task 3 Step 1).
- **Test C — M14 pool lifecycle (framework-side acceptance, NO template change).** Decided fork
  (see "Genuine forks"): **(b) a framework-side acceptance test that drives the rendered module-level
  engine against a real compose Postgres, with no template payload change.** Render baseline, bring up
  **only `postgres`** from the lite profile, point `APP_DATABASE_URL` at its ephemeral host port, and
  run a self-contained driver **inside the rendered project's own venv** (`uv run python -c <driver>`)
  that imports `demo.db.engine`, (1) opens a pooled connection and runs `SELECT 1`, (2) **restarts the
  postgres container** (`docker compose restart postgres`) to drop the pooled connection, (3) runs
  `SELECT 1` again and asserts it succeeds (proving `pool_pre_ping` re-established a live connection),
  and (4) calls `dispose_engine()` and asserts the **real pool** was disposed (a fresh pool object /
  zero checked-out connections — see Task 4 for the exact pool-state assertion). The driver prints
  `OK` on success; the test asserts the subprocess returncode + the `OK` marker. **Rationale for (b)
  over (a):** (a) would add a generated-project functional test to the TEMPLATE payload — a
  template-payload change (deferred release per policy) AND it would have to restart a container from
  *inside* pytest, which the rendered functional tier (testcontainers, in-process) is not structured to
  do. (b) keeps the change test-only (no release), drives the **exact shipped module-level engine**
  (the M14 ask — not conftest's separate test engine), and reuses the existing compose-Postgres + host
  driver pattern. Tradeoff: (b) lives in the framework acceptance tier (laptop-only, CI-ignored) rather
  than shipping the guard into every consumer's `task ci`; acceptable because M14 is a framework
  coverage gap, and a future consumer-side guard can be promoted separately if wanted.

**Tech Stack:** Python, pytest, Docker, Traefik v3.6, mongo:7, postgres:17, SQLAlchemy 2.x pooled
Engine, the existing acceptance harnesses (`_compose_env`, `_compose_host_port` — FWK31 ephemeral
ports, NEVER hardcode published ports — `_free_tcp_port`, the `_isolate_compose_project` autouse
fixture, the FWK20 `compose exec -T` query pattern).

---

## File Structure

- **Modify** `tests/acceptance/test_rendered_project.py` — add the three tests
  (`test_rendered_dev_stack_http_redirect_and_mongo_health` [M1+M2],
  `test_rendered_dev_lite_hot_reload_picks_up_edit` [M4],
  `test_rendered_db_engine_pool_pre_ping_and_dispose` [M14]). **No new shared helper is required** —
  M1/M2/M4 reuse `_compose_host_port` + a raw socket + the FWK23 `_poll_json` (M4 polls plaintext, so
  it uses a small inline `urlopen` loop, not `_poll_json`, which JSON-parses); M14 uses `subprocess`.
- **Modify** `tests/runtime_coverage/registry.py` — flip the **single** FWK26 KNOWN_GAP entry
  `service:dev.yml:mongo` → EXERCISED (M2), naming the new test. **No other registry change** — M1,
  M4, and M14 are in-app / behavioral surfaces with **no enumerated registry key** (verified below).
- **Modify** `PLAN.md` + `ACTION_LOG.md` (per the shared policy — required staged on every commit).

**Registry scope (verified against the live registry).** `grep -n "FWK26" tests/runtime_coverage/
registry.py` returns **exactly one** entry: `service:dev.yml:mongo` (registry.py:514-521, currently
`_KG`). `grep -ni "reload\|redirect\|:80\|engine\|pool_pre\|websecure" registry.py` returns **no**
enumerated surface for the redirect (M1), hot-reload (M4), or engine/pool (M14) — confirming, exactly
as FWK24's M8/M9 and FWK23's M7/M11 did, that those three are coverage adds that flip **nothing**. Do
NOT invent registry keys for them. The completeness suite
(`tests/runtime_coverage/test_completeness.py`) enforces: `test_exercised_entries_name_an_existing_test`
(the named test must exist — so Tasks 1–4 land before the flip), `test_known_gap_entries_link_a_task`
(no longer sees the flipped mongo entry), and `test_every_surface_is_classified` /
`test_no_stale_registry_entries` (unaffected — no surface added/removed).

**No template change is expected** (test-only). If a test goes red on a real template defect (a broken
:80 redirect, a malformed mongosh-ping healthcheck quote, a dead bind-mount reload, a pre-ping/dispose
regression), STOP and follow the shared real-bug policy: root-cause → small+scoped fix + a CI-visible
render guard + deferred release, OR `@pytest.mark.xfail(reason="FWK<NN>: real bug — <one line>",
strict=True)` + leave the registry entry KNOWN_GAP + a new `PLAN.md` `Next` FWK id + an `ACTION_LOG`
entry + a morning-report line. **Anticipated candidates are listed in the Self-Review.**

---

## Task 1: Test A — Traefik HTTP→HTTPS redirect (M1) + mongo service healthy (M2)

**Files:** Modify `tests/acceptance/test_rendered_project.py` (place after
`test_rendered_project_dev_stack_routes_through_traefik`, ~line 1018).

- [ ] **Step 1: Write the test.** Render `mongodb` so the `mongo:` service block renders; bring up
  `app + postgres + traefik + mongo` under the `-f base -f observability -f dev --profile dev` merge.
  Discover every host port via `_compose_host_port`. M1 uses a **raw plaintext** socket to Traefik's
  :80 (NO TLS — the redirect happens before any TLS handshake); M2 polls `docker inspect` on the mongo
  **container id** (resolved via `compose ps -q mongo`) until `Health.Status == healthy`, then runs
  `compose exec -T mongo mongosh …ping`.

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: live dev stack for the Traefik :80 redirect + mongo health",
)
def test_rendered_dev_stack_http_redirect_and_mongo_health(tmp_path: Path):
    # FWK26 (M1 + M2): the only through-Traefik test connects to :443; nothing connects to :80, so a
    # removed/broken HTTP->HTTPS redirect ships silently. And the mongo COMPOSE service (mongosh-ping
    # healthcheck quoting, mongodata volume, 27017) is never `compose up`-ed — only the testcontainers
    # data-store round-trip is. Bring up ONE dev stack (with the mongodb battery so `mongo:` renders)
    # and assert both: (M1) :80 -> 30x + Location: https://, (M2) mongo container reports healthy +
    # a mongosh client pings. NOTE: no `task certs` / mkcert — the :80 probe is plaintext and we never
    # hit :443.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": resolve(["mongodb"])})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    compose = ["docker", "compose", *fargs, "--profile", "dev"]
    up = [*compose, "up", "-d", "--build", "app", "postgres", "traefik", "mongo"]
    down = [*compose, "down", "-v"]
    env = _compose_env()
    assert subprocess.run(up, cwd=dest, env=env).returncode == 0
    try:
        # ---------- M1: HTTP (:80) redirects to HTTPS ----------
        http_port = _compose_host_port(dest, files, "traefik", 80)
        host = f"{DATA['project_slug']}.localhost"

        # Raw plaintext HTTP/1.1 GET; Traefik's `web` entrypoint redirects (RedirectScheme) BEFORE any
        # backend routing, so the Host header need not match a router — but send the real host anyway.
        def _probe_redirect() -> tuple[int, str]:
            raw = socket.create_connection(("127.0.0.1", http_port), timeout=5)
            try:
                raw.sendall(
                    f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
                )
                data = b""
                while True:
                    chunk = raw.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            finally:
                raw.close()
            head = data.split(b"\r\n\r\n", 1)[0].decode(errors="replace")
            status = int(head.split("\r\n", 1)[0].split()[1])
            location = ""
            for line in head.split("\r\n")[1:]:
                if line.lower().startswith("location:"):
                    location = line.split(":", 1)[1].strip()
            return status, location

        status, location = 0, ""
        deadline = time.time() + 90
        last = "no attempt"
        while time.time() < deadline:
            try:
                status, location = _probe_redirect()
                if status in (301, 302, 307, 308):
                    break
                last = f"HTTP {status} (no redirect)"
            except OSError as exc:  # Traefik still settling
                last = f"{type(exc).__name__}: {exc}"
            time.sleep(3)
        assert status in (301, 302, 307, 308), (
            f"Traefik :80 did not redirect within 90s (last: {last}) — the web->websecure "
            "RedirectScheme entrypoint (infra/traefik/traefik.yml) is broken/removed"
        )
        assert location.startswith("https://"), (
            f"redirect Location is not https:// (got {location!r}) — wrong scheme on the "
            "web entrypoint redirect"
        )

        # ---------- M2: mongo compose service reports healthy + a client connects ----------
        cid = subprocess.run(
            [*compose, "ps", "-q", "mongo"],
            cwd=dest, env=env, capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert cid, "mongo container id not found (the mongo service did not start)"

        healthy = False
        deadline = time.time() + 90
        while time.time() < deadline:
            state = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", cid],
                capture_output=True, text=True,
            ).stdout.strip()
            if state == "healthy":
                healthy = True
                break
            time.sleep(3)
        assert healthy, (
            "mongo compose service never reported healthy within 90s — the mongosh-ping "
            "healthcheck (quoting) or the mongodata volume mount is broken (dev.yml.jinja:83-95)"
        )

        # A client can actually connect+ping through the running service (compose exec, like the
        # FWK20 DLQ/redis queries — no host-side pymongo driver needed).
        ping = subprocess.run(
            [*compose, "exec", "-T", "mongo", "mongosh", "--quiet", "--eval",
             "db.adminCommand('ping').ok"],
            cwd=dest, env=env, capture_output=True, text=True,
        )
        assert ping.returncode == 0 and ping.stdout.strip().endswith("1"), (
            "mongosh ping against the live mongo service did not return ok==1:\n"
            + ping.stdout + ping.stderr
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
```

- [ ] **Step 2: Run — expect GREEN.** `TMPDIR=/var/tmp uv run pytest
  tests/acceptance/test_rendered_project.py::test_rendered_dev_stack_http_redirect_and_mongo_health -q`.
  First build ~3–5 min. A non-redirect on :80 (M1) or a mongo that never goes healthy / fails the
  mongosh ping (M2) is a candidate REAL BUG → follow the shared real-bug policy (the failure messages
  name the exact silent-prod hazard).

- [ ] **Step 3: Bite-proof (cheap — flip an asserted marker, no rebuild).**
  - **M1:** temporarily change the redirect assertion to require a 200
    (`assert status == 200`) → the live :80 returns a 30x → RED. Revert. (Equivalently:
    `assert location.startswith("http://")` → RED.)
  - **M2:** temporarily require `state == "unhealthy"` (or assert the mongosh ping returns
    `"0"`) → RED while the service is genuinely healthy. Revert.
  One flip per surface is sufficient; do the cheapest. Commit (PLAN/ACTION_LOG staged + skip-marker;
  `git add` then `git commit` as SEPARATE calls per [[commit-gate-hook-timing]]).

---

## Task 2: Flip the FWK26 registry entry (M2)

**Files:** Modify `tests/runtime_coverage/registry.py`.

- [ ] **Step 1: Flip `service:dev.yml:mongo` from `_KG` to `_EX`.** The current entry is
  registry.py:514-521. Replace the status + evidence:

```python
    SurfaceClass(
        "service:dev.yml:mongo",
        "infra/compose/dev.yml:83-95",
        _EX,
        # FWK26/M2: the mongo compose service is brought up live; the mongosh-ping healthcheck is
        # polled to `healthy` and a mongosh client pings it through the running service.
        "test_rendered_dev_stack_http_redirect_and_mongo_health",
    ),
```

- [ ] **Step 2: Confirm nothing else flips.** M1 (Traefik redirect), M4 (hot-reload), and M14
  (engine/pool) have **no** enumerated registry surface (verified: the only FWK26 key is
  `service:dev.yml:mongo`; there is no `traefik:web`, `*:reload`, or `*:engine`/`*:pool` key). Tasks 3
  and 4 are coverage adds that flip nothing. Do NOT invent registry keys for them.

- [ ] **Step 3:** `uv run pytest tests/runtime_coverage/ -q`. Expect all pass —
  `test_exercised_entries_name_an_existing_test` requires `test_rendered_dev_stack_http_redirect_and_
  mongo_health` to already exist (Task 1 lands first); `test_known_gap_entries_link_a_task` no longer
  sees the flipped mongo entry. Commit.

---

## Task 3: Test B — hot-reload picks up a source edit (M4)

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Write the test.** Bring up the **`lite`** profile (`app + postgres`, smallest
  reload-capable stack). The mutation target is the dependency-free **`/heartbeat`** route in
  `src/demo/routes/health.py`, which returns a plaintext `"OK"` (verified:
  `routes/health.py.jinja:10-13` `PlainTextResponse("OK", status_code=200)`). After `/heartbeat`
  returns `OK`, replace the literal `"OK"` in the rendered file with a unique sentinel and poll until
  the sentinel is served. The `app` service runs as the host UID (dev.yml.jinja:8) and the edit is a
  host-side write to a host-owned file, so no root residue is produced — but defensively reclaim in
  `finally` (mirrors the no-root tests) in case a future template change drops the `user:` line.

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: dev:lite stack to exercise --reload on the bind mount",
)
def test_rendered_dev_lite_hot_reload_picks_up_edit(tmp_path: Path):
    # FWK26 (M4): every dev/lite test runs uvicorn with --reload + WATCHFILES_FORCE_POLLING=true, but
    # none edits a source file post-startup and asserts the worker reloaded. If polling-reload broke
    # (env removed, inotify dead on the WSL bind mount), every test passes because none re-edits. Bring
    # up dev:lite, GET /heartbeat (=="OK"), edit the rendered heartbeat() to return a sentinel, and
    # poll /heartbeat until the NEW response appears — proving --reload + polling on the bind mount.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite",
          "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v"]
    env = _compose_env()
    sentinel = "FWK26-RELOADED-OK"
    health_py = dest / "src" / "demo" / "routes" / "health.py"
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        port = _compose_host_port(dest, [base, dev], "app", 8000)
        url = f"http://localhost:{port}/heartbeat"

        def _get_body() -> str | None:
            try:
                with urllib.request.urlopen(url, timeout=3) as resp:
                    if resp.status == 200:
                        return resp.read().decode()
            except OSError:
                return None
            return None

        # 1) Wait for the ORIGINAL response so the edit is a true post-startup change.
        deadline = time.time() + 90
        original = None
        while time.time() < deadline:
            original = _get_body()
            if original is not None:
                break
            time.sleep(2)
        assert original == "OK", (
            f"app did not serve the original /heartbeat 'OK' within 90s (got {original!r})"
        )

        # 2) Edit the rendered source on the host (bind-mounted into the container).
        src = health_py.read_text()
        assert '"OK"' in src, (
            "the rendered heartbeat route no longer returns the literal \"OK\" — re-confirm the "
            "mutation target in routes/health.py before relying on this reload test"
        )
        health_py.write_text(src.replace('"OK"', f'"{sentinel}"'))

        # 3) Poll until --reload + WATCHFILES polling restart the worker and serve the sentinel.
        deadline = time.time() + 90
        reloaded = False
        while time.time() < deadline:
            if _get_body() == sentinel:
                reloaded = True
                break
            time.sleep(2)
        assert reloaded, (
            "uvicorn --reload did not pick up the source edit within 90s — "
            "WATCHFILES_FORCE_POLLING / --reload on the bind mount is broken (dev.yml.jinja:9,15)"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
        # Defensive root-residue reclaim: the app runs as the host UID, so nothing root-owned is
        # expected, but reclaim in case a future template change drops the `user:` line (otherwise
        # pytest can't clean tmp_path). Mirrors the no-root tests' alpine chown.
        subprocess.run(
            ["docker", "run", "--rm", "-v", f"{dest}:/work", "alpine",
             "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/work"]
        )
```

- [ ] **Step 2: Run — expect GREEN.** `TMPDIR=/var/tmp uv run pytest
  tests/acceptance/test_rendered_project.py::test_rendered_dev_lite_hot_reload_picks_up_edit -q`. If the
  sentinel never appears, that is a candidate REAL BUG (reload env removed, or polling broken on the
  bind mount) → shared real-bug policy. Allow generous timeouts: `WATCHFILES_FORCE_POLLING` adds a
  poll-interval lag before the reload fires.

- [ ] **Step 3: Bite-proof (cheap — assert the OLD response still appears → RED, no rebuild).**
  Temporarily change the final assertion to require the original body after the edit
  (`assert _get_body() == "OK"` in the poll loop / `reloaded` only when the body is still `"OK"`) → the
  reload DID fire, so the body is now the sentinel → the "still OK" assertion goes RED. This proves the
  test depends on the live reload, not on the file edit alone. Revert. (Alternative cheap flip: assert
  the served body equals a DIFFERENT sentinel than the one written → RED.) Commit.

---

## Task 4: Test C — engine pool_pre_ping recovery + real dispose_engine (M14)

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Write the test.** Decided fork **(b)** — a framework-side acceptance test, no template
  change. Render baseline, bring up **only `postgres`** from the lite profile, point
  `APP_DATABASE_URL` at its ephemeral host port, and run a self-contained driver **inside the rendered
  project's venv** (`uv run python -c <driver>` in `cwd=dest`) so it imports the project's *shipped*
  `demo.db.engine` module (the module-level `engine`, not conftest's separate test engine). The driver:
  (1) `SELECT 1` through the pooled engine; (2) the test restarts the postgres container
  (`compose restart postgres`) to drop the live connection; (3) `SELECT 1` again — succeeds **only via
  `pool_pre_ping`** (which probes + discards the dead connection and dials a fresh one); (4)
  `dispose_engine()` then assert the **real** pool was disposed.

  The driver runs in TWO `uv run python` invocations around the container restart (a single process
  can't pause for the host to restart the container cleanly): **driver-1** opens the pool + does the
  first `SELECT 1` and exits; the test restarts postgres; **driver-2** (fresh process, same
  `APP_DATABASE_URL`) imports the engine, does `SELECT 1` (proving a brand-new pooled engine connects
  post-restart — the realistic prod-churn recovery is a single long-lived process, so driver-2 ALSO
  does the in-process pre-ping check below), then disposes and asserts pool state. The
  **in-process pre-ping** check (the strict M14 ask) lives entirely in driver-2: it opens a connection,
  the test cannot restart mid-process, so instead driver-2 forces a stale connection by
  `engine.dispose()`-ing only the *checked-in* connections is NOT pre-ping — see the precise mechanism
  below.

  **Precise pre-ping mechanism (in one driver process, no host coordination needed):** SQLAlchemy's
  `pool_pre_ping` issues a lightweight liveness check on **checkout** and transparently reconnects if
  the pooled connection is dead. To exercise it deterministically in a single process: (1) check out a
  connection and note its backend PID (`SELECT pg_backend_pid()`); (2) **terminate that backend from a
  second connection** (`SELECT pg_terminate_backend(<pid>)`), which kills the first connection's server
  process but leaves the (now-dead) connection in the pool on return; (3) check out again and run
  `SELECT 1` — **without** pre-ping this raises an `OperationalError` (server closed the connection);
  **with** pre-ping it silently reconnects and returns `1`. This needs only the one live `postgres`
  container — no restart — making Test C a **single bring-up with no mid-test container restart**,
  which is simpler and faster than the restart approach. (The restart approach is kept as the
  documented fallback if `pg_terminate_backend` is unavailable, but `pg_terminate_backend` ships in
  every Postgres ≥ 9.x, so it will work on `postgres:17`.)

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: drives the rendered module-level DB engine against a real Postgres",
)
def test_rendered_db_engine_pool_pre_ping_and_dispose(tmp_path: Path):
    # FWK26 (M14): pool_pre_ping recovery of the REAL module-level engine and real pool disposal are
    # asserted nowhere — conftest builds a SEPARATE test engine and the graceful-shutdown test
    # monkeypatches dispose_engine. Drive the shipped demo.db.engine against a live compose Postgres:
    # terminate the pooled connection's backend, prove the next checkout recovers via pre-ping, then
    # prove dispose_engine() really disposes the pool. Runs inside the rendered project's venv so it
    # imports the project's own module-level engine (not conftest's).
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0  # need the project venv

    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite",
          "up", "-d", "postgres"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v"]
    env = _compose_env()
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        pg_port = _compose_host_port(dest, [base, dev], "postgres", 5432)
        db_url = f"postgresql+psycopg://app:app@localhost:{pg_port}/app"

        # Wait for postgres to accept connections (its healthcheck is pg_isready; poll a trivial
        # query via the project's psycopg through a tiny driver).
        ready_driver = (
            "import sqlalchemy as sa;"
            "e=sa.create_engine(__import__('os').environ['APP_DATABASE_URL']);"
            "c=e.connect();c.execute(sa.text('SELECT 1'));c.close();print('READY')"
        )
        ready = False
        deadline = time.time() + 90
        while time.time() < deadline:
            r = subprocess.run(
                ["uv", "run", "python", "-c", ready_driver],
                cwd=dest, env={**env, "APP_DATABASE_URL": db_url},
                capture_output=True, text=True,
            )
            if r.returncode == 0 and "READY" in r.stdout:
                ready = True
                break
            time.sleep(2)
        assert ready, "compose postgres never accepted a connection within 90s"

        # The driver exercises the SHIPPED module-level engine:
        #  1) check out a connection, capture its backend PID;
        #  2) from a SECOND connection, pg_terminate_backend(pid) -> the first conn's server process
        #     dies, leaving a dead connection in the pool;
        #  3) check out again + SELECT 1 -> succeeds ONLY via pool_pre_ping (else OperationalError);
        #  4) dispose_engine() -> assert the real pool was disposed (a fresh QueuePool instance with
        #     zero checked-out connections; engine.pool identity changes on dispose()).
        driver = (
            "from sqlalchemy import text\n"
            "from demo.db.engine import engine, dispose_engine\n"
            "# 1) checkout + capture backend pid\n"
            "with engine.connect() as c:\n"
            "    pid = c.execute(text('SELECT pg_backend_pid()')).scalar()\n"
            "# 2) kill that backend from a fresh connection\n"
            "with engine.connect() as k:\n"
            "    k.execute(text('SELECT pg_terminate_backend(:p)'), {'p': pid})\n"
            "    k.commit()\n"
            "# 3) next checkout must transparently reconnect via pool_pre_ping\n"
            "with engine.connect() as c2:\n"
            "    assert c2.execute(text('SELECT 1')).scalar() == 1, 'pre-ping did not recover'\n"
            "    new_pid = c2.execute(text('SELECT pg_backend_pid()')).scalar()\n"
            "    assert new_pid != pid, 'reused the dead backend — pre-ping did not reconnect'\n"
            "# 4) real disposal: capture the pool identity, dispose, assert a fresh pool\n"
            "pool_before = engine.pool\n"
            "dispose_engine()\n"
            "assert engine.pool is not pool_before, 'dispose_engine did not recreate the pool'\n"
            "assert engine.pool.checkedout() == 0, 'connections still checked out after dispose'\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            ["uv", "run", "python", "-c", driver],
            cwd=dest, env={**env, "APP_DATABASE_URL": db_url},
            capture_output=True, text=True,
        )
        assert result.returncode == 0 and result.stdout.strip().endswith("OK"), (
            "the module-level engine pre-ping/dispose driver failed:\n"
            + result.stdout + result.stderr
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
```

- [ ] **Step 1b: Confirm the pool-identity invariant during the GREEN run.** SQLAlchemy `Engine.
  dispose()` by default **disposes the old pool AND replaces it with a fresh, empty pool** (`close=True`),
  so `engine.pool is not pool_before` holds. Verify this empirically on the first GREEN run; if a
  SQLAlchemy version pins `dispose()` to keep the same pool object, fall back to asserting the pool was
  drained instead — `engine.pool.checkedin() == 0 and engine.pool.checkedout() == 0` after dispose (an
  emptied pool) — which is the M14 "real disposal, not a monkeypatched stub" ask either way. The
  non-negotiable: the assertion must FAIL if `dispose_engine()` were a no-op. (Pin the exact form once,
  from the live `engine.pool` behavior; do not leave both in the committed test.)

- [ ] **Step 2: Run — expect GREEN.** `TMPDIR=/var/tmp uv run pytest
  tests/acceptance/test_rendered_project.py::test_rendered_db_engine_pool_pre_ping_and_dispose -q`. If
  the pre-ping checkout raises an `OperationalError` (step 3 of the driver), that is a candidate REAL
  BUG: `build_engine` no longer passes `pool_pre_ping=True` (engine.py:11) → silent stale-connection
  failures under prod churn → shared real-bug policy. If `dispose_engine()` doesn't dispose, same.

- [ ] **Step 3: Bite-proof (cheap — no rebuild; flip the engine to disable the surface).** Two cheap
  options, either suffices:
  - **Pre-ping:** in the driver, temporarily build a NON-pre-ping engine inline
    (`from sqlalchemy import create_engine; e2 = create_engine(<url>)  # no pool_pre_ping`) and run the
    same terminate→reconnect sequence against `e2` → the post-terminate `SELECT 1` raises
    `OperationalError` → the driver exits non-zero → the test goes RED. This proves the recovery in the
    real test depends on `pool_pre_ping`, not on a fresh checkout always working. Revert.
  - **Dispose:** temporarily replace `dispose_engine()` in the driver with a no-op (`pass`) → the
    `engine.pool is not pool_before` assertion (or the drained-pool assertion) goes RED. Revert.
  Commit.

---

## Task 5: Close-out

- [ ] **Step 1: Lint/format.** `uv run ruff check tests/ && uv run ruff format --check
  tests/acceptance/test_rendered_project.py tests/runtime_coverage/registry.py` — clean. Run
  `ruff format` (not just `check`) per [[ruff-format-check-after-inline-edits]].

- [ ] **Step 2: Full FWK26 run (laptop, `TMPDIR=/var/tmp`).** `TMPDIR=/var/tmp uv run pytest
  tests/acceptance/test_rendered_project.py -k "http_redirect_and_mongo_health or hot_reload_picks_up_edit
  or db_engine_pool_pre_ping_and_dispose" -q` → 3 passed. These are heavy (2 dev-stack bring-ups + 1
  postgres-only stack); run serially. `TMPDIR=/var/tmp` is required if `/tmp` is a small tmpfs
  ([[full-suite-exhausts-tmp-tmpfs-use-var-tmp]]). Then `uv run pytest tests/runtime_coverage/ -q`
  (expect all pass with the mongo flip).

- [ ] **Step 3: State + commit.** Per the shared policy this is ONE item on `fwk-coverage-batch`; defer
  the whole-branch Opus review to the end of the batch. Tick FWK26 in `PLAN.md` (or move to Done when
  the batch closes), append `ACTION_LOG.md` entries (per `pi-convention.md`), final commit with the
  skip-marker. **No release** (test-only; any forced template fix is deferred + flagged).

- [ ] **Step 4: Morning-report line.** Record: FWK26 green / which (if any) of M1/M2/M4/M14 went xfail
  on a real bug + the new FWK id + the `ACTION_LOG` ref.

---

## Self-Review

- **Spec coverage:** M1 → Test A redirect half (Task 1); M2 → Test A mongo half (Task 1) + registry
  flip (Task 2); M4 → Test B (Task 3); M14 → Test C (Task 4). ✓
- **Cost forks honored + justified:** M1 and M2 fold into ONE dev-stack bring-up (both read-only probes
  of one running stack; the `mongodb` render adds the `mongo:` service to the same stack the redirect
  needs). M4 uses the cheapest reload-capable stack (`lite` = app+postgres, no Traefik/obs). M14 is a
  single postgres-only bring-up with a deterministic in-process pre-ping mechanism
  (`pg_terminate_backend`) — no mid-test container restart. ✓
- **Ephemeral ports:** every host-port access is via `_compose_host_port(dest, files, service,
  container_port)` (traefik 80, app 8000, postgres 5432) — no hardcoded published ports; the mongo
  client check uses `compose exec` (no host port at all). FWK31-compliant. ✓
- **Docker-gated + local-only:** all three tests `skipif not _docker_available()`. Test A drops the
  `mkcert`/`task` preconditions (it never hits :443 / needs no certs). ✓
- **Non-vacuity:** each surface has a cheap bite-proof — M1 assert-200 / http-Location; M2
  require-unhealthy; M4 assert-the-OLD-response-still-appears → RED; M14 a non-pre-ping engine raises /
  a no-op dispose fails the pool assertion. All flip RED without a rebuild. ✓
- **Registry correctness:** exactly the ONE enumerated FWK26 `_KG` entry (`service:dev.yml:mongo`)
  flips, naming a test Task 1 actually creates (so `test_exercised_entries_name_an_existing_test`
  passes); M1/M4/M14 correctly flip nothing (no enumerated surface — verified). ✓
- **No root-residue leak:** Test A (postgres/mongo/traefik run as image users; only named volumes —
  `down -v` drops them; no bind-mount writes). Test B's app runs as the host UID and the edit is a
  host-side write, so no root residue — still reclaimed defensively in `finally`. Test C only runs
  `uv run python` on the host + a postgres-only stack (no app bind-mount writes). ✓
- **Naming consistency:** the three test names are used identically in the tests, the registry evidence,
  and the close-out `-k` filter. ✓

### Genuine design forks for the human (could not be fully resolved from code alone)

1. **M14 mechanism — (b) framework-side acceptance test, NO template change [PICKED].** The assessment
   suggested EITHER (a) a generated-project functional test in the template payload OR (b) a
   framework-side acceptance test. **This plan picks (b)** because (a) is a template-payload change
   (deferred release per policy) AND the rendered functional tier (in-process testcontainers) is not
   structured to restart/kill a container's backend mid-test, whereas (b) drives the *exact shipped
   module-level engine* (the M14 ask) with no release and reuses the existing compose-Postgres + host
   driver pattern. **Tradeoff the human may want to revisit:** (b) keeps the guard in the laptop-only
   acceptance tier (CI-ignored) rather than shipping it into every consumer's `task ci`. If the team
   would rather the pre-ping/dispose guard travel WITH consumers, switch to (a) and accept the deferred
   template release. The plan is written for (b); switching to (a) is a self-contained swap of Task 4
   (render → uv sync → mirror the driver into a `tests/functional/test_db_engine_pool_lifecycle.py.jinja`
   → run in /tmp per the template-payload TDD loop) and would flag a template-payload change in the
   morning report.

2. **M14 dispose assertion form (Task 4 Step 1b).** Whether `engine.pool is not pool_before` or the
   drained-pool form (`checkedin()==0 and checkedout()==0`) is the right disposal assertion depends on
   the installed SQLAlchemy `Engine.dispose()` semantics (default `close=True` replaces the pool). The
   plan pins the invariant (the assertion must FAIL if dispose were a no-op) and gives both forms; the
   runner confirms which holds on the first GREEN run and commits exactly one. This is a one-line
   empirical confirmation, not an open design choice.

### Real template bugs these tests may surface (per the shared real-bug policy)

- **Traefik :80 redirect broken/removed (M1, Test A).** If `infra/traefik/traefik.yml`'s `web`
  entrypoint loses its `http.redirections.entryPoint` (to websecure / scheme https) block, :80 serves a
  200/404 instead of a 30x → RED. A dev/staging HTTP-upgrade break that the :443-only test can't see.
- **mongo healthcheck quoting / volume (M2, Test A).** The mongosh-ping healthcheck uses nested quoting
  (`"db.adminCommand('ping').ok" | grep -q 1`, dev.yml.jinja:87); a quoting regression or a broken
  `mongodata` volume mount means the service never reports `healthy` → RED. Exactly the masked-by-
  app-coverage failure M2 names.
- **Hot-reload dead on the bind mount (M4, Test B).** If `--reload` or `WATCHFILES_FORCE_POLLING=true`
  is dropped from the dev app service (dev.yml.jinja:9,15), or inotify silently fails on the WSL bind
  mount without the polling fallback, the sentinel edit is never picked up → RED. The core dev
  inner-loop regression.
- **pool_pre_ping / dispose regression (M14, Test C).** If `build_engine` stops passing
  `pool_pre_ping=True` (engine.py:11), the post-terminate checkout raises `OperationalError` → RED
  (silent stale-connection failures under prod churn). If `dispose_engine()` stops really disposing the
  pool, the pool-state assertion fails → RED. Most likely a low-probability find (the engine is stable),
  but it is the precise thing M14 says is asserted nowhere today.
