# First worktree-parallel experiment — carving + seam contract

> **Date:** 2026-06-28 · **Status:** approved (brainstorm), seam hardened by adversarial panel ·
> **Author:** Chris (with Claude)
> This is the **carving** for the framework's first git-worktree-based parallel-development run.
> It is the hand-off artifact each worktree reads: it fixes the streams, the **frozen seam
> contract**, and the **merge-order DAG** — before any worktree forks. The per-stream *designs*
> happen inside the worktrees; this document does **not** design them.

## Purpose & success

First worktree experiment, **both** weighted equally: ship three real backlog items in parallel
**and** codify the worktree workflow (the latter feeds the worktree-readiness stream, A2). "Start
slow" = exactly **three** streams. The streams do **implementation**, not discussion threads.

This is a worked instance of **FWK57** (decomposition precedes parallelism; the binding constraint
is interface/decision *stability*, not serial build-order). The seam below was hardened by an
adversarial panel before freezing (see *Learnings*) — five collision-class lenses run over the
contract in one pass.

## The three streams

| Stream | Parent | Load-bearing deliverable (code) | Seam role |
|---|---|---|---|
| **A1** | `FWK75` | Behind-edge dev mode: `task dev:edge` run-mode (no per-stack Traefik binding `:443`, labels kept) · **instance-parameterized + discovery-scoped** labels · edge-source-scoped `X-Forwarded-Proto` trust · fix the identity-aware teardown tasks · behind-edge conformance test (incl. default-parity) · dispose `DEC-0006` | **defines** the `FWK88` labels + network/run-mode |
| **A2** | `FWK74` | Worktree-aware **provisioning *and* deprovisioning**: assign instance identity, write the durable per-worktree `.env`, bring up via `task dev:edge`, and tear down (identity-aware `down -v` + edge-disconnect + offset release) before `git worktree remove` · per-worktree identity/offset convention · worktree SDD-flow capture | **consumes** tier-2 |
| **B** | `FWK89` | Test inner-loop speed — the whole of test parallelization: `pytest-xdist` + parallel-safety (per-worker tmp/render isolation, testcontainer instancing, **tier-3** transient instances with guaranteed reaping) · tiered fast/full gate (`FWK77`) | **consumes** tier-3 |

`FWK88` is the cross-cutting contract (defined here; split impl — labels/network/tiers 1–2 in A1,
tier-3 in B). B is *not* "tier-3" — tier-3 is one need inside B.

## The frozen seam contract (`FWK88`)

The framework's contribution is **box-agnostic Docker-discovery metadata** on its containers; a
**box-specific edge** discovers it. Frozen here, a priori, binding.

### Instance identity — one value drives everything

A single box-agnostic env var **`STACK_INSTANCE`** (default `<project-slug>` for the standalone /
single-stack case) is the seam's master parameter. A2 sets it once per worktree to `<slug>-<inst>`;
from it flow, uniformly:

1. the discovery-label Host rules + router/service names (below), via **compose-time `${STACK_INSTANCE}` interpolation — NOT render-baked Jinja** (so multiple instances of one render coexist);
2. **`COMPOSE_PROJECT_NAME = ${STACK_INSTANCE}`** — per-instance containers, volumes, default network;
3. the discovery **constraint label** (below);
4. the optional `PORT_OFFSET` (only if direct host access is wanted).

**Instance-string contract:** `<inst>` (and thus `STACK_INSTANCE`) MUST match `^[a-z0-9-]+$` — a
single DNS label, no dots/uppercase — so `*.localhost` covers it. A2 **sanitizes** branch-derived
names to this. Default `STACK_INSTANCE=<slug>` reproduces today's labels byte-for-byte (prod/staging
and default `task dev` unchanged) — A1's conformance test asserts this parity.

### Discovery labels & scoping

Containers carry the Traefik-schema labels the template already ships
(`traefik.http.routers.<svc>.rule=Host(...)`, `...services.<svc>.loadbalancer.server.port`), Host
rule + router/service names parameterized by `${STACK_INSTANCE}`. **Plus a frozen instance
constraint label** (`swiftwater.instance=${STACK_INSTANCE}`). Every discovering component scopes
itself by it, so discovery is instance-scoped, not box-global:

- any **per-stack Traefik** (tier-1 keeps one) sets `--providers.docker.constraints` on the instance
  label — else it discovers *every* instance's containers (silent cross-route bleed);
- **promtail** `docker_sd_configs` adds a `keep` relabel on
  `__meta_docker_container_label_com_docker_compose_project` (== this instance) — else it scrapes
  every container on the box into the wrong Loki (cross-instance log bleed; PII risk via anon Grafana).

### Hostname scheme & TLS (cert seam — box-side, static)

Cert generation is box-specific (`DEC-0006` NOT-promoted) and stays **static**:

- **Tier 1 (persistent)** keeps the nested `<svc>.<slug>.localhost`, covered by the box's existing
  per-product `*.<slug>.localhost` cert.
