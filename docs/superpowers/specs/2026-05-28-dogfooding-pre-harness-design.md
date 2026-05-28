# Plan 9 — Dogfooding Pre-Harness Catch-ups — Design

**Date:** 2026-05-28
**Plan ref:** Plan 9 (meta-plan `docs/superpowers/plans/2026-05-20-meta-plan.md`) — the first of the three dogfooding slices (9 pre-harness → 10 harnesses → 11 post-harness validations).
**Status:** Design approved; awaiting implementation plan (writing-plans).

## Summary

Two independent catch-ups that must land **before** the self-quality harness (Plan 10) so the harness is trustworthy and its agent set is complete:

1. **Docker-acceptance hygiene** — the dev compose stack bind-mounts source into a root container and writes root-owned `__pycache__` onto the host. This bites builders (`task dev` litters root-owned files in their tree) and the framework's own acceptance tier (it can't reap them → `/tmp` fills → the sandbox/CI wedges). Fix the shipped `dev.yml` to run the dev app as the host UID/GID, plumb UID/GID through the Taskfile, and add belt-and-suspenders teardown to the acceptance harness.
2. **`review-contracts` agent (authored)** — the deferred 8h battery-gated reviewer + its eval fixtures, so the agent set is complete before the Plan 10 harness scores "all registered agents." **Authored here; its real-key scoring is Plan 11.**

## Goals

- A dev stack + acceptance tier that leave **no root-owned files** on the host — repeatable locally without `sudo rm -rf /tmp/pytest-of-chris/*`, and a cleaner builder dev experience.
- A registered, gated, fixture-backed `review-contracts` agent, ready for the Plan 10 harness to pick up and Plan 11 to score.

## Non-Goals (this slice)

- **Observability-completeness check** — the `tests/` invariant and/or the `review-observability` infra/db/app/fe split + obs-infra-scaling reviewer. Decided to spin out into **its own future slice** (too multi-faceted to fold in here).
- **Real-key eval scoring of `review-contracts`** — deferred to **Plan 11** (needs the Plan 10 `agent-evals.yml` + `ANTHROPIC_FRAMEWORK_CI_EVAL` secret live). The agent is not "validated" until then; the provisional threshold is tuned from Plan 11's first real scorecard.
- The dogfooding harness itself (render matrix, agent-evals live, release automation, `SECRETS.md`) — that is **Plan 10**.

---

## 1. Docker-Acceptance Hygiene

### Root cause

`infra/compose/dev.yml`'s `app` service bind-mounts `../../src:/app/src` and runs `uvicorn --reload` as **root** (the container's default user). Uvicorn writes `__pycache__` into `/app/src`, which is the bind-mounted host source → those files are **root-owned on the host**. Consequences:

