# Lock-taxonomy correction + `task doctor` — design

> **Date:** 2026-06-12 · **Status:** approved (brainstorm) · **Ships in:** v0.2.4
> **Spec for:** the v0.2.4 framework slice. Plan to follow via writing-plans.

## Context

Two signals from the second framework consumer (Meridian) converged on the same theme —
the framework over-asserts what a project may not touch, and under-declares what a project
needs.

1. **The lock challenge** (`../../meridian/_docs/architecture/handoffs/2026-06-12-seed-script-lock-challenge.md`).
   `framework integrity` blocked Meridian's build because it wired its real domain seeding into
   `scripts/seed.py`, which the framework ships **locked**. But `scripts/seed.py` is a 16-line
   composition entrypoint the scaffold *invites* you to replace — and the gotcha-bearing
   `seed()` helper it calls (`src/{{package_name}}/db/seed.py`, idempotency contract) is already
   **unlocked**. So the lock sits on the glue, not the invariant. The sanctioned escape
   (`--allow-drift`) makes the lock advisory anyway and trains reflexive drift, eroding the
   signal where it matters.

2. **The `task certs` gap.** `task certs` fails when `mkcert` is absent. The failure is the
   `certs` task's own `command -v mkcert` precondition firing — correct, but only discoverable
   by *hitting the task*. The framework declares its host-tool dependencies (docker, mkcert)
   only as scattered per-task `command -v` guards, with no upfront "here is what you need"
   surface. For a framework whose headline is environment parity, that is a real seam.

A lock audit of the 19 substantive `LOCKED_TRACKED` entries (recorded below) found the lock set
is *mostly* well-calibrated, with two files where the lock actively contradicts a documented
"this is yours" seam, and one (`services.yml`) entangled with a deeper assumption that is
explicitly **out of scope** here (see Deferred work).

## Principle

Locks earn their keep on **invariant infrastructure**: files with subtle security- or
correctness-critical scaffolding the framework fixes once and protects everywhere (migration
guards, deploy/rollback orchestration, the `APP_RUN_MIGRATIONS` gate, secret handling). They are
the wrong tool for **composition points**: files the scaffold ships as a starting example and
invites the project to replace. A lock that fires on the first legitimate use — not on a
regression — is mis-placed, and spending the scarce "do not touch" signal on glue devalues it
for the files that matter.

## Goals

- Unlock the two files that are composition seams, not invariants: `scripts/seed.py` and
  `infra/deploy/notify.sh`.
- Make the unlock **explicit and permanent** (a positive record, not a silent deletion), guarded
  by a **narrow re-lock test**. (The *full* reverse integrity-coverage check is deferred — see
  Non-goals: enumerating an all-batteries render found 23 unclassified framework-infra files, so
  the full check is its own classification audit, not a one-liner.)
- Add **`task doctor`**: an upfront, advisory host-tool preflight, so the tools the dev workflow
  assumes are discoverable before a task fails.

## Non-goals / Deferred work

- **`services.yml` / `dev.yml` data-store definitions — deferred to its own plan
  ("data-store runtime parity").** The audit showed these are *not* a clean unlock: they mix a
  real migration-safety invariant (the `worker`/`beat` services carry `APP_RUN_MIGRATIONS: "false"`,
  Celery/OTEL wiring, health-gated `depends_on`) with customizable data-store defs (`mongo`/`redis`
  image + volume). Worse, the lock is a *symptom*: the data-layer wiring bakes in a co-located,
  containerized assumption — `APP_DATABASE_URL`/`APP_REDIS_URL` are **literal** values hardcoded to
  container hostnames (`@postgres:5432`, `redis://redis:6379`, not `${VAR}` interpolations, so a
  shell env var cannot override them) and the app/worker/beat **hard-`depends_on`** the data-store
  containers. The three legitimate runtimes — managed cloud, local container, host-native — are not
  symmetric; only "local container, exactly as shipped" works without editing a locked file.
  Making that right means parameterizing the data-store endpoints, making `depends_on` conditional,
  and treating managed/container/native as first-class with docs — an architecture change, not a
  lock flip. No urgency: Meridian uses a colocated docker Postgres today. Tracked as a meta-plan row.
