# FWK4 Reviewer-Audit Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make `framework reviewer-audit` fast, legible, and safe-to-apply — fixing four issues the live shakedown surfaced.

**Architecture:** Four small, independent changes to the existing `src/framework_cli/review/audit/` package + the CLI: (H1) progress instrumentation via a `log` callback, (H2) bounded concurrency in `run_stage`, (H3) agent-name normalization in `reconcile`, (H4) a robust apply-preview that validates hunks and treats fixture edits as manual. H1 lands first (it establishes the `log`/`label` params H2 builds on).

**Tech Stack:** Python 3.12, Typer, `concurrent.futures.ThreadPoolExecutor`, `threading.Lock`, pytest. LLM-stage tests use the existing `StubBackend` (no key/quota).

**Background — shakedown findings (the why):** the first real sweep ran ~2h52m fully serial (everything one-at-a-time), emitted nothing to stdout (silent for hours), produced a changelist with inconsistent agent ids (`review-coverage-gap` vs `accessibility`), and an `apply-preview.patch` that fails `git apply --check` (corrupt — the 12 fixture edits carry nested diffs + bad paths + paraphrased `before`).

**Execution policy:** subagent-driven (Sonnet impl/spec, Opus quality per [[subagent-review-model-pattern]]); controller commits (implementers stage only — [[subagent-implementers-stop-before-commit]]); separate `git add` then `git commit` ([[commit-gate-hook-timing]]); tick PLAN.md/append ACTION_LOG before each commit. Test/maintainer-tooling only → no release, no template payload. Audit-pipeline tests run on `StubBackend` (no key).

---

## File Structure
- Modify: `src/framework_cli/review/audit/orchestrator.py` — `run_stage` gains `label`, `log`, `concurrency`.
- Modify: `src/framework_cli/review/audit/pipeline.py` — `run_audit` gains `log`/`concurrency`, threads them through, logs stage transitions.
- Modify: `src/framework_cli/review/audit/stages.py` — `reconcile` normalizes agent names (new `_canonical_agent` helper).
- Modify: `src/framework_cli/review/audit/preview.py` — `render_patch` validates hunks + routes fixture edits to notes; gains optional `root`.
- Modify: `src/framework_cli/cli.py` — `reviewer-audit` gains `--concurrency`, `--quiet`; wires `log`, `root`.
- Tests: extend `tests/review/audit/test_orchestrator.py`, `test_stages.py`, `test_preview.py`, `test_pipeline.py`, `tests/test_cli_reviewer_audit.py`.

---

# Phase H1 — Progress instrumentation

### Task H1.1: `run_stage` emits per-item progress

**Files:** Modify `src/framework_cli/review/audit/orchestrator.py`; Test `tests/review/audit/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**
```python
# add to tests/review/audit/test_orchestrator.py
def test_run_stage_logs_progress_per_item(tmp_path):
    seen = []
    run_stage(["a", "b", "c"], lambda x: {"item": x, "out": x},
              run_dir=tmp_path / "s", item_id=lambda x: x,
              label="audit", log=seen.append)
    # one line per completed item, with a monotonic done/total count
    assert any("audit" in m and "a" in m for m in seen)
    assert any("3/3" in m or "(3/3)" in m for m in seen)
    assert len([m for m in seen if "/3" in m or "/ 3" in m]) == 3
```

- [ ] **Step 2: Run → FAIL** (`run_stage() got an unexpected keyword argument 'label'`).
Run: `uv run pytest tests/review/audit/test_orchestrator.py::test_run_stage_logs_progress_per_item -v`

- [ ] **Step 3: Implement.** Change `run_stage`'s signature and body:
```python
from collections.abc import Callable

