# Traefik Docker-Provider Acceptance Coverage (FWK8) — Design

> Design spec for FWK8: a docker-acceptance test that routes a request **through**
> Traefik, closing the gap that hid the `traefik v3.1` → Docker 27 break. Status:
> approved (brainstorming, 2026-06-15). First concrete instance of the broader
> "provisioned-but-unexercised real-runtime surface" class that **FWK18** (a
> framework assessment + a conditional framework-native reviewer) will generalize.

## Context & goal

Traefik (`traefik:v3.6`, `profiles: ["dev"]`) is the dev stack's HTTPS reverse
proxy, using the **`docker` provider** (`providers.docker` in
`infra/traefik/traefik.yml`) — it reads `/var/run/docker.sock` to discover
labeled services. That docker-provider connection is exactly what broke when
Docker Engine 27+ raised the minimum API to 1.44 and Traefik ≤v3.5 hardcoded API
1.24 (`"client version 1.24 is too old"`), killing `task dev`'s proxy. Plan 28
fixed it reactively (bump to v3.6), verified on one machine, not CI.

**The gap:** the acceptance tier brings up Traefik (10 tests use `--profile dev`)
but **never routes a request through it** — they hit Prometheus, seeded items, or
the app on `:8000` directly. Traefik with a broken docker provider still *starts*
(the container comes up; `compose up -d` doesn't wait on it), it just stops
*routing*. So the break was invisible. The goal is one test that **sends a request
through Traefik** and asserts it routes to the app — which only succeeds if the
docker provider connected to the daemon, discovered the labeled app, and proxied
over TLS.

## Where it runs (decides the design)

`.github/workflows/ci.yml` runs `pytest -q --ignore=tests/acceptance`, so the
docker dev-stack acceptance tier — including this test — is **local-only**: it runs
on the dev box, which has `docker`, `mkcert`, and `go-task`. That removes any
mkcert-availability obstacle, so the test exercises the **real cert path** (the
incident's *origin* was a mkcert/WSL cert inconsistency) rather than dodging it
with Traefik's default cert. The PR's proof is **local execution on this box**, not
the render-matrix (which never runs acceptance).

## The cert + route chain (what the test exercises)

The full chain the incident exposed, in order:
1. `task certs` → `mkcert -install` + issues `infra/traefik/certs/localhost.pem`
   (wildcard, covers `*.localhost` → `{slug}.localhost`) signed by the mkcert CA.
2. `infra/traefik/dynamic/tls.yml` loads `localhost.pem` as Traefik's default cert;
   the certs dir is bind-mounted into the container.
3. Traefik's **docker provider** reads `/var/run/docker.sock`, discovers the
   app (`traefik.enable=true`, `Host(\`{slug}.localhost\`)` → `websecure`/`tls=true`
   → `server.port=8000`), and proxies over TLS.

## The test

A single dedicated docker-acceptance test in
`tests/acceptance/test_rendered_project.py`:
`test_rendered_project_dev_stack_routes_through_traefik`, decorated
`@pytest.mark.skipif(not _docker_available() or shutil.which("mkcert") is None or shutil.which("task") is None)`.

1. **Render** a baseline project (`DATA`); `uv lock`.
2. **`task certs`** — `subprocess.run(["task", "certs"], cwd=dest)` (the real builder
   command) issues the mkcert cert into `infra/traefik/certs/`. Assert it succeeds.
3. **Bring up the full `dev` profile** (which includes Traefik):
   `docker compose -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml --profile dev up -d --build`,
   `env=_compose_env()` (host UID/GID; the dev profile needs the observability
   overlay or grafana's image-less override fails config validation —
   [[compose-profile-dev-needs-observability-overlay]]).
4. **Route through Traefik with the cert chain verified:** open a TLS socket to
   **`127.0.0.1:443`** (Traefik's `websecure`), trusting **only** the mkcert root CA
   (`ssl.create_default_context(cafile=$(mkcert -CAROOT)/rootCA.pem)`), with SNI =
   `{slug}.localhost`, and send `GET /health` with `Host: {slug}.localhost`. Poll
   until HTTP 200 within a generous deadline (~120s — the dev stack is heavier than
   `lite`). Two environment realities forced this exact shape (found while building):
   - **Connect to `127.0.0.1`, not `{slug}.localhost`:** `*.localhost` is **not** in
     this host's DNS (`/etc/nsswitch.conf` is `files dns`, no `nss-myhostname`), so
     Python's `getaddrinfo` can't resolve it (browsers resolve it internally;
     `urllib`/glibc don't). Route by the `Host` header instead.
   - **`check_hostname = False` (chain verify only):** OpenSSL's `X509_check_host`
     refuses to match the cert's wildcard SAN `*.localhost` against `{slug}.localhost`
     (single-label parent — browser-valid, OpenSSL stricter). The **chain** check
     (trusting the mkcert-only CA) is what proves the served cert is the real mkcert
     cert, not a default — so the cert path stays load-bearing.
5. **Assert** status 200 and the app's `/health` JSON shape (`status ∈ {ok, degraded}`,
   `slos` present).
6. **Tear down** in `finally`: `docker compose … --profile dev down -v`.

## Why this catches the class

A **verified** 200 through `:443` proves the entire chain the incident exposed:
`task certs`/mkcert produced a valid cert → it mounted → `tls.yml` loaded it →
Traefik served it for `*.localhost` and a client **trusted** it → and the docker
provider connected to the daemon, discovered the labeled app, and proxied to
`:8000`. **Verify-ON is what makes the cert path load-bearing:** a
`task certs`/cert-mount/`tls.yml` regression fails the TLS handshake; a
docker-provider/Docker-API regression (the v3.1→Docker-27 class) fails the route.
Both surfaces, one functional assertion — far stronger and more robust than
grepping Traefik logs (log formats drift across versions).

## Robustness notes

- **`.localhost` resolution:** `{slug}.localhost` resolves to loopback (RFC 6761 /
  glibc); matches the framework's own dev-URL convention (the router rule already
  uses it). The request runs on the host, not in a container.
- **Ports 443/80:** Traefik binds them via the dev profile — the existing
  `--profile dev` acceptance tests already prove these are free where acceptance
  runs, so no new port risk.
- **`task certs` side effect:** `mkcert -install` is idempotent (the box's CA is
  already installed); re-running it is a no-op. Running the real `task certs`
  (rather than a hand-rolled `mkcert` call) is deliberate — it makes a `task certs`
  regression itself catchable.
- **Root-owned files:** uses `_compose_env()` (host UID/GID) like the sibling dev
  tests, so bind mounts stay host-owned.

## Out of scope

- The broader **assessment** of other provisioned-but-unexercised surfaces and the
  **framework-native coverage-gap reviewer** — that is **FWK18** (assessment →
  conditional reviewer), which this test is the first concrete instance of.
- Asserting Traefik's dashboard/API, or per-battery routing variations (the
  baseline app route is the representative case).

## PLAN

- **FWK8** → this design: the Traefik cert+route acceptance test. **No release** —
  it touches only `tests/acceptance/` (framework-repo tests, not in the
  `src/framework_cli` wheel), so nothing reaches builders ([[release-cut-procedure]]:
  release only when builder-facing code ships). Merges to `master` via PR; the
  **proof is running it locally on this box** (acceptance is CI-ignored).
