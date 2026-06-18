# FWK37 — `task dev` UX: detached + a "stack is up" summary (design)

> Status: approved design (2026-06-18). Next: writing-plans → implementation plan.
> Goal: stop `task dev`/`dev:lite` from tailing every container's logs in the foreground;
> bring the stack up **detached + healthy**, then print one clear, static **"stack is up"
> summary** of where everything is (PORT_OFFSET-aware), and add `task dev:logs` / `task
> dev:down` so logs and teardown are explicit on-demand actions.

## Problem

`task dev` and `task dev:lite` run `./scripts/compose.sh … up --build` **attached**. That
tails every container's logs (app access logs, healthcheck probes, Postgres/Grafana/etc.
chatter) into the terminal, so: the "app is up" line scrolls off instantly, you can't tell
what's running or where, and the terminal is held hostage until Ctrl-C (which also tears the
stack down). There is no `task` target to *follow logs on demand* or to *stop the stack
without destroying volumes* — only `dev:reset` (`down -v` + rebuild).

## Decisions (settled in brainstorming)

- **Detached + honest readiness:** `up -d --wait --build` — Compose returns only once
  healthchecked services report **healthy**, so "stack is up" is true when printed (and an
  unhealthy service fails the command loudly). The existing healthchecks (app, postgres,
  mongo, redis, traefik, …) make this free.
- **Comprehensive summary:** list **every published host port** for the services actually
  up — readability comes from a clean *static* block + no scrolling logs, not from trimming.
- **Derived from the running stack (no drift):** the summary reads `docker compose -p
  {{project_slug}} ps` (JSON, parsed by `python3`) for the services that are up and their
  *actual* published ports, then maps each to a label + URL. Single source of truth → it
  auto-reflects dev vs lite, present batteries, and any PORT_OFFSET, with zero duplication
  of `compose.sh`'s port map. (Rejected: a second hardcoded port list in the summary script
  — it would drift from `compose.sh`, against this repo's anti-drift ethos.)
- **Namespaced targets:** `task dev:logs` + `task dev:down` (under `dev:`, like
  `dev:reset`/`dev:lite`) so their scope is unambiguous.

## Design

### A. Detached + wait (Taskfile)

`dev` and `dev:lite` change their compose `cmds:` step from `… up --build` to
`… up -d --wait --build` (still via `scripts/compose.sh`, which is **unchanged** — it
port-shifts the 16 host-port vars and `exec`s the compose command). A second `cmds:` step
then runs the summary script. Preconditions (Docker / certs / `uv.lock` / `framework
integrity`) are unchanged. `dev:reset` is unchanged (it calls `task: dev`, so it inherits
the detached behavior + summary).

`compose.sh` keeps its terminal `exec docker compose "$@"` — nothing runs after `exec`, so
the orchestration (up, then summary) lives in the Taskfile's two `cmds:` steps, not in
`compose.sh`.

### B. The summary script (`scripts/dev_summary.sh`)

A new shellcheck-clean script that:
1. runs `docker compose -p {{ project_slug }} ps --format json` and parses it with `python3`
   (already a project dependency) to get each running service + its published host port(s);
2. maps known service names → friendly label + URL using a small table:
   - `app` → `https://{{ project_slug }}.localhost  ·  http://localhost:<HTTP_HOST_PORT>` if
     `traefik` is up, else `http://localhost:<HTTP_HOST_PORT>`;
   - `grafana`/`prometheus`/`alertmanager`/`loki`/`tempo`/exporters → `http://localhost:<port>`;
   - `postgres`/`mongo`/`redis` → `localhost:<port>` (connection host:port, not a URL);
3. prints one static block (comprehensive — every published port; exporters grouped compact
   since they are rarely opened directly), ending with the action hints:
   `logs: task dev:logs   ·   stop: task dev:down   ·   reset: task dev:reset`.

Because it derives from `ps -p {{ project_slug }}`, the same script serves both `dev` and
`dev:lite` (it shows whatever is actually up — lite shows App at `localhost:8000` + present
data stores, no Traefik/observability) with no mode flag.

Illustrative output (`task dev`, PORT_OFFSET=0, workers+mongodb batteries):
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {{ project_slug }} — stack is up  ✓        (PORT_OFFSET=0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  App          https://{{ project_slug }}.localhost  ·  http://localhost:8000
  Grafana      http://localhost:3000
  Prometheus   http://localhost:9090
  Alertmanager http://localhost:9093
  Loki         http://localhost:3100
  Tempo        http://localhost:3200
  Postgres     localhost:5432
  Mongo        localhost:27017
  Redis        localhost:6379
  (+ exporters: postgres :9187 · mongodb :9216 · celery :9808 · redis :9121)

  logs: task dev:logs   ·   stop: task dev:down   ·   reset: task dev:reset
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
(Exact glyphs/alignment are polish, not contract. An unknown/unmapped service still appears
with its raw published port, so a future service is never silently dropped.)

### C. `task dev:logs` + `task dev:down`

- **`task dev:logs`** — follow the dev stack's logs on demand: `docker compose -p
  {{ project_slug }} logs -f`. Ctrl-C stops *following*; containers keep running.
- **`task dev:down`** — stop the stack, **keep volumes**: `docker compose -p
  {{ project_slug }} down` (removes containers + network, **no `-v`** → Postgres/Mongo/Redis
  data survive). Distinct from `dev:reset` (`down -v` + rebuild).

Both are project-scoped via `-p {{ project_slug }}` (matching `base.yml`'s `name:`), so they
need no `-f` file list and target this stack regardless of dev vs lite.

### D. Integrity / FWK29 / testing

- `scripts/dev_summary.sh` is a new operational surface: it gets an **integrity**
  classification (`LOCKED_TRACKED`, like `compose.sh`/`doctor.sh`) and an **FWK29 registry**
  entry, plus the new `dev:logs`/`dev:down` Taskfile targets are covered by the existing
  surface enumeration if applicable.
- **Render guards:** a render asserts `dev`/`dev:lite` use `up -d --wait` and invoke
  `dev_summary.sh`; that `dev_summary.sh` renders + is shellcheck-clean; that the
  `dev:logs`/`dev:down` targets exist with the right (no-`-v`) semantics.
- **Live acceptance test:** bring up `dev:lite`, run `dev_summary.sh`, and assert the
  printed block contains the app URL at the correct **offset-aware** port and at least one
  present data store — the real proof that the derive-from-`ps` parsing works. (`dev:lite`
  keeps the acceptance tier light — no Traefik/observability.)
- `shellcheck` via the existing pre-commit hook + `task doctor`.

## Out of scope

- Changing what the stack *contains* (services, ports) — FWK37 only changes how it's
  launched and reported.
- A TUI/watch dashboard — the summary is a one-shot static print, not a live view (use
  `task dev:logs` for live).

## Release

Template payload, release-deferred. Defaults change *behavior* (detached instead of
attached) but not *capability* — a consumer re-runs `task dev` and gets the freed terminal +
summary on their next upgrade. Batches into a release with the other template-payload work
(FWK6/FWK38 already on master; FWK36 websockets fix already on master).