def run_stage(
    items: list[Any],
    work: Callable[[Any], dict[str, Any]],
    *,
    run_dir: Path,
    item_id: Callable[[Any], str],
    resume: bool = False,
    label: str = "stage",
    log: Callable[[str], None] = lambda _msg: None,
) -> list[dict[str, Any]]:
    ids = [item_id(it) for it in items]
    total = len(ids)
    if not resume or not (run_dir / "run-state.json").exists():
        init_run(run_dir, planned=ids, git_sha="", dirty_hash="", backend="audit")
    todo = set(pending_items(run_dir))
    by_id = dict(zip(ids, items))
    done = total - len(todo)
    for iid in list(todo):
        item = by_id[iid]
        try:
            record = work(item)
        except BackendExhausted:
            raise
        except Exception as exc:  # noqa: BLE001
            record = {"item": iid, "error": f"{type(exc).__name__}: {exc}"}
        append_record(run_dir, iid, record)
        done += 1
        log(f"[{label} {done}/{total}] {iid}")
    return [_persisted(run_dir, iid) for iid in ids if iid in load_state(run_dir)["done"]]
```
(Keep `load_state` import; the final return now inlines it — confirm `load_state` is still imported.)

- [ ] **Step 4: Run → PASS.** Also run the existing orchestrator tests: `uv run pytest tests/review/audit/test_orchestrator.py -v` (the 2 existing pass — `label`/`log` default to no-ops).

- [ ] **Step 5: Commit** (controller).

### Task H1.2: `run_audit` logs stage transitions + threads `log`

**Files:** Modify `src/framework_cli/review/audit/pipeline.py`; Test `tests/review/audit/test_pipeline.py`

- [ ] **Step 1: Write the failing test**
```python
# add to tests/review/audit/test_pipeline.py (reuse the _scripted from the existing test)
def test_run_audit_logs_stage_transitions(tmp_path):
    from tests.review.audit.conftest import StubBackend
    seen = []
    run_audit(["security"], backend=StubBackend(_scripted), root=Path.cwd(),
              baseline_dir=None, out_dir=tmp_path / "out", skeptics=1, log=seen.append)
    blob = "\n".join(seen)
    assert "Stage 1" in blob and "Stage 2" in blob and "Stage 3" in blob
    assert any("vetted" in m.lower() for m in seen)
```
(If the module-level `_scripted` isn't importable, define a tiny inline one matching the existing test's shape.)

- [ ] **Step 2: Run → FAIL** (`run_audit() got an unexpected keyword argument 'log'`).

- [ ] **Step 3: Implement.** Add `log: Callable[[str], None] = lambda _msg: None` to `run_audit`'s signature (import `Callable` from `collections.abc`). Then:
  - Before Stage 1: `log(f"Stage 1: auditing {len(targets)} agent(s)")`; pass `label="audit", log=log` to the Stage-1 `run_stage`.
  - Before Stage 2: `log("Stage 2: reconciling")`; after it: `log(f"Stage 2: reconcile → {sum(len(a.edits) for a in cl.agents) + len(cl.preamble_edits)} edit(s) across {len(cl.agents)} agent(s)")`.
  - Before Stage 3: `log(f"Stage 3: refuting {len(flat)} edit(s) (x{skeptics} skeptics)")`; pass `label="refute", log=log` to the Stage-3 `run_stage`.
  - After writing the changelist: `n_v = sum(len(a.edits) for a in vetted.agents) + len(vetted.preamble_edits)`; `n_all = len(flat)`; `log(f"vetted {n_v}/{n_all} ({n_all - n_v} refuted) -> {out_dir}/")`.

- [ ] **Step 4: Run → PASS** + `uv run pytest tests/review/audit/ -q`.

- [ ] **Step 5: Commit.**

### Task H1.3: CLI wires `log` (default on) + `--quiet`

**Files:** Modify `src/framework_cli/cli.py`; Test `tests/test_cli_reviewer_audit.py`

- [ ] **Step 1: Write the failing test**
```python
def test_reviewer_audit_emits_progress(tmp_path, monkeypatch):
    # reuse the stub-backend monkeypatch pattern from the existing CLI test
    ... # set up StubBackend + _resolve_review_backend as in test_reviewer_audit_writes_changelist_and_preview
    result = runner.invoke(app, ["reviewer-audit", "security", "--out", str(tmp_path / "o")])
    assert result.exit_code == 0
    assert "Stage 1" in result.output  # progress visible by default (echo'd to stderr; CliRunner merges)
