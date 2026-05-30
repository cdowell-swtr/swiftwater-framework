# Local Reviewers — Slice E2 (gate + PreToolUse hook + template shipping) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Slice E1's audit machinery into a pre-commit safety net — `/reviewers:gate` (affected-only audit + marker), a `PreToolUse` hook that auto-dispatches the gate on AI commits, and template shipping so generated projects inherit the same local-first gate.

**Architecture:** `eval-prepare --mode gate` derives affected agents from staged files (per the mapping in the spec), emits a work-item list scoped to those agents plus a `staged_hash` for the marker. `eval-finalize --mode gate` writes the per-call records, runs `eval-analyze --strict` (fail on drift), computes the verdict, writes `.framework/audit/marker.json`. A shell script at `.claude/hooks/reviewers-gate-check.sh` reads the marker, recomputes the staged hash, and blocks the AI's `git commit` Bash call with a directive when the marker is stale, failed, or absent. The same surface (audit, gate, workflows, hook, settings) ships to generated projects via the template.

**Tech Stack:** Python 3.12, Typer, JS (workflow scripts), Bash (the hook check), markdown (slash command files), Copier/Jinja (template shipping), `pytest`.

**Spec:** `docs/superpowers/specs/2026-05-29-local-reviewers-design.md`
**Depends on:** Slice E1 (merged) — uses `eval-prepare`/`eval-finalize`/`reviewers-audit.js` infrastructure.

---

## File Structure

**New files:**
- `.claude/workflows/reviewers-gate.js` (create) — copy of `reviewers-audit.js` with a different phase label; could share if appropriate.
- `.claude/commands/reviewers/gate.md` (create) — slash command definition.
- `.claude/hooks/reviewers-gate-check.sh` (create) — the hook's shell script.
- `src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja` (create) — template-side audit command.
- `src/framework_cli/template/.claude/commands/reviewers/gate.md.jinja` (create) — template-side gate command.
- `src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja` (create) — template-side audit workflow.
- `src/framework_cli/template/.claude/workflows/reviewers-gate.js.jinja` (create) — template-side gate workflow.
- `src/framework_cli/template/.claude/hooks/reviewers-gate-check.sh.jinja` (create) — template-side hook script.

**Modified files:**
- `src/framework_cli/cli.py` (modify) — extend `eval-prepare` and `eval-finalize` with gate mode (incl. regrade special case for thresholds-only changes).
- `.claude/settings.json` (modify) — add the `reviewers-gate-check.sh` PreToolUse hook entry alongside the existing CLAUDE.md commit-gate.
- `src/framework_cli/template/.claude/settings.json.jinja` (create OR modify if exists) — template version with the hook entry.
- `src/framework_cli/template/.gitignore.jinja` (modify) — add `.framework/audit/`.
- Tests: `tests/test_cli.py`.

---

