# `framework eval` Robustness + Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the `framework eval` gate trustworthy (catch fixture drift in CI, don't abort on one bad fixture) and fast (`--concurrency`).

**Architecture:** Four pieces, built in the order that keeps each step verifiable: (3) wrap the unwrapped `realize_cached` call so eval records-and-continues; (2) a gate-tier test that realizes every fixture (RED on the current drifted tree); (1) re-anchor the 4 drifted fixtures (turns the guard GREEN); (4) `--concurrency` via a pre-render-then-thread-pool split. All in `evals.py`-adjacent code + the eval command + the fixtures; no template payload, no release.

**Tech Stack:** Python 3.12, Typer, `concurrent.futures.ThreadPoolExecutor`, `threading.Lock`, pytest. Realization is Copier render + `git apply` (no docker, no backend).

**Spec:** `docs/superpowers/specs/2026-06-21-eval-robustness-design.md`

**Execution policy (repo):** subagent-driven (Sonnet impl/spec, Opus quality per [[subagent-review-model-pattern]]); controller commits (implementers stage only — [[subagent-implementers-stop-before-commit]]); separate `git add` then `git commit` ([[commit-gate-hook-timing]]); tick PLAN.md / append ACTION_LOG before each commit. Run full runs with `TMPDIR=/var/tmp` ([[full-suite-exhausts-tmp-tmpfs-use-var-tmp]]). No release, no template payload.

**Reference — the eval command (`src/framework_cli/cli.py`, `@app.command(name="eval")`):**
- setup: `_base_dir = Path(tempfile.mkdtemp(...))`, `_combo_cache: dict = {}`, `thresholds`, `by_agent`.
- `targets = [agent] if agent else agent_names()`; `failing = 0`; `missing: list[str] = []`.
- loop: `for a in targets:` → `spec = get_agent(a)` → `fx_list = by_agent.get(a, [])` → `for fx in fx_list: rroot, rdiff = realize_cached(fx, _combo_cache, _base_dir)` **(UNWRAPPED — the abort bug)** → `for i in range(repeat):` (backend `_eval_run`, already wrapped for `BackendExhausted`→Exit(4) / `openai.APIError`→Exit(3) / `FindingsParseError`→score-as-no-findings) → `score_agent(...)` → echo `f"{spec.name}    recall ...    {status}"` → `if not score.passed: failing += 1`.
- end: `summary = f"{len(targets)} agent(s) · {failing} failing"` (+ missing) → `raise typer.Exit(1 if failing or coverage_fail else 0)`.
- `realize_cached(fx, cache, base_dir) -> (work_path, diff)` raises `subprocess.CalledProcessError` when `git apply` rejects a drifted patch.

---

## File Structure
- Modify: `src/framework_cli/cli.py` — the `eval` command (Pieces 3 + 4); extract a `_score_one_agent` helper.
- Modify: `tests/review/test_evals.py` — `+ test_every_fixture_realizes` (Piece 2, gate-tier).
- Modify: `tests/test_cli.py` — `+` record-and-continue test (Piece 3) + `--concurrency` tests (Piece 4).
- Modify: `tests/eval/fixtures/{documentation/good/documented-public-function, env-parity/good/parity-preserved, observability-infra/bad/exporter-without-scrape, observability-infra/good/complete-obs-surface}/change.patch` — re-anchored (Piece 1).

---

# Phase A — Piece 3: eval record-and-continue on a realize failure

### Task A1: Wrap `realize_cached`; skip+warn+exit 5 instead of aborting

