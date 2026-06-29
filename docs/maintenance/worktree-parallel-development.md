# Worktree-parallel development — the SDD workflow

How to run several backlog items in parallel, each in its own git worktree, under the
subagent-driven-development (SDD) flow. This is the **process playbook** — the sequence, the real
commands, the decisions, and the gotchas — distilled live while running the framework's *first*
worktree-parallel experiment (three streams: A1 `fwk75-behind-edge`, A2 `fwk74-provisioning`,
B `fwk89-test-speed`).

It is a worked instance of **FWK57** (decomposition precedes parallelism; the binding constraint is
interface/decision *stability*, not serial build-order). The *what* of that experiment — the streams,
the frozen seam contract (`FWK88`), the tiers, the network invariants — lives in the carving spec and
is **not duplicated here**:

> **Carving spec (the binding seam):**
> `docs/superpowers/specs/2026-06-28-worktree-parallel-experiment-carving-design.md`

Read the carving spec for the contract; read this for how you *run* against it.

## Honest status of this playbook (read first)

This doc was written live, so it reports three different kinds of step honestly — don't read the
whole arc as "done":

- **Lived and verified** (this is the bulk): carving + the adversarial panel; forking the worktrees;
  the per-worktree fractal loop (decompose → sub-PLAN → TDD → commit → `/clear`); rebasing a stream
  onto an updated carving; the **stub-vs-wait decision** (→ WAIT, made at both `FWK94` and `FWK95`).
- **Built but not yet exercised against a live stack:** `task worktree:up` / `worktree:down`. Across
  A2's whole build (`FWK92`–`FWK95`) **no stack was ever brought up** — A1 had not yet shipped
  `task dev:edge`, so the orchestration was tested through an *injected runner*, and the `/clear`
  teardown protocol always resolved to "no teardown owed." The commands in §5 are what you *will* run;
  their first live run against a real edge is a **Milestone-M** item (§7).
- **Designed but pending:** Milestone M itself — rebase onto the real parent, delete any stub,
  re-verify, **re-key the FWK IDs**, merge. Written below as the protocol ahead, because at the time
  of writing A1 is still mid-flight.

## 0. When to reach for this

Use a worktree-parallel run when you have **2–4 genuinely independent backlog items** whose interfaces
can be frozen *before* anyone starts designing. "Independent" is the hard part — see FWK57. If the
items share a moving interface, you don't have parallel streams; you have one serial stream wearing a
disguise. Start slow: the first experiment was **exactly three** streams.