- **Tier 2 (worktree)** uses the **flat single-label** `<svc>-<slug>-<inst>.localhost` so the box's
  static `*.localhost` wildcard covers every dynamic instance. Nested two-label names are avoided
  (a `*.localhost` wildcard cannot cover them). The single-label `^[a-z0-9-]+$` rule above is what
  guarantees coverage.

### Network isolation invariants — FROZEN (was wrongly deferred; the panel's B1)

Network *membership* — not hostname/label parameterization — is the master isolation control. These
invariants are **frozen and cross-stream** (A2 and B consume them); only the network *mechanism* is
A1-internal:

- **Only edge-routed services** (app + opted-in obs) attach to the shared edge network. **Data
  stores (postgres/redis/mongo) stay on the per-project `default` network exclusively** — otherwise
  worktree A's app reaches worktree B's Postgres, and the shared service alias `postgres` resolves
  ambiguously across instances (silent cross-instance data corruption; creds are uniform `app/app`).
- **Tier-3 transient instances MUST NOT join the shared edge network and MUST NOT mount the host
  docker socket** — disjoint by construction, not by hostname omission.
- The A1 mechanism choice (shared `external` net vs. box `docker network connect`) is bound by: (a)
  **standalone-safe** — the shipped/default render MUST NOT reference a pre-existing `external`
  network (it would break every standalone `docker compose up` + prod/staging); (b) `task dev:edge`
  **idempotently ensures** the network on up and **disconnects before `down`** (no active-endpoint
  teardown deadlock).

### Host-port pool & budget

Edge HTTP routes over the Docker network, so **edge access needs no host ports**. `PORT_OFFSET`
(`FWK31`) is for **optional direct host access** only. Post-A1, **tier-1 persistent stacks run
edge-only (no host ports)** so they draw nothing from the pool (3 products at offset 0 would
otherwise collide). Honest cap: **~5 concurrent host-publishing stacks** — the *only* cross-service
mod-1000 collision among the 16 base ports is grafana(`3000`)↔app(`8000`) at offset-diff 5
(verified). The `32768` OS-ephemeral floor is *not* the cap; it guarantees tier-2 (≤offset 4, max
`31017`) and tier-3 (`32768+`) never overlap — a disjointness property. **`PORT_OFFSET` must be
*exported*** (the per-worktree `.env` is sourced via Taskfile `dotenv:`/shell export) — a bare
`.env` value is invisible to `scripts/compose.sh` and silently runs at offset 0.

### Tiers

| Tier | Instance | Edge (hostname) | Network | Host ports | Impl |
|---|---|---|---|---|---|
| **1 · persistent** | main | yes — nested `<svc>.<slug>.localhost` | shared (edge-routed svcs); stores on default | **none** (edge-only) | A1 |
| **2 · temporary** | per-worktree | yes — flat `<svc>-<slug>-<inst>.localhost` (opt-in obs) | shared (edge-routed svcs); stores on default | optional (`PORT_OFFSET`) | A1 labels + A2 provisioning |
| **3 · transient** | per-test/`xdist` worker | no | **default only — never shared, no socket** | OS-ephemeral `32768+` | B |

**Tier-2 ↔ tier-3 name disjointness (frozen):** B's transient project names carry a reserved marker
A2's tier-2 generator can never emit (e.g. `<slug>-t-<uuid>`), so the two never collide on
`COMPOSE_PROJECT_NAME` (shared containers/volumes).

## Provision / deprovision lifecycle — FROZEN (the panel's B2)

The provision path needs a **symmetric, identity-aware deprovision path**:

- **Durable identity store:** A2 writes a per-worktree `.env` (`STACK_INSTANCE`,
  `COMPOSE_PROJECT_NAME`, `PORT_OFFSET` if any) that **all** `dev:*` tasks source — the single source
  of truth for provision *and* teardown.
- **Fix the teardown tasks (A1):** today `dev:down`/`dev:logs`/`dev:reset` hardcode
  `-p {{ project_slug }}` (`Taskfile.yml.jinja:59,64`) → in a worktree they target the **tier-1 main
  stack**, tearing it down and orphaning the worktree's containers. Make them resolve
  `${STACK_INSTANCE}` instead; add `dev:edge:down`.
- **Down before remove (A2):** deprovision = `down -v` (reclaim the 3–7 named volumes — `dev:down`
  keeps volumes by design, so the normal path leaks them) + edge-disconnect, ordered **before**
  `git worktree remove`. Reused instance ids must not inherit stale `pgdata` (wipe on down, or never
  reuse).
- **Offset release:** the `PORT_OFFSET` pool needs reserve-on-provision / release-on-deprovision +
  orphan GC, else the ~5 slots erode on every crashed/abandoned stack.
- **Tier-3 reaping (B):** transient instances are guaranteed-reaped (Ryuk on, or a session-scoped
  finalizer that `down`s by a per-run label) + an end-of-session orphan sweep — they must not leak on
  an `xdist` worker crash/SIGKILL.
- **`/clear` boundary (protocol):** before `/clear`-ing between sub-PLANs, a worktree deprovisions or
  records its running stacks (the durable `.env`/registry), so a fresh context can reconcile/clean
  rather than re-provision duplicates.

