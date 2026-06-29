# Second worktree-parallel experiment — carving + seam contract

> **Date:** 2026-06-29 · **Status:** FROZEN — two-panel-hardened, operator-approved ·
> **Author:** Chris (with Claude)
> The carving for the framework's second git-worktree parallel run. The hand-off artifact each
> worktree reads. It was drafted at three streams, run through a **six-lens adversarial panel**,
> **recut to two**, then run through a **second four-lens panel** that caught the recut as an
> over-correction — landing at **three honest, file-disjoint streams**. Both panels + the
> exclusion-reasoning corrections that drove the final shape are recorded in §"Learnings" and
> §"Panel record" so the next carving doesn't repeat them. Companion: experiment-1's carving,
> `docs/superpowers/specs/2026-06-28-worktree-parallel-experiment-carving-design.md`.

## Purpose & success

Second worktree experiment. Honest scope after two panels: **ship real reviewer + test-infra debt
in parallel** and **re-exercise the worktree workflow** a second time. It does **not** test a new
"shared-state seam class" — panel 1 proved the coupling the first draft invented (between reviewer
sub-streams) does not exist in the code. We declined to *manufacture* a dependency just to have one
to test. What experiment-2 genuinely exercises: three independent streams, the per-worktree
brainstorm→TDD→`/clear` discipline, merge-time renumber, one real within-stream shared resource (the
eval backend), and a **fractal seam-review** (one stream runs its own layer-2 panel on a safety
sub-seam — §"S1 · FWK116").

The streams follow the **coupling**, not a tidy symmetry: the reviewer debt splits where the files
split (`FWK45` ⊥ the audit module); the test-infra debt is genuinely independent; and the one
contract-adjacent item (`FWK116`) is **completion** of experiment-1's instance-isolation, not a
contract change (see §"S1 · FWK116").

## The three streams

| Stream | Rows (serial within) | Load-bearing deliverable (code) | Notes |
|---|---|---|---|
| **S1** | `FWK45` · `FWK116` · `FWK107` | reviewer fixtures/prompts (`FWK45`); tier-3 per-worktree namespace `<slug>-<inst>-t-<uuid>` + finish-sweep (`FWK116`); behind-edge conformance consolidation + `DEC-0006` disposal (`FWK107`) | `FWK45` is the **sole live-eval consumer** → eval-backend hygiene holds within-S1 by construction. `FWK116` runs an **internal layer-2 panel** (§below). Paired here to absorb `FWK45`'s eval-latency idle time. |
| **S2** | `FWK46` → `FWK47` → `FWK48` | harden the unparseable-skeptic retry (`FWK46`, `audit/stages.py::refute`); `--resume` provenance guard (`FWK47`); consumer-side audit oracle against a render (`FWK48`) | The **audit pipeline end-to-end**. `FWK46/47` are unit-tested, no live backend. `FWK48` sits at the tail because it leans on the hardened pipeline; it brainstorms its own scope (framework-repo-vs-consumer-tooling) inside the worktree. |
| **S3** | `FWK70` → `FWK90` | render-helper `restore` version-skew fix (`FWK70`); per-mutation test-impact selection (`FWK90`) | `FWK70` first (trivial), so `FWK90` builds on a known-good helper. |

**Dropped (not a stream):** `FWK98` (shared-container xdist for the *generated* suite) — a **no-op
now**: `FWK97` already measured the generated suite stays serial; records-only until a real consumer
suite grows. Ship via `FWK97`'s path when a consumer pulls.

There is **no held-out set this time.** Everything previously held out was re-examined and brought in
or correctly placed (see §"Learnings #3"): `FWK90` (the "needs a brainstorm" tag is not exclusion
grounds — worktrees brainstorm internally); `FWK48` (a soft dependency is a *placement* signal → S2's
tail, not exclusion); `FWK116`/`FWK107` (the "frozen FWK88 contract" reason was transient-freeze
inertia, and `FWK116` is contract *completion*, not change).

## Cross-stream surface — file-disjoint except one named file

The three streams are file-disjoint with **one** named cross-stream shared file, flagged loud per the
methodology (a shared file is a merge-time concern, not a runtime hazard — experiment-1 Learning #5):

- **`tests/acceptance/conftest.py`** — `FWK116` (S1) edits the tier-3 sweep hooks (`_should_sweep`,
  sessionstart/finish); `FWK90` (S3) may touch the same file for test selection. **Rule:** coordinate
  the tier-3 hooks at merge; Git resolves the textual overlap. (Placing `FWK116` in S1 introduced this
  point; S3-placement would have kept it intramural to S3 — accepted for the wall-clock balance.)

Everything else is disjoint: S1's `FWK45` writes `review/agents/*.md` + `tests/eval/fixtures/**`; S2
writes `review/audit/**`; S3's `FWK70` writes `tests/acceptance/test_rendered_project.py`. No
cross-stream merge-order dependency.

## The one real shared resource — the eval backend (within-S1 hygiene)

The single genuine shared resource (panel 1, Lens 6) is the **live eval backend / Anthropic account
rate-limit**: `framework eval` drives a live `messages.create` / `claude -p` per fixture per repeat,
and `FWK45` is "eval-gated each" (~9+ full evals). Because **`FWK45` is the only live-eval consumer in
the whole experiment** (S2 is unit-tested; S3 hits no live backend — `test_evals.py` is realization,
not live scoring), this is a **within-S1 hygiene rule, not a cross-stream seam**:

1. **Exhaustion ≠ verdict.** A `BackendExhausted` / exit-4 / truncated-`repeat` eval is **INVALID**,
   never a gate result — it is indistinguishable in CI from a threshold FAILURE
   ([[framework-eval-no-builtin-resume]]). Capture eval's **own** `$?` (not `tee`'s,
   [[registering-review-agent-gate-completeness]]) and re-run.
