# Deploy Reference Strategy — e2e Harness & Packaging (Plan 5c-2 §7/§8 resolution) — Design Spec

**Date:** 2026-06-02
**Status:** Approved (brainstorm) — feeds the Plan 5c-2 implementation plan.
**Companion to:** `docs/superpowers/specs/2026-05-22-deploy-reference-strategy-design.md` (the parent 5c design). This doc resolves the parent's **§7 (the proof harness)** and **§8 (deferred implementation details)**, plus the temp-disk prerequisite that the harness depends on. The parent spec's brainstorm is left intact; this is the plan-time resolution it called for.
**Roadmap row:** Plan 5c-2 in `docs/superpowers/plans/2026-05-20-meta-plan.md`.

---

## 1. Purpose & boundary

Plan 5b shipped the deploy *contract* + an opinionated `strategy.sh` skeleton whose `__target_*` hooks are `_todo`. Plan 5c-1 shipped the migration-safety half of the parent 5c spec (the `APP_RUN_MIGRATIONS` entrypoint gate + the contract-direction migration guard). **Plan 5c-2** is the remaining half: a turnkey compose-over-SSH 1..N reference implementation **and** the multi-container e2e that proves the parent spec's headline claim — *no-downtime rolling across N independent hosts, given a health-draining LB and graceful shutdown.*

This design settles the implementation-level questions the parent spec deliberately deferred (§8) and specifies the proof harness (§7) concretely enough to plan.

**Out of scope** (inherited from the parent §2): no real cloud-LB automation, no managed-Postgres provisioning, no second concrete target (Fly/Render/k8s stay builder-implemented against the 5b seam), no multi-region / data-tier blue-green.

## 2. Strategy packaging — selectable target file

The 5b `strategy.sh` skeleton must stay **target-agnostic** (builders deploy to Fly/k8s/their own infra). 5c-2 therefore packages compose-over-SSH as an **opt-in target file**, not as the default:

```
infra/deploy/
  strategy.sh          # skeleton (prescribed logic) — sources targets/${DEPLOY_TARGET}.sh when set
  targets/
    compose-ssh.sh     # the turnkey 1..N implementation (this slice)
  README.md            # documents DEPLOY_TARGET + the compose-over-SSH config vars
```

- `strategy.sh` sources `infra/deploy/targets/${DEPLOY_TARGET}.sh` **only when `DEPLOY_TARGET` is set**; unset → today's `_todo` skeleton, byte-for-byte unchanged (so existing builders and the 5b contract are unaffected).
- `targets/compose-ssh.sh` defines the `__target_*` hooks (`__target_place_image`, `__target_migrate`, `__target_record_release`, `__target_release_history`, `__target_teardown`) for compose-over-SSH across `DEPLOY_HOSTS`.
- Both `strategy.sh` (unchanged) and the new `targets/compose-ssh.sh` are **integrity-locked** (tracked tier) so a builder can't silently weaken the prescribed logic; this is a baseline manifest shift (one-time framework bump), consistent with prior overlay additions.
- The builder opts in with a single env var (`DEPLOY_TARGET=compose-ssh`) in their deploy environment; no `framework new` question is added (keeps the integrity manifest invariant across answers, and the file is always present and discoverable).

## 3. App-only host compose

A new `infra/compose/app-host.yml.jinja` for the app hosts (§3 of the parent):
- Mirrors `base.yml`'s `app` service, but: `image: ${APP_IMAGE}` (no `build:`), **no Traefik labels** (TLS/routing is the builder's external LB), serves plain HTTP on the private port (default 8000), and sets `APP_RUN_MIGRATIONS=false` (the deploy migrates once centrally — see parent §4/§5; the 5c-1 entrypoint gate makes this safe).
- Retains the container healthcheck (the existing `/heartbeat` liveness probe). **Note the distinction:** the container healthcheck is liveness for compose; the **LB drains on the SLO `/health` probe** (parent §3 contract). The e2e proxy keys on `/health`.
- **No Postgres service** — the DB is the single shared external one referenced by `APP_DATABASE_URL`.

## 4. The e2e harness (the proof) — §7 resolved

A **Docker-gated acceptance test** (skips without Docker, like the existing live-stack tests in `tests/acceptance/test_rendered_project.py`). Topology:

