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

## The test

A single dedicated docker-acceptance test in
`tests/acceptance/test_rendered_project.py`:
`test_rendered_project_dev_stack_routes_through_traefik`.

1. **Render** a baseline project (`DATA`); `uv lock`.
2. **Bring up the full `dev` profile** (which includes Traefik):
   `docker compose -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml --profile dev up -d --build`,
   with `env=_compose_env()` (host UID/GID, per [[compose-profile-dev-needs-observability-overlay]] — the dev profile needs the observability overlay or grafana's image-less override fails config validation).
3. **Route through Traefik:** poll `https://{project_slug}.localhost/health` (Traefik's
   `websecure`/443 entrypoint; the app is already labeled
   `traefik.http.routers.app.rule=Host(\`{slug}.localhost\`)` → `tls=true` →
   `server.port=8000`) with an **unverified TLS context** (Traefik serves its
   default self-signed cert — `task certs`/mkcert is NOT required), until HTTP 200
   within a deadline (mirroring the existing `dev_lite_stack` poll, ~120s for the
   heavier dev stack to settle).
4. **Assert** status 200 and the app's `/health` JSON shape (`status ∈ {ok, degraded}`,
   `slos` present) — proving the response came from the app *via Traefik*, not a
   Traefik error page.
5. **Tear down** in `finally`: `docker compose … --profile dev down -v`.

`@pytest.mark.skipif(not _docker_available())`, like the sibling dev-stack tests.

## Why this catches the class

A 200 through `:443` is an end-to-end proof of the whole chain the bug severed:
Traefik **connected to the Docker daemon** (else the provider has no services),
**discovered the app** by its labels, and **proxied to `:8000` over TLS**. If a
future Docker-API or Traefik-version change breaks the docker provider, Traefik
keeps starting but this request stops returning 200 — the test fails loudly. A
functional route is also more robust than grepping Traefik logs for the
API-version string (log formats drift across versions).

## Robustness notes

- **`.localhost` resolution:** `{slug}.localhost` resolves to loopback (RFC 6761 /
  glibc) on the test host and GHA runners; this matches the framework's own dev
  URL convention (the router rule already uses it). The request runs on the host,
  not in a container.
- **Ports 443/80:** Traefik binds them via the dev profile — the existing
  `--profile dev` acceptance tests already prove these are free where acceptance
  runs, so this adds no new port risk.
- **Settle time:** the dev stack is heavier than `lite` (app + traefik + grafana +
  prometheus + otel + loki + tempo + postgres); use a generous poll deadline.
- **Root-owned files:** uses `_compose_env()` (host UID/GID) like the other dev
  tests, so the bind mounts stay host-owned.

## Out of scope

- The broader **assessment** of other provisioned-but-unexercised surfaces and the
  **framework-native coverage-gap reviewer** — that is **FWK18** (assessment →
  conditional reviewer), which this test is the first concrete instance of.
- `task certs` / mkcert cert generation (Traefik's default cert suffices for the
  TLS-verify-off route).
- Asserting Traefik's dashboard/API, or per-battery routing variations (the
  baseline app route is the representative case).

## PLAN

- **FWK8** → this design: the Traefik route-through acceptance test. **No release** —
  it touches only `tests/acceptance/` (framework-repo tests, not in the
  `src/framework_cli` wheel), so nothing reaches builders ([[release-cut-procedure]]:
  release only when builder-facing code ships). It merges to `master` via PR and the
  render-matrix is the proof.