- **The full reverse integrity-coverage check — deferred to its own slice** (pairs with
  "data-store runtime parity"; both finish the integrity classification). Enumerating an
  all-batteries render found **23 unclassified files** under `.github/workflows/`/`infra/`/`scripts/`,
  most of them framework-managed files that escaped the locked registry — not composition seams:
  **18 battery observability files** (9 Grafana dashboards + 9 Prometheus alert files for
  `frontend`/`graphql`/`mongodb`/`otel-collector`/`prometheus`/`redis`/`webhooks`/`websockets`/`workers`,
  generated by `gen_observability`; their base siblings *are* locked), **2 battery scripts**
  (`scripts/export-graphql-schema.sh`, `scripts/pact-publish.sh`), **1 battery workflow**
  (`.github/workflows/docs.yml`), **1 conditional infra** (`infra/docker/postgres.Dockerfile`), and
  **1 placeholder** (`infra/traefik/certs/.gitkeep`). A full scan asserting every infra-surface file
  is classified would force a per-file lock/unlock decision on all of them — a real audit. This
  slice records `INTENTIONALLY_UNLOCKED` (which that future check consumes) and guards the two
  unlocks narrowly; the full scan + battery-infra classification is its own plan.
- **Version-floor checks** in `task doctor` — v1 answers "is it installed," not "is it new enough."
  Version assertions are subtle and false-green-prone (cf. the `action.yml` Node-runtime episode);
  deferred.
- **The tail glue files stay locked** — `scripts/load.sh`, `scripts/coverage.sh`,
  `scripts/export-openapi.sh`, `scripts/gen_observability.py`, `.dockerignore`, `alembic.ini`,
  `.gitattributes`. They are mechanical, have no concrete edit-driver, and several are the
  mechanism half of a CI contract the framework relies on. Unlocking them is churn without a
  reason; the audit's purpose is to keep the lock signal *meaningful*, not minimal.

## Design

### 1. Unlock + reverse-coverage guard (paired)

In `src/framework_cli/integrity/classes.py`:

- Remove `"scripts/seed.py"` and `"infra/deploy/notify.sh"` from `LOCKED_TRACKED`.
- Add a new classification tuple:

  ```python
  # Framework-shipped files deliberately left unmanaged: composition seams the scaffold
  # invites the project to replace. Not checksummed; recorded here so (a) the unlock is
  # intentional and visible, and (b) the reverse-coverage check below can tell "deliberately
  # unlocked" from "a new framework file that escaped classification".
  INTENTIONALLY_UNLOCKED: tuple[str, ...] = (
      "scripts/seed.py",        # thin entrypoint; the seed() helper in db/seed.py is the mechanism
      "infra/deploy/notify.sh", # notification seam — "wire your channel here"
  )
  ```

- Update the `classes.py:13-18` comment: the reverse check is no longer deferred.

**Narrow re-lock guard (this slice).** A small test in `tests/integrity/test_classes.py` asserts
the two unlocked files are *not* in `LOCKED_TRACKED` **and** *are* in `INTENTIONALLY_UNLOCKED`.
This gives the "cannot silently drift back into the locked set" protection without the full
infra-surface scan — which, as the enumeration showed, would force a 23-file classification audit
(deferred; see Non-goals). The `INTENTIONALLY_UNLOCKED` tuple added here is exactly the allowlist
that future check will consume.

### 2. `task doctor`

- **`scripts/doctor.sh`** (jinja; **locked** — the framework owns the required-tool list, so the
  script itself *is* invariant infra), invoked by a `doctor:` task in the Taskfile's
  `FRAMEWORK:BEGIN/END` region.
- Checks, by `command -v` (presence only):
  - `docker`, `docker compose` (plugin), `docker buildx`
  - `mkcert`
  - `uv`
  - `git`
  - `node` + `npm` — **rendered in only when the `react` battery is present** (jinja-conditional,
    mirroring how the data-store services are battery-gated)
- Output: a ✓/✗ line per tool; a one-line install hint per **missing** tool; exit non-zero if any
  **required** tool is absent.
- **Advisory**: run manually. **Not** wired into `task ci` (CI has no `mkcert` → it would
  false-fail) and **not** a precondition of every `task dev`/`task certs` (a tool-scan per
  invocation is noise).