```

- [ ] **Step 2: Run → FAIL** (no progress in output).

- [ ] **Step 3: Implement.** Add `quiet: bool = typer.Option(False, "--quiet", help="Suppress progress output.")` to the command. Build `log = (lambda _m: None) if quiet else (lambda m: typer.echo(m, err=True))` and pass `log=log` to `run_audit`.

- [ ] **Step 4: Run → PASS.** (If `CliRunner` doesn't merge stderr, construct it with `CliRunner(mix_stderr=True)` or assert on `result.output` after enabling stderr capture — adjust the test to however the existing CLI tests read output.)

- [ ] **Step 5: Commit.**

---

# Phase H2 — Bounded concurrency

### Task H2.1: `run_stage` runs items concurrently (thread-safe)

**Files:** Modify `src/framework_cli/review/audit/orchestrator.py`; Test `tests/review/audit/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**
```python
def test_run_stage_concurrency_matches_serial(tmp_path):
    work = lambda x: {"item": x, "out": x.upper()}
    items = [f"a{i}" for i in range(8)]
    s = run_stage(items, work, run_dir=tmp_path/"ser", item_id=lambda x: x, concurrency=1)
    p = run_stage(items, work, run_dir=tmp_path/"par", item_id=lambda x: x, concurrency=4)
    assert {r["out"] for r in s} == {r["out"] for r in p}
    assert len(p) == 8 and (tmp_path/"par"/"findings"/"a7.json").exists()

def test_run_stage_concurrency_is_actually_parallel(tmp_path):
    import time, threading
    active, peak, lock = 0, 0, threading.Lock()
    def work(x):
        nonlocal active, peak
        with lock:
            active += 1; peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return {"item": x, "out": x}
    run_stage([str(i) for i in range(8)], work, run_dir=tmp_path/"p",
              item_id=lambda x: x, concurrency=4)
    assert peak >= 2  # genuinely overlapped

def test_run_stage_concurrent_resume_skips_done(tmp_path):
    calls = []
    work = lambda x: (calls.append(x), {"item": x, "out": x})[1]
    run_stage(["a","b","c"], work, run_dir=tmp_path/"r", item_id=lambda x: x, concurrency=4)
    calls.clear()
    run_stage(["a","b","c"], work, run_dir=tmp_path/"r", item_id=lambda x: x,
              concurrency=4, resume=True)
    assert calls == []
```

- [ ] **Step 2: Run → FAIL** (`concurrency` unknown).

- [ ] **Step 3: Implement.** Add `concurrency: int = 1` param. When `concurrency <= 1`, keep the existing serial loop. When `> 1`, use a thread pool; serialize checkpoint writes + progress under a lock; stop scheduling on `BackendExhausted`:
```python
import threading
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
...
    todo_list = [iid for iid in ids if iid in todo]  # stable order
    if concurrency <= 1 or len(todo_list) <= 1:
        # ... existing serial loop over todo_list ...
    else:
        lock = threading.Lock()
        exhausted: list[BackendExhausted] = []
        def _do(iid: str) -> None:
            try:
                record = work(by_id[iid])
            except BackendExhausted as exc:
                with lock:
                    exhausted.append(exc)
                return
            except Exception as exc:  # noqa: BLE001
                record = {"item": iid, "error": f"{type(exc).__name__}: {exc}"}
            with lock:
                nonlocal done
                append_record(run_dir, iid, record)
                done += 1
                log(f"[{label} {done}/{total}] {iid}")
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = [ex.submit(_do, iid) for iid in todo_list]
            wait(futures, return_when=FIRST_EXCEPTION)
        if exhausted:
            raise exhausted[0]
```
Notes: `append_record` reads+writes `run-state.json`, so it MUST be under the lock (the `findings/<id>.json` writes are independent, but the done-list append races). `BackendExhausted` is captured (not raised inside the worker) so the pool drains in-flight work, then re-raised after — completed items stay checkpointed and a `--resume` continues. Keep the final `return [_persisted(...) for iid in ids if iid in load_state(...)["done"]]` (stable order, unaffected by completion order).