## Top-level merge-order DAG (binding merge-deps)

```
A1 (FWK75) ──provides task dev:edge + STACK_INSTANCE label/network/teardown──▶ A2 (FWK74)
B  (FWK89) ── independent on the A1 code axis (tier-3 uses OS-ephemeral host ports, no edge, no
              shared network) — but shares the COMPOSE_PROJECT_NAME namespace with A2, governed by
              the frozen tier-2↔tier-3 name-disjointness rule (no merge-order dep, a naming rule both honor)
```

- **A1 merges before A2**, OR A2 stubs `task dev:edge` (and assumes the frozen `STACK_INSTANCE`
  schema) for its own tests, then rebases onto real A1 and **deletes its stub** (a duplicate Taskfile
  target is a shadowed key, not a clean textual merge). State the choice in A2's worktree before it forks.
- `FWK88` is **not** a merge node — it is this frozen spec.

## Per-worktree protocol (the carving applied fractally)

Each worktree, on entry, takes its parent PLAN row + **this spec** and:

1. **Treats the seam contract as fixed** — no mid-stream renegotiation. A wrong cut is a **loud
   finding** (record + surface), not a quiet adaptation.
2. **Finds its work package's internal seams.**
3. **Decomposes into smaller, individually-committable PLAN entries** (sub-ids under its parent),
   each sized to be committed then **`/clear`-ed** before the next (and see the `/clear` lifecycle
   rule above — tear down or record running stacks first).
4. **Builds and records its own local impl + merge-deps DAG.**
5. **Executes one sub-PLAN at a time** (brainstorm → spec-if-needed → TDD → commit), `/clear`, next.
6. **Respects the top-level merge-deps** when integrating back to `main`.

## Box-side preconditions & accepted dev-only risks

Owned by the box (`local-reverse-proxy`), recorded so they aren't mistaken for framework gaps:

- The shared edge, `*.localhost` resolution, the mkcert CA/wildcard certs, and a widened Docker
  `default-address-pools` (high tier-3 fan-out can exhaust the daemon's subnet pool) are **box
  prerequisites the consumer supplies**.
- `socket:ro` is **not** a privilege boundary — a discovering edge is root-equivalent on the host;
  trust its image/config provenance (a socket-proxy is the box's option).
- The edge binding `:443` and exposing instances by predictable hostname (incl. anon-admin Grafana)
  removes the prior per-port localhost confinement — bind loopback / front with auth is the box's call.
- **Off-box on-ramp:** `task dev:edge` **requires** a consumer-provided edge; it must **fail-fast
  with a clear message** when none is present (not silently produce an unreachable stack). The frozen
  `FWK88` label schema **is** the published contract any adopter builds a conformant edge to —
  `DEC-0006`'s "just upgrade and you have it" is amended to "upgrade + stand up a conformant edge."

## A-priori & binding

The seam is cut **before** any worktree brainstorms — not derived post-hoc by comparing finished
designs (that makes the seam an output, removing the worktrees' obligation to respect it, and assumes
temporal symmetry that doesn't hold). The capability under test: **can independent streams build to
an interface frozen before any of them designed anything?**

## Learnings (live)

The experiment's second product (codify the workflow) starts in the carving itself.

1. **Seams need an adversarial panel review before they're frozen.** Five shared-resource collision
   classes (multi-product budget, edge discovery, mkcert, `COMPOSE_PROJECT_NAME`, edge network) were
   found *reactively*, ~one per review pass. A panel of distinct collision-class lenses at the freeze
   point would have surfaced them in one pass. Generalized as `FWK91`.
2. **The panel proved it by catching a deferred blocker.** Run after the contract felt "done," the
   panel found that the edge↔instance network — which the operator and assistant had *jointly agreed
   to defer as A1-internal one message earlier* — is the **master isolation control** (cross-instance
   Postgres reachability + service-alias ambiguity + standalone-break + teardown deadlock). It also
   found the provision path had **no symmetric deprovision** (existing `dev:down` tears down the wrong
   stack) and that the **actual crossing datum** (the var injecting `<inst>` into the label) was never
   frozen. A human + a capable assistant in dialogue still deferred a blocker the panel caught — that
   is the case for `FWK91`, demonstrated, not asserted.

## PLAN mapping emitted by this carving

- `FWK75` → A1 parent (behind-edge dev mode; defines `FWK88` labels/network/run-mode + tiers 1–2;
  fixes the identity-aware teardown tasks).
- `FWK74` → A2 parent (worktree-aware provisioning **and deprovisioning**; tier-2 consumer; durable
  per-worktree `.env`).
- `FWK88` → cross-cutting: instance addressing + isolation via Docker discovery (this spec).
- `FWK89` → B parent (test inner-loop speed) → children `FWK76` (parallelize; tier-3 transient
  instances, guaranteed-reaped, reserved namespace) + `FWK77` (tier commit-vs-merge).
- `FWK90` → follow-up to `FWK89`: tight per-mutation test scoping at interim runs.
- `FWK91` → adversarial panel review for specs & seams (the process this carving demonstrated).
