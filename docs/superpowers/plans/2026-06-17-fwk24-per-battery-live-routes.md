# FWK24 — Per-battery live routes through Traefik + RUM — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans`. Read the shared
> policy first: `docs/superpowers/plans/2026-06-17-coverage-batch-execution-policy.md` (branch,
> commit cadence, skip-marker gate, real-bug rule, no-release, laptop/TMPDIR). Steps use `- [ ]`.

**Goal:** Close M8 (per-battery app routes exercised on a LIVE compose stack through Traefik, not just in-process) + M9 (react RUM round-trip actually run) + the re-pointed `service:dev.yml:frontend` (the Vite dev-server serving the SPA live).

**Architecture:** Fork **1A** — ONE combined render (`websockets+webhooks+llm+graphql+agents+react`) and ONE `--profile dev` stack; hit every route against it. Fork **2A** — the two LLM-backed routes (`/llm/complete`, `/agents/run`) have no API key in the container, so assert reachability + the documented structured failure + (for llm) the metric series, not a real completion. Routing is through Traefik: discover the ephemeral host port with `_compose_host_port(dest, files, "traefik", 443)` (FWK31 binds 443 to an ephemeral port — never hardcode 443), connect `127.0.0.1:<port>` with SNI+Host `demo.localhost`, chain-verify the mkcert CA (`check_hostname=False`). Mirrors `test_rendered_project_dev_stack_routes_through_traefik` (test_rendered_project.py:943).

**Tech Stack:** Python, pytest, Docker, Traefik v3.6 (mkcert TLS), the existing acceptance harnesses.

---

## File Structure

- **Modify** `tests/acceptance/test_rendered_project.py` — add two shared helpers (`_traefik_request`, `_traefik_ws_upgrade`), the combined live-route test, the RUM test, the Vite-serve test.
- **Modify** `tests/runtime_coverage/registry.py` — flip `service:dev.yml:frontend` → EXERCISED (the Vite-serve test).
- **Modify** `PLAN.md` + `ACTION_LOG.md` (per the shared policy).

Per the M8/M9 assessment entries these routes are **in-app code paths**, OUT of the FWK29 enumerated registry — so only `service:dev.yml:frontend` flips. No template change is expected; if a route is genuinely unreachable live, that's a real bug → follow the shared real-bug policy.

---

## Task 1: Shared Traefik request helpers

**Files:** Modify `tests/acceptance/test_rendered_project.py` (place beside `_run_image_serving`).

- [ ] **Step 1: Add the helpers**

```python
def _mkcert_ssl_context() -> "ssl.SSLContext":
    """An SSL context that trusts ONLY the mkcert CA (chain-verify), with hostname check off
    (the cert's *.localhost wildcard SAN is browser-valid but OpenSSL won't match it)."""
    caroot = subprocess.run(
        ["mkcert", "-CAROOT"], capture_output=True, text=True
    ).stdout.strip()
    ctx = ssl.create_default_context(cafile=str(Path(caroot) / "rootCA.pem"))
    ctx.check_hostname = False
    return ctx


def _traefik_request(
    https_port: int,
    host: str,
    ctx: "ssl.SSLContext",
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, str]:
    """One HTTP/1.1 request THROUGH Traefik over TLS (connect 127.0.0.1:<port>, SNI+Host=<host>,
    Connection: close so we read to EOF). Returns (status, body_text). Mirrors the recipe in
    test_rendered_project_dev_stack_routes_through_traefik."""
    lines = [f"{method} {path} HTTP/1.1", f"Host: {host}", "Connection: close"]
    for k, v in (headers or {}).items():
        lines.append(f"{k}: {v}")
    if body is not None:
        lines.append(f"Content-Length: {len(body)}")
    req = ("\r\n".join(lines) + "\r\n\r\n").encode() + (body or b"")
    raw = socket.create_connection(("127.0.0.1", https_port), timeout=5)
    with ctx.wrap_socket(raw, server_hostname=host) as ssock:
        ssock.sendall(req)
        data = b""
        while True:
            chunk = ssock.recv(4096)
            if not chunk:
                break
            data += chunk
    head, _, payload = data.partition(b"\r\n\r\n")
    status = int(head.split(b"\r\n", 1)[0].split()[1])
    return status, payload.decode(errors="replace")


def _traefik_ws_upgrade(https_port: int, host: str, ctx: "ssl.SSLContext") -> int:
    """Open a WebSocket upgrade to /ws THROUGH Traefik; return the HTTP status (expect 101
    Switching Protocols — proves the proxy negotiates the WS upgrade, the M8 risk). We assert the
    handshake only (frame echo is covered in-process by the websockets battery's own test)."""
    import base64

    key = base64.b64encode(b"fwk24-ws-test-key").decode()
    req = (
        f"GET /ws HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode()
    raw = socket.create_connection(("127.0.0.1", https_port), timeout=5)
    with ctx.wrap_socket(raw, server_hostname=host) as ssock:
        ssock.sendall(req)
        head = ssock.recv(4096)
    return int(head.split(b"\r\n", 1)[0].split()[1])
```