- [ ] **Step 4: Run → PASS** (4 new + existing orchestrator/pipeline tests green).

- [ ] **Step 5: Commit.**

### Task H2.2: Thread `concurrency` through `run_audit` + CLI `--concurrency`

**Files:** Modify `pipeline.py`, `cli.py`; Test `test_pipeline.py`, `test_cli_reviewer_audit.py`

- [ ] **Step 1: Write the failing test**
```python
# test_pipeline.py — concurrency is passed to BOTH fan-out stages, reconcile stays single-call
def test_run_audit_passes_concurrency_to_fanout(tmp_path, monkeypatch):
    import framework_cli.review.audit.pipeline as pl
    seen = []
    real = pl.run_stage
    def spy(*a, **k): seen.append(k.get("concurrency")); return real(*a, **k)
    monkeypatch.setattr(pl, "run_stage", spy)
    from tests.review.audit.conftest import StubBackend
    run_audit(["security"], backend=StubBackend(_scripted), root=Path.cwd(),
              baseline_dir=None, out_dir=tmp_path/"o", skeptics=1, concurrency=5)
    assert seen == [5, 5]  # stage1 + stage3 both got concurrency=5
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement.** Add `concurrency: int = 1` to `run_audit`; pass `concurrency=concurrency` to BOTH `run_stage` calls (Stage 1 + Stage 3). Reconcile is untouched (single call). In `cli.py`, add `concurrency: int = typer.Option(6, "--concurrency", help="Parallel audit/refute calls (1 = serial).")` and pass `concurrency=concurrency` to `run_audit`.

- [ ] **Step 4: Run → PASS** + `uv run pytest tests/review/audit/ tests/test_cli_reviewer_audit.py -q`.

- [ ] **Step 5: Commit.**

---

# Phase H3 — Agent-name normalization

### Task H3.1: `reconcile` normalizes + validates agent names

**Files:** Modify `src/framework_cli/review/audit/stages.py`; Test `tests/review/audit/test_stages.py`

- [ ] **Step 1: Write the failing test**
```python
def test_reconcile_normalizes_review_prefixed_agent_names():
    cl_json = json.dumps({"agents": [
        {"agent": "review-application-logic", "proposed_block_threshold": "info", "edits": [], "fixture_verdicts": {}},
        {"agent": "security", "proposed_block_threshold": "high", "edits": [], "fixture_verdicts": {}},
    ], "preamble_edits": []})
    cl = reconcile([], {"application-logic": "info", "security": "high"}, StubBackend([cl_json]))
    names = {a.agent for a in cl.agents}
    assert names == {"application-logic", "security"}  # review- prefix stripped

def test_reconcile_drops_unknown_agent_with_note():
    cl_json = json.dumps({"agents": [
        {"agent": "totally-made-up", "proposed_block_threshold": "high", "edits": [], "fixture_verdicts": {}},
        {"agent": "security", "proposed_block_threshold": "high", "edits": [], "fixture_verdicts": {}},
    ], "preamble_edits": []})
    seen = []
    cl = reconcile([], {"security": "high"}, StubBackend([cl_json]), log=seen.append)
    assert {a.agent for a in cl.agents} == {"security"}  # unknown dropped
    assert any("totally-made-up" in m for m in seen)
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement.** Add a pure helper + normalize in `reconcile`:
```python
from framework_cli.review.registry import AGENTIC_MODEL, agent_names

def _canonical_agent(name: str) -> str | None:
    """Map a model-emitted agent id to its registry key, or None if unresolvable.
    Strips a leading 'review-' (the AgentSpec.name form) and validates against the roster."""
    known = set(agent_names())
    candidate = name[len("review-"):] if name.startswith("review-") else name
    return candidate if candidate in known else None
```
Give `reconcile` a `log: Callable[[str], None] = lambda _m: None` param. After `_extract_json`/normalization but before `Changelist.from_dict`, rewrite/drop agents:
```python
    kept = []
    for a in parsed.get("agents", []):
        canon = _canonical_agent(str(a.get("agent", "")))
        if canon is None:
            log(f"reconcile: dropped change for unknown agent {a.get('agent')!r}")
            continue
        a["agent"] = canon
        kept.append(a)
    parsed["agents"] = kept
```
(Keep the existing `"null"`-threshold normalization. Import `Callable` from `collections.abc`.)