2. S1 runs its evals serially (one worktree). No other stream evals, so there is **no** concurrent-eval
   contention against the shared account by construction.

## Provenance freeze (the reviewer invariant)

Inside this experiment, **no one re-runs `reviewer-audit`-then-applies.** `FWK45` hand-authors the
deferred fixture/prompt edits from the **existing, frozen** `.framework/reviewer-audit-v2/changelist-full.json`
(2026-06-19; verified on disk, 49 KB) and eval-gates each hunk via `score_agent` — a refute-independent
signal. A *fresh* `reviewer-audit` run (now that `FWK46`/S2 changes which proposed edits survive
`refute`) would vet a **different** edit set; that is the only path by which S2 could reach S1's work,
and the freeze severs it. `FWK46` is validated by its own `tests/review/audit/*` unit tests
(injectable `StubBackend`), not by re-deriving the changelist.

**Post-experiment (clarifier — panel B):** the freeze binds only for this run. After `FWK46` merges,
the next `reviewer-audit` re-baselines under the new `refute` (the `env-parity` edit dropped on 2/3
parse-fails then becomes a fresh proposal), so the frozen changelist is **not** a standing source of
truth post-merge — it is this experiment's input, not a permanent canon.

## S1 · FWK116 — contract completion + a fractal layer-2 panel

`FWK116` is **not** a change to the frozen `FWK88` contract — it **completes** it. `FWK88`'s master
principle is "`STACK_INSTANCE` drives per-instance isolation, uniformly"; tiers 1–2 honor it, but
tier-3 was pinned `<slug>-t-<uuid>` **without** the `<inst>` component — an artifact of experiment-1's
narrower scope (tier-3 then meant xdist workers within *one* session, so the cross-session case wasn't
in view). `FWK116` brings tier-3 (`<slug>-<inst>-t-<uuid>`) into line with the principle the rest of
the contract already embodies. No external consumer reads the tier-3 name (it is never edge-routed —
`FWK88` forbids tier-3 on the shared network — and Meridian regenerates the harness on adoption), so it
is an **in-repo** change with no cross-repo break. Doing it now, **before** Meridian adopts v0.4.4, is
strictly safer than shipping a half-isolated tier-3 and changing it under adopters — and it removes the
cross-session tier-3 clobbering that concurrent worktree runs themselves risk.

