# First worktree-parallel experiment — carving + seam contract

> **Date:** 2026-06-28 · **Status:** approved (brainstorm) · **Author:** Chris (with Claude)
> This is the **carving** for the framework's first git-worktree-based parallel-development run.
> It is the hand-off artifact each worktree reads: it fixes the streams, the **frozen seam
> contract**, and the **merge-order DAG** — before any worktree forks. The per-stream *designs*
> happen inside the worktrees; this document does **not** design them.

## Purpose & success

First worktree experiment, **both** weighted equally: ship three real backlog items in parallel
**and** codify the worktree workflow (the latter feeds the worktree-readiness stream, A2). "Start
slow" = exactly **three** streams. The streams do **implementation**, not discussion threads — a
design-only run exercises none of the load-bearing parts (live stacks, real code merges, build
contention), so it would prove nothing.

This is a worked instance of **FWK57** (decomposition precedes parallelism; the binding constraint
is interface/decision *stability*, not serial build-order). The experiment's second product is
evidence about whether an **a-priori** seam cut actually holds — see *A-priori & binding*.

## The three streams

| Stream | Parent PLAN id | Load-bearing deliverable (code) | Seam role |
|---|---|---|---|
| **A1** | `FWK75` (mutated) | Behind-edge dev mode: a supported run-mode (`task dev:edge`) that runs the stack **without a per-stack Traefik binding `:443`** while **keeping the Docker-discovery labels** on its containers · **instance-parameterized labels** (so multiple instances coexist behind one shared edge) · `X-Forwarded-Proto` trust in the app · behind-edge conformance test · dispose `DEC-0006`. | **defines** `FWK88` labels; **provides** `task dev:edge` |
| **A2** | `FWK74` (mutated) | Worktree-aware stack provisioning: a tool/command that assigns a worktree's **box-agnostic instance identity** (→ the discovery-label parameter) + an optional `PORT_OFFSET` (only if direct host access is wanted), and brings the stack up via `task dev:edge` · the per-worktree identity/offset convention · worktree SDD-flow capture. | **consumes** tier-2 |
| **B** | `FWK89` (new) | Test inner-loop speed — **the whole of test parallelization**: `pytest-xdist` + the parallel-safety hardening it requires (per-worker tmp/render isolation, testcontainer instancing — incl. **tier-3** transient instances) · tiered fast/full gate (`FWK77`). | **consumes** tier-3 |

The contract is a cross-cutting id: **`FWK88`** (defined here; implemented split — the
instance-labels + tiers 1–2 in A1, tier-3 in B). B is *not* "tier-3" — tier-3 instances are one
need inside B's broader parallelization work.

## The frozen seam contract — instance addressing via Docker discovery (`FWK88`)

The framework's contribution is **box-agnostic Docker-discovery metadata** on its containers; a
**box-specific edge** discovers it. Frozen here, a priori. Expressed as responsibilities,
expectations, and the data that crosses the boundary — *not* a file partition.

### What the framework provides (box-agnostic — this is the frozen seam)

Each stack's containers carry **instance-parameterized Docker labels** — the same Traefik-schema
labels the template **already ships** (`traefik.http.routers.<svc>.rule=Host(...)`,
`...services.<svc>.loadbalancer.server.port=...`), but with the Host rule and router/service names
**parameterized by a box-agnostic instance identity** `<product-slug>[-<instance>]`, so N instances
of M products never collide on a hostname or a Traefik router name. This identity + addressing data
is the seam. (Already half-built: the template ships these labels and mounts
`/var/run/docker.sock` into Traefik — discovery, not a static registry.)

The **same instance identity** `<slug>[-<inst>]` drives three things uniformly, so all per-instance
namespacing flows from one value A2 sets at provision time:

1. the discovery-label Host rules (above);
2. **`COMPOSE_PROJECT_NAME = <slug>-<inst>`** — namespaces containers, volumes (so per-instance
   Postgres data isolation is automatic — no shared-volume corruption between two worktrees of the
   same product), and the default network. The template already sets `name: {{ project_slug }}` in
   `base.yml` and documents that `COMPOSE_PROJECT_NAME` overrides it — A2 supplies the override;
