# FWK74 (worktree-stream A2) — worktree-aware stack provisioning & deprovisioning

> **Date:** 2026-06-28 · **Status:** approved (brainstorm) · **Author:** Chris (with Claude)
> **Parent carving (binding seam):** `docs/superpowers/specs/2026-06-28-worktree-parallel-experiment-carving-design.md`
> **Stream:** A2 (`FWK74`), stacked on A1 (`FWK75`, `fwk75-behind-edge`). Consumes A1's frozen
> `FWK88` contract — `STACK_INSTANCE`, `task dev:edge`, the network-isolation invariants — which
> this design **does not renegotiate**. A wrong cut against the seam is a loud finding, not a quiet
> adaptation.

## Purpose & scope

A2 is the **tier-2 consumer** of the frozen seam. It builds the tool a developer (or Claude
session) runs inside a git worktree to bring up an isolated dev stack behind the shared box edge,
and the symmetric tool that tears it down before the worktree is removed. Plus the worktree
SDD-flow capture — the "worktree-readiness" deliverable, dogfooded by *this* experiment.

**In scope:** instance-identity derivation; the durable per-worktree `.env`; idempotent
provisioning via `task dev:edge`; symmetric identity-aware deprovision (`down -v` +
edge-disconnect + offset release, ordered before `git worktree remove`); optional `PORT_OFFSET`
allocation; tier-3 name-disjointness on A2's side; the process doc.

**Out of scope (owned elsewhere, consumed frozen):** the `dev:edge` run-mode, the
instance-parameterized labels, the network mechanism, and the identity-aware fixes to
`dev:down`/`dev:logs`/`dev:reset` (all **A1**); tier-3 transient instances + reaping (**B**); the
box edge / cert / discovery wiring (`local-reverse-proxy`).

## Decisions settled in brainstorm

| # | Decision | Choice |
|---|---|---|
| D1 | Tool home & invocation | **Template payload**: `worktree:up` / `worktree:down` task targets in the managed `FRAMEWORK:BEGIN/END` block, backed by a script. Auto-derives identity from the worktree's branch — no manual id (branch name = worktree name = session label align, by convention). |
| D2 | Offset allocation | **Live docker introspection** (`docker compose ls` + published ports) picks a free `PORT_OFFSET` **only when direct host access is requested**; release is automatic (stack down → ports free). No registry, no GC, nothing to leak. |
| D3 | Instance-id derivation | **Branch-derived**, sanitized to `^[a-z0-9-]+$` (single DNS label, so the box's static `*.localhost` cert covers it). Deterministic → re-provision of the same branch reconciles, never duplicates. |
| D4 | SDD-flow capture | **Live-captured process doc** under `docs/maintenance/` (sits with `laptop-dev-parity.md`), written incrementally as the experiment is lived. |
| D5 | Engine language | **Python** (`scripts/worktree.py`), not bash. The logic (derivation, sanitization, offset introspection, `.env` reconcile) needs unit tests + mypy; matches the `gen_observability.py`/`seed.py` precedent and the template-payload TDD loop. `compose.sh`/`dev_summary.sh` stay bash — they are branchless `docker compose` wrappers. |

## Architecture

### Template payload (renders into generated projects)

- **`scripts/worktree.py`** — the provision/deprovision engine and **single entrypoint**. It
  **sources the durable `.env` and exports the vars itself** before invoking the dev task, so the
  A2 happy path does not depend on A1's `dotenv:` wiring (and `compose.sh` only ever sees an
  *exported* `PORT_OFFSET`, never a bare `.env` value). Orchestration (docker / task / git) is
  subprocess calls; the pure logic is independently callable for unit tests.
- **`worktree:up` / `worktree:down`** task targets → `uv run python scripts/worktree.py up|down`.
- **The durable per-worktree `.env`** — gitignored, naturally per-worktree (each worktree dir has
  its own working tree). The single source of truth for provision *and* teardown: `STACK_INSTANCE`,
  `COMPOSE_PROJECT_NAME=${STACK_INSTANCE}`, and `PORT_OFFSET` (only if `--ports`). Written/merged
  idempotently — an existing value is reconciled, not blindly appended.

### Framework-repo (not template)

- **`docs/maintenance/worktree-parallel-development.md`** — the SDD-flow process doc.

### Command behaviour

