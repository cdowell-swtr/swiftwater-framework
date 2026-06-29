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

### Fourth, parallel consumer: the box edge (`local-reverse-proxy`)

The existing shared edge is a **static registry → generated nginx → host ports** helper (`stacks.yml`
+ `generate.py` + `ports.py`; per-product `slug`+offset; `*.<slug>.localhost` cert; transient/worktree
routing explicitly *out of scope*). It does **not** match `FWK88`'s Docker-discovery model — so the
box **reworks its edge to consume the contract**: discover instances by the `FWK88` labels, route over
the Docker network, honor the network-isolation invariants + the flat tier-2 hostnames + the
`*.localhost` cert, and **delete its interim static edge + the README "exclude Traefik" instructions**
(the `DEC-0006` generator-side copy-deletion). This is the **generator-side adoption** under the
cross-repo convention (box = generator, framework = absorber). It runs **in parallel** with A1/A2/B,
fed this same spec, and — because `local-reverse-proxy` is **not git-backed** — it needs no worktree
and carries **no merge-collision risk**. It consumes A1's label schema (the contract), not A1's code,
so it's independent on the code axis like B; full end-to-end (worktree stack → box edge → browser)
integrates at the contract. It is the experiment's strongest a-priori test: an independent repo, in a
different stack (nginx/Traefik vs Python/compose), building to the frozen seam without coordinating.

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

### Labeled service set — which services the edge can route (amended; the box's Finding 1)

A discovery edge routes **only labeled containers**. The template today labels **only `app`**
(`base.yml.jinja:22-26`); the observability UIs carry **no** Traefik labels, so a discovery edge would
route the app and *silently* route no observability. (The *prior static edge* routed obs via host-port
mapping, which needs no labels — the Docker-discovery reframe dropped that routability. The tier table
assumed obs was routable; the template never delivered it.) **A1 adds the discovery labels**
(instance-parameterized Host rule + router/service names + the constraint label, exactly like `app`)
to the browsable obs UIs:

