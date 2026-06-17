# FWK23 — Observability live exercise — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans`. Read the shared
> policy first: `docs/superpowers/plans/2026-06-17-coverage-batch-execution-policy.md` (branch
> `fwk-coverage-batch`, commit cadence + skip-marker gate, real-bug rule, **no release**,
> laptop/`TMPDIR=/var/tmp`, non-vacuity). This is item **#2** of the batch and lands **after FWK24**
> (whose `_traefik_request` / `_traefik_ws_upgrade` / `_mkcert_ssl_context` helpers may be assumed to
> exist — FWK23 does not redefine them, though it only needs HTTP-API helpers, not Traefik). Steps
> use `- [ ]`.

**Goal:** Close the C3 observability med cluster — five live-runtime gaps that today ship to a
consumer's prod unexercised:

- **M7** — a *worker-side* OTEL span actually reaches Tempo (the existing Tempo test is app-only and
  queries `service.name='demo'`, which an app span alone satisfies — a worker-span regression passes
  silently).
- **M10** — the exporter / self-scrape Prometheus targets report `up==1`: `prometheus` self-scrape +
  `otel-collector` (baseline), and the battery-gated `postgres-exporter` / `redis-exporter` /
  `celery-exporter` / `mongodb-exporter` (variant render). The only live-targets test today
  hard-filters to `job=='app'`.
- **M11** — Prometheus alert rule files are actually loaded/parsed (`/api/v1/rules`), not merely
  mounted. A malformed PromQL expr fails rule-group load while target health stays green.
- **M12** — Alertmanager *routes* a webhook notification through the real `alertmanager.yml`
  (`amtool check-config` today validates syntax only).