- **≥2 "host" containers** — a small custom image: `docker:dind` (alpine) + `openssh-server`. Run **`--privileged`** (test-harness only; never shipped to builders). Each host runs its **own dockerd** with its **own networks and image cache** — a faithful independent host, which is what makes the no-downtime/rolling proof meaningful (a shared-daemon socket-mount approach was rejected because "N hosts" would collapse into one daemon and the test could pass for the wrong reasons). The dind data dir is placed on a **disk-backed volume** (§6), never tmpfs.
- **1 shared Postgres** container — the external/managed-DB stand-in, reached by every host via `APP_DATABASE_URL`.
- **1 LB stand-in proxy** — a **stock `nginx`** configured to route only to hosts whose `/health` returns 200 and to drain a host promptly when it goes unhealthy (passive health checks). nginx over a bespoke proxy: zero proxy code to maintain, and it's a faithful "builder-provided LB" stand-in.
- **The test acts as the deploy controller:** renders a project with `DEPLOY_TARGET=compose-ssh`, then invokes the **real `strategy.sh`** over **real SSH** to each host container — scp the app-only compose, migrate-once against the shared DB, then the rolling drain→update→await-healthy→rejoin across the host list. Real dind + real SSH means the actual compose-over-SSH plumbing is exercised, not stubbed.

The proof, in two assertions:
1. **No-downtime:** a **continuous poller** hits the app *through the nginx proxy* for the entire roll and asserts **zero failed requests** (this is the only thing that genuinely proves the headline claim, given a draining LB + the app's Plan-4 graceful shutdown).
2. **Rollback correctness:** then exercise rollback — code-back on **all** hosts (same rolling mechanism) → `alembic downgrade` **once** against the shared DB — and assert the prior release serves with the schema reverted (the symmetric inverse of forward: up = schema→code, down = code→schema).

The contract-direction detector is **already** unit-tested (shipped in 5c-1), so it is not re-proven here.

## 5. Host model & SSH — §8 resolved

- **dind, not docker-socket-mount** — chosen for fidelity (separate daemons/networks per host). Cost: `--privileged` + slower nested-daemon startup, both acceptable at the Docker-gated acceptance tier.
- **Real SSH** (sshd in each host image), so the strategy's compose-over-SSH path is faithful end-to-end rather than the test reaching the dind daemons directly.

## 6. Temp / RAM infrastructure (prerequisite)

The dev WSL instance mounts `/tmp` as **tmpfs — RAM-backed, capped at 16 GB** (half of 31 GB RAM; via systemd's `tmp.mount`). The real disk is the 936 GB ext4 root (`/`); Docker's data-root (`/var/lib/docker`) already lives there. Heavy renders + dind layers on RAM-backed `/tmp` are what previously wedged the acceptance tier (a RAM cap, not a disk cap). Two distinct problems, two fixes — plus an environmental insurance fix:

- **(a) Surgical redirect — load-bearing, travels to CI.** A conftest/fixture points pytest's `basetemp` **and** the dind data volumes at a disk-backed dir on `/` (e.g. `/var/tmp/swiftwater-e2e`). This is the fix the harness actually depends on; it is reproducible on any machine and in CI, independent of this box's `/tmp` configuration.
- **(b) Root-owned-artifact cleanup.** Run the acceptance/host containers as the **host UID** (`--user $(id -u):$(id -g)` / compose `user:`) and clean up renders (incl. any root-owned artifacts) in teardown. This folds in the long-standing Plan 9 follow-up (root-owned `__pycache__` accumulation), which is orthogonal to *where* `/tmp` lives.
- **(c) Environmental insurance — this box only.** `sudo systemctl mask tmp.mount` + `wsl --shutdown` reverts `/tmp` to the ext4 root (disk-backed, 936 GB), fixing sandbox fragility for *all* tools. One-time; requires a WSL restart (ends the running session), so it is run as a discrete step, not mid-implementation. It is **not** load-bearing for the harness — (a) is — it is quality-of-life for the dev environment.

## 7. Self-review

- **Placeholders:** none — host model (dind+sshd), LB stand-in (nginx), strategy packaging (selectable `targets/compose-ssh.sh`), app-only compose shape, and the temp strategy are all settled. The parent §8's contract-detector bullet is moot (shipped in 5c-1).
- **Internal consistency:** the migrate-once direction (expand, up-first) and rollback ordering (code-back-then-downgrade) match the parent §5 model and §3 rolling mechanism; the no-downtime claim stays qualified (given a draining LB + graceful shutdown) and is what §4's poller proves.
- **Scope:** one reference target + its proof + the temp prerequisite. The only shipped-file changes are additive (`targets/compose-ssh.sh`, `app-host.yml.jinja`, README/DEPLOY.md docs) plus the inert `DEPLOY_TARGET` source-hook in `strategy.sh`; the skeleton's default behavior is byte-identical when `DEPLOY_TARGET` is unset.
- **Ambiguity:** the `/health` (LB drains) vs `/heartbeat` (container liveness) distinction is called out explicitly in §3 so the harness keys the proxy on the right probe.

---

*End of design. Next step: `superpowers:writing-plans` to produce the Plan 5c-2 implementation plan from the parent 5c spec + this companion.*
