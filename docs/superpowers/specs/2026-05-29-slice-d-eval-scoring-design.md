# Slice D — real-key eval scoring + threshold tuning — design (DRAFT)

**Date:** 2026-05-29
**Status:** ⚠ DRAFT — brainstormed and presented; **not yet user-approved**. Captured for session continuity (we paused to sort local API-key env + rotate two leaked dev keys). Re-confirm §2/§3 with the user before writing the plan.
**Slice of:** the context-aware review agents redesign (the original Plan 11). Builds on Slices A (spine + bundle fixtures), B (agentic loop), C (framework target), and the scoped-reviewer-key-envvars slice.

## 1. Shape: build now, score when a key is in-session
The **build** (§2–§4) is fully hermetic and merges on its own. The **scoring** (§5) is the key-gated tail — it runs once `ANTHROPIC_EVAL_API_KEY` is available to the session and the GH secrets are set. If the key isn't ready when the build lands, merge the build; scoring becomes the final step.

## 2. Eval-harness migration to rendered-project fixtures
`load_fixtures` today discovers `*.diff` files and reads `fx.diff` eagerly. Migrate to the **directory format** (`<agent>/<bad|good>/<case>/{fixture.yaml,change.patch,expect.json}`), **lazily**: a `Fixture` carries `(agent, kind, name, batteries, patch_path, seeded_file)` and realizes on demand via `realize_fixture` (Slice A) → `(root, diff)`, with a **per-battery-combo render cache** (render the base once, copy+patch per fixture) so a full scoring run renders a handful of trees, not ~70. The `framework eval` loop realizes each fixture then routes through `_eval_run` (bundle→`assemble`, agentic→`run_agent_agentic`). **Retire the legacy `.diff` fixtures**; adapt the coverage/well-formed gate tests to the directory format (presence + valid patch, no eager render).

## 3. Fixture work
- **Author rendered-project fixtures for the 7 agentic agents** (architecture, data-lineage, privacy, api-design, observability-infra, observability-db, contracts) — Slice B left them on `.diff`. Each gets cross-file defects a diff can't show (data-lineage across modules, api-design consumer+provider, contracts both-ends, etc.) so agentic exploration is exercised. (Open: scope to 2 bad + 1 good per agent to start, vs the full 3+1.)
- **Enrich the shallow good fixtures** (carried-over OBS-COMPLETE input): the obs agents' good fixtures exercise only the metric/span true-negative — add health-signal + correlation-id cases; add a second good fixture where precision is currently binary.

## 4. Model changes (hermetic)
- `review/context.py` `_MODEL_CONTEXT_TOKENS`: `claude-opus-4-7` → `1_000_000`; add `claude-opus-4-8` → `1_000_000` (Opus's real 1M window, per the model migration guide).
- Set the **7 agentic agents' `model` to `claude-opus-4-8`** (a registry constant); the 11 bundle agents stay `claude-sonnet-4-6` (still the latest Sonnet). Decided: try Opus 4.8 on the agentic tier before scoring; the scorecard validates whether it's worth the cost.
- Refresh CLAUDE.md's model-ID note: Opus 4.8 (`claude-opus-4-8`) is now the latest Opus; Sonnet 4.6 / Haiku 4.5 unchanged.

## 5. Scoring + calibration (key-gated tail)
With `ANTHROPIC_EVAL_API_KEY` in-session: `framework eval --require-key --repeat 4` across all 18 agents → first real scorecard. Calibrate `tests/eval/fixtures/thresholds.yaml` per agent with a **safety margin** (recall_min a notch below observed healthy recall; fp_max a notch above observed FP), writing entries only where the `0.67`/`0.34` defaults don't fit. Commit a **dated scorecard** under `docs/superpowers/eval-scorecards/`. GHA confirmation: add a `workflow_dispatch` trigger to `agent-evals.yml`, set the secrets, dispatch → green; confirm `review.yml` runs green on a framework PR/push. Retire the "never real-key scored / provisional thresholds" caveats (review-contracts, the two obs agents, all defaults).

## 6. Testing (hermetic) + risks
- **Hermetic build:** the lazy loader (discovery + realize), the per-combo cache, the agentic agents' fixtures realize/assemble against a real render, the gate tests on the directory format, the budget-map + opus-4-8 registry values, `framework eval` smoke (skips cleanly without a key).
- **Risks:** authoring cross-file-defect fixtures for the 7 agentic agents is the bulk of the effort; the opus-4-8 agentic agents raise scoring cost (bounded by the turn cap); the GHA run needs the secrets. A full `--repeat 4` run over 18 agents (7 on Opus) costs real money — budget for a few tuning iterations.
- **Decomposition:** large enough to run the build subagent-driven (loader, fixtures, model changes as separate tasks); scoring is the explicit key-gated final phase.

## Open questions to confirm before the plan
1. Agentic-fixture scope: 2 bad + 1 good per agent (faster) vs 3 bad + 1 good (parity with bundle tier)?
2. Sequencing: build-then-score in one slice (key-gated tail) vs split into D1 (build, merge) + D2 (score, later)?
3. Opus-4-8 on agentic agents now vs after a sonnet baseline scorecard (already leaned "now").

## Operational notes (session resume)
- **Two `helmuthwsl` dev keys (eval + runtime) were leaked into a session transcript on 2026-05-29 and must be rotated.** Recreate them in the Anthropic console (revoke the old) before scoring.
- Local env: the keys belong in a profile the shell actually sources, **with `export`** (the first attempt put them in `~/.bashrc` without `export` + behind the non-interactive guard, so `framework` never saw them). Alternative: an out-of-repo keys file sourced per-command (`set -a; . ~/.swiftwater-keys.env; set +a; uv run framework eval …`).