Host prerequisites are the normal framework dev set (`task doctor` → 10/10; see `CLAUDE.md` "Operating
environment"). The docker/acceptance tier needs `TMPDIR=/var/tmp` and the sandbox disabled.

## 1. Carve before you fork (a-priori, binding)

Write the **carving** — one document that fixes the streams, the **frozen seam contract**, and the
**merge-order DAG** — *before any worktree forks*. The seam is cut a-priori and is **binding**: a
worktree that finds the seam wrong raises a **loud finding** (record + surface), it does not quietly
adapt. (The capability under test: can independent streams build to an interface frozen before any of
them designed anything?)

**Run an adversarial panel over the seam before freezing it.** In this experiment the seam leaked a
shared-resource collision class on *nearly every* review pass (multi-product port budget · edge
discovery · mkcert hostname coverage · `COMPOSE_PROJECT_NAME` · the edge↔instance network) — all found
one-at-a-time, reactively. A panel of distinct collision-class lenses (resource-collision ·
lifecycle/teardown · isolation · cross-repo/box-boundary · scaling) run in one pass at the freeze
point catches them together. This is `FWK91`, and the carving spec's *Learnings* section records the
specific blockers it caught (including one the operator and assistant had jointly agreed to defer one
message earlier). A corollary: **a seam review must reach every repo the seam touches** — here the seam
crossed into a non-git sibling repo (`local-reverse-proxy`) no panelist had read, which became the
experiment's fourth, cross-repo consumer.

## 2. Fork the worktrees

All streams branch from the **same carving commit** on `main`. Worktrees live as siblings under
`$DEV_ROOT/swiftwater-framework/` (one dir per stream, named for its branch):

```bash
cd "$DEV_ROOT/swiftwater-framework/main"
git worktree add "$DEV_ROOT/swiftwater-framework/fwk75-behind-edge"  -b fwk75-behind-edge
git worktree add "$DEV_ROOT/swiftwater-framework/fwk74-provisioning" -b fwk74-provisioning
git worktree add "$DEV_ROOT/swiftwater-framework/fwk89-test-speed"   -b fwk89-test-speed
git worktree list      # confirm the three + main
```

Each worktree is a full, isolated working tree sharing one `.git` — independent checkouts, no stashing
between streams. Open one Claude Code session **per worktree** (`cd` into the worktree dir).

> **Gotcha — the shared-counter collision Git cannot catch (carving learning #5; the crown jewel).**
> All three streams branched at the same high-water PLAN id (`FWK91`) and *independently* minted their
> sub-PLAN ids starting at `FWK92`. A1 took 92–99; A2 and B **both** took 92–96. Unlike a textual edit,
> non-adjacent row inserts three-way-merge **clean** → silent triplicate IDs (and even an adjacent
> conflict "resolves" by keeping both same-id rows). This is the documented exception to *"shared files
> always conflict, that's what Git's for"*: id allocation from a shared counter isn't textual, so Git is
> blind to it. The standing fix is **not** an a-priori id partition — it's a **per-stream
> merge-discipline override: re-key your whole sub-PLAN block to the next free range when you rebase to
> merge** (§7). Record the re-key step in your stream's own merge-DAG so a fresh context can't forget it.

## 3. The per-worktree fractal protocol

Each worktree applies the carving *fractally*. On entry it takes its parent PLAN row + the carving
spec and:

1. **Treats the seam contract as fixed** — no mid-stream renegotiation; a wrong cut is a loud finding.
2. **Finds its work package's internal seams** (brainstorm — `superpowers:brainstorming`).
3. **Decomposes into smaller, individually-committable PLAN rows** (fresh monotonic `FWK` ids per
   `PI-convention: v3` — **never dotted**; an early `FWK74.1` attempt was operator-corrected). Each
   sub-PLAN is sized to be committed then `/clear`-ed before the next. Record a local merge-DAG.
4. **Executes one sub-PLAN at a time:** brainstorm → spec/plan if needed (`superpowers:writing-plans`)
   → **TDD** (`superpowers:test-driven-development`; red → minimal green) → per-task review → commit →
   whole-sub-PLAN review → tick PLAN → `/clear`. Then the next.
5. **Respects the top-level merge-deps** when integrating back to `main` (§7).

**Review-model policy holds inside worktrees** ([[subagent-review-model-pattern]]): implementers →
Sonnet (Haiku for trivial); code-quality + whole-sub-PLAN reviews → **Opus**. The subagent implementer
stages but does **not** run the final commit — the controller verifies and commits
([[subagent-implementers-stop-before-commit]]).

A worked example of the loop (A2's `FWK92`–`FWK95`, the **provisional** ids — re-keyed to
`FWK108`–`FWK113` at Milestone M, the very learning #5 below): each sub-PLAN was a plan doc under
`docs/superpowers/plans/`, 2–4 TDD tasks appending to one `scripts/worktree.py`, framework-venv
importlib tests (the `tests/test_check_migrations.py` precedent — pure logic needs no render), then an
Opus whole-sub-PLAN review on the combined diff before ticking. The full per-task narrative is in
`ACTION_LOG.md` (#0340–#0363; the re-key mapping is #0364).

> **The `/clear`-between-sub-PLANs lifecycle rule.** The operator runs `/clear` between FWK ids to keep
> each context tight. **Before `/clear`-ing, deprovision or record any running stack** (the durable
> per-worktree `.env` is the record) so the fresh context *reconciles* an existing stack rather than
> re-provisioning a duplicate. In this experiment every sub-PLAN was pure logic or used an injected
> runner, so each `/clear` resolved to "no stack brought up → no teardown owed" — but the discipline is
> the point, and §5's `worktree:down` is what you run when a stack *is* up.

> **Commit-gate.** A `PreToolUse` hook blocks `git commit` until `PLAN.md` or `ACTION_LOG.md` is
> staged. Stage them in the same commit. `git add` and `git commit` must be **separate** tool calls
> (chaining trips the hook before the add lands; [[commit-gate-hook-timing]]).

## 4. Stub-vs-wait (when your parent hasn't landed)

A *stacked* stream (A2 depends on A1's `task dev:edge`) hits a fork the moment it needs the parent's
not-yet-shipped capability: **stub it, or wait?**

- **Stub** = write a minimal, clearly-fenced fake of the parent's interface so you can test against it,
  then delete it on rebase. A duplicate Taskfile target is a *shadowed* key, not a clean textual merge
  — so a stub **must** be deleted at Milestone M.
- **Wait** = don't fake the interface; test your own logic through an **injected runner** (dependency
  injection — pass `run=subprocess.run` as a seam, inject a fake in tests), and defer the live
  integration to Milestone M.

**In this experiment the call was WAIT, both times** (`FWK94` and `FWK95`, each via the advisor with
full session context). Reasoning: a stub of `task dev:edge` validated nothing the injected runner
didn't, *and* a real `worktree:up` also needs A1's compose plumbing → the live integration test is
inherently a Milestone-M item regardless. So A2 built the orchestration tested entirely through the
injected runner, with **no stub to delete** — cheaper than stub-then-rebase-then-delete. State your
choice explicitly in the stream before it forks; record it in the sub-PLAN.

> **Heuristic:** prefer WAIT + injected-runner tests over a stub whenever the live path needs *more*
> of the parent than the stub would fake (then the stub is busywork). Reach for a stub only when it
> genuinely unblocks testable behavior the injection seam can't reach.

## 5. Provision / deprovision a worktree's stack

The tool A2 built (`scripts/worktree.py`, exposed as Taskfile targets). It assigns the worktree's
instance identity from its branch, writes a durable per-worktree `.env`, and brings the stack up behind
the shared box edge — and tears it down symmetrically.

```bash
# bring this worktree's isolated stack up behind the shared edge (edge-only, no host ports):
task worktree:up

# also want direct host access + selected obs UIs? (flags go to the script directly — the
# Taskfile target takes no pass-through args yet; that ergonomic is a Milestone-M item):
uv run python scripts/worktree.py up --ports --obs grafana,prometheus

# tear the stack down + reclaim its named volumes, BEFORE `git worktree remove`:
task worktree:down
git worktree remove "$DEV_ROOT/swiftwater-framework/<this-worktree>"
```

What it does, against the frozen `FWK88` seam (details in the carving spec — *not* re-derived here):

- **Identity:** `<inst>` is derived from the worktree's branch and sanitized to a single
  `^[a-z0-9-]+$` DNS label (so the box's static `*.localhost` cert covers it); `STACK_INSTANCE =
  <slug>-<inst>` drives `COMPOSE_PROJECT_NAME` (→ per-instance containers/volumes/default network) and
  the discovery labels. Deterministic → re-running `up` on the same branch **reconciles**, never
  duplicates.
- **`--ports`** picks a free `PORT_OFFSET` by live docker introspection (optional — only when you want
  direct host access; edge routing needs no host ports). `down` clears it so a later `up` re-picks
  fresh rather than reusing a stale offset another worktree may have grabbed.
- **`down`** issues `docker compose -p <inst> down -v` — the `-v` reclaims the named volumes that the
  ordinary `task dev:down` keeps by design (so the worktree path doesn't leak 3–7 volumes per stack).

> **Not yet run against a live edge.** As of this first pass, A1 had not shipped `task dev:edge`, so
> `worktree:up`'s edge attach + the `down` edge-disconnect are Milestone-M deferrals — the script issues
> the A2-owned half (`down -v`, offset release) but leaves the edge wiring to A1's targets once landed.
> The first end-to-end live run (worktree stack → box edge → browser) is the experiment's integration
> proof at the contract, executed at Milestone M.

> **Network isolation is the master control (frozen, carving B1).** Only edge-routed services join the
> shared edge net **`swiftwater-shared-edge`**; **data stores stay on the per-project `default` net** —
> else worktree A's app reaches B's Postgres and the `postgres` alias resolves ambiguously. A
> render-time conformance guard (`test_data_stores_never_on_shared_edge_net`) asserts this; it is armed
> today and becomes load-bearing at the M rebase.

## 6. Rebase as the parent / carving advances

A stacked or carving-dependent stream **rebases forward** rather than drifting:

```bash
cd "$DEV_ROOT/swiftwater-framework/fwk74-provisioning"
git fetch && git rebase <parent-or-carving-tip>     # e.g. the updated carving commit, then real A1
```

This happened live: the operator updated the carving on `main` (`e2ad99c`, PR #92, freezing two
box-consumer findings); A2 rebased its two commits onto it. **The only conflict was `ACTION_LOG.md`**
(both sides appended after the same entry) — resolved by keeping main's entry and **re-keeping the
local entries to the next free numbers**; PLAN auto-merged clean (the exact silent-clean-merge that
learning #5 warns about). When you rebase, **scope your id fix-ups** — touch only your own ranges,
never rewrite main's historical ranges.

## 7. Milestone M — re-key, then merge

Each stream merges to `main` per the **top-level merge-DAG** (binding merge-deps; e.g. A1 before A2;
B is independent on the code axis but shares the `COMPOSE_PROJECT_NAME` namespace, governed by the
frozen tier-2↔tier-3 name-disjointness rule). At the rebase-to-merge ("Milestone M"):

1. **Rebase onto the real parent** (A2 onto the landed A1).
2. **Delete any stub** you wrote in §4 (if you chose WAIT, there's nothing to delete — the payoff).
3. **Re-verify** the sub-PLANs that touched the seam against the now-real interface (run the deferred
   live integration tests — e.g. the first real `worktree:up`/`down` against `task dev:edge`, the
   2-instance network-isolation conformance).
4. **RE-KEY the whole sub-PLAN id block** to the next free range read from the *then-current* `main`
   PLAN (learning #5). Rename the PLAN rows, the spec/plan docs, and the `_memory`/doc cross-refs;
   **commit-message ids stay as historical**. This is the per-stream merge-discipline override, a
   limited-lifetime patch the standing protocol didn't contemplate (root-cured later by a PLAN-id
   service).
5. **Merge** (protected `main` → PR; required checks `gate` + `build` + `render-complete`;
   [[master-branch-protection-ruleset]]). Template-payload changes ship a release; docs-only do not.

## Learnings (the transferable payload)

The carving spec's *Learnings (live)* section is the record of record (learnings #1–#5). The three that
shape **how you run** a worktree experiment, surfaced here so they aren't buried:

1. **The shared monotonic counter is the collision class Git can't catch** (learning #5; §2 + §7). Plan
   for the re-key at merge from the start; it is invisible until it bites.
2. **The `/clear` lifecycle rule** (§3): tear down or record running stacks before clearing context, so
   the next context reconciles instead of re-provisioning.
3. **Stub-vs-wait is a decision, not a default** (§4): prefer WAIT + injected-runner tests when the
   live path needs more of the parent than a stub would fake.

And two about the seam itself, for the *next* carving: **run an adversarial panel before freezing**
(`FWK91`; §1), and **make that panel reach every repo the seam touches** — the load-bearing assumption
may live in a repo no reviewer has read.

### Second experiment (2026-06-29) — execution-validated additions

The full record is the second carving spec
(`docs/superpowers/specs/2026-06-29-second-worktree-parallel-experiment-carving-design.md`, §Learnings +
§Panel record). What running it end-to-end (three streams → PRs #103/#104/#105) *added*:

4. **Milestone M is lived, not just designed.** The re-key-then-merge protocol (§7) ran across three
   merges: each later stream **self-reconciled** its FWK IDs + ACTION_LOG numbers above the running
   high-water mark (ids 118→131, log #0375→#0397) with zero collisions. Learning #1's "plan for the
   re-key" resolves to: streams do it themselves, at merge, in merge order.
5. **A carving can need more than one adversarial pass.** The draft's first panel killed a *phantom*
   seam (an invented signal-coupling with no data flow in the code) and recut three streams to two; a
   **second** panel caught that recut as an *over-correction* (file-disjoint work needlessly serialized)
   and restored three. One pass is not always enough — and "no coupling" means **more** parallelizable,
   never "serialize."
6. **Three exclusion heuristics that look principled but aren't.** Don't hold a row out of a parallel run
   for: *"needs a brainstorm"* (worktrees brainstorm internally), *"touches a frozen contract"* (the
   freeze may be transient/expired, or the change is contract *completion*), or *a soft dependency*
   (that's a placement signal → the depended-on stream's tail, e.g. `FWK48` at S2's tail).
7. **The panel is fractal.** A stream touching a safety-critical or contract surface runs its *own*
   layer-2 panel before changing it. `FWK116`'s caught **3 real holes and rejected the author's first
   namespace scheme** — the carving-panel value, one level down. Not ceremony.
8. **Kill debt in-stream.** A big row decomposes into top-level sub-rows that **all land in the stream**
   (`FWK48`→118-120, `FWK116`→128/129); deferring the hard halves to future rows perpetuates the debt
   the experiment exists to kill.
9. **Per-stream branch-end adversarial review earns its keep at integration.** A focused review of each
   completed stream caught a real provenance gap in S2 (closed in-stream as `FWK121/122`) and confirmed
   S1's contract-completion was disjoint-by-construction — *before* merge, not after.
