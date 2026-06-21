# FWK44 — `framework eval` robustness + speed — Design

**Date:** 2026-06-21
**Status:** Design (brainstormed).
**Origin:** task #19, surfaced by the FWK43 reviewer-tuning eval gate.

## Problem

The FWK43 tuning pass leaned heavily on `framework eval` as the empirical gate, and the
run exposed three real defects in the eval harness:

1. **Fixture drift is undetectable until a live run hits it.** Four golden fixtures'
   `change.patch` files no longer apply to the current rendered template (they anchor on
   `README.md` / `.env.example` / `infra/compose/{observability,services}.yml` lines that
   recent template work — FWK6 data-store, observability — moved). The existing guards
   (`test_fixtures_are_wellformed`, `validate_patch_hunks`) only validate **structure**
   (non-empty patch, correct hunk counts); **neither renders the template and applies the
   patch**, so drift is invisible to CI. It only surfaces when a backend-gated `eval`
   reaches that fixture — i.e. weeks later, by accident.
2. **One un-realizable fixture aborts the entire run.** The `realize_cached(...)` call in
   the eval command is unwrapped, so a drifted fixture's `CalledProcessError: git apply`
   propagates uncaught and kills the whole sweep — every later agent goes unscored. (The
   *backend* call is already wrapped for parse errors / exhaustion; the *realize* step is
   not.)
3. **eval is fully serial.** No `--concurrency`; the FWK43 gate took ~2h, ~10 min per
   agentic agent. The independent per-agent scoring is embarrassingly parallel.

The 4 drifted fixtures (authoritative count via a no-backend realize sweep — 57 OK / 4
fail):

| Fixture | Drifted on |
| --- | --- |
| `documentation/good/documented-public-function` | `README.md:75` |
| `env-parity/good/parity-preserved` | `.env.example:16` |
| `observability-infra/bad/exporter-without-scrape` | `infra/compose/observability.yml:91` |
| `observability-infra/good/complete-obs-surface` | `infra/compose/services.yml:3` |

## Goals

Make the eval gate trustworthy again, and fast:

1. **Re-anchor the 4 drifted fixtures** so they realize against the current template.
2. **A gate-tier guard** that fails CI the instant a fixture stops realizing.
3. **eval record-and-continues** on a realize failure instead of aborting.
4. **`eval --concurrency N`** to parallelize the per-agent scoring.

## Non-goals

- No change to scoring semantics, `thresholds.yaml`, or the agents/prompts.
- No re-tuning — fixture re-anchoring restores the *intended* seeded change, it does not
  alter what each fixture tests.
- No docker — realization is Copier-render + `git apply` only.

## Design

### Piece 1 — Re-anchor the 4 drifted fixtures

For each drifted fixture, per [[eval-fixtures-coupled-to-template]]: render a base at the
fixture's `batteries`, re-apply the *intended* seeded change to the current template
content (via `patch --fuzz` against the old hunk, or by hand where the anchor moved),
regenerate `change.patch` with `git diff`, and confirm `realize_cached` succeeds. The
seeded behavior (the bug a `bad` fixture introduces / the clean pattern a `good` fixture
shows) is **preserved**; only the surrounding context lines / line numbers update. A
`bad` fixture's `expect.json` (`file`) is re-verified to still name the seeded file.

### Piece 2 — Gate-tier realize guard

New `gate`-tier test (sibling to `test_fixtures_are_wellformed` in
`tests/review/test_evals.py`): `test_every_fixture_realizes` calls `realize_cached` for
every discovered fixture against a freshly rendered base and asserts each succeeds
(collecting *all* failures into one assertion message, not failing on the first). No
backend, no docker — Copier render + `git apply`. Reuses the same `realize_cached` the
eval command uses, so the guard and the runtime path can't diverge. Renders the handful
of unique battery-sets once (cached via the `_combo_cache` it owns). This is the durable
fix for defect 1: a template change that drifts a fixture fails this test on its own PR.

### Piece 3 — eval record-and-continue on realize failure

Wrap the `realize_cached(fx, ...)` call in the eval command's fixture loop. On
`CalledProcessError` (or any realize error): emit a loud `eval: FIXTURE-ERROR <agent>
<kind>/<name> — could not realize (git apply failed); skipping` warning (stdout, per the
FWK43 stream convention), record `(agent, kind, name)` in an `unrealizable` list, and
`continue` to the next fixture. The agent is still scored on its **realizable** fixtures,
and the run **completes for every agent**. After the loop: if `unrealizable` is non-empty,
print a summary block and **exit 5** (a dedicated code — existing codes are 0 skip / 1
usage + threshold-FAIL / 2 bad-`--repeat` / 3 API-abort / 4 exhaustion, so 5 is free) so a
maintainer or CI notices — even
though the scorable agents may have PASSed. This mirrors the existing
`FindingsParseError` record-and-continue, applied one level up at realization.

### Piece 4 — `eval --concurrency N`