- [ ] **Step 2: Lint** — `uv run ruff check tests/acceptance/test_rendered_project.py && uv run ruff format tests/acceptance/test_rendered_project.py`. Commit (per shared policy: PLAN/ACTION_LOG staged + skip-marker).

---

## Task 2: Combined live-route test through Traefik

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Write the test**

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker + mkcert: live per-battery routes through Traefik",
)
def test_rendered_per_battery_routes_through_traefik(tmp_path: Path):
    # M8/FWK24: every _passes test asserts routes at ~100% IN-PROCESS (TestClient, LLM mocked) —
    # never on a live compose stack served through Traefik. Render the route-batteries together
    # (fork 1A), bring up app+postgres+traefik, and exercise each route through 127.0.0.1:<traefik
    # 443 ephemeral port> with Host: demo.localhost.
    import hashlib
    import hmac

    dest = tmp_path / "demo"
    render_project(
        dest,
        {
            **DATA,
            "batteries": resolve(
                ["websockets", "webhooks", "llm", "graphql", "agents", "react"]
            ),
        },
    )
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    certs = subprocess.run(["task", "certs"], cwd=dest, capture_output=True, text=True)
    assert certs.returncode == 0, "task certs failed:\n" + certs.stdout + certs.stderr

    # Inject a known webhook signing secret via a merge overlay (base.yml hardcodes the app
    # environment; compose merges `environment` maps additively, so this adds without replacing).
    secret = "fwk24-test-secret"
    (dest / "infra" / "compose" / "fwk24.override.yml").write_text(
        "services:\n  app:\n    environment:\n"
        f'      APP_WEBHOOK_SIGNING_SECRET: "{secret}"\n'
    )
    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
        "infra/compose/fwk24.override.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    up = [
        "docker", "compose", *fargs, "--profile", "dev",
        "up", "-d", "--build", "app", "postgres", "traefik",
    ]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    assert subprocess.run(up, cwd=dest, env=env).returncode == 0
    try:
        https_port = _compose_host_port(dest, files, "traefik", 443)
        host = f"{DATA['project_slug']}.localhost"
        ctx = _mkcert_ssl_context()
        # Readiness: poll /health through Traefik until 200 (proves the chain + app up).
        deadline = time.time() + 120
        ready = False
        while time.time() < deadline:
            try:
                st, _ = _traefik_request(https_port, host, ctx, "GET", "/health")
                if st == 200:
                    ready = True
                    break
            except OSError:
                pass
            time.sleep(3)
        assert ready, "app never served /health 200 through Traefik within 120s"

        # websockets: the upgrade negotiates through the proxy (101).
        assert _traefik_ws_upgrade(https_port, host, ctx) == 101, (
            "WS /ws upgrade did not return 101 through Traefik"
        )

        # webhooks: valid HMAC-SHA256(secret, raw body) -> 200; tampered sig -> 401.
        # NOTE: confirm the minimal accepted JSON body against the rendered routes/webhooks.py
        # (+ its functional test) — the assertion is the signature gate, not payload semantics.
        payload = b'{"id": "fwk24-1", "type": "ping"}'
        good = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        st, _ = _traefik_request(
            https_port, host, ctx, "POST", "/webhooks",
            headers={"X-Webhook-Signature": good, "Content-Type": "application/json"},
            body=payload,
        )
        assert st == 200, f"signed /webhooks did not return 200 (got {st})"
        st, _ = _traefik_request(
            https_port, host, ctx, "POST", "/webhooks",
            headers={"X-Webhook-Signature": "deadbeef", "Content-Type": "application/json"},
            body=payload,
        )
        assert st == 401, f"bad-signature /webhooks did not return 401 (got {st})"

        # graphql: a basic query succeeds (introspection is ON in dev — assert dev behavior; the
        # prod fail-closed off-path is env-derived + unit-covered, not re-tested on this dev stack).
        st, gql = _traefik_request(
            https_port, host, ctx, "POST", "/graphql",
            headers={"Content-Type": "application/json"},
            body=b'{"query": "{ __typename }"}',
        )
        assert st == 200 and '"data"' in gql, f"/graphql query failed: {st} {gql[:200]}"

        # llm (fork 2A): no API key -> service raises LLMError -> route 502; the attempt records
        # app_llm_calls_total{outcome="error"} -> assert the series appears on /metrics.
        st, _ = _traefik_request(
            https_port, host, ctx, "POST", "/llm/complete",
            headers={"Content-Type": "application/json"},
            body=b'{"prompt": "hi"}',
        )
        assert st == 502, f"/llm/complete (no key) did not return 502 (got {st})"
        st, metrics = _traefik_request(https_port, host, ctx, "GET", "/metrics")
        assert st == 200 and "app_llm_calls_total" in metrics, (
            "app_llm_* series missing from /metrics after a live /llm/complete attempt"
        )

        # agents (fork 2A): LLM-backed (AgentRunner -> LLMService.respond) -> 502/503 with no key,
        # proving the route is mounted + reached on the live ASGI/Traefik path.
        st, _ = _traefik_request(
            https_port, host, ctx, "POST", "/agents/run",
            headers={"Content-Type": "application/json"},
            body=b'{"prompt": "hi"}',
        )
        assert st in {502, 503}, f"/agents/run (no key) returned {st}, expected 502/503"
    finally:
        subprocess.run(down, cwd=dest, env=env)
