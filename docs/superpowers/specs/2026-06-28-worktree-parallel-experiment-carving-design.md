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
| **A1** | `FWK75` (mutated) | Behind-edge dev mode: supported Traefik-decoupled run-mode (`task dev:edge`) · `X-Forwarded-Proto` trust in the app · behind-edge conformance test · dispose `DEC-0006`. Implements **tiers 1–2** of the contract. | **defines** contract; **provides** `task dev:edge` |
| **A2** | `FWK74` (mutated) | Worktree-aware stack provisioning: a tool/command that assigns a worktree's `PORT_OFFSET`, brings its stack up via `task dev:edge`, and (de)registers the chosen edge subdomains · the per-worktree offset/edge-registration convention · worktree SDD-flow capture. | **consumes** tier-2 |
| **B** | `FWK89` (new) | Test inner-loop speed — **the whole of test parallelization**: `pytest-xdist` + the parallel-safety hardening it requires (per-worker tmp/render isolation, testcontainer instancing — incl. **tier-3** transient instances) · tiered fast/full gate (`FWK77`). | **consumes** tier-3 |

The contract itself is a cross-cutting id: **`FWK88`** (defined here, implemented split: tiers 1–2
in A1, tier-3 within B). B is *not* "tier-3" — tier-3 instances are one need inside B's broader
parallelization work.

## The frozen seam contract — three-tier instance/port allocation (`FWK88`)

A single runtime contract, **frozen here, a priori**. Expressed as responsibilities, expectations,
and the data that crosses the boundary — *not* a file partition.

### Tiers

| Tier | Instance | `PORT_OFFSET` | Edge engagement | Implemented by |
|---|---|---|---|---|
| **1 · persistent** | main-branch dev stack | `0` (base) | **full** fan-out — app + all observability subdomains (`grafana.<slug>.localhost`, `prometheus.<slug>.localhost`, …) | A1 |
| **2 · temporary** | per-worktree dev stack | `k × 1000` (k = worktree index) | **opt-in per work package** — app by default, plus only the obs subdomains that package touches | A1 (run-mode) + A2 (provisioning) |
| **3 · transient** | per-test-run / per-`xdist`-worker stack | OS-ephemeral (see below) | **none** — test-local, reached directly by its test | B |

### Concrete bands (binding)

- **Port-derivation** — already shipped & binding (`FWK31`): `scripts/compose.sh` shifts every
  published host port by `${PORT_OFFSET:-0}`. Base map = the `_p` table (`HTTP 8000`, `POSTGRES
  5432`, `TRAEFIK_HTTPS 443`, `TRAEFIK_HTTP 80`, `MONGO 27017`, `REDIS 6379`, `FRONTEND 5173`,
  `PROMETHEUS 9090`, `GRAFANA 3000`, `ALERTMANAGER 9093`, `LOKI 3100`, `TEMPO 3200`, exporters
  `9187/9216/9808/9121`). A2 consumes this; **A1 must not break it**.
- **Tier-3 band** — OS-ephemeral ports (Linux default `32768–60999`). **Disjoint from tiers 1–2 by
  construction** because the highest base port (mongo `27017`) `+ PORT_OFFSET` stays below `32768`
  as long as the worktree index **`k ≤ 5`** (`27017 + 5×1000 = 32017 < 32768`). The experiment uses
  `k ∈ {1,2,3}`. **Binding constraint: `k ≤ 5`** — raising it requires lowering the step or
  reserving a different tier-3 band, which is a contract change (re-cut here, not in a worktree).

### Run-mode selector (pinned)

`task dev:edge` brings the **full** stack (app + observability) up with **Traefik excluded**
(`:443`/`:80` unbound), all other host ports per `PORT_OFFSET`. A2 invokes `task dev:edge`; A1
implements it. The *mechanics* (profile split) are A1's to design; the **invocation + guarantee is
frozen**.

### Stays box-specific (NOT promoted — A1 constraint, from `FWK75`)

The nginx edge itself, `*.localhost` / `grafana.<slug>.localhost` naming, the mkcert edge cert,
`stacks.yml`, and the name→port generator belong to `local-reverse-proxy`. A1 ships only the
generic capability (a stack that *can* run behind a shared edge).

## Top-level merge-order DAG (binding merge-deps)

```
A1 (FWK75) ──provides task dev:edge──▶ A2 (FWK74)
B  (FWK89) ── independent (consumes only the frozen FWK88 contract; no code dep on A1/A2)
```

- **A1 merges before A2**, OR A2 stubs the `task dev:edge` run-mode for its own tests and integrates
  against real A1 at the end. State the choice in A2's worktree before it forks.
- **B is independent** — it depends on the *contract* (tier-3 disjointness, `k ≤ 5`), not on A1/A2
  code, so it merges whenever ready.
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

The experiment is **runnable today** — `PORT_OFFSET` already ships (`FWK31`), so three stacks
coexist now (`k = 0/1/2/3`), each binding its own `:k443`. Behind-edge (A1) is therefore a *product*
of the experiment, not a *prerequisite*: it replaces the ugly `:k443` URLs + the hand-rolled
Traefik-exclusion with clean `*.localhost` + one TLS edge. File-level conflicts on shared files
(`Taskfile.yml`, `pyproject.toml`, CI workflows, `PLAN.md`, `ACTION_LOG.md`) are ordinary merges —
Git's job, same as any human team; they are **not** pre-partitioned.

## A-priori & binding

The seam is cut **before** any worktree brainstorms or specs — not derived post-hoc by comparing
finished designs. Post-hoc reconciliation would make the seam an *output* (removing any obligation
on the worktrees to respect it) and would assume temporal symmetry (all streams reaching the
seam-relevant decision together) that does not hold. The capability under test is precisely:
**can independent streams build to an interface frozen before any of them designed anything?**

## PLAN mapping emitted by this carving

- `FWK75` → **mutated** into the A1 parent (behind-edge dev mode; tiers 1–2; scope preserved incl.
  the NOT-promoted box-specific list).
- `FWK74` → **mutated** into the A2 parent (worktree-aware stack provisioning; tier-2 consumer).
  Dropped as done: "land `$DEV_ROOT` + FWK72 relocation first" (FWK72 closed). Moved to A1: the
  worktree-aware Traefik-decouple profile.
- `FWK88` → **new**, cross-cutting: the three-tier instance/port allocation contract (this spec is
  its definition; implementation split A1 tiers 1–2 / B tier-3).
- `FWK89` → **new** B parent (test inner-loop speed) → children `FWK76` (parallelize, owns tier-3
  transient instances) + `FWK77` (tier commit-vs-merge).
- `FWK90` → **new**, follow-up to `FWK89`: tight per-mutation test scoping at interim runs (run only
  the tests a code mutation affects, not the whole suite — distinct from FWK77's commit-vs-merge
  tiers).