**Files:**
- Modify: `src/framework_cli/cli.py` (the `eval` command)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test.** A fixtures tree with one realizable good fixture and one un-realizable fixture (a `change.patch` that won't `git apply`); eval must score the good one, warn on the bad, and exit 5.
```python
# tests/test_cli.py — add near the other eval tests
def test_eval_records_and_continues_on_unrealizable_fixture(tmp_path, monkeypatch):
    """A fixture whose change.patch fails `git apply` must NOT abort the whole run:
    eval skips it (loud warning), scores the rest, and exits 5."""
    import framework_cli.cli as cli_mod

    # one realizable good fixture for `security`, one broken good fixture for `architecture`
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")
    _make_fixture(tmp_path, "architecture", "good", "broken",
                  "--- a/nonexistent-file-xyz.py\n+++ b/nonexistent-file-xyz.py\n@@ -1 +1 @@\n-nope\n+nope2\n")

    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", _real_realize_cached)  # the real one (renders)
    monkeypatch.setattr(cli_mod, "_eval_run", lambda *a, **k: [])  # backend returns no findings

    result = runner.invoke(app, ["eval", "--fixtures", str(tmp_path), "--backend", "api"])
    assert result.exit_code == 5, result.output
    assert "FIXTURE-ERROR" in result.output and "architecture" in result.output
    assert "review-security" in result.output  # the realizable agent still got scored
```
Reuse the existing `_make_fixture` helper in `tests/test_cli.py` (it writes `change.patch` + `fixture.yaml` + `expect.json`). `_real_realize_cached` = the genuine `evals.realize_cached` (import it; for `security/good/g1` a trivial patch realizes against the rendered template — if the trivial patch doesn't apply, use a patch that does, e.g. append a comment to an existing template file; the point is one realizes and one does not). Confirm the realizable fixture's patch actually applies during Step 2; adjust its content if not.

- [ ] **Step 2: Run → FAIL.** `uv run pytest tests/test_cli.py::test_eval_records_and_continues_on_unrealizable_fixture -v` → currently the broken fixture raises `CalledProcessError` and the command crashes (not exit 5).

- [ ] **Step 3: Implement.** In the eval command, replace the bare `for fx in fx_list:` realize with a wrapped version, and add an `unrealizable` tracker + the exit-5 path. Concretely:
  - Before the `for a in targets:` loop add: `unrealizable: list[str] = []`.
  - Replace `rroot, rdiff = realize_cached(fx, _combo_cache, _base_dir)` with:
```python
            try:
                rroot, rdiff = realize_cached(fx, _combo_cache, _base_dir)
            except subprocess.CalledProcessError:
                label = f"{a} {fx.kind}/{fx.name}"
                typer.echo(
                    f"eval: FIXTURE-ERROR {label} — could not realize "
                    f"(git apply failed; fixture likely drifted from the template); skipping"
                )
                unrealizable.append(label)
                continue
```
  - At the end, before the final `raise typer.Exit(...)`, fold `unrealizable` into the summary + exit code:
```python
    if unrealizable:
        typer.echo(
            f"eval: {len(unrealizable)} fixture(s) could not be realized "
            f"(drifted from the template): {', '.join(unrealizable)}"
        )
    summary = f"{len(targets)} agent(s) · {failing} failing"
    if missing:
        summary += f" · {len(missing)} without fixtures"
    if unrealizable:
        summary += f" · {len(unrealizable)} unrealizable"
    typer.echo(summary)
    coverage_fail = bool(missing) and require_fixtures
    if unrealizable:
        raise typer.Exit(5)  # drift — distinct from a threshold FAIL (1) or API/exhaustion (3/4)
    raise typer.Exit(1 if failing or coverage_fail else 0)
```
  Ensure `import subprocess` is present at the top of `cli.py` (it is — used elsewhere; confirm).

- [ ] **Step 4: Run → PASS.** Re-run the test → exit 5, warning present, security scored.

- [ ] **Step 5: Commit** (controller).

---

# Phase B — Piece 2: gate-tier realize guard

### Task B1: `test_every_fixture_realizes`

**Files:**
- Modify: `tests/review/test_evals.py` (gate-tier — `tests/review/` runs in the gate by default)

- [ ] **Step 1: Write the test.** Realize every fixture; collect ALL failures into one message (don't stop at the first).
```python
# tests/review/test_evals.py — add (it already has `_FIXTURES_ROOT`)
def test_every_fixture_realizes():
    """Every golden fixture's change.patch must apply to a fresh render of the current
    template — the durable guard against fixture/template drift the structural checks miss.
    No backend; Copier render + `git apply` only."""
    import subprocess
    import tempfile

    from framework_cli.review.evals import load_fixtures, realize_cached

    base = Path(tempfile.mkdtemp(prefix="fixture-realize-"))
    cache: dict = {}
    failures: list[str] = []
    for fx in load_fixtures(_FIXTURES_ROOT):
        try:
            realize_cached(fx, cache, base)
        except subprocess.CalledProcessError:
            failures.append(f"{fx.agent}/{fx.kind}/{fx.name}")
    assert not failures, (
        "fixtures drifted from the template (change.patch no longer applies) — "
        f"re-anchor: {failures}"
    )
```

- [ ] **Step 2: Run → FAIL** (on the current tree — the 4 drifted fixtures).
`uv run pytest tests/review/test_evals.py::test_every_fixture_realizes -v`
Expected: FAIL listing `documentation/good/documented-public-function`, `env-parity/good/parity-preserved`, `observability-infra/bad/exporter-without-scrape`, `observability-infra/good/complete-obs-surface`.

- [ ] **Step 3: (no impl — the fix is Phase C.)** Leave the test RED; it is the acceptance criterion for the re-anchoring. Note the exact failing set from Step 2 for Phase C.

- [ ] **Step 4: Commit** the test as known-RED (the next phase greens it). State in the commit message that it is RED pending Phase C.

---

# Phase C — Piece 1: re-anchor the 4 drifted fixtures

Re-anchoring procedure (apply per fixture; the new `change.patch` content is generated from the live render, so it cannot be pre-written here):

1. Render a base at the fixture's batteries (almost all are `batteries: []`):
   `uv run python -c "from framework_cli.review.evals import realize_fixture; from pathlib import Path; import tempfile; d=Path(tempfile.mkdtemp()); realize_fixture(d, batteries=[], patch='')" ` — or render directly via `render_project` to a scratch dir and `git init` it.
2. In the rendered tree, **re-create the fixture's intended seeded change by hand** on the *current* file content (read the OLD `change.patch` to see the intent; apply the same edit to where that code now lives).
3. `git -C <render> add -A && git -C <render> diff --cached` → the new `change.patch`. Write it back to the fixture dir.
4. Verify: `realize_cached` for that fixture now succeeds (Phase B's test, scoped to the agent).
5. For a `bad` fixture: confirm `expect.json`'s `file` still names the seeded path (update if the path moved).

**The seeded behavior must be preserved** — a `bad` fixture must still introduce the same defect; a `good` fixture must still show the same clean pattern. Do not weaken a fixture to make it apply.

### Task C1: Re-anchor `documentation/good/documented-public-function` (drifted on `README.md:75`)

**Files:** Modify `tests/eval/fixtures/documentation/good/documented-public-function/change.patch`

- [ ] **Step 1:** Read the current `change.patch` to capture intent (a *documented* public function — the clean/good case). `git show HEAD:tests/eval/fixtures/documentation/good/documented-public-function/change.patch`.
- [ ] **Step 2:** Render a `batteries: []` base; locate where the patch's `README.md` anchor (line ~75) now lives in the current render; re-apply the same documented-function addition there.
- [ ] **Step 3:** `git diff --cached` in the render → write the new `change.patch`.
- [ ] **Step 4: Verify:** `uv run pytest "tests/review/test_evals.py::test_every_fixture_realizes" -v` no longer lists this fixture (still lists the other 3).
- [ ] **Step 5: Commit.**

### Task C2: Re-anchor `env-parity/good/parity-preserved` (drifted on `.env.example:16`)

**Files:** Modify `tests/eval/fixtures/env-parity/good/parity-preserved/change.patch`

- [ ] Same procedure as C1, anchoring on the current `.env.example`. Intent: an env var added in parity across `.env.example` + compose (the clean parity-preserved case). Verify it realizes; commit.

### Task C3: Re-anchor `observability-infra/bad/exporter-without-scrape` (drifted on `infra/compose/observability.yml:91`)

**Files:** Modify `tests/eval/fixtures/observability-infra/bad/exporter-without-scrape/change.patch` (+ re-check `expect.json`)

- [ ] Same procedure, anchoring on the current `infra/compose/observability.yml`. Intent (bad): an exporter added with no matching Prometheus scrape — the seeded obs gap. After re-anchor, confirm `expect.json`'s `file` still names the seeded file; verify it realizes; commit.

### Task C4: Re-anchor `observability-infra/good/complete-obs-surface` (drifted on `infra/compose/services.yml:3`)

**Files:** Modify `tests/eval/fixtures/observability-infra/good/complete-obs-surface/change.patch`

- [ ] Same procedure, anchoring on the current `infra/compose/services.yml`. Intent (good): a complete obs surface (exporter + scrape + alert). Verify it realizes; commit.

### Task C5: Confirm the guard is fully GREEN

- [ ] **Step 1:** `uv run pytest tests/review/test_evals.py -q` → all green (incl. `test_every_fixture_realizes`).
- [ ] **Step 2: Bite-proof the guard** — temporarily break one re-anchored `change.patch` (e.g. change a context line), run the guard → RED naming that fixture, then revert. Confirms the guard genuinely catches drift.
- [ ] **Step 3:** No commit (verification); note the bite-proof in the task log.

---

# Phase D — Piece 4: `eval --concurrency N`

### Task D1: Extract `_score_one_agent` (pure refactor, no behavior change)

**Files:** Modify `src/framework_cli/cli.py`

- [ ] **Step 1: Write the characterization test** (the serial path must be unchanged). Drive eval over 2 agents with a stub backend and assert the two result lines + exit code; this test must pass before AND after the extraction.
```python
# tests/test_cli.py
def test_eval_serial_scores_each_agent(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")
    _make_fixture(tmp_path, "architecture", "good", "g1", "+++ b/a.py\n# clean\n")
    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", lambda fx, c, b: (tmp_path, "diff"))
    monkeypatch.setattr(cli_mod, "_eval_run", lambda *a, **k: [])
    result = runner.invoke(app, ["eval", "--fixtures", str(tmp_path), "--backend", "api"])
    assert result.exit_code == 0, result.output
    assert "review-security" in result.output and "review-architecture" in result.output
```

- [ ] **Step 2: Run → PASS** (it characterizes current behavior).

- [ ] **Step 3: Extract.** Move the per-agent loop body into a module-level helper that takes everything it needs and RETURNS a result dataclass — raising `BackendExhausted`/`openai.APIError` out (NOT catching them; the driver handles those), but catching the realize `CalledProcessError` (Piece 3) and `FindingsParseError` (existing) internally:
```python
from dataclasses import dataclass, field

@dataclass
class _AgentEvalResult:
    agent: str
    line: str                       # the "review-X  recall ..  PASS" line, or a no-fixtures note
    passed: bool
    unrealizable: list[str] = field(default_factory=list)
    no_fixtures: bool = False

def _score_one_agent(a, *, by_agent, thresholds, repeat, backend, findings_out, combo_cache, base_dir):
    from framework_cli.review.evals import score_agent, flags, DEFAULT_THRESHOLDS
    spec = get_agent(a)
    fx_list = by_agent.get(a, [])
    if not fx_list:
        return _AgentEvalResult(a, f"{spec.name}    no fixtures (skipped)", True, no_fixtures=True)
    bad_rates: list[float] = []
    good_rates: list[float] = []
    unrealizable: list[str] = []
    for fx in fx_list:
        try:
            rroot, rdiff = realize_cached(fx, combo_cache, base_dir)
        except subprocess.CalledProcessError:
            unrealizable.append(f"{a} {fx.kind}/{fx.name}")
            continue
        hits = 0
        for i in range(repeat):
            report = {} if findings_out else None
            try:
                found = _eval_run(rdiff, rroot, spec, report=report, backend=backend)
            except FindingsParseError as exc:
                if report is not None:
                    report["parse_error"] = str(exc)
                found = []
            if findings_out:
                _write_findings(Path(findings_out), fx, i, found, report or {})
            blocked = flags(found, spec, file=fx.seeded_file) if fx.kind == "bad" else flags(found, spec)
            hits += 1 if blocked else 0
        (bad_rates if fx.kind == "bad" else good_rates).append(hits / repeat)
    score = score_agent(a, bad_rates, good_rates, thresholds.get(a, DEFAULT_THRESHOLDS))
    status = "PASS" if score.passed else f"FAIL ({score.reason})"
    line = f"{spec.name}    recall {score.recall:.2f}  fp {score.fp_rate:.2f}    {status}"
    return _AgentEvalResult(a, line, score.passed, unrealizable=unrealizable)
```
  In the command, replace the loop body with: call `_score_one_agent(a, ...)`, then echo `res.line`, fold `res.unrealizable` into the outer `unrealizable`, increment `failing` if `not res.passed`, append to `missing` if `res.no_fixtures`. The `BackendExhausted`/`openai.APIError` handlers (Exit 4/3 + their warnings) move to WRAP the `_score_one_agent` call in the serial loop (unchanged behavior). The unknown-agent `KeyError` (Exit 1) stays at the call site.

- [ ] **Step 4: Run → PASS** (the characterization test + the Phase-A record-and-continue test + the full eval test suite all still green — the extraction changed nothing).

- [ ] **Step 5: Commit.**

### Task D2: Add `--concurrency` (pre-render bases serially, thread-pool the scoring)

**Files:** Modify `src/framework_cli/cli.py`; Test `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests.**
```python
def test_eval_concurrency_matches_serial(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    for ag in ("security", "architecture", "compliance"):
        _make_fixture(tmp_path, ag, "good", "g1", "+++ b/a.py\n# clean\n")
    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", lambda fx, c, b: (tmp_path, "diff"))
    monkeypatch.setattr(cli_mod, "_eval_run", lambda *a, **k: [])
    serial = runner.invoke(app, ["eval", "--fixtures", str(tmp_path), "--backend", "api", "--concurrency", "1"])
    par = runner.invoke(app, ["eval", "--fixtures", str(tmp_path), "--backend", "api", "--concurrency", "3"])
    assert serial.exit_code == 0 and par.exit_code == 0
    for ag in ("review-security", "review-architecture", "review-compliance"):
        assert ag in serial.output and ag in par.output

def test_eval_concurrency_is_actually_parallel(tmp_path, monkeypatch):
    import threading, time
    import framework_cli.cli as cli_mod
    for ag in ("security", "architecture", "compliance", "performance"):
        _make_fixture(tmp_path, ag, "good", "g1", "+++ b/a.py\n# clean\n")
    active = 0; peak = 0; lock = threading.Lock()
    def slow_eval(*a, **k):
        nonlocal active, peak
        with lock:
            active += 1; peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return []
    monkeypatch.setenv("ANTHROPIC_EVAL_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "realize_cached", lambda fx, c, b: (tmp_path, "diff"))
    monkeypatch.setattr(cli_mod, "_eval_run", slow_eval)
    runner.invoke(app, ["eval", "--fixtures", str(tmp_path), "--backend", "api", "--concurrency", "4"])
    assert peak >= 2
```

- [ ] **Step 2: Run → FAIL** (`--concurrency` unknown option).

- [ ] **Step 3: Implement.** Add the option + the pre-render + pool. To the command signature add:
```python
    concurrency: int = typer.Option(
        4, "--concurrency", min=1, max=16,
        help="Parallel per-agent scoring (1 = serial). The subagent backend has no backoff; keep modest.",
    ),
```
  After `targets`/`unrealizable` setup, replace the `for a in targets:` loop with: (a) a serial pre-render warm of the cache so the thread pool never races on render; (b) a dispatch that's serial when `concurrency <= 1` and a bounded pool otherwise; (c) results echoed in `targets` order after collection.
```python
    import threading
    from concurrent.futures import ThreadPoolExecutor, wait

    # (a) Pre-render bases serially → _combo_cache read-only during parallel scoring.
    #     A realize failure here is recorded (Piece 3) and the fixture skipped; warming
    #     never raises out (the per-agent helper re-checks + records too).
    for a in targets:
        for fx in by_agent.get(a, []):
            try:
                realize_cached(fx, _combo_cache, _base_dir)
            except subprocess.CalledProcessError:
                pass  # recorded per-agent during scoring

    def _run(a):  # raises BackendExhausted / openai.APIError; the driver handles those
        return _score_one_agent(a, by_agent=by_agent, thresholds=thresholds, repeat=repeat,
                                backend=_backend, findings_out=findings_out,
                                combo_cache=_combo_cache, base_dir=_base_dir)

    results: dict[str, "_AgentEvalResult"] = {}
    if concurrency <= 1 or len(targets) <= 1:
        for a in targets:
            try:
                results[a] = _run(a)
            except KeyError as exc:
                typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1) from exc
            except BackendExhausted as exc:
                _echo_exhausted(a); raise typer.Exit(4) from exc
            except openai.APIError as exc:
                _echo_api_error(a, exc); raise typer.Exit(3) from exc
    else:
        stop = threading.Event(); err: list[tuple] = []; lock = threading.Lock()
        def _task(a):
            if stop.is_set():
                return
            try:
                r = _run(a)
            except (BackendExhausted, openai.APIError, KeyError) as exc:
                stop.set()
                with lock:
                    err.append((a, exc))
                return
            with lock:
                results[a] = r
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            wait([ex.submit(_task, a) for a in targets])
        if err:
            a, exc = err[0]
            if isinstance(exc, BackendExhausted):
                _echo_exhausted(a); raise typer.Exit(4) from exc
            if isinstance(exc, openai.APIError):
                _echo_api_error(a, exc); raise typer.Exit(3) from exc
            typer.echo(f"Error: {exc}", err=True); raise typer.Exit(1) from exc

    for a in targets:                 # echo + tally in stable order
        res = results.get(a)
        if res is None:               # skipped due to exhaustion mid-run
            continue
        typer.echo(res.line)
        unrealizable.extend(res.unrealizable)
        if res.no_fixtures:
            missing.append(a)
        elif not res.passed:
            failing += 1
```
  Extract the two warning blocks into small local helpers `_echo_exhausted(agent)` and `_echo_api_error(agent, exc)` (the same stderr messages + Exit codes as today) so the serial and parallel paths share them. Keep the `unrealizable`/summary/exit-5 tail from Phase A.

- [ ] **Step 4: Run → PASS** (both new tests + all prior eval tests). Loop the parallel test 3× for flake.

- [ ] **Step 5: Commit.**

---

# Phase E — Gate + branch-end review + PR

- [ ] **Step 1: Full gate.** `TMPDIR=/var/tmp uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src`.
- [ ] **Step 2: Live smoke** (optional, subagent backend): `framework eval security architecture --concurrency 2 --backend subagent` — confirms real concurrent scoring + clean output; skip-neutral without a backend.
- [ ] **Step 3:** Update PLAN.md (FWK44 → Done) + ACTION_LOG; mark task #19 done.
- [ ] **Step 4:** Branch-end Sonnet spec review + Opus quality review (focus: the concurrency thread-safety + exhaustion-stop, and that the re-anchored fixtures preserve their seeded intent). Address findings; open PR (protected master; required checks gate+build+render-complete).

---

## Self-Review

**Spec coverage:** Piece 1 (re-anchor) → C1–C4; Piece 2 (gate guard) → B1 + C5; Piece 3 (record-and-continue + exit 5) → A1; Piece 4 (`--concurrency`) → D1 (extract) + D2 (pool). Build order 3→2→1→4 honored (A, B, C, D). ✓

**Placeholder scan:** no TBD/TODO. Phase C's re-anchored `change.patch` content is genuinely generated at execution time (it depends on the live render), so the plan gives the exact mechanical procedure + per-fixture intent + the verify step rather than pre-written patch text — that is the correct level, not a placeholder. The Phase-A test's realizable-fixture patch is flagged to confirm/adjust during Step 2.

**Type/signature consistency:** `realize_cached(fx, cache, base_dir)` used consistently (A1, B1, D1, D2). `_score_one_agent(a, *, by_agent, thresholds, repeat, backend, findings_out, combo_cache, base_dir) -> _AgentEvalResult` defined in D1, called in D2. `_AgentEvalResult(agent, line, passed, unrealizable, no_fixtures)` fields consistent. `unrealizable: list[str]` + exit-5 tail consistent A1↔D2. Exit codes 1/3/4/5 consistent with the spec.