Add `--concurrency N` (default 4, `min=1 max=16` — the FWK41 H2 footgun fence; `1` =
today's serial behavior). Race-safe structure:

1. **Pre-render bases serially.** Before scoring, realize every fixture once to warm
   `_combo_cache` (this also *is* the realize check — a realize failure here feeds Piece
   3's `unrealizable` list). After warming, `_combo_cache` is read-only, so concurrent
   `realize_cached` calls hit the cache with no render race.
2. **Parallelize per-agent scoring** on a bounded `ThreadPoolExecutor(max_workers=N)`.
   Each agent's `(realize cached fixtures → repeat × backend score → score_agent →
   record)` runs as one task; the slow `claude -p` calls overlap. A `threading.Lock`
   guards the shared mutable state (the `failing` counter, the per-agent result `echo` so
   lines don't interleave). `findings_out` writes are per-`(agent,fixture,repeat)` files,
   already independent.
3. **Exhaustion / API-error semantics under concurrency** (carry over FWK41 H2): capture
   `BackendExhausted` / `openai.APIError` from a worker, set a stop flag so not-yet-started
   agent tasks skip, let in-flight finish, then re-raise → the existing Exit(4)/Exit(3)
   clean-stop. A `--repeat 3` worker still scores its fixtures serially within the agent
   (repeat is inner); only the *agent* dimension parallelizes.

Implementation stays **local to the eval command** (a thread pool over a
`_score_one_agent(agent) -> AgentResult` helper extracted from the current loop body) —
NOT a reuse of the audit `run_stage` orchestrator, whose checkpoint/findings-file model
doesn't fit eval's in-memory scoring + `thresholds.yaml` + `findings-out` shape.

## Components / boundaries

- `evals.py` — unchanged core (`realize_cached`, `load_fixtures`, `score_agent`); the
  guard test calls it.
- `tests/review/test_evals.py` — `+ test_every_fixture_realizes` (gate-tier).
- `cli.py` `eval` command — extract `_score_one_agent`; wrap realize (Piece 3); add the
  pre-render + thread pool + `--concurrency` (Piece 4). The agent-scoring helper has one
  job (score one agent, return recall/fp/pass + any unrealizable fixtures) and is
  independently testable with a stub backend.
- `tests/eval/fixtures/{documentation,env-parity,observability-infra}/...` — re-anchored
  `change.patch` files (Piece 1).

## Error handling

- Realize failure → record-and-continue + nonzero exit (Piece 3).
- `BackendExhausted` → stop scheduling, Exit(4) (existing, made concurrency-safe).
- `openai.APIError` → stop scheduling, Exit(3) (existing, made concurrency-safe).
- `FindingsParseError` → score-as-no-findings, continue (existing, unchanged).
- Threshold FAIL → nonzero exit (existing, unchanged).

## Testing

- **Piece 1:** the new realize guard (Piece 2) going green *is* the proof the 4 fixtures
  re-anchored; plus each `bad` fixture's `expect.json` still names its seeded file.
- **Piece 2:** `test_every_fixture_realizes` passes on the fixed tree; **bite-proof** —
  temporarily corrupt one fixture's `change.patch` and confirm RED.
- **Piece 3:** a unit test drives the eval command (CliRunner + stub backend) with a
  deliberately-broken fixture and asserts: the run completes + scores the other agents,
  the FIXTURE-ERROR warning appears, the exit code is the new nonzero.
- **Piece 4:** `--concurrency 1` == serial result (parity); a stub-backend test asserts
  per-agent results match serial and that `--concurrency 4` genuinely overlaps (peak >=2
  active, à la FWK41 H2); exhaustion from one worker stops scheduling + exits cleanly.
- Full gate green: `uv run pytest -q` / `ruff check` / `ruff format --check` / `mypy src`.

## Risks

- **Gate-tier render cost** (Piece 2): renders the unique battery-sets (~handful, Copier
  only, no docker) — adds ~2–3 min to the gate. Accepted: the failure mode it prevents
  (silent eval-gate blindness for weeks) is worth it.
- **Concurrency × shared render cache:** mitigated by pre-rendering serially before the
  pool (cache read-only during parallel scoring).
- **Concurrency × subscription backend** (no backoff): default 4, clamped 16 — same fence
  as FWK41 H2.
- **Re-anchor authenticity:** a re-anchored fixture must still *test the same thing*; the
  realize guard proves it applies, but a reviewer confirms the seeded change is unchanged
  in intent (not silently weakened).

## Phasing (build order)

1. Piece 3 (record-and-continue) — small; lets a full eval complete + report all drift.
2. Piece 2 (gate-tier realize guard) — RED on the current tree (proves it catches drift).
3. Piece 1 (re-anchor the 4) — turns the guard GREEN.
4. Piece 4 (concurrency) — the speed layer, on top of a now-trustworthy gate.

Maintainer-tooling + eval-fixtures only → **no release, no template payload**.