```

- [ ] **Step 2: Run — expect GREEN.** `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_per_battery_routes_through_traefik -q`. If a route is unreachable live (e.g. WS upgrade not 101 through Traefik, or a router not mounted), that's a candidate REAL BUG — follow the shared real-bug policy.

- [ ] **Step 3: Bite-proof (cheap):** flip one asserted status to an impossible value (e.g. assert `/webhooks` bad-sig `== 200`) → RED; or point `_traefik_request` at `/no-such-route` and confirm a 404 surfaces. Revert. Commit.

---

## Task 3: react RUM round-trip (M9)

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Write the test** (in-process in the rendered project — no live stack)

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker: runs the rendered react project's RUM functional test",
)
def test_rendered_react_rum_round_trip(tmp_path: Path):
    # M9/FWK24: the rendered react project SHIPS tests/functional/test_frontend_rum.py
    # (test_frontend_metrics_round_trip_through_metrics_endpoint: POST /internal/rum -> app_frontend_*
    # on /metrics), but no framework tier runs the react project's python pytest. Run that one test.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["uv", "run", "pytest", "tests/functional/test_frontend_rum.py", "-q"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "the rendered react RUM round-trip test failed:\n" + result.stdout + result.stderr
    )
```

- [ ] **Step 2: Run — expect GREEN.** `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_react_rum_round_trip -q`. Commit.

---

## Task 4: Vite dev-server serves the SPA live (re-pointed service:dev.yml:frontend)

**Files:** Modify `tests/acceptance/test_rendered_project.py` + `tests/runtime_coverage/registry.py`.

- [ ] **Step 1: Write the test**

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker (+ npm network): the dev Vite server serves the SPA live",
)
def test_rendered_frontend_dev_server_serves_spa(tmp_path: Path):
    # FWK24 (re-pointed from H6/FWK21): the dev `frontend` service runs the Vite dev server
    # (`npm ci && npm run dev -- --host`) — brought up by the no-root test but never asserted to
    # SERVE. Up it and GET the Vite port, asserting the SPA shell (id="root").
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    up = ["docker", "compose", *fargs, "--profile", "dev", "up", "-d", "--build", "frontend"]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    served = ""
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        port = _compose_host_port(dest, files, "frontend", 5173)
        # Vite + `npm ci` take time on first boot; poll for the served shell.
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/", timeout=3
                ) as resp:
                    if resp.status == 200:
                        served = resp.read().decode()
                        if 'id="root"' in served:
                            break
            except Exception:
                pass
            time.sleep(3)
    finally:
        subprocess.run(down, cwd=dest, env=env)
        subprocess.run(
            ["docker", "run", "--rm", "-v", f"{dest}:/work", "alpine",
             "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/work"]
        )
    assert 'id="root"' in served, (
        f"the Vite dev server never served the SPA shell within 180s:\n{served[:300]}"
    )
```

- [ ] **Step 2: Run — expect GREEN.** Commit.

- [ ] **Step 3: Flip the registry** — `service:dev.yml:frontend` from KNOWN_GAP to:

```python
        "service:dev.yml:frontend",
        "infra/compose/dev.yml",
        _EX,
        # FWK24: the dev Vite server is brought up and GET / asserts the served SPA shell (id="root").
        "test_rendered_frontend_dev_server_serves_spa",
```

- [ ] **Step 4:** `uv run pytest tests/runtime_coverage/ -q` (expect 9 passed). Commit.

---

## Task 5: Close-out

- [ ] **Step 1:** `uv run ruff check tests/ && uv run ruff format --check tests/acceptance/test_rendered_project.py tests/runtime_coverage/registry.py` — clean.
- [ ] **Step 2:** Per shared policy — this is one item on the batch branch; defer the whole-branch Opus review to the end of the batch. Update `PLAN.md` (FWK24 done) + `ACTION_LOG.md`; final commit.

---

## Self-Review

- **Spec coverage:** M8 (5 routes live through Traefik) → Task 2; M9 (RUM) → Task 3; re-pointed dev Vite-serve → Task 4. ✓
- **Forks honored:** 1A combined render (Task 2); 2A reachability+error+metric for llm/agents (Task 2); Traefik port via `_compose_host_port` (Tasks 2/4). ✓
- **Placeholders:** the only soft spot is the exact `/webhooks` JSON body — Task 2 Step 1 flags reading `routes/webhooks.py` + its functional test to confirm the minimal accepted body; everything else is concrete. ✓
- **Non-vacuity:** Task 2 Step 3 bite-proof; Task 3 fails if the RUM round-trip regresses; Task 4 asserts the *read* body. ✓
- **Naming consistency:** `_traefik_request` / `_traefik_ws_upgrade` / `_mkcert_ssl_context` defined in Task 1 and called in Tasks 2/4. ✓