- **Cross-reference**: the existing lazy guards get a pointer — `task certs`'s mkcert message and
  the `command -v docker` precondition messages append "— run `task doctor` to check all host
  tools." README gains a one-line **Prerequisites** entry pointing at `task doctor`.

### 3. `seed.py` / `notify.sh` as examples

Now that they are unlocked, make them read as deliberate examples:

- `infra/deploy/notify.sh` already says "wire your channel here" — leave as is.
- `scripts/seed.py` gains a one-line comment: "compose your domain seeding here — the reusable,
  idempotent helper is in `src/{{package_name}}/db/seed.py`," mirroring `models.py`'s
  "replace with your domain models."

### 4. Docs

- Update any lock documentation that enumerates the managed set (e.g. the upgrading / integrity
  docs) to reflect the two unlocks and the new `INTENTIONALLY_UNLOCKED` category.
- The `classes.py` header comment update from §1.

### 5. Folded-in: Traefik Docker-API fix (added during execution)

`infra/compose/dev.yml` pins `traefik:v3.1`. Docker Engine 27+ (incl. 29) raised the minimum
Docker API to 1.44 and rejects Traefik ≤v3.5's hardcoded API 1.24 — `"client version 1.24 is too
old"` — which breaks `task dev`'s Traefik HTTPS proxy (surfaced by Meridian). **Verified empirically
on Docker 29:** `DOCKER_API_VERSION` env has no effect; v3.2/v3.3/v3.5 bumps still send 1.24; only
**v3.6** (Docker API auto-negotiation) connects cleanly. Fix: bump to `traefik:v3.6` + a render guard
asserting the pin is ≥ v3.6 + an explanatory comment. It was never caught because the acceptance tier
uses the `lite` profile (no Traefik), so Traefik's docker-provider discovery is unexercised — tracked
as a follow-up (see Non-goals). Thematically env-parity, hence folded into this slice.

## Testing (TDD throughout)

- **Narrow re-lock guard**: a test in `tests/integrity/test_classes.py` asserting `scripts/seed.py`
  and `infra/deploy/notify.sh` are absent from `LOCKED_TRACKED` and present in `INTENTIONALLY_UNLOCKED`.
- **Unlock behavior**: an integrity test proving a *modified* `scripts/seed.py` / `infra/deploy/notify.sh`
  is **no longer flagged** by `framework integrity` (was fatal; now clean).
- **`task doctor`** (template-payload loop — render → exercise in a generated project): the rendered
  `doctor.sh` checks the expected tool set; `node`/`npm` appear **only** with the `react` battery;
  exit code is non-zero when a required tool is stubbed absent and zero when all present. Assert
  `doctor` is **absent** from `task ci`'s job graph.
- **Cross-reference**: assert the `certs`/`docker` guard messages mention `task doctor`.
- Standard gate green throughout (`pytest`, `ruff check`, `ruff format --check`, `mypy src`), plus
  the render + acceptance tiers since this is template-payload work.

## Rollout

- Ships in **v0.2.4** (release-cut procedure). Meridian then pulls it with a plain
  `framework upgrade . --to v0.2.4` (identity already repaired by the manual v0.2.3 hop). At that
  point the seed.py `--allow-drift` bridge becomes a no-op — the file leaves the tracked set.

## Execution note

Per the repo's review-model policy (CLAUDE.md), the implementation plan's Execution section must
restate it: implementers → Sonnet (Haiku for trivial); spec-compliance review → Sonnet;
code-quality review → **Opus**; branch-end whole-branch review → **Opus**. The plan is authored
via the writing-plans skill and executed subagent-driven, TDD per task.

## Appendix — audited `LOCKED_TRACKED` entries (keep-locked, with the high-stakes invariants)

`check_migrations.py` (migration-safety AST guard), `infra/deploy/strategy.sh` +
`targets/compose-ssh.sh` (migration-aware rollback), `scripts/entrypoint.sh` +
`infra/compose/app-host.yml` (the `APP_RUN_MIGRATIONS` gate), `infra/docker/Dockerfile`
(build-layer subtleties), `infra/deploy/check_alert_secrets.sh` (fail-closed secret guard),
`infra/compose/base.yml` (healthcheck contract), plus the workflows / traefik / observability /
dependabot configs not re-litigated. These are exactly what locks are for.