**`worktree.py up [--ports] [--obs <svc,...>]`**
0. `--obs` opt-in exposes observability UIs. The routable labeled set is **frozen** (carving
   amendment, box Finding 1): `grafana`, `prometheus`, `alertmanager` (the browsable UIs A1 labels;
   `app` is always routed). `loki`/`tempo`/exporters/`otel-collector` are **not** edge-routable (no
   UI) — `--obs` rejects them. A2 only chooses *which* of the frozen set to expose per worktree; it
   does not invent labels.
1. Derive `<inst>` from `git symbolic-ref --short HEAD`; sanitize to `^[a-z0-9-]+$`
   (lowercase, non-conforming runs → `-`, collapse repeats, trim leading/trailing `-`).
2. Form `STACK_INSTANCE=<slug>-<inst>`. **Tier-3 guard:** if the derived `<inst>` would let the
   name match B's reserved transient marker (`<slug>-t-<uuid>`), remap/refuse so A2 can never emit
   it. *(Coordination point — confirm the exact reserved token with stream B / `FWK76`; until
   confirmed, A2 conservatively reserves the `t-` prefix.)*
3. **Idempotent reconcile:** if a stack for this `STACK_INSTANCE` already exists, reattach / report
   — do not create a duplicate (the `/clear` protocol requires a fresh context to reconcile, not
   re-provision).
4. If `--ports`: pick a free `PORT_OFFSET` by live introspection.
5. Write/merge the durable `.env`; export the vars; run `task dev:edge`.

**`worktree.py down`**
1. Source the durable `.env` for `STACK_INSTANCE`.
2. `docker compose ... -p ${STACK_INSTANCE} down -v` (reclaim the named volumes — the normal
   `dev:down` keeps them by design, so the worktree path would otherwise leak 3–7 volumes) +
   edge-disconnect from the **frozen** shared network **`swiftwater-shared-edge`** (carving
   amendment, box Finding 2) — via A1's `dev:edge:down` once landed. A2 references the frozen name;
   it does not choose the network.
3. Offset auto-released (introspection — nothing to release explicitly).
4. **Ordered before `git worktree remove`** — the tool tears the stack down first; removing the
   worktree is the operator's next step (the tool may print/guard it, but does not delete the
   worktree itself unless explicitly asked).

## Seam-consumed invariants (frozen — asserted, never re-derived)

- `COMPOSE_PROJECT_NAME = ${STACK_INSTANCE}` makes the `default` network per-instance → data
  stores (`postgres`/`redis`/`mongo`) are isolated per worktree. **FWK95 asserts this directly**:
  two instances up → their store networks (and thus the `postgres` alias) are disjoint.
- Only edge-routed services join the shared edge net **`swiftwater-shared-edge`** (frozen name);
  stores stay on `default`. A2 does not attach stores to any shared network.
- Routable labeled set is frozen to `app`+`grafana`+`prometheus`+`alertmanager` (A1 adds the obs-UI
  labels). A2's `--obs` selects from this set only.
- `PORT_OFFSET` must be **exported** — guaranteed because `worktree.py` exports before exec.
- Instance string is a single `^[a-z0-9-]+$` DNS label — enforced by D3 sanitization.

## Decomposition → sub-PLANs (children of FWK74)

