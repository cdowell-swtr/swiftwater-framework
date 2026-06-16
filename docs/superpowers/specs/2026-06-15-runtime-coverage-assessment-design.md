# Provisioned-but-Unexercised Coverage — Assessment (FWK18a) — Design

> Design spec for **FWK18a**: a one-off multi-agent (`Workflow`) assessment that
> finds places where the framework's **template provisions** a real-runtime/build
> surface but **no test exercises** it — the class behind FWK17 (a git dep that
> broke `docker build`, no git in the builder) and FWK8 (Traefik routing nothing
> routed through). Status: approved (brainstorming, 2026-06-15). FWK18b (the
> durable mechanism) is designed *from this assessment's evidence*, separately.

## Context & goal

Two recent bugs were the same class: a surface the template **provisions** (a
build step, a compose service, runtime wiring) that **no test drives**, so a
regression was invisible until a consumer (Meridian) or a hand-built test hit it.
The host-based tiers (unit, functional, `uv sync`) and even `compose up` (which
starts a service without exercising it) miss the class.

Recon already shows ≥1 concrete gap (**baseline `docker build` is never run** — the
only Dockerfile build test is claudesubscriptioncli-gated). The goal of FWK18a is
to find **all** such surfaces, ranked, so each confirmed gap becomes a candidate
test PR (the way FWK8/FWK17 were), and so FWK18b can be designed on evidence.

## The "exercised" heuristic (shared, load-bearing)

A surface is **exercised** iff a test **drives it and asserts its effect** — not
merely renders or provisions it. Three classifications:
- **exercised** — a test runs the surface (e.g. `docker build`, brings up the
  stack and routes/queries through it) and asserts a real outcome.
- **indirect** — the surface runs incidentally (e.g. `entrypoint.sh` during any
  `compose up`) but nothing asserts *its* effect; a regression could pass silently.
- **unexercised** — no test touches it.

`indirect` and `unexercised` are gaps (ranked by risk).

## Search space (the surfaces the sweep enumerates)

Grouped into clusters for the finder fan-out:
1. **Docker image build** — builder / frontend-build / runtime stages, for the
   **baseline** render and representative **battery combos** (not just
   claudesubscriptioncli). Today only the claudesubscriptioncli builder stage is built.
2. **base/dev compose stack** — app + healthchecks + hot-reload + Traefik (Traefik
   routing now covered by FWK8; the rest?).
3. **Observability stack** — prometheus / loki / tempo / otel-collector /
   alertmanager / the battery exporters (postgres/mongo/redis/celery).
4. **Data + services stack** — postgres extension preload (timescaledb/age),
   mongo, redis, worker/beat (celery), their healthchecks.
5. **Entrypoint + certs + tasks** — `entrypoint.sh` alembic-upgrade + seed
   idempotency, `task certs`/mkcert, other `Taskfile` targets the stack relies on.
6. **Non-dev compose overlays** — `prod.yml` / `staging.yml` / `app-host.yml` /
   `test.yml`: are they ever brought up or config-validated?
7. **Per-battery live wiring** — each battery's runtime surface in a live stack
   (most batteries have only unit/functional tests, no live-stack exercise).

## The assessment — a `Workflow` multi-agent sweep

1. **Enumerate (cheap):** the cluster list above is the fixed work-list (no
   discovery agent needed — it's enumerated here).
2. **Find (fan-out, one agent per cluster):** each finder reads the relevant
   template files AND greps `tests/` (acceptance + `scripts/dogfood_e2e.py`),
   classifying every provisioned surface in its cluster as
   exercised/indirect/unexercised with **file:line evidence on both sides**
   (where provisioned; which test exercises it, or "none found").
3. **Adversarially verify (per claimed gap):** a second agent is given each
   `indirect`/`unexercised` claim and tries to **refute** it — find any test that
   actually drives that surface. A gap survives only if the skeptic can't. (Kills
   false positives — the FWK8 "the dev tests start Traefik" subtlety is exactly the
   trap.)
4. **Synthesize:** one agent merges the surviving gaps into a single **ranked
   inventory**, deduped, each entry: `{surface, provisioned (file:line), status
   (indirect|unexercised), risk (high|med|low) + why, suggested test}`.

Model: finders + skeptics on the session model; the synthesizer likewise. Agents
get read/grep/glob over the repo (they reason over real files, not a diff).

## Output

A committed report: `docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md`
— the ranked inventory. Each confirmed gap is a
candidate follow-on **test task** (new `FWK` ids, sequenced by risk), mirroring how
FWK8/FWK17 closed their instances. The report also feeds **FWK18b**.

## Out of scope (FWK18a)

- **FWK18b — the durable mechanism.** Whether the recurring pattern warrants a
  **framework-native agentic reviewer** (and how it resolves the target-scope
  wrinkle: the framework-target diff *excludes* the template payload, so a
  reviewer reasoning about `template/infra/...` vs `tests/...` needs a bespoke
  scope) **and/or deterministic completeness checks** (like the existing
  obs-completeness / integrity reverse-scan) is decided from this report's
  evidence, in a separate brainstorm.
- **Fixing the gaps.** Each confirmed gap is its own follow-on test PR, prioritized
  off the inventory; FWK18a only *finds and ranks* them.

## PLAN

- **FWK18a** → this design: run the multi-agent assessment, commit the ranked
  inventory. No release (analysis + a docs artifact). The inventory spawns
  follow-on test tasks + gates FWK18b.