- **Builders:** after `task dev`, root-owned `__pycache__` litters their `src/` tree (can't `rm` without sudo).
- **Acceptance tier:** the tier renders many projects under pytest's `tmp_path` (`/tmp/pytest-of-chris/…`) and brings up the dev / dev:lite compose stacks (live-stack tests). The root-owned writes can't be reaped by pytest teardown → they accumulate and fill `/tmp` → because the bash tool also writes to `/tmp`, the whole sandbox goes non-functional (every command fails, exit 1, no output) and can't self-recover. This wedged SVC-PROD Task 4.

### Fix

**(a) Run the dev app container as the host UID/GID** — in `dev.yml`, the `app` service gains:

```yaml
    user: "${UID:-1000}:${GID:-1000}"
```

so bind-mounted writes are owned by the invoking host user. The `:-1000` default keeps a raw `docker compose` invocation working (and on the CI runner / WSL the host user is typically `1000`, so even the default is correct there).

- This applies to the **dev app service only** — it is the bind-mount + reload surface. Prod/staging use the baked image with no source bind-mount; the `test` profile's rendered tests run on the host (testcontainers Postgres keeps its data inside the container, not bind-mounted), so neither needs the change.
- **Build-time risk to verify:** running as a passwd-less UID — confirm uvicorn `--reload` is happy (set `HOME=/tmp` for the service only if a tool needs a home dir); confirm the dev app writes nothing that requires root. Re-confirm the app image doesn't pin a conflicting non-root `USER` that would fight the override.

**(b) UID/GID plumbing in the Taskfile** — the dev-stack tasks (`dev`, `dev:lite`, and any task that `docker compose up`s the dev stack) export `UID`/`GID` for compose. Compute them once as task vars:

```yaml
vars:
  UID:
    sh: id -u
  GID:
    sh: id -g
```

and pass them in the env of the compose invocations. (Taskfile is a HYBRID-managed file; the change lives in the framework-owned region.)

**(c) Belt-and-suspenders teardown in the acceptance harness** — the framework's `tests/acceptance/test_rendered_project.py`:
- sets `UID`/`GID` in the `env` of its `docker compose … up` subprocess calls (so the harness doesn't rely on the `:-1000` default);
- ensures every compose-stack test tears down via a fixture/`finally` that runs `docker compose … down -v` **even on failure** (no leaked containers/volumes);
- with writes now host-owned, pytest's `tmp_path` cleanup succeeds — no residual root-owned render dirs.

### Integrity

`dev.yml` is a LOCKED tracked file → adding `user:` changes its rendered bytes for **every** project = a deliberate **one-time baseline manifest shift** (existing projects pick it up on `framework upskill`), precedented by OBS-PROD/SVC-PROD. The service *set* in `dev.yml` is unchanged (only the `app` service gains a field), so the structural `dev.yml` render tests (e.g. `test_render_compose_byte_identical_without_workers`, which asserts the service keys) stay green; any test asserting exact `app`-service content is updated to expect the `user:` line.

---

## 2. `review-contracts` Agent (authored)

Mirrors the `review-api-design` pattern (a battery-gated interface reviewer). The live `gates_agents` machinery (8d/8g) wires it into the generated CI review matrix automatically once the `consumers` battery declares it.

### Components

- **Prompt** — `src/framework_cli/review/agents/contracts.md`, modeled on `api-design.md`. Focus: consumer-driven-contract risks a schema diff or the Pact `contracts` CI job can miss — a provider change that breaks a committed consumer pact; removing/renaming a field a consumer depends on; an incompatible status/shape/required-field change without versioning; pacts not regenerated/published after a provider change; consumer tests that don't actually assert the contract (over-loose matchers); provider-state drift between the pact and the seeded baseline.
- **Registration** — in `registry.py` `_SPECS`:

  ```python
  "contracts": AgentSpec(
      "review-contracts", _prompt("contracts"), "high", "battery", DEFAULT_MODEL
  ),
  ```

  Blocking on `high`; `active_when="battery"` → PR-only (battery agents are auto-excluded from the push base).
- **Gating** — in `batteries.py`, the `consumers` battery gains `gates_agents=("contracts",)`. It activates only for projects with the consumers battery.
- **Eval fixtures** — `tests/eval/fixtures/contracts/` with bad fixtures (breaking-contract diffs — e.g. a removed/renamed provider field, an incompatible status change) + a good fixture (a safe additive change), matching the `api-design` fixture shape (the 8d precedent: ~3 bad + 1 good). A provisional `contracts` entry is added to `tests/eval/fixtures/thresholds.yaml` (recall/fp), to be **tuned from Plan 11's first real scorecard**.

### Severity rationale

Blocking (`high`), consistent with the sibling `review-api-design`: a genuinely breaking contract change is serious, and the Pact provider-verification CI job is example-driven (it can't catch every consumer-driven gap), so a diff-level reviewer that blocks adds real protection. PR-only keeps it off the push-to-main subset.

---

## 3. Testing

- **Hygiene (hermetic):** render tests asserting `dev.yml`'s `app` service carries `user: "${UID:-1000}:${GID:-1000}"` and the Taskfile region computes/passes `UID`/`GID`; the existing structural `dev.yml` render tests stay green; `framework integrity` green with the one-time `dev.yml` shift. The host-UID + teardown effect is exercised by the (Docker-gated) acceptance tier — verify a dev-stack test leaves no root-owned files (renders clean up).
- **`review-contracts` (hermetic — no API calls):** a registry test (registered; gated by `consumers`; present on `pull_request`, absent on `push`); a fixture-loading test; the `consumers`→`contracts` `gates_agents` wiring test. The **real-key eval scoring is deferred to Plan 11**.
- **Framework gate:** `ruff` / `ruff format --check` / `mypy src` / `uv lock --check` / `uv build` clean; **no new framework dependency**.

## 4. Surfaces Touched

- `src/framework_cli/template/infra/compose/dev.yml` (LOCKED) — `user:` on the `app` service.
- `src/framework_cli/template/Taskfile.yml` (HYBRID) — `UID`/`GID` vars + pass-through to dev compose tasks.
- `tests/acceptance/test_rendered_project.py` — UID/GID env on compose subprocesses + teardown fixture.
- `src/framework_cli/review/agents/contracts.md` — new prompt.
- `src/framework_cli/review/registry.py` — register `contracts`.
- `src/framework_cli/batteries.py` — `consumers.gates_agents = ("contracts",)`.
- `tests/eval/fixtures/contracts/` + `tests/eval/fixtures/thresholds.yaml` — fixtures + provisional threshold.
- Framework tests for the above (render/registry/fixture/wiring).

## 5. Open Questions / Risks

- **Passwd-less UID:** verify uvicorn `--reload` runs cleanly as an arbitrary `user:` with no `/etc/passwd` entry; add `HOME=/tmp` to the dev app env only if required.
- **Taskfile `sh:` portability:** `id -u`/`id -g` are POSIX; fine on the Linux/WSL/CI targets the framework supports.
- **`dev:lite` coverage:** confirm whether `dev:lite` reuses the same `app` service definition (it should — the `user:` line then covers it); if `dev:lite` has a separate app definition, apply the same directive.
- **review-contracts provisional threshold:** intentionally a guess until Plan 11's real scorecard — call this out so it isn't mistaken for a validated value.