## Task 1: `eval-prepare --mode gate` (affected-mapping + staged-hash)

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_eval_prepare_gate_affected_single_prompt(tmp_path, monkeypatch):
    """A staged change to one agent's prompt → only that agent in the work items."""
    import framework_cli.cli as cli_mod
    # Simulate: only src/framework_cli/review/agents/security.md is staged.
    monkeypatch.setattr(
        cli_mod,
        "_staged_files",
        lambda: ["src/framework_cli/review/agents/security.md"],
    )
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff content")
    result = runner.invoke(app, ["eval-prepare", "--mode", "gate"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["mode"] == "gate"
    assert data["agents_set"] == ["security"]
    assert len(data["work_items"]) == 1
    assert "staged_hash" in data
    assert data["staged_hash"].startswith("sha256:")


def test_eval_prepare_gate_runner_change_affects_all_bundle(monkeypatch):
    """A staged change to runner.py → all 11 bundle agents."""
    import framework_cli.cli as cli_mod
    monkeypatch.setattr(
        cli_mod, "_staged_files",
        lambda: ["src/framework_cli/review/runner.py"],
    )
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    result = runner.invoke(app, ["eval-prepare", "--mode", "gate"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    # 11 bundle agents (everything not agentic) should be the agent set.
    from framework_cli.review.registry import agent_names, get_agent
    expected = sorted(
        a for a in agent_names() if get_agent(a).context.strategy != "agentic"
    )
    assert sorted(data["agents_set"]) == expected
    assert len(data["work_items"]) == len(expected)


def test_eval_prepare_gate_thresholds_only_signals_regrade(monkeypatch):
    """If the only staged file is tests/eval/fixtures/thresholds.yaml, the manifest
    signals mode='regrade' (no subagent dispatch needed)."""
    import framework_cli.cli as cli_mod
    monkeypatch.setattr(
        cli_mod, "_staged_files", lambda: ["tests/eval/fixtures/thresholds.yaml"]
    )
    result = runner.invoke(app, ["eval-prepare", "--mode", "gate"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["mode"] == "regrade"
    assert data["work_items"] == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "eval_prepare_gate" -v`
Expected: failures (no gate mode in eval-prepare, no `_staged_files` helper).

- [ ] **Step 3: Add `_staged_files` and the affected-mapping helpers** to `src/framework_cli/cli.py`

```python
def _staged_files() -> list[str]:
    """Return the list of files in the staged set (git diff --cached --name-only)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, check=False,
    )
    return [line for line in result.stdout.splitlines() if line]


def _affected_agents(staged: list[str]) -> tuple[str, list[str]]:
    """Return (mode, agents_set). mode is 'gate', 'regrade', or 'noop'."""
    from framework_cli.review.registry import agent_names, get_agent

    if not staged:
        return ("noop", [])
    # Thresholds-only → regrade
    review_relevant = {p for p in staged if _is_review_relevant(p)}
    if review_relevant == {"tests/eval/fixtures/thresholds.yaml"}:
        return ("regrade", [])
    if not review_relevant:
        return ("noop", [])

    all_agents = agent_names()
    bundle_agents = [a for a in all_agents if get_agent(a).context.strategy != "agentic"]
    agentic_agents = [a for a in all_agents if get_agent(a).context.strategy == "agentic"]
    affected: set[str] = set()
    for path in review_relevant:
        # Per-agent prompt
        if path.startswith("src/framework_cli/review/agents/") and path.endswith(".md"):
            name = Path(path).stem
            if name in all_agents:
                affected.add(name)
            continue
        # Per-agent fixture
        if path.startswith("tests/eval/fixtures/"):
            parts = Path(path).parts
            if len(parts) >= 4:  # tests/eval/fixtures/<agent>/<kind>/<case>/<file>
                name = parts[3]
                if name in all_agents:
                    affected.add(name)
            continue
        # runner.py → all bundle
        if path == "src/framework_cli/review/runner.py":
            affected.update(bundle_agents)
            continue
        # agentic.py → all agentic
        if path == "src/framework_cli/review/agentic.py":
            affected.update(agentic_agents)
            continue
        # context.py / findings.py / registry.py → all
        if path in (
            "src/framework_cli/review/context.py",
            "src/framework_cli/review/findings.py",
            "src/framework_cli/review/registry.py",
        ):
            affected.update(all_agents)
            continue
        # template/** → all (fixtures render from template)
        if path.startswith("src/framework_cli/template/"):
            affected.update(all_agents)
            continue
    return ("gate", sorted(affected))


def _is_review_relevant(path: str) -> bool:
    """True if `path` is one of the review-relevant paths the gate cares about."""
    if path.startswith("src/framework_cli/review/"):
        return True
    if path.startswith("src/framework_cli/template/"):
        return True
    if path.startswith("tests/eval/fixtures/"):
        return True
    return False


def _staged_hash(staged: list[str]) -> str:
    """sha256 of concatenated staged review-relevant file contents (sorted by path)."""
    import hashlib
    h = hashlib.sha256()
    for p in sorted(staged):
        if not _is_review_relevant(p):
            continue
        try:
            content = subprocess.run(
                ["git", "show", f":{p}"],  # the staged blob's content
                capture_output=True, text=True, check=False,
            ).stdout
        except Exception:
            content = ""
        h.update(p.encode())
        h.update(b"\x00")
        h.update(content.encode())
        h.update(b"\x00")
    return "sha256:" + h.hexdigest()
```

- [ ] **Step 4: Extend `eval-prepare` to accept `--mode gate`**

In the `eval_prepare` Typer command, add a branch:

```python
    if mode == "gate":
        _emit_gate_prep()
        return
```

And implement `_emit_gate_prep()`:

```python
def _emit_gate_prep() -> None:
    """Emit a gate-mode manifest from the current staged set."""
    staged = _staged_files()
    detected_mode, agents = _affected_agents(staged)
    if detected_mode == "noop":
        manifest = {
            "mode": "noop",
            "agents_set": [],
            "work_items": [],
            "staged_hash": _staged_hash(staged),
            "output_dir": ".framework/audit/latest",
        }
        typer.echo(json.dumps(manifest, indent=2))
        return
    if detected_mode == "regrade":
        manifest = {
            "mode": "regrade",
            "agents_set": [],
            "work_items": [],
            "staged_hash": _staged_hash(staged),
            "output_dir": ".framework/audit/latest",
        }
        typer.echo(json.dumps(manifest, indent=2))
        return
    # Build work items for each affected agent (same shape as audit-mode items)
    from framework_cli.review.context import assemble
    diff = _review_diff()
    root = Path.cwd()
    work_items: list[dict] = []
    for a in agents:
        try:
            spec = get_agent(a)
        except KeyError:
            continue
        work_items.append(_build_audit_work_item(spec, diff, root))
    manifest = {
        "mode": "gate",
        "agents_set": agents,
        "work_items": work_items,
        "staged_hash": _staged_hash(staged),
        "output_dir": ".framework/audit/latest",
    }
    typer.echo(json.dumps(manifest, indent=2))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "eval_prepare_gate" -v`
Expected: 3 passed.

- [ ] **Step 6: Quality gate + commit** (with CLAUDE.md update)

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest tests/test_cli.py -q
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git commit -m "feat(eval-prepare): gate mode — affected-agent mapping + staged hash

eval-prepare --mode gate computes affected agents from the staged set per
the spec's mapping (prompt → that agent, runner.py → all bundle, etc.) and
emits the work items + a sha256 staged_hash that the marker keys on.
Special case: thresholds.yaml-only changes signal mode='regrade' so the
gate skips subagent dispatch.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: `eval-finalize --mode gate` (marker.json + verdict)

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_eval_finalize_gate_writes_marker_pass(tmp_path):
    """gate-mode finalize writes marker.json with verdict=PASS when no high+ findings."""
    out = tmp_path / "audit"
    out.mkdir()
    results = [
        {
            "agent": "security", "findings": [],
            "usage": {}, "latency_ms": None, "stop_reason": "end_turn",
            "raw_text": "[]", "turns": 1, "tool_calls": [],
        },
    ]
    payload = {
        "results": results,
        "meta": {
            "mode": "gate", "staged_hash": "sha256:abc", "agents_set": ["security"],
        },
    }
    results_file = tmp_path / "results.json"
    results_file.write_text(_json.dumps(payload))
    result = runner.invoke(
        app, ["eval-finalize", "--mode", "gate", "--results", str(results_file),
              "--out-dir", str(out)],
    )
    assert result.exit_code == 0, result.output
    marker_path = out.parent / "marker.json"
    assert marker_path.is_file()
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "PASS"
    assert marker["staged_hash"] == "sha256:abc"
    assert marker["agents_run"] == ["security"]
    assert marker["drift_detected"] is False


def test_eval_finalize_gate_writes_marker_fail_on_high_finding(tmp_path):
    """A high-severity finding on security (block_threshold='high') → verdict=FAIL."""
    out = tmp_path / "audit"
    out.mkdir()
    results = [
        {
            "agent": "security",
            "findings": [
                {"path": "a.py", "line": 1, "severity": "high",
                 "message": "secret", "suggestion": None},
            ],
            "usage": {}, "latency_ms": None, "stop_reason": "end_turn",
            "raw_text": "[]", "turns": 1, "tool_calls": [],
        },
    ]
    payload = {"results": results,
               "meta": {"mode": "gate", "staged_hash": "sha256:abc",
                        "agents_set": ["security"]}}
    results_file = tmp_path / "results.json"
    results_file.write_text(_json.dumps(payload))
    result = runner.invoke(
        app, ["eval-finalize", "--mode", "gate", "--results", str(results_file),
              "--out-dir", str(out)],
    )
    assert result.exit_code == 0, result.output  # finalize itself succeeds
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "FAIL"


def test_eval_finalize_gate_marks_drift_detected(tmp_path):
    """A tool_calls entry using a disallowed tool → drift_detected: true in marker."""
    out = tmp_path / "audit"
    out.mkdir()
    results = [
        {
            "agent": "architecture", "findings": [],
            "usage": {}, "latency_ms": None, "stop_reason": "end_turn",
            "raw_text": "[]", "turns": 2,
            "tool_calls": [{"turn": 1, "tool": "Bash", "input": {"command": "ls"}}],
        },
    ]
    payload = {"results": results,
               "meta": {"mode": "gate", "staged_hash": "sha256:abc",
                        "agents_set": ["architecture"]}}
    results_file = tmp_path / "results.json"
    results_file.write_text(_json.dumps(payload))
    result = runner.invoke(
        app, ["eval-finalize", "--mode", "gate", "--results", str(results_file),
              "--out-dir", str(out)],
    )
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["drift_detected"] is True
    assert marker["verdict"] == "FAIL"


def test_eval_finalize_gate_regrade_skips_dispatch(tmp_path):
    """A regrade-mode payload re-flags existing findings against current thresholds
    without invoking subagents."""
    out = tmp_path / "audit"
    out.mkdir()
    (out / "findings").mkdir()
    (out / "findings" / "security.json").write_text(_json.dumps({
        "agent": "security", "findings": [],
        "usage": {}, "latency_ms": None, "stop_reason": "end_turn",
        "raw_text": "[]", "turns": 1, "tool_calls": [],
    }))
    payload = {"results": [],
               "meta": {"mode": "regrade", "staged_hash": "sha256:abc"}}
    results_file = tmp_path / "results.json"
    results_file.write_text(_json.dumps(payload))
    result = runner.invoke(
        app, ["eval-finalize", "--mode", "gate", "--results", str(results_file),
              "--out-dir", str(out)],
    )
    assert result.exit_code == 0, result.output
    marker_path = out.parent / "marker.json"
    marker = _json.loads(marker_path.read_text())
    assert marker["verdict"] == "PASS"  # empty findings → PASS
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "eval_finalize_gate" -v`
Expected: 4 failures (no gate-mode branch).

- [ ] **Step 3: Extend `eval_finalize` and add `_finalize_gate`** in `src/framework_cli/cli.py`

In the existing `eval_finalize` command, add:

```python
    elif mode == "gate":
        _finalize_gate(records, findings_dir, out, meta_in)
```

And implement `_finalize_gate`:

```python
def _finalize_gate(records: list, findings_dir: Path, out: Path, meta_in: dict) -> None:
    """Write records (if any), compute verdict, write marker.json."""
    from datetime import datetime, timezone

    from framework_cli.review import analyze
    from framework_cli.review.evals import flags
    from framework_cli.review.registry import get_agent

    actual_mode = meta_in.get("mode", "gate")
    staged_hash = meta_in.get("staged_hash", "")
    agents_run = meta_in.get("agents_set", [])

    # In gate mode (non-regrade), write per-agent records first.
    if actual_mode == "gate":
        for r in records:
            record = {
                "agent": r["agent"],
                "findings": r.get("findings", []),
                "usage": r.get("usage", {}),
                "latency_ms": r.get("latency_ms"),
                "stop_reason": r.get("stop_reason"),
                "raw_text": r.get("raw_text", ""),
                "turns": r.get("turns", 1),
                "tool_calls": r.get("tool_calls", []),
            }
            (findings_dir / f"{r['agent']}.json").write_text(
                json.dumps(record, indent=2, sort_keys=True)
            )

    # Load all records under findings_dir (works for regrade too).
    loaded = analyze.load_records(findings_dir)

    # Compute verdict: any agent's findings include a finding at/above its block_threshold?
    failing = False
    summary_parts: list[str] = []
    for r in loaded:
        try:
            spec = get_agent(r.agent)
        except KeyError:
            continue
        from framework_cli.review.findings import Finding
        findings_objs = [
            Finding(f["path"], int(f["line"]), f["severity"], f["message"], f.get("suggestion"))
            for f in r.findings
        ]
        if flags(findings_objs, spec):
            failing = True
            summary_parts.append(f"{r.agent}:{len([f for f in findings_objs])}")
    drifts = analyze.drift_check(loaded)
    drift_detected = bool(drifts)
    verdict = "FAIL" if failing or drift_detected else "PASS"
    if drift_detected and not failing:
        summary_parts.append("drift")

    # marker.json lives at .framework/audit/marker.json (sibling to latest/)
    marker_path = out.parent / "marker.json"
    marker = {
        "staged_hash": staged_hash,
        "agents_run": agents_run,
        "verdict": verdict,
        "drift_detected": drift_detected,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": "; ".join(summary_parts)
                   or f"{len(agents_run)} agents · 0 findings above block threshold",
    }
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(marker, indent=2, sort_keys=True))
    typer.echo(f"eval-finalize: verdict={verdict}, marker={marker_path}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "eval_finalize_gate" -v`
Expected: 4 passed.

- [ ] **Step 5: Quality gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest tests/test_cli.py -q
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git commit -m "feat(eval-finalize): gate mode — write marker.json with verdict + drift_detected

Computes the gate's verdict (any high+ finding above the agent's block_threshold
OR any drift detected → FAIL; else PASS) and writes .framework/audit/marker.json
with the staged_hash, agents_run, verdict, drift flag, timestamp, summary.
Regrade mode reuses the existing findings under .framework/audit/latest/findings/
without dispatching subagents.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: `reviewers-gate.js` workflow

**Files:**
- Create: `.claude/workflows/reviewers-gate.js`

Same shape as `reviewers-audit.js` (one call per agent), labeled for the Gate phase.

- [ ] **Step 1: Write the workflow** at `.claude/workflows/reviewers-gate.js`

```javascript
export const meta = {
  name: 'reviewers-gate',
  description: 'Affected-only audit dispatched by /reviewers:gate before commits.',
  phases: [
    { title: 'Gate', detail: 'one subagent call per affected agent, in parallel' },
  ],
}

phase('Gate')

const items = args.work_items
if (!Array.isArray(items)) {
  throw new Error('reviewers-gate: args.work_items must be an array')
}
if (items.length === 0) {
  // No affected agents → trivial PASS (the caller handles the noop case).
  return { results: [], meta: args.meta || {} }
}

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'line', 'severity', 'message'],
        properties: {
          path: { type: 'string' },
          line: { type: 'integer' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'info'] },
          message: { type: 'string' },
          suggestion: { type: ['string', 'null'] },
        },
      },
    },
  },
}

const results = await parallel(items.map((item) => async () => {
  const sys = item.system_blocks.map(b => b.text).join('\n\n')
  const prompt = `${sys}\n\n${item.user_message}`
  const label = `gate:${item.agent}`
  try {
    const out = await agent(prompt, {
      label,
      phase: 'Gate',
      schema: FINDINGS_SCHEMA,
      agentType: item.subagent_type,
    })
    return {
      agent: item.agent,
      findings: out.findings,
      usage: {},
      latency_ms: null,
      stop_reason: 'end_turn',
      raw_text: JSON.stringify(out.findings),
      turns: 1,
      tool_calls: [],
    }
  } catch (e) {
    log(`gate agent call failed for ${label}: ${e.message}`)
    return null
  }
}))

return { results: results.filter(Boolean), meta: args.meta || {} }
```

- [ ] **Step 2: Commit** (with CLAUDE.md update)

```bash
git add .claude/workflows/reviewers-gate.js CLAUDE.md
git commit -m "feat(workflows): reviewers-gate.js for affected-only gate dispatch

Mirrors reviewers-audit.js but labeled for the Gate phase and tolerant of
empty work_items (the regrade and noop cases return without dispatching).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: `/reviewers:gate` slash command

**Files:**
- Create: `.claude/commands/reviewers/gate.md`

- [ ] **Step 1: Write the slash command** at `.claude/commands/reviewers/gate.md`

```markdown
---
description: Pre-commit gate. Affected-only review of the staged set, writes the marker the PreToolUse hook reads. Usually invoked automatically by the hook, but can be run manually to pre-warm.
---

You are running `/reviewers:gate`. Your job: evaluate the staged set with the affected review agents, write `.framework/audit/marker.json`.

**Steps:**

1. **Run eval-prepare**:
   ```bash
   uv run framework eval-prepare --mode gate > /tmp/reviewers-gate-prep.json
   ```

2. **Read the prep manifest**.

3. **Branch on mode**:

   **If `mode == "noop"`** (no review-relevant files staged):
   - Run eval-finalize directly (it writes a PASS marker with empty agents_run):
     ```bash
     echo '{"results": [], "meta": '$(cat /tmp/reviewers-gate-prep.json | jq '{mode, staged_hash, agents_set}')'}' > /tmp/reviewers-gate-results.json
     uv run framework eval-finalize --mode gate \
       --results /tmp/reviewers-gate-results.json \
       --out-dir .framework/audit/latest
     ```
   - Print: "Gate noop — no review-relevant changes."
   - DONE.

   **If `mode == "regrade"`** (only thresholds.yaml staged):
   - Run eval-finalize directly (it re-flags existing findings against current thresholds):
     ```bash
     echo '{"results": [], "meta": '$(cat /tmp/reviewers-gate-prep.json | jq '{mode, staged_hash, agents_set}')'}' > /tmp/reviewers-gate-results.json
     uv run framework eval-finalize --mode gate \
       --results /tmp/reviewers-gate-results.json \
       --out-dir .framework/audit/latest
     ```
   - Print: "Gate regrade — re-flagged existing findings against new thresholds."
   - DONE.

   **If `mode == "gate"`** (the normal case):
   - Print a one-line summary: "Gate: N affected agents (<list>). Dispatching..."
   - If N > 30, confirm with the user.

4. **Invoke the Workflow tool** (`name: "reviewers-gate"`, `args:` the prep manifest).

5. **Write the workflow's `{results, meta}` to a temp file** (`/tmp/reviewers-gate-results.json`).

6. **Run eval-finalize**:
   ```bash
   uv run framework eval-finalize --mode gate \
     --results /tmp/reviewers-gate-results.json \
     --out-dir .framework/audit/latest
   ```

7. **Print the verdict** from `.framework/audit/marker.json`:
   - PASS: "Gate PASS — marker written. Commit can proceed."
   - FAIL: "Gate FAIL — see `.framework/audit/latest/audit-report.md` for findings."

**Important notes:**
- This command is usually invoked automatically by the PreToolUse hook when you (Claude) try to commit. You can also invoke it manually to pre-warm the marker before a commit.
- The output is **ephemeral** — `.framework/audit/` is gitignored.
- The hook reads `.framework/audit/marker.json` to decide whether to allow the commit; if you skip running the gate, the hook will block your commit until you run it.
```

- [ ] **Step 2: Commit** (with CLAUDE.md update)

```bash
git add .claude/commands/reviewers/gate.md CLAUDE.md
git commit -m "feat(commands): /reviewers:gate slash command — affected-only gate dispatch

Handles all three eval-prepare modes (gate/regrade/noop). The PreToolUse hook
auto-invokes this; it can also be run manually to pre-warm the marker.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: PreToolUse hook shell script

**Files:**
- Create: `.claude/hooks/reviewers-gate-check.sh`

- [ ] **Step 1: Create `.claude/hooks/` directory**

```bash
mkdir -p .claude/hooks
```

- [ ] **Step 2: Write the hook script** at `.claude/hooks/reviewers-gate-check.sh`

```bash
#!/usr/bin/env bash
# PreToolUse hook: matches Bash tool calls containing `git commit`. Reads
# .framework/audit/marker.json and decides allow vs block based on:
#   - staged_hash matches the current review-relevant staged set
#   - verdict is PASS
#   - drift_detected is false
# On any failure, blocks with a directive Claude reads and acts on.

set -euo pipefail

# Only fire on `git commit` invocations.
grep -Eq '(^|[^[:alnum:]_])git[[:space:]]+([^[:space:]].*[[:space:]]+)?commit([^[:alnum:]_]|$)' || exit 0

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root"

marker=".framework/audit/marker.json"
if [ ! -f "$marker" ]; then
  echo "Pre-commit gate not run for current staged set. Invoke /reviewers:gate, then retry this commit." >&2
  exit 2
fi

# Recompute staged_hash from the current staged set.
current_hash=$(uv run python -c "
import sys, subprocess
from pathlib import Path
sys.path.insert(0, 'src')
from framework_cli.cli import _staged_files, _staged_hash
print(_staged_hash(_staged_files()))
" 2>/dev/null) || {
  echo "Pre-commit gate: could not compute staged hash (uv run failed?). Invoke /reviewers:gate manually, then retry." >&2
  exit 2
}

marker_hash=$(uv run python -c "
import json, sys
m = json.load(open('$marker'))
print(m.get('staged_hash', ''))
" 2>/dev/null) || marker_hash=""

if [ "$current_hash" != "$marker_hash" ]; then
  echo "Pre-commit gate stale (staged set changed since last gate). Invoke /reviewers:gate, then retry." >&2
  exit 2
fi

verdict=$(uv run python -c "
import json
m = json.load(open('$marker'))
print(m.get('verdict', 'FAIL'))
" 2>/dev/null) || verdict="FAIL"

summary=$(uv run python -c "
import json
m = json.load(open('$marker'))
print(m.get('summary', ''))
" 2>/dev/null) || summary=""

drift=$(uv run python -c "
import json
m = json.load(open('$marker'))
print('true' if m.get('drift_detected', False) else 'false')
" 2>/dev/null) || drift="false"

if [ "$verdict" != "PASS" ]; then
  echo "Pre-commit gate FAILED: $summary. Address findings in .framework/audit/latest/audit-report.md and re-evaluate (re-run /reviewers:gate), then retry. To override (rare): git commit --no-verify." >&2
  exit 2
fi

if [ "$drift" = "true" ]; then
  echo "Drift detected during last gate run: subagent used disallowed tools (see .framework/audit/latest/audit-report.md '## Drift check'). Investigate before committing." >&2
  exit 2
fi

# All checks pass — allow the commit.
exit 0
```

- [ ] **Step 3: Make it executable**

```bash
chmod +x .claude/hooks/reviewers-gate-check.sh
```

- [ ] **Step 4: Smoke test the script** (in a clean state — no marker)

```bash
rm -rf .framework/audit/
# Stage a fake review-relevant file
git stash -u 2>/dev/null || true
echo "test" > src/framework_cli/review/agents/security.md.bak
git add src/framework_cli/review/agents/security.md.bak 2>/dev/null || true
# Run the hook directly (it should fail with "not run for current staged set")
CLAUDE_TOOL_BASH_COMMAND="git commit -m test" bash .claude/hooks/reviewers-gate-check.sh
echo "Exit code: $?"
# Expected: exit 2, stderr message about invoking /reviewers:gate.
# Cleanup
git reset HEAD src/framework_cli/review/agents/security.md.bak 2>/dev/null || true
rm -f src/framework_cli/review/agents/security.md.bak
git stash pop 2>/dev/null || true
```

Note: the hook reads the Bash command from stdin or via env vars depending on CC's contract. Adjust the matcher if needed; the exact mechanism is the CC convention used by the existing CLAUDE.md commit-gate hook in `.claude/settings.json` (an inline grep), which is the model to follow.

- [ ] **Step 5: Commit** (with CLAUDE.md update)

```bash
git add .claude/hooks/reviewers-gate-check.sh CLAUDE.md
git commit -m "feat(hooks): reviewers-gate-check.sh — PreToolUse blocker on git commit

Reads .framework/audit/marker.json, recomputes the staged hash, blocks the
AI's git commit Bash call with a directive when the marker is missing/stale,
fails, or shows drift. Claude reads the directive and invokes /reviewers:gate,
then retries.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Wire the hook into `.claude/settings.json`

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: Update `.claude/settings.json`** to add the gate hook alongside the existing CLAUDE.md commit-gate

Open `.claude/settings.json` and add a SECOND entry to the `PreToolUse` matcher list. The exact JSON shape depends on whether the existing format supports multiple hooks per matcher (which the current file does — it's an array under `"hooks"`). The new entry follows the same pattern as the CLAUDE.md commit-gate; replace the inline command with a path to the script:

```json
{
  "permissions": { /* ...unchanged... */ },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "grep -Eq '(^|[^[:alnum:]_])git[[:space:]]+([^[:space:]].*[[:space:]]+)?commit([^[:alnum:]_]|$)' || exit 0; root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0; git -C \"$root\" diff --cached --name-only 2>/dev/null | grep -qx 'CLAUDE.md' && exit 0; echo 'Commit blocked: update the Current State pointer in CLAUDE.md and stage it (git add CLAUDE.md) before committing.' >&2; exit 2",
            "statusMessage": "Checking CLAUDE.md is current before commit"
          },
          {
            "type": "command",
            "command": "bash \"$(git rev-parse --show-toplevel 2>/dev/null)/.claude/hooks/reviewers-gate-check.sh\"",
            "statusMessage": "Checking review-agent gate before commit"
          }
        ]
      }
    ]
  }
}
```

The hooks run in order; the CLAUDE.md gate fires first (cheap), the reviewers gate fires second (reads marker). If either exits non-zero, the commit is blocked.

- [ ] **Step 2: Verify the file parses as valid JSON**

```bash
uv run python -c "import json; json.load(open('.claude/settings.json'))"
```
Expected: no output (success).

- [ ] **Step 3: Commit** (with CLAUDE.md update)

```bash
git add .claude/settings.json CLAUDE.md
git commit -m "chore(.claude/settings): wire reviewers-gate-check.sh into PreToolUse

Adds the gate hook alongside the existing CLAUDE.md commit-gate. Both fire
on Bash git commit calls; CLAUDE.md gate first (cheap), reviewers gate
second (reads marker). Either non-zero exit blocks the commit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Manual verification — gate end-to-end

**Files:** none (manual smoke test).

- [ ] **Step 1: Test the regrade path**

```bash
cd "/home/chris/Claude Code/Projects/framework/swiftwater-framework"
# Stage only thresholds.yaml (touch it harmlessly)
echo "" >> tests/eval/fixtures/thresholds.yaml
git add tests/eval/fixtures/thresholds.yaml
```

In CC session:
```
/reviewers:gate
```

Verify: command identifies `mode=regrade`, doesn't dispatch subagents, writes a marker with verdict=PASS (assuming existing audit/latest has clean records or no records at all).

Reset:
```bash
git reset HEAD tests/eval/fixtures/thresholds.yaml
git checkout tests/eval/fixtures/thresholds.yaml
```

- [ ] **Step 2: Test the noop path**

```bash
# Stage a non-review-relevant file
touch /tmp/non-review-test.md
cp /tmp/non-review-test.md ./non-review-test.md
git add non-review-test.md
```

In CC session:
```
/reviewers:gate
```

Verify: `mode=noop`, no dispatch, marker written with PASS + empty agents_run.

Cleanup:
```bash
git reset HEAD non-review-test.md
rm non-review-test.md
```

- [ ] **Step 3: Test the normal gate path**

```bash
# Stage a real prompt edit
echo "" >> src/framework_cli/review/agents/security.md
git add src/framework_cli/review/agents/security.md
```

In CC session:
```
/reviewers:gate
```

Verify: `mode=gate`, agents_set=[security], 1 subagent call dispatched, marker written (verdict depends on what subagent finds).

Reset:
```bash
git reset HEAD src/framework_cli/review/agents/security.md
git checkout src/framework_cli/review/agents/security.md
```

- [ ] **Step 4: Test the PreToolUse hook end-to-end**

Set up a stale-marker scenario:
```bash
rm -rf .framework/audit/
# Stage a review-relevant change
echo "" >> src/framework_cli/review/agents/security.md
git add src/framework_cli/review/agents/security.md
```

In CC session, ask Claude to commit:
```
commit this change with message "test gate"
```

Verify:
- Claude invokes Bash `git commit -m "test gate"`.
- Hook blocks with the directive "Pre-commit gate not run...".
- Claude reads the directive, invokes `/reviewers:gate`.
- Gate runs, writes marker (verdict depends on findings).
- Claude retries the commit.
- Hook now allows (PASS) or blocks again (FAIL with findings summary).

Reset:
```bash
git reset HEAD src/framework_cli/review/agents/security.md
git checkout src/framework_cli/review/agents/security.md
rm -rf .framework/audit/
```

- [ ] **Step 5: If the hook misfires or the directive isn't read by Claude**, iterate on the script's stderr message clarity and the matcher pattern. Reference the existing CLAUDE.md commit-gate as the working example.

---

## Task 8: Template shipping — audit + gate + workflows + hook + settings + gitignore

**Files:**
- Create: `src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja`
- Create: `src/framework_cli/template/.claude/commands/reviewers/gate.md.jinja`
- Create: `src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja`
- Create: `src/framework_cli/template/.claude/workflows/reviewers-gate.js.jinja`
- Create: `src/framework_cli/template/.claude/hooks/reviewers-gate-check.sh.jinja`
- Create or modify: `src/framework_cli/template/.claude/settings.json.jinja`
- Modify: `src/framework_cli/template/.gitignore.jinja`

The template versions are essentially copies of the framework-repo files with package-name substitutions where applicable.

- [ ] **Step 1: Create the template `.claude/` structure**

```bash
mkdir -p src/framework_cli/template/.claude/commands/reviewers
mkdir -p src/framework_cli/template/.claude/workflows
mkdir -p src/framework_cli/template/.claude/hooks
```

- [ ] **Step 2: Copy and adapt the audit slash command**

```bash
cp .claude/commands/reviewers/audit.md src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja
```

Then edit the `.jinja` file: replace any framework-specific paths (e.g., `src/framework_cli/`) with their project equivalents. For most of the file, no substitution is needed because the audit slash command uses target auto-detection. Verify by reading the file and confirming no framework-only paths remain.

- [ ] **Step 3: Copy and adapt the gate slash command**

```bash
cp .claude/commands/reviewers/gate.md src/framework_cli/template/.claude/commands/reviewers/gate.md.jinja
```

Same review pass — should be largely unchanged.

- [ ] **Step 4: Copy the workflows**

```bash
cp .claude/workflows/reviewers-audit.js src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja
cp .claude/workflows/reviewers-gate.js src/framework_cli/template/.claude/workflows/reviewers-gate.js.jinja
```

These are self-contained — no framework-specific paths.

- [ ] **Step 5: Copy and adapt the hook script**

```bash
cp .claude/hooks/reviewers-gate-check.sh src/framework_cli/template/.claude/hooks/reviewers-gate-check.sh.jinja
```

Edit: the `uv run python -c "...from framework_cli.cli import _staged_files, _staged_hash..."` block is framework-specific. In a generated project, the equivalent functionality lives elsewhere (the project's CI uses the framework CLI). For the template version, either:
   - Replace the helpers with inline shell equivalents (compute the hash with `sha256sum` over a sorted file list).
   - Or shell out to `uv run framework eval-prepare --mode gate` and parse `staged_hash` from its output.

Recommended: the second approach (shell out to `framework`). Replace the helpers section:

```bash
current_hash=$(uv run framework eval-prepare --mode gate 2>/dev/null | python -c "
import json, sys
print(json.load(sys.stdin).get('staged_hash', ''))
") || {
  echo "Pre-commit gate: could not compute staged hash. Invoke /reviewers:gate manually, then retry." >&2
  exit 2
}
```

Apply the same change to the framework-repo version too for consistency (in a separate commit after this task).

- [ ] **Step 6: Create the template `.claude/settings.json.jinja`** with the hook entry

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$(git rev-parse --show-toplevel 2>/dev/null)/.claude/hooks/reviewers-gate-check.sh\"",
            "statusMessage": "Checking review-agent gate before commit"
          }
        ]
      }
    ]
  }
}
```

Note: the generated project doesn't have the CLAUDE.md commit-gate (that's framework-specific), so the template settings only includes the reviewers gate.

- [ ] **Step 7: Add `.framework/audit/` to the template `.gitignore.jinja`**

```bash
echo "" >> src/framework_cli/template/.gitignore.jinja
echo "# Local reviewers (audit + gate) ephemeral outputs" >> src/framework_cli/template/.gitignore.jinja
echo ".framework/audit/" >> src/framework_cli/template/.gitignore.jinja
```

- [ ] **Step 8: Run the existing template tests to ensure nothing is broken**

```bash
uv run pytest tests/test_copier_runner.py -q
```
Expected: all green. If the test discovers new files in the template, it may need an update — adjust per the existing convention.

- [ ] **Step 9: Commit** (with CLAUDE.md update)

```bash
git add src/framework_cli/template/.claude/ src/framework_cli/template/.gitignore.jinja CLAUDE.md
git commit -m "feat(template): ship /reviewers:audit + /reviewers:gate + PreToolUse hook

Generated projects inherit the same local-first review economics — the
audit/gate slash commands, their workflows, the hook script, and the
.framework/audit/ gitignore entry are all rendered into every new project.
The gate's staged-hash check shells out to 'framework eval-prepare --mode
gate' so the template doesn't need the framework's internal helpers.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: Manual verification — fresh project has working gate

**Files:** none (manual smoke).

- [ ] **Step 1: Render a fresh test project**

```bash
cd /tmp
rm -rf test-gate
uv --directory "/home/chris/Claude Code/Projects/framework/swiftwater-framework" run framework new test-gate
cd test-gate
```

- [ ] **Step 2: Verify the template shipped the artifacts**

```bash
ls -la .claude/commands/reviewers/
ls -la .claude/workflows/
ls -la .claude/hooks/
cat .claude/settings.json | head -30
grep -A1 "audit" .gitignore
```
Expected: all the shipped files are present, gitignore includes `.framework/audit/`.

- [ ] **Step 3: Init git and make a review-relevant change**

```bash
git init -q
git add -A
git commit -qm "initial render"
# Make a change that should affect the project's review agents
echo "# test edit" >> src/test_gate/main.py
git add src/test_gate/main.py
```

- [ ] **Step 4: Open a CC session in `/tmp/test-gate`** and ask Claude to commit

```
commit this change with message "test"
```

Verify:
- The hook fires (no marker exists).
- Hook blocks with the "Pre-commit gate not run" directive.
- Claude invokes `/reviewers:gate`.
- Gate runs, dispatches subagents, writes the project's `.framework/audit/marker.json`.
- Claude retries commit; hook allows or blocks based on findings.

- [ ] **Step 5: Clean up**

```bash
cd /
rm -rf /tmp/test-gate
```

---

## Task 10: Final quality gate + acceptance

**Files:** none.

- [ ] **Step 1: Full quality gate**

```bash
cd "/home/chris/Claude Code/Projects/framework/swiftwater-framework"
uv run pytest -q --ignore=tests/acceptance
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green.

- [ ] **Step 2: Confirm Slice E2 acceptance criteria** from the spec:
   - [x] `/reviewers:gate` correctly identifies affected agents (Task 1 tests + Task 7).
   - [x] `/reviewers:gate` writes `.framework/audit/marker.json` with correct `staged_hash`/`verdict`/`drift_detected` (Task 2 tests + Task 7).
   - [x] `/reviewers:gate` regrade mode skips subagent dispatch when only `thresholds.yaml` is staged (Task 1 test + Task 7).
   - [x] PreToolUse hook blocks AI git commits when marker is missing/stale with the correct directive (Task 7).
   - [x] Claude responds to the block by invoking `/reviewers:gate`, then retrying (Task 7).
   - [x] Hook blocks on FAIL marker with findings summary (Task 7).
   - [x] Template-shipped versions work in a freshly-rendered project (Task 9).
   - [x] `.framework/audit/` is in both `.gitignore` and `.gitignore.jinja` (Task E1-6 + Task E2-8).

- [ ] **Step 3: Update CLAUDE.md** Current State pointer to mark Slice E2 ready-to-merge.

- [ ] **Step 4: Final commit if state-pointer changes pending**

```bash
git add CLAUDE.md
git commit -m "docs(state): Slice E2 complete — local gating safety net ready

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Notes for the implementing engineer

- **The CC PreToolUse hook contract** for getting the Bash command into the hook script: the existing CLAUDE.md commit-gate uses an inline `grep -Eq ...` on the command (so the command is available via shell context somehow). Verify the convention by reading the existing hook entry in `.claude/settings.json` and matching it.
- **The hook script uses `uv run python -c`** to invoke Python helpers; this works in the framework repo because uv + the framework_cli source are both present. In generated projects, the equivalent shells out to `framework eval-prepare` (the project has the `framework` CLI installed as a dev dep per template).
- **Hook ordering** matters: the CLAUDE.md gate runs first (it's about repo hygiene), the reviewers gate runs second (it's about review semantics). If the CLAUDE.md gate blocks, the reviewers gate never runs — that's correct (no point evaluating a commit you can't make).
- **Regrade mode** depends on `.framework/audit/latest/findings/` having recent records. If that's empty (fresh repo, first commit), regrade still produces a PASS marker (no findings means nothing exceeds any threshold). Subsequent runs accumulate state via the normal gate path.
- **For the second `eval-finalize` test (audit-mode from E1)**: it's marked passing in this plan but was actually added in E1. Re-verify it still passes after the gate-mode additions don't accidentally break it.
- **If CC custom-agent-type names** (Explore, general-purpose) change in a future CC release, the workflow scripts and `_build_work_item` need updates. The drift check whitelist (`Read`, `Grep`, `Glob`) is similarly tied to CC's current tool names.