The one genuine care: tier-2↔tier-3 disjointness is a **safety property** (a `COMPOSE_PROJECT_NAME`
collision destroys shared volumes), and `FWK74`'s `t-`-prefix ban is coupled. So `FWK116`'s sub-PLAN
**runs its own layer-2 adversarial panel** on the new namespace scheme (verify disjointness across the
tier-2/tier-3 forms; confirm `FWK74`'s ban is updated in lockstep) before implementing — the carving
pattern applied fractally, one level down. The safety verification lives inside the worktree, not as a
gate on the whole experiment.

## Top-level merge-order DAG

```
S1 (FWK45 · FWK116 · FWK107) ─┐
S2 (FWK46 → FWK47 → FWK48)     ├─ file-disjoint; no cross-stream merge-order dep
S3 (FWK70 → FWK90) ───────────┘   (one shared file: tests/acceptance/conftest.py, S1↔S3 — merge-time)
DROPPED: FWK98 (no-op)
```

No cross-stream dependency. Each stream merges as an atomic renumbered subtree per the inherited
protocol. There is no merge-node re-eval mandate — there is no cross-stream eval signal to revalidate;
S1's own eval-gating happens *within* S1 before it merges.

## Per-worktree protocol

Unchanged — reuse the **fractal per-worktree protocol** verbatim from experiment-1
(`2026-06-28-…-carving-design.md` §"Per-worktree protocol"): treat the carving as fixed (a wrong cut is
a **loud finding**); decompose into individually-committable sub-PLAN rows; **brainstorm→spec-if-needed
→TDD→commit inside the worktree**, `/clear` between; **reconcile numbering only at merge, in merge
order** (the shared PLAN.md/ACTION_LOG monotonic counter is governed by this rule).

## A-priori & binding

The carving is fixed before either worktree brainstorms. What experiment-2 tests (honestly, post-panel):
the worktree workflow on **three genuinely independent streams** — provisioning, `/clear` discipline,
merge-time renumber, the eval-backend hygiene rule, and a fractal layer-2 panel — without a manufactured
cross-stream seam.

## Learnings (live)

The carving's second product (codify the workflow) starts here.

1. **A file-disjoint split is not a shared-state seam.** The first draft reached three streams by
   *inventing* a coupling (reviewer sub-stream B moves sub-stream A's eval signal) to justify the cut.
   Panel 1 refuted it from the code in two independent lenses: `evals.py` (the gate) and
   `audit/stages.py` (the refute) share vocabulary ("vote/survive/finding") but **no data flow**.
   **Generalization:** when a carving's claimed seam is *signal/state* (not spatial), verify the data
   flow in code **before** freezing. A seam you have to argue for is often one that isn't there.
2. **"No seam" means *more* parallelizable, not "serialize."** The recut over-corrected — it collapsed
   the file-disjoint reviewer debt into one serial stream, citing a shared test suite (contradicting
   experiment-1 Learning #5) and the eval backend (which only one row consumes). Panel 2 caught it.
   **Generalization:** absence of a coupling is a reason to run things in parallel; serialize **only**
   where there is real file-overlap (here: `FWK46`/`FWK47`/`FWK48` on the audit module).
3. **The held-out set kept collapsing under three bad exclusion heuristics. Name them so they don't
   recur:**
   - *"Needs a brainstorm"* → **invalid.** Worktrees brainstorm internally (the per-worktree protocol
     is brainstorm→spec→TDD). It excluded `FWK90` and contaminated `FWK48`.
   - *"Touches the frozen contract"* → **transient-freeze inertia.** Experiment-1's a-priori freeze was
     a methodological device that **expired** on merge. Distinguish it from the *durable* constraints
     (published external consumers; load-bearing safety invariants). And a "contract change" may be
     contract **completion** — `FWK116` finishes `FWK88`'s own instance-isolation principle for the one
     tier left short. (Operator: "we often give too much weight to decisions made transiently.")
   - *A soft dependency* → a **placement** signal, not exclusion. `FWK48`'s "best after FWK46/47" puts
     it at S2's tail, not in a deferral bucket.
4. **Carvings can need more than one adversarial pass, and panels nest.** Two passes were required: the
   first found the phantom seam + rebalanced; the second, run on the *recut*, caught the
   over-correction. And the freeze is fractal — `FWK116`'s worktree runs its **own** layer-2 panel on
   its safety sub-seam. One pass is not always enough; the cost of a second pass is far below the cost
   of forking on a bad cut. Reinforces `FWK91`.
5. **Isolate the shared resource into one stream and the cross-stream invariant dissolves.** The eval
   backend was the one real shared resource (panel 1, Lens 6 — the analog of experiment-1's shared
   Docker network). Making `FWK45` the sole eval consumer turned a would-be cross-stream contract into
   a within-S1 hygiene rule that holds by construction.

## Panel record

**Pass 1 — six lenses on the three-stream draft:**

| Lens | Verdict | Outcome |
|---|---|---|
| 1 — third-stream-real | SPLIT-IS-COSMETIC | (→ recut to 2, later revised) |
| 2 — eval-gate coupling | CONTRACT-INSUFFICIENT (phantom) | delete threshold-ownership; provenance-freeze |
| 3 — volume balance | LOPSIDED-OTHER | FWK48 re-placed; FWK98 dropped |
| 4 — held-out completeness | HELD-OUT-SET-COMPLETE (then revised) | confirmed FWK90/98 don't brush FWK88 |
| 5 — FWK48 placement | FWK48-MISPLACED (then re-placed to S2 tail) | — |
| 6 — cross-cutting state | UNNAMED-SURFACE-FOUND | eval-backend hygiene invariant |

**Pass 2 — four lenses on the recut-to-two:**

| Lens | Verdict | Outcome |
|---|---|---|
| A — over-correction | OVER-CORRECTED→THREE | split the reviewer debt; restore three on honest grounds |
| B — provenance-freeze | FREEZE-COHERENT | +post-merge re-baseline clarifier |
| C — T independence | T-INDEPENDENT | confirmed; FWK90 not eval-coupled |
| D — recut fidelity | INCONSISTENCIES-FOUND | (moot — wholesale rewrite to three) |

**Post-panel operator corrections** (the exclusion-reasoning fixes in Learning #3) reshaped the
"two" into the final **three**: FWK90 in, FWK48→S2 tail, FWK116(+FWK107) in (completion, pre-adoption),
FWK116 paired into S1 for eval-latency balance.

## PLAN mapping emitted by this carving

- **S1** → `FWK45`, `FWK116`, `FWK107` · **S2** → `FWK46`, `FWK47`, `FWK48` · **S3** → `FWK70`, `FWK90`
- Dropped (no-op): `FWK98`
- `FWK116` updates `FWK74`'s `t-`-prefix ban in lockstep; runs an internal layer-2 panel.
- New process-row candidate: an experiment-2 record + Learning #3 (the three bad exclusion heuristics)
  as a candidate promotion into the adversarial-panel / decomposition guidance (`FWK91`/`FWK57`).