- [ ] **Step 4: Run → PASS** + full `tests/review/audit/`. Update `run_audit` to pass `log=log` into `reconcile` (so drops surface in CLI output).

- [ ] **Step 5: Commit.**

---

# Phase H4 — Robust apply-preview

### Task H4.1: `render_patch` routes fixture edits to notes + validates hunks

**Files:** Modify `src/framework_cli/review/audit/preview.py`; Test `tests/review/audit/test_preview.py`

- [ ] **Step 1: Write the failing tests**
```python
def test_render_patch_routes_fixture_edits_to_notes_not_hunks():
    # a fixture edit whose `after` is itself a diff must NOT become an inline hunk
    cl = Changelist(agents=[AgentChange("accessibility", None, edits=[
        ProposedEdit(target="fixture", rationale="add good pair",
                     before="(no good fixture)",
                     after="diff --git a/x.tsx b/x.tsx\n--- a/x.tsx\n+++ b/x.tsx\n@@ -1 +1 @@\n-a\n+b\n",
                     path="tests/eval/fixtures/accessibility/good/semantic-button")
    ], fixture_verdicts={})], preamble_edits=[])
    patch = render_patch(cl)
    assert "diff --git a/x.tsx" not in patch          # nested diff not embedded
    assert "tests/eval/fixtures/accessibility/good/semantic-button" in patch  # surfaced as a note
    assert "manual" in patch.lower() or "changelist-full.json" in patch

def test_render_patch_quarantines_non_applying_hunk(tmp_path):
    import subprocess
    subprocess.run(["git","init","-q"], cwd=tmp_path, check=True)
    (tmp_path/"f.md").write_text("real content\n")
    subprocess.run(["git","add","-A"], cwd=tmp_path, check=True)
    cl = Changelist(agents=[AgentChange("x", None, edits=[
        ProposedEdit(target="domain_prompt", rationale="stale before",
                     before="WRONG content\n", after="new\n", path="f.md")  # before != file
    ], fixture_verdicts={})], preamble_edits=[])
    patch = render_patch(cl, root=tmp_path)
    (tmp_path/"p.patch").write_text(patch)
    # whatever we emit must apply cleanly (the bad hunk is quarantined to notes)
    r = subprocess.run(["git","apply","--check","p.patch"], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

def test_render_patch_valid_domain_edit_still_applies(tmp_path):
    import subprocess
    subprocess.run(["git","init","-q"], cwd=tmp_path, check=True)
    (tmp_path/"f.md").write_text("alpha\nbeta\n")
    subprocess.run(["git","add","-A"], cwd=tmp_path, check=True)
    cl = Changelist(agents=[AgentChange("x", None, edits=[
        ProposedEdit(target="domain_prompt", rationale="ok",
                     before="alpha\nbeta\n", after="alpha\nBETA\n", path="f.md")
    ], fixture_verdicts={})], preamble_edits=[])
    patch = render_patch(cl, root=tmp_path)
    assert "+alpha" not in patch or "BETA" in patch  # a real hunk was emitted
    (tmp_path/"p.patch").write_text(patch)
    assert subprocess.run(["git","apply","--check","p.patch"], cwd=tmp_path).returncode == 0
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement.** Change `render_patch(changelist, root: Path | None = None)`:
  - Drop `"fixture"` from `_TEXTUAL` — a fixture edit is NOT a simple before/after text edit. Route every `fixture` edit to a note: `f"# {label}: rewrite fixture {edit.path} ({edit.rationale}) — see changelist-full.json"`.
  - Keep `domain_prompt`/`rubric` in `_TEXTUAL`.
  - When `root` is given, validate each candidate textual hunk by writing it to a temp file and running `git apply --check` in `root`; if it fails, route that edit to a note (`f"# {label}: {edit.target} edit did not apply cleanly ({edit.rationale}) — see changelist-full.json"`) instead of the patch body. When `root` is None, keep today's best-effort behavior (emit the hunk unvalidated).
  - Helper:
```python
import subprocess, tempfile
def _hunk_applies(hunk: str, root: Path) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as tf:
        tf.write(hunk); p = tf.name
    try:
        return subprocess.run(["git", "apply", "--check", p], cwd=root,
                              capture_output=True, text=True).returncode == 0
    finally:
        Path(p).unlink(missing_ok=True)
