# FWK31 — Compose isolation for concurrent stacks (design)

> Status: approved design (2026-06-16). Next: writing-plans → implementation plan.
> Goal: let multiple generated-project stacks (and the framework's own acceptance tier)
> run on one host at the same time without colliding or destroying each other's data.
> Diagnosed via Meridian's `task dev` ↔ the framework acceptance tier (2026-06-16).

## Problem

A generated project's compose stack is **not isolated** from any other stack on the same
host. Two failure modes:

1. **Shared project namespace.** No top-level compose `name:` is set, so
   `docker compose -f infra/compose/base.yml …` derives the project name from the
   compose-file directory → **`compose`** for *every* generated project. Two stacks (two
   consumers, or a consumer's `task dev` and the framework's docker acceptance tier) then
   share container names (`compose-app-1`), the `compose_default` network, and named
   volumes (`compose_pgdata`). A `down -v` on one **destroys the other's database**.
2. **Fixed host ports.** A full `task dev` stack publishes **16 fixed host ports**
   (`dev.yml` 7, `observability.yml` 9). Even as separate projects, two stacks can't both
   bind `:8000` / `:443` / `:5432` / `:3000` / … at once.

This blocks the user's real workflow: keeping a UAT stack live in the browser while other
projects' stacks (and tests) run concurrently — increasingly common when driving several
projects at once through Claude Code.

**Scope decision (confirmed):** design for full concurrency (two+ live stacks at once),
not merely non-destructive coexistence.

## Already shipped on this branch (the interim)

PR #45's `_isolate_compose_project` autouse fixture gives each **acceptance test** a unique
`COMPOSE_PROJECT_NAME` (`swfwacc-<testname>`), so the framework's test tier no longer shares
the `compose` namespace with a consumer stack and its `down -v` can't destroy consumer data.
This fixed the namespace half for the test tier. FWK31 completes the picture: the
template-side namespace fix (so *consumers* are isolated too) and the host-port half.

## Design

### 1. Per-project compose namespace

Add a top-level `name: {{ project_slug }}` to `base.yml.jinja`. Every generated project
becomes its own compose project (`meridian`, `demo`, …) — distinct container/network/volume
names, and `down -v` scoped to that project. This is the decisive, cheap fix.

The acceptance fixture's per-test `COMPOSE_PROJECT_NAME` (env) still overrides the file's
`name:` (env beats the file key), so tests stay isolated from each other *and* from the
default `<slug>` project. Both mechanisms compose correctly.

### 2. Parameterized host ports (per-service, today's defaults)

Every published host port becomes `${<SERVICE>_HOST_PORT:-<default>}:<container>`. Defaults
are today's values, so single-project DX is byte-for-byte unchanged and raw
`docker compose` (no `task`) still works.

The full inventory (16):

| File | Service | Default | 
|------|---------|---------|
| `dev.yml` | app | 8000 |
| `dev.yml` | postgres | 5432 |
| `dev.yml` | traefik (https) | 443 |
| `dev.yml` | traefik (http) | 80 |
| `dev.yml` | mongo (mongodb battery) | 27017 |
| `dev.yml` | redis (workers/redis battery) | 6379 |
| `dev.yml` | frontend (react battery) | 5173 |
| `observability.yml` | prometheus | 9090 |
| `observability.yml` | grafana | 3000 |
| `observability.yml` | alertmanager | 9093 |
| `observability.yml` | loki | 3100 |
| `observability.yml` | tempo | 3200 |
| `observability.yml` | otel-collector | 9808 |
| `observability.yml` | postgres-exporter | 9187 |
| `observability.yml` | mongodb-exporter (mongodb battery) | 9216 |
| `observability.yml` | redis-exporter (redis/workers battery) | 9121 |

`.env.example` documents each var with its default.

**Naming constraint:** the per-port vars and the offset MUST NOT use the `APP_` prefix —
that prefix is the generated app's pydantic-settings namespace, and a settings model with
`extra="forbid"` would reject an unexpected `APP_*` var. Use a neutral, compose-scoped
naming (`<SERVICE>_HOST_PORT`, `PORT_OFFSET`); the plan finalizes exact names and verifies
they don't collide with a declared `APP_*` setting.

### 3. The offset knob (ergonomic co-run)

A single `PORT_OFFSET` (default `0`) that `task dev` / `task dev:lite` apply to shift *all*
host ports at once (`8000+N`, `443+N`, …). Co-running a second stack is then **one** number
in that project's `.env`. The per-service `*_HOST_PORT` vars from §2 sit underneath as
fine-grained overrides (e.g. set `TRAEFIK_HTTPS_PORT=8443` if `443+N` is awkward). The
offset is applied in the Taskfile (compose can't do arithmetic in `${}`); raw
`docker compose` without `task` falls back to the per-service defaults.

Tradeoff (accepted): the second stack's Traefik URL gains a port suffix
(`other.localhost:8443`); the first stack (offset 0) stays clean on `:443`.

### 4. Acceptance tests → ephemeral host ports

Building on §interim: the docker-up acceptance tests additionally set every
`*_HOST_PORT=0` (random free port) via the existing `_isolate_compose_project` fixture, and
discover the assigned host port with `docker compose port <svc> <container-port>` before
polling/connecting. This makes the test tier collide with **nothing** — not a live UAT
stack, not another test. The Traefik routing test connects to the *discovered* HTTPS host
port with the `Host: {slug}.localhost` header instead of hardcoded `:443`.

### 5. Upgrade impact (documented, not migrated)

On `framework upgrade`, an existing consumer (Meridian) gains `name: <slug>`, so its old
`compose`-project volumes orphan and the new project starts a fresh DB. **Accepted:** that
DB holds only a small seed dataset; a re-seed is fine. Documented as an upgrade note (e.g.
in the generated `infra/README` / upgrade notes), not migrated. Parameterized ports default
to today's values, so nothing else changes on upgrade unless the consumer opts in.

## Scope & boundaries

- **In scope:** the local dev composition (`base.yml`, `dev.yml`, `observability.yml`, +
  per-battery services), `.env.example`, the Taskfile (`dev`/`dev:lite`), and the framework
  acceptance tier.
- **Out of scope:** the staging/prod deploy compositions (`staging.yml`/`prod.yml`/
  `services.yml` + `app-host.yml`). They run on separate hosts (no local collision) and
  never set `PORT_OFFSET`; the parameterized observability ports keep today's defaults
  there. No behavior change for deploy.
- **Ships a patch release** (template payload) so consumers get it via `framework upgrade`.

## Testing

- **Render assertions** (`test_copier_runner.py`): `name: {{ project_slug }}` renders into
  `base.yml`; each published port renders as `${<SERVICE>_HOST_PORT:-<default>}`; the
  defaults match today's values; no `APP_`-prefixed host-port var leaks into the app's
  settings namespace.
- **Offset behavior** (cheap): `task dev` with `PORT_OFFSET=N` → `docker compose config`
  shows every host port shifted by N (no live bring-up needed).
- **Two-stack co-run acceptance test** (the definitive proof, docker tier): render one
  project, bring up two stacks of it concurrently under distinct project names + offsets
  (e.g. offset 0 and offset 100), assert both serve `/health` on their respective ports
  with no port clash, then tear both down (each `down -v` touches only its own volume).
- **Existing docker acceptance tests** pass unchanged on ephemeral ports (regression).

## Approach alternatives considered

- **Project-name only (Layer 1) vs + port isolation (Layer 2).** Chose both — the user
  needs concurrent *live* stacks (browser UAT + tests), not just non-destructive
  coexistence.
- **Port mechanism:** per-service env vars with defaults (chosen) vs a single
  Taskfile-derived offset vs Traefik-only ingress (drop host-published DB ports). Chose
  per-service vars (correct under raw compose, preserves tooling ports) **plus** the offset
  as the ergonomic layer on top.
- **All 16 ports vs only the dev.yml 7.** Chose all 16 — if an observability port
  (`grafana:3000`, exporters) collides, a second full `task dev` won't come up; the offset
  shifts them uniformly at no extra per-use cost.
- **Volume migration on upgrade vs re-seed.** Chose re-seed (dev DB is a small seed set);
  documented, not migrated.