- **Labeled / routable:** `app` (8000), `grafana` (3000), `prometheus` (9090), `alertmanager` (9093)
  — the browsable web UIs (the prior static edge's routed set).
- **Not labeled / not edge-routed:** `loki`, `tempo`, the exporters, `otel-collector` — scrape /
  query / ingest endpoints, not browsable UIs (Loki/Tempo are reached *through* Grafana as datasources).
- Hostname forms per the tier table: tier-1 nested `<svc>.<slug>.localhost`; tier-2 flat
  `<svc>-<slug>-<inst>.localhost`. **Tier-2 obs is opt-in** per work package (A2 chooses which of the
  labeled obs UIs to expose).

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
- **The shared edge network name is FROZEN: `swiftwater-shared-edge`** (amended; the box's Finding 2).
  Edge-routed services attach to *that* named network, and the box edge's `--providers.docker.network`
  uses the **identical string** — it is a cross-stream datum (A1 ↔ box), not A1-internal. The
  `docker network connect`-per-stack alternative is **excluded** (it yields no single shared network
  name the edge's provider can use). The name is bound by: (a) **standalone-safe** — the shipped/default
  render MUST NOT reference a pre-existing `external` network (it would break every standalone
  `docker compose up` + prod/staging), so the shared network is **edge-mode-gated** (referenced/attached
  only under `task dev:edge`, never in the default `task dev`); (b) `task dev:edge` **idempotently
  ensures** `swiftwater-shared-edge` on up and **disconnects before `down`** (no active-endpoint
  teardown deadlock). A1 retains latitude only in *how* it ensures the network (e.g. an idempotent
  `docker network create` vs. an edge-gated compose overlay), **not** in the name or the attach model.

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

**Tier-2 ↔ tier-3 name disjointness (frozen — marker PINNED 2026-06-28, operator):** tier-3 transient
project names are **`<slug>-t-<uuid>`**; the **`<slug>-t-` prefix is reserved for tier-3**. The
disjointness is **structural, not coincidental**: A2's tier-2 generator (`<slug>-<inst>`) MUST reject any
`<inst>` beginning with `t-`, so the two never collide on `COMPOSE_PROJECT_NAME` (shared
containers/volumes). *(Was left unpinned "e.g. `<slug>-t-<uuid>`"; B's stream-B decomposition raised it as
a loud finding — a slug-value-coincidence marker like `swfwacc-` can't be verified disjoint across the
parallel A2 stream — and the operator pinned the structural form. B/`FWK95` builds to `<slug>-t-<uuid>`;
A2/`FWK74` enforces the `t-`-prefix ban on `<inst>`.)*

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
7. **Reconciles numbering only at merge, in merge order — never mid-run.** A worktree's PLAN `FWK`
   ids and `ACTION_LOG` entries are **provisional/local** while it runs (mid-run commits, even PRs,
   keep them as-minted). At integration, **in merge order**, renumber the worktree's ids + log entries
   to the next free monotonic block after `main`'s current max, so each worktree's contribution lands
   as an **atomic subtree** — a contiguous renumbered block, not interleaved. **Do not reconcile
   mid-run:** an earlier-merging sibling shifts the base, so any mid-run renumber goes stale and must be
   redone at merge (wasted work — observed live). Monotonicity is a **merge-time invariant**, not a
   during-run one. (Remedy for learning #5; a candidate to promote into `pi-convention.md` — see
   `FWK92`.)

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
  **`local-reverse-proxy` is the first/reference adopter** — it reworks its static edge to this
  contract in parallel (see *Fourth, parallel consumer*), proving the on-ramp is real.

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
3. **The seam reached past the reviewed artifact.** The panel reviewed the framework template (which
   *does* ship Traefik labels + the docker socket) and inferred "the edge already does Docker
   discovery" — but the actual shared edge lives in a *different, non-git repo* (`local-reverse-proxy`)
   and is static registry + host ports. The contract's load-bearing assumption was about a component
   no reviewer had read. Lesson: a seam review must reach **every repo the seam touches**, not just the
   one in hand. The upside: the mismatch turned the box into a fourth, cross-repo consumer of the same
   frozen contract — the strongest a-priori test available.
4. **The cross-repo consumer caught what the panel couldn't — twice in one trip.** Building its
   discovery edge to the frozen seam, the box surfaced two cross-stream data the contract left
   unfrozen: (1) the **labeled service set** — the discovery reframe silently dropped obs routability
   (the prior static edge routed obs by host-port, needing no labels; a discovery edge routes only
   labeled services, and only `app` is labeled); (2) the **shared edge network name** — the box's
   `--providers.docker.network` and A1's attach-step must use one identical string, yet the contract
   had marked the network mechanism "A1-internal." Both are the same class as B1/B3 — the network and
   the crossing datum kept being mis-scoped as A1-internal. The panel reviewed only the framework
   template, so it *could not* catch these: they live at the seam between the template and a
   *different repo's* edge. The loud-finding rule (surface, don't quietly adapt) is what made each
   amendment clean. Operational confirmation of learning #3.

5. **A shared monotonic counter is the collision class Git cannot catch — and it joins the panel
   thread.** All three worktrees branched at `FWK91` and independently minted their sub-PLAN rows from
   `FWK92` (A1: 92–99; A2/B: 92–96). Unlike a textual conflict, non-adjacent row inserts three-way-merge
   **clean** → silent triplicate IDs (an adjacent-line conflict "resolves" by keeping both same-ID rows).
   This is the documented exception to *"shared files always conflict, that's what Git's for"* (the rule
   that retired a-priori file-sandboxing): allocation from a shared counter isn't textual, so Git is
   blind to it. It is the **same meta-pattern as learning #1** — a shared-resource collision class found
   *reactively*, here post-fork — so it folds into the adversarial-panel thread: `FWK91`'s generalized
   lens set gains a **shared-namespace / monotonic-allocation lens** (IDs, host ports, project names, any
   global counter), which would have flagged it at the carving freeze. The remedy is **not** an a-priori
   partition (the standing protocol didn't contemplate parallel allocation; Bearing's MCP PLAN service
   root-cures it) but a **binding merge-time reconciliation rule** — see *Per-worktree protocol* step 7:
   renumber at merge, in merge order, never mid-run. A candidate to promote into `pi-convention.md` once
   the experiment validates it.

6. **Contract amendments have two propagation shapes — and choosing between them is a task-management
   concern, not a carving rule.** The box's findings landed as a **standalone** amendment PR (#92);
   stream-B's tier-2↔tier-3 marker pin landed **bundled inside its implementation PR** (#94). Both are
   valid, but they fan out differently: a standalone amendment lets a dependent stream (here A2, which
   must add the `t-`-prefix ban) pick up the contract change without pulling the surfacing stream's whole
   implementation; a bundled one couples them. Deliberately **not** settled as a carving-spec rule —
   per the operator, deferred to the **process design around Bearing's MCP-mediated task-management
   service** (the same service that root-cures learning #5's shared-counter collision), where an
   amendment and its dependent fan-out become **first-class tracked tasks** rather than a PR-shape
   convention each stream re-decides. Recorded here so the future service inherits the requirement.

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

## Promotion hand-off (`FWK92` — capture-only)

The experiment was validated end-to-end (runtime payoff, `ACTION_LOG #0368`: fresh-render
dual-instance e2e behind the live box edge — discovery, routing, isolation, host-port
collision-avoidance, cert trust, teardown all green). **This spec — §Learnings 1–6 + the
*Per-worktree protocol* step 7 + `docs/maintenance/worktree-parallel-development.md` (`FWK112`) — is
the durable record-of-record for the transferable workflow.** The three reusable parts:

1. **A-priori binding seam method + per-worktree fractal protocol** (novel).
2. **Adversarial-panel-before-freeze** lens set incl. the shared-namespace/monotonic-allocation lens
   (`FWK91`; §Learnings 1/2/5) — generalizes the existing adversarial-security-review method from
   security to design/seam artifacts; **must reach every repo the seam touches** (§Learnings 3/4).
3. **Merge-time reconciliation rule** (step 7; §Learning 5) — provisional ids while a stream runs,
   renumber in merge order to a contiguous atomic subtree, never mid-run; prefix-agnostic.

**The framework does NOT drive the promote-up.** Operator decision (2026-06-28): capture the
learnings here and hand the *implementation* (generalize into convention(s), tag, vendor back) to the
**absorber** — `cdowell-swtr/patterns`, most likely via **Bearing's MCP task-management service**
(the same service expected to root-cure §Learning 5's shared-counter collision and §Learning 6's
amendment-fan-out). Candidate homes (the absorber's call, *not* settled here): a new
`worktree-parallel-convention.md` composing with `pi-convention` (the merge-time rule) and
`adversarial-security-review-convention` (the design-seam lens) — vs. three independent amendments.
Conformance for a *process* promotion is itself the open question; the proposed seed is this
experiment's captured behavior (`#0368` + the `FWK112` honest-tense capture) replayed against the
generalized convention. When the absorber adopts, the framework vendors the convention and retires
its forward-looking "candidate to promote" claims (this section + step 7's note); the dated spec
stays as history.