- **M13** — Grafana datasources + dashboards are provisioned and resolve, with anonymous-admin auth
  (Grafana is merged today only so `--profile dev` config-validation passes; "the obs containers
  never start").

**Architecture:** Three live bring-ups, chosen to bound cost (this is the heaviest stack):

- **Test A — baseline obs stack, multi-surface assert (one bring-up).** Render baseline `DATA`, up
  `-f base -f observability -f dev --profile dev` (the same merge the existing
  `test_rendered_project_dev_stack_prometheus_scrapes_app` uses). Against this ONE stack assert
  M10-baseline (`prometheus`, `otel-collector` self-scrape targets `up==1`), M11 (the baseline rule
  groups loaded), and M13 (Grafana health + datasources + dashboards). **Justification:** these three
  surfaces all read-only-query the prometheus/grafana HTTP APIs of an already-running stack; a single
  bring-up amortises the ~2–4 min build+boot across all three. Splitting them would triple the
  heaviest bring-up in the suite for no extra signal. M12 (alertmanager routing) and M7 (worker
  tracing) need *different* compose shapes (a webhook receiver / a live worker + OTEL), so they get
  their own tests.
- **Test B — battery-variant exporter targets (one bring-up).** The four exporters are battery-gated
  (`postgres-exporter` always; `redis-exporter` under `redis|workers`; `celery-exporter` under
  `workers`; `mongodb-exporter` under `mongodb`). Render the **`workers+redis+mongodb`** variant so
  ALL FOUR exporter services + their scrape jobs render in one stack, up the obs overlay (with the
  exporters' data deps), and assert each exporter target `up==1` in `/api/v1/targets`. **One render
  covers all four** — no need for per-battery variants. (`postgres-exporter` also renders in baseline,
  but its scrape job needs postgres up; Test B brings postgres up anyway, so it is asserted here with
  the others rather than complicating Test A.)
- **Test C — alertmanager live routing (M12).** A tiny in-process `http.server` thread is the webhook
  receiver. Bring up `alertmanager` alone (it needs no data deps) with a **test override** that mounts
  a `webhook_url` file pointing at `host.docker.internal:<receiver-port>` (the rendered
  `alertmanager.yml` reads the receiver URL from `url_file: /etc/alertmanager/webhook_url`). `POST` a
  firing alert to `/api/v2/alerts`, then assert the receiver thread captured the routed/grouped
  notification.
- **Test D — worker-side OTEL span reaches Tempo (M7).** Reuse the FWK20 live-broker pattern: render
  `workers`, up `postgres+redis+worker+beat+otel-collector+tempo` under the obs overlay (OTEL is
  enabled by `observability.yml`'s `APP_OTEL_ENABLED=true` on the `app`/worker env — confirm it is set
  on the worker; see Task 5 Step 1), enqueue a task through the live broker (the FWK20 `_exec`
  recipe), then query Tempo `/api/search` filtered to a **worker/task-specific** attribute
  (`name="run/demo.tasks.tasks.heartbeat"` or the `celery` span kind) — NOT `service.name='demo'`,
  which an app span already satisfies.

**Tech Stack:** Python, pytest, Docker, the existing acceptance harnesses
(`_compose_env`, `_compose_host_port` — FWK31 ephemeral ports, NEVER hardcode published ports —
`_free_tcp_port`, the `_isolate_compose_project` autouse fixture, the FWK20 `compose exec -T`
pattern), Prometheus v2.55.1 / Grafana 11.3.0 / Alertmanager v0.27.0 / Tempo 2.6.1 /
otel-collector 0.111.0 HTTP APIs.

---

## File Structure

- **Modify** `tests/acceptance/test_rendered_project.py` — add a small shared helper
  `_poll_json(url, *, timeout, predicate)` (DRY the "poll an HTTP-JSON API until a predicate holds"
  loop the four tests share), then the four tests (A/B/C/D).
- **Modify** `tests/runtime_coverage/registry.py` — flip the **8 FWK23 KNOWN_GAP entries** to
  EXERCISED, each naming its closing test (exact entries enumerated in Task 6).
- **Modify** `PLAN.md` + `ACTION_LOG.md` (per the shared policy — required on every commit).

**Registry note (M7/M11 have no enumerated surface).** Like FWK24's M8/M9, the worker-OTEL path
(M7) and the alert-rules-loaded check (M11) are *in-process / config* surfaces, not enumerated compose
services — there is **no** `prometheus-rules` or `worker-tracing` registry key (verified:
`grep FWK23 registry.py` returns exactly the 8 service entries below). So Tests A (the M11 half) and D
flip nothing in the registry; they are pure coverage adds. The 8 flips come from M10 (6 exporter/
self-scrape services) + M13 (2 grafana services) + M12 (1 alertmanager service) = 9 — but
`service:dev.yml:grafana` and `service:observability.yml:grafana` are TWO keys for the one Grafana
surface, so M13 is 2 keys; total **8** (see Task 6 for the exact list).

**No template change is expected** (test-only). If a test goes red on a real template defect (a wrong
datasource URL, an unscraped exporter, a malformed rule, a mis-routed alert), STOP and follow the
shared real-bug policy (root-cause → small+scoped fix + render guard + deferred release, OR
`xfail(strict=True)` + leave the registry entry KNOWN_GAP + a new `PLAN.md` `Next` FWK id + an
`ACTION_LOG` entry + a morning-report line). **Anticipated candidates are listed in the Self-Review.**

---

## Task 1: Shared `_poll_json` helper

**Files:** Modify `tests/acceptance/test_rendered_project.py` (place beside `_run_image_serving`).

- [ ] **Step 1: Add the helper.** The file already imports `json`, `socket`, `time`,
  `urllib.request`, and `Iterator`/`contextmanager`.

```python
def _poll_json(url: str, *, timeout: float, predicate) -> dict | None:
    """Poll an HTTP endpoint returning JSON until `predicate(parsed)` is truthy or `timeout`
    elapses. Returns the parsed JSON that satisfied the predicate, else None. Tolerates the
    not-yet-up window (connection refused / 5xx / partial JSON) by swallowing OSError + JSON
    errors between polls — the obs stack's scrape/ingest/provisioning all have a boot lag."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                parsed = json.loads(resp.read())
            if predicate(parsed):
                return parsed
        except (OSError, ValueError):
            pass
        time.sleep(3)
    return None
```

- [ ] **Step 2: Lint** — `uv run ruff check tests/acceptance/test_rendered_project.py && uv run ruff format tests/acceptance/test_rendered_project.py`. Commit per shared policy (PLAN/ACTION_LOG staged + skip-marker; `git add` then `git commit` as separate calls).

---

## Task 2: Test A — baseline obs stack: self-scrape targets + rules loaded + Grafana provisioned (M10-baseline, M11, M13)

**Files:** Modify `tests/acceptance/test_rendered_project.py` (place after
`test_rendered_project_dev_stack_prometheus_scrapes_app`, ~line 1088).

- [ ] **Step 1: Write the test.** It brings up the FULL obs stack (`--profile dev`, no service
  allowlist, so grafana/alertmanager/otel-collector/tempo/loki all start — unlike the FWK20 worker
  test, which allowlists services to keep the obs containers down). Discover every host port via
  `_compose_host_port`.

```python
@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live obs-stack test"
)
def test_rendered_obs_stack_self_scrape_rules_and_grafana(tmp_path: Path):
    # FWK23 (M10-baseline + M11 + M13): the only live obs test today asserts the `app` scrape
    # target healthy and nothing else — the prometheus/otel-collector self-scrape targets, the
    # alert-rule groups, and the entire Grafana provisioning (datasources/dashboards/anon-auth)
    # are present-but-unasserted. Bring the FULL obs stack up ONCE and assert all three.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    files = ["infra/compose/base.yml", "infra/compose/observability.yml", "infra/compose/dev.yml"]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    # No service allowlist: bring the whole --profile dev obs stack up (grafana included). dev.yml
    # re-applies grafana's anonymous-admin override (GF_AUTH_ANONYMOUS_*), so M13 anon-auth is live.
    up = ["docker", "compose", *fargs, "--profile", "dev", "up", "-d", "--build"]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    assert subprocess.run(up, cwd=dest, env=env).returncode == 0
    try:
        prom_port = _compose_host_port(dest, files, "prometheus", 9090)
        graf_port = _compose_host_port(dest, files, "grafana", 3000)

        # --- M10-baseline: prometheus + otel-collector self-scrape targets up==1 ---
        # (The app target is already covered by the existing test; here assert the self-scrape ones.)
        def _baseline_targets_up(parsed: dict) -> bool:
            actives = parsed.get("data", {}).get("activeTargets", [])
            by_job = {t.get("labels", {}).get("job"): t.get("health") for t in actives}
            return by_job.get("prometheus") == "up" and by_job.get("otel-collector") == "up"

        targets = _poll_json(
            f"http://localhost:{prom_port}/api/v1/targets?state=active",
            timeout=120,
            predicate=_baseline_targets_up,
        )
        assert targets is not None, (
            "prometheus/otel-collector self-scrape targets never both reported up==1 within 120s"
        )

        # --- M11: alert rule groups loaded/parsed (no rule-group load error) ---
        # Baseline (no batteries) renders: slo, postgres, otel-collector, prometheus, alertmanager.
        expected_groups = {"slo", "postgres", "otel-collector", "prometheus", "alertmanager"}

        def _rules_loaded(parsed: dict) -> bool:
            groups = parsed.get("data", {}).get("groups", [])
            names = {g.get("name") for g in groups}
            return expected_groups.issubset(names)

        rules = _poll_json(
            f"http://localhost:{prom_port}/api/v1/rules", timeout=90, predicate=_rules_loaded
        )
        assert rules is not None, (
            "prometheus did not load all baseline rule groups "
            f"{sorted(expected_groups)} within 90s (a malformed PromQL expr fails the group load)"
        )

        # --- M13: Grafana health (anon), datasources resolve, dashboards provisioned ---
        # anon-admin is on (dev.yml override), so no auth header is needed.
        health = _poll_json(
            f"http://localhost:{graf_port}/api/health",
            timeout=90,
            predicate=lambda p: p.get("database") == "ok",
        )
        assert health is not None, "grafana /api/health never reported database==ok within 90s"

        ds = _poll_json(
            f"http://localhost:{graf_port}/api/datasources",
            timeout=30,
            predicate=lambda p: {d.get("uid") for d in p} >= {"prometheus", "loki", "tempo"},
        )
        assert ds is not None, (
            "grafana did not provision the prometheus/loki/tempo datasources "
            "(wrong uid or a malformed provisioning yaml)"
        )
        # Each datasource's upstream health probe must pass (catches a wrong url in the .yml).
        for uid in ("prometheus", "loki", "tempo"):
            h = _poll_json(
                f"http://localhost:{graf_port}/api/datasources/uid/{uid}/health",
                timeout=60,
                predicate=lambda p: p.get("status") == "OK",
            )
            assert h is not None, (
                f"grafana datasource {uid!r} health probe never returned OK "
                "(the datasource url in provisioning/datasources/*.yml is unreachable/wrong)"
            )

        # dashboards: the SLO provider loads the provisioned dashboards from /var/lib/grafana/dashboards.
        search = _poll_json(
            f"http://localhost:{graf_port}/api/search?type=dash-db",
            timeout=60,
            predicate=lambda p: len(p) >= 1,
        )
        assert search is not None, (
            "grafana provisioned no dashboards (the dashboards provider.yml path or the dashboard "
            "JSON failed to load)"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
```

- [ ] **Step 2: Run — expect GREEN.** `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_obs_stack_self_scrape_rules_and_grafana -q`. First build ~3–5 min. If a datasource-health probe or a rule group fails, that is a candidate REAL BUG → follow the shared real-bug policy (the datasource-URL and malformed-rule cases are exactly the silent-prod failures M11/M13 exist to catch).

- [ ] **Step 3: Bite-proof (cheap — flip an asserted marker, no rebuild).**
  - For M10/M11: temporarily change `_baseline_targets_up` to require a non-existent job
    (`by_job.get("does-not-exist") == "up"`) → the poll times out → RED. Revert.
  - For M11: temporarily add `"no-such-group"` to `expected_groups` → RED. Revert.
  - For M13: temporarily require a 4th datasource uid (`>= {"prometheus", "loki", "tempo", "x"}`) →
    RED. Revert.
  Each flip proves the assertion truly depends on the live response. Commit (one bite-proof flip is
  sufficient evidence; do the cheapest).

---

## Task 3: Test B — battery-variant exporter scrape targets up==1 (M10-batteries)

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Write the test.** Render `workers+redis+mongodb` so all four exporters
  (`postgres-exporter`, `redis-exporter`, `celery-exporter`, `mongodb-exporter`) + their prometheus
  scrape jobs (`postgres`, `redis`, `celery`, `mongodb`) render. Up the obs overlay PLUS the
  exporters' data deps (`postgres`, `redis`, `mongo`) and the worker (so `celery-exporter`'s broker
  has traffic and the celery exporter reports up — the celery-exporter scrapes the broker, so it is
  `up` once redis is healthy regardless of worker activity, but bring the worker up too for realism).

```python
@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live obs-stack test"
)
def test_rendered_obs_exporter_targets_up(tmp_path: Path):
    # FWK23 (M10-batteries): the postgres/redis/celery/mongodb exporter scrape targets are
    # battery-gated AND present-but-unasserted (the baseline live-targets test hard-filters to
    # job=='app'). Render workers+redis+mongodb so ALL FOUR exporters render in one stack, up the
    # obs overlay + the exporters' data deps, and assert each exporter target reports up==1.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": resolve(["workers", "redis", "mongodb"])})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    files = ["infra/compose/base.yml", "infra/compose/observability.yml", "infra/compose/dev.yml"]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    # Up the scrape source (prometheus) + every exporter + each exporter's data dep. The exporters
    # depend_on their data store HEALTHY (postgres/redis/mongo), so naming the exporters pulls the
    # deps; name them explicitly too for clarity. The app is needed so prometheus's depends_on
    # (service_healthy) is satisfied and the scrape loop runs.
    services = [
        "app", "postgres", "redis", "mongo", "prometheus",
        "postgres-exporter", "redis-exporter", "celery-exporter", "mongodb-exporter",
    ]
    up = ["docker", "compose", *fargs, "--profile", "dev", "up", "-d", "--build", *services]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    assert subprocess.run(up, cwd=dest, env=env).returncode == 0
    try:
        prom_port = _compose_host_port(dest, files, "prometheus", 9090)
        # The exporter scrape JOB names in prometheus.yml are: postgres, redis, celery, mongodb.
        expected_jobs = {"postgres", "redis", "celery", "mongodb"}

        def _exporters_up(parsed: dict) -> bool:
            actives = parsed.get("data", {}).get("activeTargets", [])
            up_jobs = {
                t.get("labels", {}).get("job")
                for t in actives
                if t.get("health") == "up"
            }
            return expected_jobs.issubset(up_jobs)

        targets = _poll_json(
            f"http://localhost:{prom_port}/api/v1/targets?state=active",
            timeout=180,
            predicate=_exporters_up,
        )
        assert targets is not None, (
            "not all exporter scrape targets reported up==1 within 180s "
            f"(expected jobs {sorted(expected_jobs)} — a wrong DATA_SOURCE_NAME, a down exporter, "
            "or a wrong telemetry address would leave one down)"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
        # mongo/postgres/redis run as their image users; nothing root-owned is written to the bind
        # mount here (only named volumes), so no chown-reclaim is needed (cf. the worker test, which
        # does need it because worker/beat write the bind-mounted /app). Down -v drops the volumes.
```

- [ ] **Step 2: Run — expect GREEN.** `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_obs_exporter_targets_up -q`. If a specific exporter never reaches `up==1`, that is a candidate REAL BUG (e.g. a wrong `DATA_SOURCE_NAME` for postgres-exporter, or a celery-exporter `--broker-url` mismatch) → root-cause per the shared policy; name the offending job in the failure (the assert message already lists the expected jobs).

- [ ] **Step 3: Bite-proof (cheap).** Temporarily add a non-existent job to `expected_jobs`
  (e.g. `{"postgres", "redis", "celery", "mongodb", "nope"}`) → the poll times out → RED. Revert.
  This proves the assert depends on the live target set. Commit.

---

## Task 4: Test C — alertmanager routes a webhook notification (M12)

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Write the test.** Mechanism, concretely:
  1. Render baseline `DATA` — `alert_channels` defaults to `["webhook"]`, so the rendered
     `alertmanager.yml` has a `webhook_configs` receiver reading `url_file:
     /etc/alertmanager/webhook_url`. (Confirmed: `copier.yml` `alert_channels.default: ["webhook"]`.)
  2. Start a tiny `http.server.HTTPServer` in a daemon thread bound to `0.0.0.0:<free-port>`; its
     handler appends each POST body to a shared list (the capture).
  3. Write a `webhook_url` file containing `http://host.docker.internal:<receiver-port>/` and a
     **test override** compose file that (a) mounts that file at
     `/etc/alertmanager/webhook_url` and (b) adds `extra_hosts: ["host.docker.internal:host-gateway"]`
     to the `alertmanager` service so the container can reach the host's receiver. Lower the
     `group_wait` so the routed notification fires fast — do this by mounting a tweaked alertmanager
     config is unnecessary; instead just POST and poll up to the default `group_wait` (10s) +
     margin.
  4. Bring up ONLY `alertmanager` (it has no data deps). Discover its host port.
  5. `POST` a firing alert to `http://localhost:<am-port>/api/v2/alerts` (a JSON array with one
     alert: `labels.alertname`, `startsAt` now, no `endsAt` → firing).
  6. Poll the capture list until it received a notification whose payload references the alert.

```python
@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live alertmanager test"
)
def test_rendered_alertmanager_routes_webhook(tmp_path: Path):
    # FWK23 (M12): amtool check-config validates SYNTAX only — no test fires an alert through the
    # real alertmanager.yml and asserts the route/group/receiver actually delivers. Bring up
    # alertmanager with its webhook receiver pointed at a local capture server, POST a firing alert,
    # and assert the capture server received the routed/grouped notification.
    import http.server
    import json as _json
    import threading
    from datetime import datetime, timezone

    dest = tmp_path / "demo"
    render_project(dest, DATA)  # alert_channels defaults to ["webhook"] -> webhook_configs receiver
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    captured: list[dict] = []

    class _Receiver(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                captured.append(_json.loads(body))
            except ValueError:
                captured.append({"_raw": body.decode(errors="replace")})
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):  # silence the default stderr logging
            pass

    recv_port = _free_tcp_port()
    server = http.server.HTTPServer(("0.0.0.0", recv_port), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Mount the webhook_url file (the rendered alertmanager.yml reads `url_file`) and give the
    # container a route back to the host's capture server via host.docker.internal.
    url_file = dest / "infra" / "observability" / "alertmanager" / "webhook_url"
    url_file.write_text(f"http://host.docker.internal:{recv_port}/")
    (dest / "infra" / "compose" / "fwk23.override.yml").write_text(
        "services:\n"
        "  alertmanager:\n"
        "    extra_hosts:\n"
        '      - "host.docker.internal:host-gateway"\n'
        "    volumes:\n"
        "      - \"../observability/alertmanager/webhook_url:/etc/alertmanager/webhook_url:ro\"\n"
    )
    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/fwk23.override.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    up = ["docker", "compose", *fargs, "up", "-d", "alertmanager"]
    down = ["docker", "compose", *fargs, "down", "-v"]
    env = _compose_env()
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        am_port = _compose_host_port(dest, files, "alertmanager", 9093)

        # Wait for alertmanager to be ready (its own /-/ready endpoint).
        ready = _poll_json(
            f"http://localhost:{am_port}/api/v2/status",
            timeout=60,
            predicate=lambda p: bool(p.get("cluster") or p.get("versionInfo")),
        )
        assert ready is not None, "alertmanager never became ready within 60s"

        # POST a firing alert. /api/v2/alerts accepts a JSON array of alerts.
        now = datetime.now(timezone.utc).isoformat()
        alert = [
            {
                "labels": {"alertname": "FWK23ProbeAlert", "severity": "warning"},
                "annotations": {"summary": "fwk23 routing probe"},
                "startsAt": now,
            }
        ]
        req = urllib.request.Request(
            f"http://localhost:{am_port}/api/v2/alerts",
            data=_json.dumps(alert).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status in (200, 202), f"alertmanager rejected the alert POST: {resp.status}"

        # The route's group_wait is 10s; poll the capture server for the routed notification.
        deadline = time.time() + 60
        routed = None
        while time.time() < deadline:
            for note in captured:
                alerts = note.get("alerts", []) if isinstance(note, dict) else []
                if any(
                    a.get("labels", {}).get("alertname") == "FWK23ProbeAlert" for a in alerts
                ):
                    routed = note
                    break
            if routed is not None:
                break
            time.sleep(2)
        assert routed is not None, (
            "alertmanager never routed the firing alert to the webhook receiver within 60s "
            "(a route/group/receiver-wiring regression that stays amtool-valid would do this)"
        )
        # The grouped notification carries the receiver name from the route.
        assert routed.get("receiver") == "default", (
            f"webhook notification routed to an unexpected receiver: {routed.get('receiver')!r}"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
        server.shutdown()
```

- [ ] **Step 2: Run — expect GREEN.** `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_alertmanager_routes_webhook -q`. If the receiver never captures, root-cause: confirm `host.docker.internal` resolves in the container (the `extra_hosts: host-gateway` line is required on Linux/WSL2), and that the rendered receiver block is `webhook_configs` (it is, given the `["webhook"]` default). A genuine route/receiver-wiring bug here is exactly the M12 silent-prod hazard.

- [ ] **Step 3: Bite-proof (cheap, by disabling the surface — no rebuild).** Point the `webhook_url`
  file at a dead port (e.g. `http://host.docker.internal:1/`) and re-run → the capture list stays
  empty → the `routed is not None` assert goes RED, proving the test depends on real delivery, not on
  the POST returning 202. Revert. (Alternative cheap flip: assert
  `routed.get("receiver") == "nope"` → RED.) Commit.

---

## Task 5: Test D — worker-side OTEL span reaches Tempo (M7)

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Worker OTEL env — already set (no override needed).** Verified against the template:
  the dev `worker:` service in `infra/compose/dev.yml.jinja` sets `APP_OTEL_ENABLED: "true"` +
  `APP_OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"` directly in its `environment:` map
  (NOT inherited from `observability.yml`, which sets them on `app` only). So bringing the worker up
  under `-f base -f observability -f dev --profile dev` gives it OTEL-on with no test override. The
  CeleryInstrumentor + worker provider in `tracing.py.jinja:61-74` is gated on
  `settings.otel_enabled`, so this env is load-bearing. **No `fwk23.worker-otel.override.yml` is
  required** — drop the override from the test. (If a future template change removes the worker's
  OTEL env, this test goes RED, which is the correct M7 signal.)

- [ ] **Step 2: Write the test.** Reuse the FWK20 live-broker recipe (the `_exec` closure, the
  alembic-on-worker bootstrap, the host-UID chown-reclaim teardown). Enqueue the shipped `heartbeat`
  task (or the FWK20 `_acceptance_boom`) through the live broker, then query Tempo `/api/search`
  filtered to a **worker/task-specific** span — the CeleryInstrumentor emits a span named
  `run/<task-dotted-path>` with kind CONSUMER, distinct from any app HTTP span. Query Tempo with a
  TraceQL filter on the span name rather than `service.name`.

```python
@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live worker-tracing test"
)
def test_rendered_worker_span_reaches_tempo(tmp_path: Path):
    # FWK23 (M7): the Tempo test is app-only and queries service.name='demo' (shared by app+worker),
    # so a worker-span regression passes silently. Bring up worker + otel-collector + tempo with OTEL
    # enabled, run a Celery task through the LIVE broker, and assert a WORKER/TASK span (the
    # CeleryInstrumentor 'run/<task>' span) reaches Tempo — not just service.name.
    import urllib.parse

    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": resolve(["workers"])})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base, obs, dev = (
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    )
    # The dev worker service already sets APP_OTEL_ENABLED=true + the OTLP endpoint (verified in
    # dev.yml.jinja), so OTEL is on with no override.
    files = [base, obs, dev]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    compose = ["docker", "compose", *fargs, "--profile", "dev"]
    # otel-collector forwards to tempo; bring up the worker's data deps + the trace pipeline.
    up = [
        *compose, "up", "-d", "--build",
        "postgres", "redis", "worker", "otel-collector", "tempo",
    ]
    down = [*compose, "down", "-v"]
    env = _compose_env()

    def _exec(*argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*compose, "exec", "-T", *argv], cwd=dest, env=env,
            capture_output=True, text=True, check=check,
        )

    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        # worker depends_on postgres+redis healthy; create the schema by hand (the app service, which
        # would migrate, is not started). Mirrors the FWK20 worker bootstrap.
        migrated = False
        deadline = time.time() + 120
        while time.time() < deadline:
            if _exec("worker", "alembic", "upgrade", "head", check=False).returncode == 0:
                migrated = True
                break
            time.sleep(3)
        assert migrated, "alembic upgrade head never succeeded in the worker container"

        # Enqueue the shipped heartbeat task through the live redis broker; the worker runs it under
        # CeleryInstrumentor, emitting a 'run/demo.tasks.tasks.heartbeat' span exported to tempo.
        _exec(
            "worker", "python", "-c",
            "from demo.tasks.tasks import heartbeat; heartbeat.delay()",
        )

        tempo_port = _compose_host_port(dest, files, "tempo", 3200)
        # TraceQL: match a span by name (the celery task span), NOT service.name. URL-encode the query
        # `{ name =~ "run/.*heartbeat.*" }`. (If the worker's celery span name differs, broaden to
        # `{ span.celery.task_name != "" }` — confirm the attribute via a one-off tempo search during
        # the GREEN run.)
        traceql = '{ name =~ "run/.*heartbeat.*" }'
        q = urllib.parse.urlencode({"q": traceql, "limit": "1"})

        found = _poll_json(
            f"http://localhost:{tempo_port}/api/search?{q}",
            timeout=120,
            predicate=lambda p: bool(p.get("traces")),
        )
        assert found is not None, (
            "no WORKER/TASK span reached Tempo within 120s — the celery task span "
            "'run/<task>' is missing (worker OTEL tracing is the M7 surface; an app span alone "
            "would NOT satisfy this name filter)"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
        subprocess.run(
            ["docker", "run", "--rm", "-v", f"{dest}:/work", "alpine",
             "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/work"]
        )
```

- [ ] **Step 2b: Verify the span-name filter during the GREEN run.** The exact CeleryInstrumentor
  span name can be `run/<task>` or `<task>` depending on the instrumentation version. During Step 3's
  first run, if the `name =~ "run/.*heartbeat.*"` filter returns no traces while
  `{ resource.service.name = "demo" }` DOES (proving traces arrive), the worker span name differs —
  query Tempo's `/api/search/tags` + `/api/v2/search/tag/name/values` once to read the real span name
  and tighten the filter to whatever distinguishes the **worker/task** span from the app HTTP span
  (e.g. `{ span.celery.task_name = "demo.tasks.tasks.heartbeat" }`, since `celery.task_name` is a
  worker-only attribute). The non-negotiable: the filter must NOT be satisfiable by an app-only span.

- [ ] **Step 3: Run — expect GREEN.** `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_worker_span_reaches_tempo -q`. If no worker span ever arrives (and Step 2b confirms traces arrive but only app ones), that is a candidate REAL BUG: worker OTEL is not wired (the worker env, `worker_process_init` hook, or `configure_worker_tracing`) → real-bug policy.

- [ ] **Step 4: Bite-proof (the point of M7 — distinguish worker from app).** Two cheap flips,
  either suffices:
  - Re-run with the worker OTEL env forced off (`fwk23` override `APP_OTEL_ENABLED: "false"` on the
    worker) → the worker emits no span → RED while the stack still boots. This proves the assert
    depends on worker tracing specifically. Revert.
  - OR temporarily change the TraceQL to match an app-only path
    (`{ name =~ "GET /heartbeat" }` with no worker task run) and confirm it would pass for an app
    span — demonstrating the chosen worker-span filter is strictly narrower. Revert.
  Commit.

---

## Task 6: FWK29 registry reconciliation

**Files:** Modify `tests/runtime_coverage/registry.py`.

Flip these **8** entries from `_KG` to `_EX`, each naming its closing test. (Exact keys verified
against the live `registry.py`; line anchors preserved.)

- [ ] **Step 1: M10 — the 6 exporter/self-scrape service entries.**

  - `service:observability.yml:otel-collector` → `_EX`, evidence
    `test_rendered_obs_stack_self_scrape_rules_and_grafana` (asserted `up==1` in Test A).
  - `service:observability.yml:postgres-exporter` → `_EX`, evidence
    `test_rendered_obs_exporter_targets_up` (Test B).
  - `service:observability.yml:redis-exporter` → `_EX`, evidence
    `test_rendered_obs_exporter_targets_up`.
  - `service:observability.yml:celery-exporter` → `_EX`, evidence
    `test_rendered_obs_exporter_targets_up`.
  - `service:observability.yml:mongodb-exporter` → `_EX`, evidence
    `test_rendered_obs_exporter_targets_up`.

  Replace each `_KG` + evidence accordingly, e.g.:

  ```python
      SurfaceClass(
          "service:observability.yml:otel-collector",
          "infra/compose/observability.yml",
          _EX,
          # FWK23/M10: the otel-collector self-scrape target (:8888) is asserted up==1 on the live
          # baseline obs stack (alongside the prometheus self-scrape).
          "test_rendered_obs_stack_self_scrape_rules_and_grafana",
      ),
  ```

  (The `prometheus` self-scrape target has no separate registry key — `service:observability.yml:prometheus`
  is already `_EX` via the existing app-scrape test — so the prometheus self-scrape assertion in Test A
  is a coverage add with no flip, like M11.)

- [ ] **Step 2: M12 — alertmanager.**

  - `service:observability.yml:alertmanager` → `_EX`, evidence
    `test_rendered_alertmanager_routes_webhook`.

- [ ] **Step 3: M13 — the two grafana entries (one surface, two keys).**

  - `service:observability.yml:grafana` → `_EX`, evidence
    `test_rendered_obs_stack_self_scrape_rules_and_grafana`.
  - `service:dev.yml:grafana` → `_EX`, evidence
    `test_rendered_obs_stack_self_scrape_rules_and_grafana` (the test ups `--profile dev`, which
    merges the dev.yml anon-auth override — so the dev-specific grafana surface is exercised too).

- [ ] **Step 4: Confirm nothing else flips.** M7 (worker tracing) and M11 (rule-group load) have **no**
  enumerated registry surface (verified: `grep -n "FWK23" registry.py` lists exactly the 8 service
  entries above; there is no `prometheus-rules:*` or `*:worker-tracing` key). Tests A (M11 half) and D
  are coverage adds that flip nothing. Do NOT invent registry keys for them.

- [ ] **Step 5: Run the completeness suite.** `uv run pytest tests/runtime_coverage/ -q`. Expect all
  pass: `test_exercised_entries_name_an_existing_test` confirms each named test exists (so the four
  new tests must already be in the file — Tasks 2–5 land first); `test_known_gap_entries_link_a_task`
  no longer sees the 8 flipped entries; `test_every_surface_is_classified` /
  `test_no_stale_registry_entries` unaffected (no surfaces added/removed). Commit.

---

## Task 7: Close-out

- [ ] **Step 1: Lint/format.** `uv run ruff check tests/ && uv run ruff format --check tests/acceptance/test_rendered_project.py tests/runtime_coverage/registry.py`. (Run `ruff format` — not just `check` — per [[ruff-format-check-after-inline-edits]].)

- [ ] **Step 2: Full obs-test run (optional, on the laptop with `TMPDIR=/var/tmp`).**
  `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py -k "obs_stack_self_scrape or obs_exporter_targets or alertmanager_routes_webhook or worker_span_reaches_tempo" -q` → 4 passed. These are heavy (3 obs bring-ups + 1 worker stack); run serially. If `/tmp` is a small tmpfs, `TMPDIR=/var/tmp` is required ([[full-suite-exhausts-tmp-tmpfs-use-var-tmp]]).

- [ ] **Step 3: State + commit.** Per the shared policy this is ONE item on `fwk-coverage-batch`;
  defer the whole-branch Opus review to the end of the batch. Tick FWK23 in `PLAN.md` (or move to Done
  when the batch closes), append `ACTION_LOG.md` entries (per `pi-convention.md`), final commit with
  the skip-marker. **No release** (test-only; any forced template fix is deferred + flagged).

- [ ] **Step 4: Morning-report line.** Record: FWK23 green / which (if any) of the 5 surfaces went
  xfail on a real bug + the new FWK id + the `ACTION_LOG` ref.

---

## Self-Review

- **Spec coverage:** M7 → Test D (Task 5); M10 → Test A baseline-self-scrape (Task 2) + Test B
  battery exporters (Task 3); M11 → Test A rules half (Task 2); M12 → Test C (Task 4); M13 → Test A
  grafana half (Task 2). Registry flips → Task 6. ✓
- **Cost forks honored + justified:** Test A is ONE bring-up asserting 3 surfaces (M10-baseline +
  M11 + M13) because all three only read the prometheus/grafana HTTP APIs of one running stack —
  splitting them would triple the heaviest bring-up for no extra signal. M12 (needs a receiver) and
  M7 (needs a live worker + OTEL) get separate bring-ups because their compose shapes differ. Test B
  uses ONE `workers+redis+mongodb` render to exercise all four battery-gated exporters at once (no
  per-battery variants); nothing is dropped — all four exporter jobs are asserted. ✓
- **Ephemeral ports:** every host-port access is via `_compose_host_port(dest, files, service,
  container_port)` (prometheus 9090, grafana 3000, alertmanager 9093, tempo 3200) — no hardcoded
  published ports (FWK31). The webhook receiver uses `_free_tcp_port()` on the host. ✓
- **Non-vacuity:** each test has a cheap bite-proof (Task 2 flip a marker; Task 3 add a phantom job;
  Task 4 dead webhook port; Task 5 worker-OTEL-off OR app-only filter) — all flip RED without a
  rebuild. ✓
- **Registry correctness:** exactly the 8 enumerated FWK23 `_KG` entries flip, each naming a test that
  Tasks 2–5 actually create (so the `test_exercised_entries_name_an_existing_test` guard passes); M7
  and M11 correctly flip nothing (no enumerated surface). ✓
- **Real-bug readiness:** each test's failure message names the silent-prod hazard it would catch, and
  the run steps route a genuine failure to the shared real-bug policy. ✓

### Genuine design forks for the human (could not be fully resolved from code alone)

1. **Tempo worker-span filter (Task 5, Step 2b).** The exact CeleryInstrumentor span name / attribute
   that distinguishes a worker span from an app span (`run/<task>` vs `<task>` vs
   `span.celery.task_name`) is version-dependent and must be confirmed empirically during the first
   GREEN run. The plan pins the *invariant* (the filter must be unsatisfiable by an app-only span) and
   gives the concrete fallback query, but the literal TraceQL may need a one-line adjustment the runner
   makes from the live Tempo tag values.

### Real template bugs these tests may surface (per the shared real-bug policy)

- **Grafana datasource URL / uid drift (M13, Test A).** The per-datasource `/health` probe
  (`/api/datasources/uid/<uid>/health`) is the strongest assertion here — a wrong `url:` in
  `provisioning/datasources/{prometheus,loki,tempo}.yml` (e.g. a stale port or hostname) passes
  config-validation today but fails the live health probe. Likely the highest-probability find.
- **Exporter mis-wiring (M10, Test B).** A wrong `DATA_SOURCE_NAME` for postgres-exporter, a
  `--broker-url`/`--redis.addr` mismatch, or a `--mongodb.uri` typo would leave that exporter's scrape
  target `down` — silent today, RED here.
- **Malformed alert rule (M11, Test A).** A PromQL syntax error in any baseline `*_alerts.yml` fails
  the rule-group load; `/api/v1/rules` won't list the group → RED. (Battery alert files aren't
  rendered in baseline DATA, so only the 5 baseline groups are checked here.)
- **Alertmanager route/receiver wiring (M12, Test C).** A route/grouping/receiver regression that
  stays `amtool`-valid but never delivers would pass syntax-checks and fail the live-delivery assert.
- **Worker OTEL not wired (M7, Test D).** If the worker never exports a span (env not inherited, or
  `configure_worker_tracing`/`worker_process_init` not hooked), the worker-span filter stays empty —
  the exact silent failure M7 names.