```
  Assemble the final patch from validated hunks only; everything else (fixture edits, non-applying hunks) goes to the notes block. Guarantee: when `root` is given, the emitted patch passes `git apply --check`.

- [ ] **Step 4: Run → PASS** + full `tests/review/audit/`.

- [ ] **Step 5: Commit.**

### Task H4.2: CLI passes `root` to `render_patch`

**Files:** Modify `src/framework_cli/cli.py`; Test `tests/test_cli_reviewer_audit.py`

- [ ] **Step 1:** In the `reviewer-audit` command, change `render_patch(cl)` → `render_patch(cl, root=Path.cwd())` so the emitted `apply-preview.patch` is validated against the real repo.
- [ ] **Step 2:** Existing CLI tests stay green (the StubBackend produces no edits, so the patch is empty/clean). Run `uv run pytest tests/test_cli_reviewer_audit.py -q`.
- [ ] **Step 3: Commit.**

---

# Phase H5 — Gate + branch-end review + PR

- [ ] **Step 1: Full gate.** `TMPDIR=/var/tmp uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src`.
- [ ] **Step 2: Optional live smoke** (subagent backend, cheap): `framework reviewer-audit security --concurrency 1 --out /tmp/ra-h-smoke` — confirm progress lines appear + a clean (possibly empty) `apply-preview.patch`. Then `framework reviewer-audit accessibility contracts --concurrency 4 --out /tmp/ra-h-smoke2` to exercise concurrency on real backends if quota allows; skip-neutral without a backend.
- [ ] **Step 3:** Update PLAN.md (add an FWK item for the hardening; the roadmap `Next` currently empty) + ACTION_LOG entry.
- [ ] **Step 4:** Branch-end Sonnet spec review + Opus whole-branch quality review; address findings; open PR (protected master; required checks gate+build+render-complete).

---

## Self-Review
- **Coverage:** H1 (instrumentation) → H1.1–H1.3; H2 (concurrency) → H2.1–H2.2; H3 (name normalize) → H3.1; H4 (preview robustness) → H4.1–H4.2. All four shakedown findings mapped.
- **Type/signature consistency:** `run_stage(..., label, log, concurrency)` defined in H1.1/H2.1 and called with those kwargs in H1.2/H2.2; `run_audit(..., log, concurrency)` consistent H1.2/H2.2; `reconcile(..., log)` H3.1 + caller updated; `render_patch(changelist, root=None)` H4.1 + caller H4.2. `_canonical_agent`/`_hunk_applies` are new pure helpers.
- **No placeholders:** every code step shows the change. The two "adapt to how the existing test reads output / `_scripted`" notes are explicit reconciliation steps, not deferred work.
- **Ordering:** H1 before H2 (shared `log`/`label` params); H3/H4 independent. Each phase is independently green + committable.