IDs are fresh, monotonic, never-reused (`PI-convention: v3`) — **not** dotted. A2 minted FWK92–96
from the `FWK91` high-water at fork time — but **so did A1 (92–99) and B (92–96)**: a shared-counter
collision Git cannot catch (carving learning #5). These IDs are therefore **provisional**; per the
operator's per-stream merge-discipline override, A2 **re-keys the whole block to the next free range
at Milestone M** (the rebase-to-merge), not now. The labels below stay 92–96 for the duration of the
stream's local work.

| Sub-PLAN | Scope | Stub-dep |
|---|---|---|
| **FWK92** | Instance identity — derive + sanitize + `STACK_INSTANCE`; tier-3 `t-` namespace guard. Pure, unit-tested. Records the stub-vs-wait decision point. | **stub-free** |
| **FWK93** | Durable `.env` writer + idempotent reconcile; offset selection via live introspection (mocked `docker compose ls`). Pure-ish, unit-tested. | **stub-free** |
| **FWK94** | Provision orchestration — `worktree:up` → export + `task dev:edge`. **First stub-touching SP** — the stub-vs-wait call is made here. | **stub-touching** |
| **FWK95** | Deprovision — `down -v` + edge-disconnect + offset release, ordered before `git worktree remove` + the 2-instance network-isolation conformance test. | **stub-touching** |
| **FWK96** | Worktree SDD-flow capture doc — written live across the experiment. | **independent** |

### Local merge-DAG

```
FWK92 ──▶ FWK93 ──▶ FWK94 ──▶ FWK95          (sequential: identity → .env → provision → deprovision)
FWK96  (independent — written anytime, integrates at the doc)
Milestone M: rebase onto real A1 → RE-KEY FWK92–96 to the next free range (learning #5)
             → delete dev:edge stub (if used) → re-verify → gates merge to main
```

Each sub-PLAN is **brainstorm-if-needed → TDD → commit → `/clear`**, then the next. Per the
`/clear` lifecycle rule: before `/clear`-ing, deprovision or record any running stack in the
durable `.env` so a fresh context reconciles rather than re-provisions. FWK92/FWK93 bring up no
stack (pure logic + dry-run), so no teardown is needed between them; FWK94+ may leave a stack up →
tear down or record first.

## The stub-vs-wait decision (recorded; decided at FWK94)

FWK92/FWK93 are stub-free, so the stub-vs-wait call is **deferred to FWK94**, by which point A1
may have landed. At FWK94:
- **If A1 has landed** (`fwk75-behind-edge` exposes real `task dev:edge` + `dev:edge:down`):
  rebase onto it and use it directly.
- **Else:** write a **minimal, clearly-fenced** `dev:edge` stub in A2's Taskfile (a duplicate
  Taskfile key is a *shadowed* merge, not a clean textual one — so it must be deleted on rebase),
  test A2's orchestration against it, then at **Milestone M** rebase → delete the stub →
  re-verify FWK94/FWK95. Tests assert A2's own logic, not the stub's shape, so the
  delete-and-re-verify is cheap.

This stream is stacked on A1: `git rebase fwk75-behind-edge` as it advances; **merge to `main`
only after A1 lands**.

## Testing

- **Unit (pytest in the rendered project, per the template-payload TDD loop):** instance
  derivation + sanitization (incl. the `t-` guard); `.env` write/merge + idempotent reconcile;
  offset selection against a mocked `docker compose ls`. These are the bulk and touch no
  `dev:edge`.
- **Integration (guarded, FWK94/FWK95):** `worktree:up` brings up a stack via `dev:edge`;
  `worktree:down` tears it down + reclaims volumes; the 2-instance network-isolation conformance
  test. Docker-tier, run with the sandbox disabled (`TMPDIR=/var/tmp`).
- Template payload is validated by render + acceptance; the framework's own `mypy` excludes the
  template dir, so `worktree.py` is type-checked **inside the generated project**.

## Release posture

Template-payload change → render + acceptance → **release-worthy**, like A1. A2 merges after A1;
the two are likely co-released or A2 rides the next cut. (FWK74's PLAN row omits the explicit
"ships a release" note A1's carries; this design treats it as release-worthy.)

## Open coordination points (surfaced, not deferred silently)

1. **Exact tier-3 reserved token** — ✅ **RESOLVED (pinned 2026-06-28, FWK97).** Stream B raised the
   unpinned marker as a loud finding; the operator pinned the structural form on `main`'s carving spec
   (*Tier-2 ↔ tier-3 name disjointness*): tier-3 = `<slug>-t-<uuid>`, the `<slug>-t-` **prefix** is
   reserved, and A2 **rejects any `<inst>` beginning with `t-`** (the trailing hyphen is load-bearing —
   `tango` fine, `t-foo` not, bare `t` fine). FWK97 tightened FWK92's conservative first-segment guard
   to `inst.startswith("t-")` (`RESERVED_TIER3_PREFIX`). *(My branch's carving copy stays pre-pin until
   the Milestone-M rebase, which re-verifies the code against the in-tree pinned spec.)*
2. **`dotenv:` ownership** — A1 owns wiring the Taskfile to source the durable `.env` (part of
   "make the teardown tasks resolve `${STACK_INSTANCE}`"). A2 does not depend on it for its own
   path (worktree.py exports), but bare `task dev:down` correctness is A1's. Noted, not owned here.