3. the **optional** `PORT_OFFSET` (only when direct host access is wanted).

**Edge↔instance Docker network (A1-internal, deliberately not pinned here).** A shared edge can only
route to containers it shares a Docker network with; the template defines none today (each stack
uses its own `<project>_default`). Closing this — a shared external `swiftwater-edge`-style network
the instances attach to, vs. the box edge dynamically `docker network connect`-ing to each
instance's default network — is an **A1-internal first-decision**. It is left unpinned because
**A2/B do not consume the network choice** (they consume the identity, `task dev:edge`, and the
label schema); A1 records its resolution in its own worktree. This is the one sub-decision the
carving intentionally defers, and only because it crosses no stream boundary.

### What the box provides (box-specific — NOT a framework concern)

A shared edge with Docker-socket access **discovers** the labeled containers and routes to them
**over the Docker network** (`container:port`), terminating TLS on the one host `:443`. The
mechanism is the box's call — a shared Traefik (Docker provider) or nginx-via-docker-gen — and lives
in `local-reverse-proxy` (it is on `DEC-0006`'s NOT-promoted list). This document does **not** freeze
it.

### Consequence: host ports are optional

Because the edge routes over the Docker network, **HTTP edge access needs no host ports** — only the
edge binds `:443`. `PORT_OFFSET` (`FWK31`) is needed **only for optional direct host-port access**
(hitting a DB/app on `localhost:PORT` without the edge — IDE/debug). A worktree that only needs edge
access publishes no host ports and draws nothing from any budget. When host access *is* wanted,
offsets come from a box-global pool; the honest cap (~**5** concurrent host-publishing stacks — from
the `step-1000` cross-service collision at offset-diff 5, where app `8000` meets grafana `3000`, plus
the `32768` tier-3 floor) applies **only to that opt-in surface**, not to edge routing.

### Tiers

| Tier | Instance | Edge (hostname form) | Host ports | Implemented by |
|---|---|---|---|---|
| **1 · persistent** | main-branch dev stack | yes — **nested** `<slug>.localhost` + `<svc>.<slug>.localhost` obs | base (offset 0), as today | A1 |
| **2 · temporary** | per-worktree dev stack | yes — **flat single-label** `<slug>-<inst>.localhost` + `<svc>-<slug>-<inst>.localhost` obs (opt-in) | **optional** — `PORT_OFFSET` from the pool only if direct host access is wanted | A1 (labels) + A2 (provisioning) |
| **3 · transient** | per-test-run / per-`xdist`-worker stack | no | OS-ephemeral (`32768–60999`), test-local | B |

### Hostname scheme & TLS (cert seam)

Cert generation is box-specific (`DEC-0006` NOT-promoted), and stays **static** — no per-worktree
cert work — because the framework picks hostname forms that two **static** box-side mkcert certs
already cover:

- **Tier 1 (persistent)** keeps the **nested** form `<svc>.<slug>.localhost`, covered by the box's
  **existing** per-product `*.<slug>.localhost` cert. Unchanged.
- **Tier 2 (worktree)** uses the **flat single-label** form `<svc>-<slug>-<inst>.localhost` so the
  box's static **`*.localhost`** wildcard covers every dynamic instance. Nested two-labels-deep
  names (`grafana.<slug>-<inst>.localhost`) are **avoided** for tier-2 precisely because
  `*.localhost` cannot cover them.

The framework owns the **flat-vs-nested label choice** (this is `FWK88`/A1); the certs themselves
are box-side.

### The seam (runtime data crossing)

The **Docker label schema** — instance-parameterized Host rules + router/service names + service
port. Frozen here, a priori, binding. The edge's *discovery* of those labels is box-side and is not
frozen by us.

## Top-level merge-order DAG (binding merge-deps)

```
A1 (FWK75) ──provides task dev:edge + the instance-label schema──▶ A2 (FWK74)
B  (FWK89) ── independent (consumes only the frozen FWK88 tier-3 band; no code dep on A1/A2)
```

- **A1 merges before A2**, OR A2 stubs the `task dev:edge` run-mode + assumes the frozen label
  schema for its own tests and integrates against real A1 at the end. State the choice in A2's
  worktree before it forks.
- **B is independent** — it depends on the *contract* (tier-3 OS-ephemeral disjointness), not on
  A1/A2 code, so it merges whenever ready.
- `FWK88` is **not** a merge node — it is this frozen spec.

## Per-worktree protocol (the carving applied fractally)

Each worktree, on entry, takes its parent PLAN row + **this spec** and:

1. **Treats the seam contract as fixed.** Do not renegotiate it mid-stream. If you discover the
   a-priori cut is *wrong*, that is a **loud finding** — record it and surface it; do **not** quietly
   adapt. (There is no reconciliation hatch; a wrong cut failing loudly is a headline result of the
   experiment, per FWK57/FWK73.)
2. **Finds its work package's internal seams** — the sub-boundaries within its own stream.
3. **Decomposes into smaller, individually-committable PLAN entries** (sub-ids under its parent),
   each sized so it can be done, committed, and then **`/clear`-ed** before the next — keeping each
   sub-PLAN's context tight.
4. **Builds and records its own local impl + merge-deps tiny DAG** (the order its sub-PLANs land),
   the same shape as the top-level DAG above, one level down.
5. **Executes one sub-PLAN at a time** (brainstorm → spec-if-needed → TDD → commit), `/clear`, next.
6. **Respects the top-level merge-deps** when integrating back to `main`.

## Bootstrap & validation contention

The experiment is **runnable today** — the template already ships Docker-discovery labels +
`PORT_OFFSET` (`FWK31`), so multiple stacks already coexist. Behind-edge (A1) is therefore a
*product* of the experiment, not a *prerequisite*: it replaces the per-stack Traefik + ugly direct
host ports with instance-parameterized labels behind one shared box edge. File-level conflicts on
shared files (`Taskfile.yml`, `pyproject.toml`, CI workflows, `PLAN.md`, `ACTION_LOG.md`) are
ordinary merges — Git's job, same as any human team; they are **not** pre-partitioned.

## A-priori & binding

The seam is cut **before** any worktree brainstorms or specs — not derived post-hoc by comparing
finished designs. Post-hoc reconciliation would make the seam an *output* (removing any obligation
on the worktrees to respect it) and would assume temporal symmetry (all streams reaching the
seam-relevant decision together) that does not hold. The capability under test is precisely:
**can independent streams build to an interface frozen before any of them designed anything?**

## Learnings (live)

Captured as the experiment runs — the experiment's second product (codify the workflow) starts here,
in the carving itself.

1. **Seams need an adversarial panel review before they're frozen.** The shared-resource collision
   classes between instances — multi-product offset budget, edge discovery, mkcert hostname coverage,
   `COMPOSE_PROJECT_NAME`, the edge↔instance Docker network — were each found *reactively*, roughly
   one per review pass. A single adversarial panel of distinct collision-class lenses
   (resource-collision · lifecycle/teardown · isolation · cross-repo/box-boundary · scaling) at the
   seam-freeze point would have surfaced them in one pass instead of five. Applied retroactively to
   this seam before forking; generalized as a process in `FWK91`.

## PLAN mapping emitted by this carving

- `FWK75` → **mutated** into the A1 parent (behind-edge dev mode; defines the `FWK88` labels +
  tiers 1–2; scope preserved incl. the NOT-promoted box-specific list).
- `FWK74` → **mutated** into the A2 parent (worktree-aware stack provisioning; tier-2 consumer).
  Dropped as done: "land `$DEV_ROOT` + FWK72 relocation first" (FWK72 closed). Moved to A1: the
  worktree-aware Traefik-decouple run-mode.
- `FWK88` → **new**, cross-cutting: instance addressing via Docker discovery (this spec is its
  definition; the edge itself is box-specific and out of scope).
- `FWK89` → **new** B parent (test inner-loop speed) → children `FWK76` (parallelize, owns tier-3
  transient instances) + `FWK77` (tier commit-vs-merge).
- `FWK90` → **new**, follow-up to `FWK89`: tight per-mutation test scoping at interim runs (run only
  the tests a code mutation affects, not the whole suite — distinct from FWK77's commit-vs-merge
  tiers).
