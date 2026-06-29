# Stream B (FWK89) — test inner-loop speed: decomposition + internal merge-DAG

> **Date:** 2026-06-28 · **Status:** approved (brainstorm) · **Stream:** B (independent) of the first
> worktree-parallel experiment · **Parent carving (binding):**
> `docs/superpowers/specs/2026-06-28-worktree-parallel-experiment-carving-design.md`
>
> This is the per-worktree decomposition for stream **B** — the *whole* of test parallelization
> (`FWK89` over `FWK76` parallelize + `FWK77` tier). It applies the carving's per-worktree protocol
> fractally: internal seams → individually-committable sub-PLANs → a local merge-DAG, `/clear`-ing
> between sub-PLANs. It **consumes only** the frozen `FWK88` **tier-3** contract; it does not
> renegotiate the seam. A wrong cut is a loud finding, not a quiet adaptation.

## Purpose & success

Cut the test inner-loop **wall-clock** (the operator's stated goal — duration, not cost). The framework
`gate` runs `pytest` single-process; the long pole is `tests/test_copier_runner.py` (~11–12 min of the
gate). Success = the same coverage at materially lower wall-clock, locally and in CI, with **no silent
coverage gap** introduced by any tiering.

## The cost structure (measured, this branch)

- `test_copier_runner.py` makes **283 `render_project()` calls** across 273 test functions.
- **100** are the byte-identical base render (`render_project(dest, DATA)`); the other 177 collapse into
  **~15–20 distinct battery combos** (`workers`, `webhooks`, `react`, `redis`, `websockets`, pairs).
  → **283 renders ≈ 20 distinct inputs rendered redundantly.** High commonality, not 283 bespoke fixtures.
- ~17 other test modules also call `render_project`.
- The docker/**acceptance** tier already has per-test isolation: `tests/acceptance/test_rendered_project.py`
  `_isolate_compose_project` → unique `COMPOSE_PROJECT_NAME=swfwacc-<test>` + FWK31 **ephemeral host ports**
  (port `0`). The `gate` CI job already runs `pytest --ignore=tests/acceptance` (`ci.yml`).
- `xdist` is **not** installed; there is **no** `tests/conftest.py`.
- Prior art for caching exists and is race-hardened: `src/framework_cli/review/evals.py`
  `prerender_base` / `realize_cached` / `_freeze_git_base` — a battery-combo-keyed rendered base with the
  `realize_cached` copytree-vs-git-GC race already solved ([[flaky-realize_cached-copytree-git-gc-race]]),
  plus a documented *serial-warm-then-concurrent-read* discipline.

## Two wall-clock levers (stacked, complementary)

1. **Parallelism — `pytest-xdist -n auto`.** Shards the suite across the box's cores. Headline duration
   win. *Parallelizes* the redundant rendering; does not remove it.
2. **Elimination — answer-set-keyed render cache.** Render each distinct input **once**; read-only callers
   use it directly, mutating callers copytree a cheap copy. *Removes* ~14× redundant render work,
   independent of cores. Generalizes the existing `realize_cached` pattern.

They stack: under xdist the cache is **per-worker** (each worker process renders its own ~20 bases, not
283) — never a shared on-disk cache across workers (that would recreate the `realize_cached` race at
process granularity).

## Sub-PLANs (committable units; `/clear` between each)

| Sub | ID | Parent | One-line scope |
|---|---|---|---|
| **B1** | `FWK93` | `FWK76` | Enable `pytest-xdist -n auto` + fix the real parallel-safety hazards it exposes |
| **B2** | `FWK94` | `FWK76` | Generalize the `realize_cached` render-cache to the broad render-callers (per-worker) |
| **B3** | `FWK95` | `FWK76` | Tier-3 transient-instance contract: guaranteed reaping + reserved namespace + no-edge-net/no-socket guard |
| **B4** | `FWK96` | `FWK77` | Fast (per-commit) vs full (per-merge) test tiers + prove-no-coverage-gap |
| **B5** | `FWK97` | `FWK89` | Mirror the proven xdist + tiering speedups into the generated template's own suite |

### Internal merge-DAG (binding within B)

```
B1 (FWK93, xdist) ──▶ B2 (FWK94, cache) ──▶ B4 (FWK96, tiering) ──▶ B5 (FWK97, template mirror)
B3 (FWK95, tier-3 contract) ── independent — lands in any order
```

**Sequencing rationale (operator-confirmed):** xdist-first. It is the headline wall-clock win, and turning
`-n auto` on *empirically exposes* the real hazards (a `-n auto` failure is the TDD red) rather than
auditing for phantom ones. The cache (B2) is then born xdist-aware (per-worker by construction). B4's fast
tier is *defined* by the xdist split, so it follows B2. B5 lands at the tail once the levers are proven on
the framework's own suite — a template change ships in the release FWK75/74 are already cutting.

### B1 — `FWK93` — xdist + parallel-safety (child of FWK76)

Add `pytest-xdist` (dev dep), enable `-n auto`, wire into the `gate` job. **TDD = empirical:** run
`-n auto`, fix what actually breaks, keep it green. Known hazard surface to verify/fix:

- `tests/acceptance/conftest.py` `disk_tmp` keys on **bare `request.node.name`** (not the full nodeid) →
  two same-named tests in different modules collide under `-n auto`. (Acceptance is excluded from the gate,
  but the full tier still runs it — fix or prove no collision.)
- The **5 module-scoped fixtures** (`scope="module"`/`session`) that may write fixed shared paths
  (`test_obs_completeness.py`, `integrity/test_coverage.py` ×2, `runtime_coverage/test_{completeness,enumerate}.py`).
- Per-worker `basetemp` — pytest-xdist isolates this by default; **verify**, don't assume.
- Re-verify the `realize_cached` GC-race fix holds under *process-level* concurrent base build/read
  (the FWK33 fix covered a single writer; xdist is a different concurrency).

**Done:** `pytest -n auto` green; gate uses it; a measured wall-clock before/after recorded in ACTION_LOG.

### B2 — `FWK94` — render-cache generalization (child of FWK76)

Lift the `prerender_base`/`realize_cached`/`_freeze_git_base` pattern out of `review/evals.py` into a
shared test helper (likely a `tests/conftest.py` session fixture keyed on a frozen answer-set). Read-only
render-callers consume the cached base directly; mutating callers (integrity tamper/restore, anything that
edits the rendered tree) copytree a cheap copy. **Per-worker** cache dir — no cross-worker on-disk sharing.

**xdist distribution mode matters for the hit rate:** the default `--dist load` scatters same-combo tests
across workers, fragmenting the per-worker cache (the 100 base-`DATA` tests spread over N workers → N base
renders, not 1). Use `--dist loadscope` (group by module) or `loadgroup` to keep same-combo tests on one
worker and raise the cache hit rate — set this as the intended mode in B1/B2.

**Gate on B1's measured number (duration-first / YAGNI):** if B1's before/after shows `-n auto` *alone*
already hits the wall-clock target, B2 may not earn its complexity — re-evaluate B2's value against B1's
measurement before building it rather than treating the cache as a given.

**Done:** `test_copier_runner` + the high-frequency render-callers reuse cached bases; redundant
`render_project` calls drop from 283 → ~20-per-worker; suite still green; measured wall-clock delta recorded.

### B3 — `FWK95` — tier-3 transient-instance contract (child of FWK76; `FWK88` consumption)

Narrow remainder over what the acceptance tier already does (unique project name + ephemeral ports). With
**no testcontainers-python / no Ryuk** in this suite, reaping is a session finalizer + label sweep:

- **Guaranteed reaping:** tag every transient stack with a per-run label; sweep `docker` for that label at
  session **start *and* finish** (the start-sweep catches a prior SIGKILL'd / crashed-worker run that
  `sessionfinish` never reaped).
- **Reserved namespace (tier-2↔tier-3 disjointness) — PINNED in `FWK88` (operator, 2026-06-28):** tier-3 =
  **`<slug>-t-<uuid>`** (for the rendered test slug `demo` → `demo-t-<uuid>`); the **`<slug>-t-` prefix is
  reserved for tier-3**, and A2's tier-2 generator MUST reject any `<inst>` beginning with `t-` — so
  disjointness is **structural**, not a slug-value coincidence. B3's concrete change: switch the acceptance
  tier's transient project name from `swfwacc-<test>` to the pinned `<slug>-t-<uuid>` form, and assert the
  `<slug>-t-` reservation. *(This resolves the loud finding below — B raised the unpinned marker; the
  operator pinned the structural form; A2/`FWK74` carries the `t-`-prefix ban.)*
- **Guard test:** assert transient stacks use the plain compose path — **never** the shared edge network,
  **never** the host docker socket.

**Done:** a reaping finalizer + start-sweep exist and are tested; the reserved-marker disjointness is
asserted; a guard test pins no-edge-net/no-socket.

### B4 — `FWK96` — fast vs full test tiers (child of FWK77)

- **Fast tier (per-commit / local):** the non-docker suite, `-n auto`. (The gate already does
  `--ignore=tests/acceptance`; this is the same cut, now the *named* fast tier.)
- **Full tier (per-merge / PR):** + acceptance/docker, **bounded `-n`** (not `auto` — cap resource
  contention).
- **Prove no coverage gap (load-bearing FWK77 requirement) — define it against the *real CI topology*, not
  a clean two-way split.** The fast tier is a strict *subset* of the full suite, so a naive "fast ∪ full =
  whole suite" guard is **vacuous** (trivially true, proves nothing). The actual invariant is: **every test
  the commit/fast tier skips must run in *some required PR check*.** And the gating topology has a real hole
  today (FWK70): `gate` runs `pytest --ignore=tests/acceptance`, and **acceptance runs in no gating CI job
  at all** — so promoting acceptance into a "full tier" that isn't a required check would leave it in
  *neither* the commit tier *nor* an enforced PR check (the silent gap FWK77 forbids). So B4 must
  **explicitly decide**: does acceptance become a *required* PR check?
  - If **yes** — that is a genuine new enforcement, and it will surface **FWK70's known-failing acceptance
    test** as a PR blocker → **sequence FWK70's fix ahead of making acceptance required.**
  - Build the partition guard against the **actual jobs** (commit · `gate` · `build` · `render-complete`),
    asserting every pytest test is claimed by ≥1 *required* job. Be explicit that `render-complete` /
    render-matrix is **not pytest** — state what "whole suite" spans so the guard isn't comparing unlike sets.

**Done:** fast/full invocation paths exist + documented; the required-coverage guard (every commit-skipped
test runs in a required PR check) passes; the acceptance-as-required decision is recorded; if acceptance
becomes required, FWK70 is fixed first; required PR checks updated deliberately, not by accident.

### B5 — `FWK97` — template-suite mirror (child of FWK89; tail)

Apply the proven levers to the **generated** project's shipped suite (its own `pytest`, pre-commit, CI):
xdist in the rendered project + a fast(pre-commit)/full(CI) split mirroring B4. Template change → re-run
render + acceptance; ships in the release.

**Done:** the rendered project's suite runs `-n auto`; its pre-commit vs CI mirror the tiering;
`test_copier_runner` + acceptance green; a clean first `pre-commit` pass still holds.

## Protocol notes (the carving applied fractally)

- **Seam is fixed.** B consumes the `FWK88` tier-3 contract verbatim; any mismatch is a loud finding
  surfaced to the carving, not a mid-stream renegotiation.
- **`/clear` between sub-PLANs.** Stream B's sub-PLANs spin up **no persistent stacks** (B3's transient
  stacks are reaped within the test session), so the `/clear` deprovision boundary is satisfied by the B3
  reaper itself — record running stacks only if a debug session leaves one up.
- **Independent stream.** No code dep on A1/A2; B PRs to `main` whenever ready. The only shared surface is
  the `COMPOSE_PROJECT_NAME` namespace, governed by the frozen tier-2↔tier-3 disjointness rule (a naming
  rule both honor — not a merge-order dep).
- **Learnings capture is A2's deliverable;** B records worktree-flow learnings inline in ACTION_LOG as they
  arise (it dogfoods the protocol) but builds no separate capture artifact.

### Loud findings raised (to the carving / `FWK88`)

Per the protocol ("a wrong cut is a loud finding, not a quiet adaptation"), B surfaces — does **not** silently
absorb — these seam concerns it cannot resolve from its own worktree:

- **The tier-3 reserved-marker convention was unpinned in the frozen `FWK88` contract → RESOLVED.** It was
  left as an "e.g. `<slug>-t-<uuid>`", but the choice imposes *different* constraints on A2 (a structural
  `t-`-prefix ban vs. a `swfwacc`-slug-value coincidence) and governs the tier-2↔tier-3 disjointness both
  streams must honor. **Outcome (operator, 2026-06-28):** pinned the structural form **`<slug>-t-<uuid>`**
  in `FWK88` (carving spec + the `FWK88`/`FWK74` rows); A2/`FWK74` enforces the `t-`-prefix ban on `<inst>`;
  B3/`FWK95` builds to it (dropping `swfwacc-`). *This is the experiment's first loud finding: a seam gap B
  could not resolve from its own worktree, surfaced rather than quietly adapted, and decided by the
  contract owner.*

## YAGNI / explicitly out of scope

- **Per-mutation test-impact selection** — that is `FWK90` (its own row), not B.
- A **cross-worker shared on-disk render cache** — deliberately rejected (recreates the `realize_cached`
  race at process granularity). Per-worker only.
- **Splitting the gate into sibling lint|typecheck|test CI jobs** — lint/mypy are seconds; the test job
  stays the pole, so xdist on it is the win. (Notable, not built.)
