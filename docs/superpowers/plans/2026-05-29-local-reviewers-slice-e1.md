# Local Reviewers — Slice E1 (infrastructure + tune + audit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build subagent-backed dispatch for the review-agent system and expose it as two slash commands — `/reviewers:tune` (calibration vs fixtures, framework-only) and `/reviewers:audit` (hygiene review vs current code, framework + project) — so the substantive review work happens on CC subagents (subscription quota) instead of the paid Anthropic API.

**Architecture:** Two new Python CLI commands (`eval-prepare`, `eval-finalize`) bracket a `Workflow`-tool dispatch step. `eval-prepare` builds a complete work-item list (rendered diffs + assembled prompts + per-agent subagent type/model); the workflow fans out one `agent()` call per item in parallel; `eval-finalize` writes the per-call JSON records, runs `eval-analyze`, generates `apply.md` and `meta.json`. The agentic tier uses the `Explore` subagent (read-only, has Read/Grep/Glob) with a soft prompt constraint, backed by a hard `drift_check` in `eval-analyze` that flags any disallowed tool usage.

**Tech Stack:** Python 3.12, Typer, JS (workflow scripts), markdown (slash command files), `pytest`. Run all Python tooling via `uv run`.

**Spec:** `docs/superpowers/specs/2026-05-29-local-reviewers-design.md`

---

## File Structure

**New files:**
- `src/framework_cli/review/analyze.py` (modify) — `drift_check`, drift markdown section, audit-shape schema tolerance.
- `src/framework_cli/cli.py` (modify) — `--strict` flag on `eval-analyze`; new `eval-prepare` + `eval-finalize` commands.
- `.claude/workflows/reviewers-tune.js` (create) — fan-out workflow script for tune.
- `.claude/workflows/reviewers-audit.js` (create) — fan-out workflow script for audit.
- `.claude/commands/reviewers/tune.md` (create) — slash command definition.
- `.claude/commands/reviewers/audit.md` (create) — slash command definition.
- `.gitignore` (modify) — add `.framework/audit/`.

**Test files:**
- `tests/test_cli.py` (modify) — tests for drift detection, --strict, schema tolerance, eval-prepare, eval-finalize.

**File naming note:** the slash command files use subdirectory namespacing (`.claude/commands/reviewers/tune.md` → invoked as `/reviewers:tune`). If CC's convention differs in this version, adjust during Task 9's verification.

---

## Task 1: Drift detection in `eval-analyze`

**Files:**
- Modify: `src/framework_cli/review/analyze.py`
- Modify: `src/framework_cli/cli.py` (add `--strict` flag)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests** at the end of `tests/test_cli.py`

```python
def test_drift_check_flags_disallowed_tools(tmp_path):
    """drift_check returns one record per call that used tools outside the local whitelist."""
    from framework_cli.review.analyze import drift_check, Record

    records = [
        Record(
            agent="architecture", kind="bad", case="b1", repeat=0, seeded_file=None,
            findings=[], usage={}, latency_ms=None, stop_reason=None, raw_text="",
            turns=3,
            tool_calls=[
                {"turn": 1, "tool": "Read", "input": {"path": "x"}},
                {"turn": 2, "tool": "Bash", "input": {"command": "ls"}},
                {"turn": 3, "tool": "WebFetch", "input": {"url": "..."}},
            ],
        ),
        Record(
            agent="security", kind="bad", case="b1", repeat=0, seeded_file=None,
            findings=[], usage={}, latency_ms=None, stop_reason=None, raw_text="",
            turns=1, tool_calls=[],
        ),
    ]
    drifts = drift_check(records)
    assert len(drifts) == 1
    assert drifts[0]["agent"] == "architecture"
    assert set(drifts[0]["disallowed_tools"]) == {"Bash", "WebFetch"}
    assert drifts[0]["counts"] == {"Bash": 1, "WebFetch": 1}


def test_eval_analyze_strict_exits_2_on_drift(tmp_path):
    """eval-analyze --strict exits 2 when any drift is detected."""
    d = tmp_path / "f"
    _write_record(
        d, "architecture", "bad", "b1", 0,
        findings=[],
        turns=2,
        tool_calls=[{"turn": 1, "tool": "Bash", "input": {"command": "ls"}}],
    )
    result = runner.invoke(app, ["eval-analyze", str(d), "--strict"])
    assert result.exit_code == 2, result.output
    assert "Drift" in result.output or "drift" in result.output


def test_eval_analyze_strict_exits_0_without_drift(tmp_path):
    """eval-analyze --strict exits 0 when no drift is detected (only Read/Grep/Glob used)."""
    d = tmp_path / "f"
    _write_record(
        d, "architecture", "bad", "b1", 0,
        findings=[],
        turns=2,
        tool_calls=[{"turn": 1, "tool": "Read", "input": {"path": "x"}}],
    )
    result = runner.invoke(app, ["eval-analyze", str(d), "--strict"])
    assert result.exit_code == 0, result.output


def test_eval_analyze_renders_drift_section(tmp_path):
    """The analyze report includes a ## Drift check section listing offending calls."""
    d = tmp_path / "f"
    _write_record(
        d, "architecture", "bad", "b1", 0,
        findings=[],
        turns=2,
        tool_calls=[{"turn": 1, "tool": "Bash", "input": {"command": "ls"}}],
    )
    result = runner.invoke(app, ["eval-analyze", str(d)])
    assert result.exit_code == 1, result.output  # FAIL on agent's score, not exit code 2
    assert "## Drift check" in result.output
    assert "architecture" in result.output
    assert "Bash" in result.output
```

- [ ] **Step 2: Run to verify all three fail**

Run: `uv run pytest tests/test_cli.py -k "drift" -v`
Expected: 4 failures (ImportError on `drift_check`, missing `--strict` flag, missing `## Drift check` section).

- [ ] **Step 3: Add `drift_check` to `src/framework_cli/review/analyze.py`** (add near other diagnosis functions)

```python
_ALLOWED_LOCAL_TOOLS = frozenset({"Read", "Grep", "Glob"})


def drift_check(records: list[Record]) -> list[dict[str, Any]]:
    """Flag any record whose tool_calls include a tool outside the local whitelist
    (Read, Grep, Glob — the CC equivalents of the production read_file/grep/glob sandbox)."""
    out: list[dict[str, Any]] = []
    for r in records:
        disallowed_counts: dict[str, int] = {}
        for tc in r.tool_calls:
            name = tc.get("tool")
            if isinstance(name, str) and name not in _ALLOWED_LOCAL_TOOLS:
                disallowed_counts[name] = disallowed_counts.get(name, 0) + 1
        if disallowed_counts:
            out.append(
                {
                    "agent": r.agent,
                    "case": r.case,
                    "repeat": r.repeat,
                    "disallowed_tools": sorted(disallowed_counts),
                    "counts": disallowed_counts,
                }
            )
    return out
```

- [ ] **Step 4: Add the drift section to `render_markdown`** in `analyze.py` (add after `## Agentic behavior`, before `## Proposed thresholds.yaml`)

```python
    lines.append("## Drift check")
    drifts = drift_check(records)
    if not drifts:
        lines.append("_(no drift detected — all tool calls within the production sandbox)_")
    else:
        for d in drifts:
            tools = ", ".join(f"{t}×{d['counts'][t]}" for t in d["disallowed_tools"])
            lines.append(
                f"- ⚠ `{d['agent']}` / `{d['case']}` r{d['repeat']} — disallowed tools: {tools}"
            )
    lines.append("")
```

Pass `records` through to `render_markdown` if not already; the function signature already takes `records` as its first argument per the existing code.

- [ ] **Step 5: Add `--strict` flag to `eval-analyze`** in `src/framework_cli/cli.py` (the existing `eval_analyze` function)

```python
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit code 2 if any drift is detected (used by the gate context).",
    ),
```

And after the markdown is rendered/printed, before the existing exit:

```python
    if strict:
        drifts = analyze.drift_check(records)
        if drifts:
            typer.echo(
                f"eval-analyze: STRICT failure — {len(drifts)} drifted call(s) "
                f"(see ## Drift check section above)",
                err=True,
            )
            raise typer.Exit(2)
```

- [ ] **Step 6: Run all four tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "drift" -v`
Expected: 4 passed.

- [ ] **Step 7: Run the full quality gate**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest tests/test_cli.py -q`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/review/analyze.py src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git commit -m "feat(analyze): drift_check + --strict flag for local-dispatch fidelity

The local subagent dispatch uses the Explore subagent type, which has tools
beyond the production sandbox (Read/Grep/Glob). A soft prompt constraint
asks it to use only those three, but soft constraints can drift. drift_check
flags any record whose tool_calls include a non-whitelisted tool; --strict
on eval-analyze fails the run on any drift (used by /reviewers:gate to
hard-stop on fidelity issues).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

(Remember to update `CLAUDE.md` Current State pointer first — the commit hook enforces this.)

---

## Task 2: Schema tolerance for audit-shaped records

**Files:**
- Modify: `src/framework_cli/review/analyze.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests** at the end of `tests/test_cli.py`

```python
def test_load_records_tolerates_missing_audit_dimensions(tmp_path):
    """Records without kind/case/repeat (audit shape) load with sensible defaults."""
    from framework_cli.review.analyze import load_records
    import json as _json

    d = tmp_path / "f"
    (d / "security").mkdir(parents=True)
    # Audit-shape record: just agent + findings + telemetry, no kind/case/repeat.
    (d / "security" / "security.json").write_text(_json.dumps({
        "agent": "security",
        "findings": [{"path": "a.py", "line": 1, "severity": "high", "message": "x"}],
        "usage": {"input_tokens": 100, "output_tokens": 10,
                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        "latency_ms": 200,
        "stop_reason": "end_turn",
        "raw_text": "[]",
        "turns": 1,
        "tool_calls": [],
    }))
    records = load_records(d)
    assert len(records) == 1
    r = records[0]
    assert r.agent == "security"
    assert r.kind == "current"          # default for audit
    assert r.case == "security"         # default = agent name
    assert r.repeat == 0


def test_eval_analyze_handles_audit_records_gracefully(tmp_path):
    """eval-analyze on an audit-shape dir produces useful output without crashing
    on the absent fixture dimensions (no recall/fp diagnosis sections)."""
    import json as _json
    d = tmp_path / "f"
    (d / "security").mkdir(parents=True)
    (d / "security" / "security.json").write_text(_json.dumps({
        "agent": "security",
        "findings": [{"path": "a.py", "line": 1, "severity": "high", "message": "x"}],
        "usage": {"input_tokens": 100, "output_tokens": 10,
                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        "latency_ms": 200,
        "stop_reason": "end_turn",
        "raw_text": "[]",
        "turns": 1,
        "tool_calls": [],
    }))
    result = runner.invoke(app, ["eval-analyze", str(d)])
    assert result.exit_code in (0, 1), result.output  # 1 if score FAIL, 0 if PASS
    assert "review-security" in result.output
    assert "## Drift check" in result.output
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "audit_dimensions or audit_records_gracefully" -v`
Expected: failures (current `_REQUIRED = ("agent", "kind", "case", "repeat", "findings")` rejects audit-shape records).

- [ ] **Step 3: Make `load_records` tolerant** in `src/framework_cli/review/analyze.py`

Change `_REQUIRED` and the record construction:

```python
_REQUIRED = ("agent", "findings")  # kind/case/repeat are optional (audit shape)


def load_records(root: Path) -> list[Record]:
    """Load all per-call JSON records under `root`. Skips files missing required keys.
    Tolerant of audit-shape records (no kind/case/repeat dimensions): kind defaults to
    'current', case defaults to the agent name, repeat defaults to 0."""
    records: list[Record] = []
    for f in sorted(root.rglob("*.json")):
        try:
            d = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not all(k in d for k in _REQUIRED):
            continue
        records.append(
            Record(
                agent=d["agent"],
                kind=d.get("kind", "current"),
                case=d.get("case", d["agent"]),
                repeat=int(d.get("repeat", 0)),
                seeded_file=d.get("seeded_file"),
                findings=list(d.get("findings", [])),
                usage=dict(d.get("usage", {})),
                latency_ms=d.get("latency_ms"),
                stop_reason=d.get("stop_reason"),
                raw_text=d.get("raw_text", ""),
                turns=int(d.get("turns", 1)),
                tool_calls=list(d.get("tool_calls", [])),
            )
        )
    return records
```

- [ ] **Step 4: Make `recall_diagnosis` / `fp_diagnosis` skip audit-shape records**

In `recall_diagnosis`:

```python
def recall_diagnosis(records: list[Record]) -> dict[str, list[dict[str, Any]]]:
    """For each bad record: did it catch the seeded defect, and what else did it flag?
    Skips audit-shape records (kind=='current' or no seeded_file)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if r.kind != "bad" or r.seeded_file is None:
            continue
        # ...rest unchanged
```

In `fp_diagnosis`:

```python
def fp_diagnosis(records: list[Record]) -> dict[str, list[dict[str, Any]]]:
    """For each good record that flagged something: the actual findings (= the fp surface).
    Skips audit-shape records (kind=='current')."""
    out: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if r.kind != "good" or not r.findings:
            continue
        # ...rest unchanged
```

- [ ] **Step 5: Make `scorecard` skip agents with no fixture-shape records**

Replace the entire `scorecard()` function with this version (skips audit-shape records inline; skips agents that only have audit-shape data):

```python
def scorecard(
    records: list[Record], thresholds: dict[str, Thresholds]
) -> list[AgentScore]:
    """Re-derive recall/fp per agent from records by re-running `flags()` per call.
    Skips audit-shape records (kind=='current') — they have no ground-truth dimension."""
    by_agent: dict[str, list[Record]] = {}
    for r in records:
        by_agent.setdefault(r.agent, []).append(r)
    out: list[AgentScore] = []
    for agent in sorted(by_agent):
        try:
            spec = get_agent(agent)
        except KeyError:
            continue
        bad_by_case: dict[str, list[int]] = {}
        good_by_case: dict[str, list[int]] = {}
        for r in by_agent[agent]:
            if r.kind not in ("bad", "good"):
                continue  # audit-shape record — no fixture dimension to score
            f = _findings(r)
            blocked = (
                flags(f, spec, file=r.seeded_file)
                if r.kind == "bad"
                else flags(f, spec)
            )
            bucket = bad_by_case if r.kind == "bad" else good_by_case
            bucket.setdefault(r.case, []).append(1 if blocked else 0)
        if not bad_by_case and not good_by_case:
            continue  # agent had only audit-shape data — no scorecard line
        bad_rates = [sum(hits) / len(hits) for hits in bad_by_case.values()]
        good_rates = [sum(hits) / len(hits) for hits in good_by_case.values()]
        thr = thresholds.get(agent, DEFAULT_THRESHOLDS)
        out.append(score_agent(agent, bad_rates, good_rates, thr))
    return out
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "audit_dimensions or audit_records_gracefully" -v`
Expected: 2 passed.

- [ ] **Step 7: Run all existing analyze-related tests to confirm no regression**

Run: `uv run pytest tests/test_cli.py -k "eval_analyze or load_records" -v`
Expected: all passed (including the existing ones that use fixture-shape records).

- [ ] **Step 8: Quality gate**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest tests/test_cli.py -q`
Expected: all green.

- [ ] **Step 9: Commit** (with CLAUDE.md state update)

```bash
git add src/framework_cli/review/analyze.py tests/test_cli.py CLAUDE.md
git commit -m "feat(analyze): tolerate audit-shape records (no kind/case/repeat dims)

Audit records (from /reviewers:audit) have no fixture/repeat dimension —
agents run once against current code, not against seeded fixtures. load_records
defaults missing kind to 'current', case to agent name, repeat to 0. recall/fp
diagnosis sections skip audit-shape records gracefully; scorecard skips agents
with no fixture-shape data. Same eval-analyze command now produces useful
output for both tune dirs and audit dirs.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: `framework eval-prepare` for tune mode

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`

This command outputs the complete work-item list the workflow needs: per (agent × fixture × repeat) tuple, the assembled prompt + diff + subagent type + model.

- [ ] **Step 1: Write the failing test** at the end of `tests/test_cli.py`

```python
def test_eval_prepare_tune_outputs_work_items_for_single_agent(tmp_path, monkeypatch):
    """eval-prepare --mode tune --agent security outputs a JSON list of work items
    with diff + system_blocks + user_message + subagent_type + model per (agent,fixture,repeat)."""
    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n# clean\n")

    import framework_cli.cli as cli_mod
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)

    result = runner.invoke(
        app,
        [
            "eval-prepare",
            "--mode", "tune",
            "--agent", "security",
            "--fixtures", str(tmp_path),
            "--repeat", "2",
        ],
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["mode"] == "tune"
    assert data["agents_set"] == ["security"]
    # 2 fixtures × 2 repeats = 4 items
    assert len(data["work_items"]) == 4
    item = data["work_items"][0]
    assert item["agent"] == "security"
    assert item["kind"] in ("bad", "good")
    assert item["case"] in ("b1", "g1")
    assert item["repeat_idx"] in (0, 1)
    assert item["subagent_type"] == "general-purpose"  # security is bundle tier
    assert item["model"] == "claude-sonnet-4-6"
    assert "system_blocks" in item and len(item["system_blocks"]) >= 2
    assert "user_message" in item
    assert "diff" in item
    assert item["tools_allowed"] is None  # bundle: no tools


def test_eval_prepare_tune_uses_explore_for_agentic_agents(tmp_path, monkeypatch):
    """Agentic-tier agents (e.g., architecture) get subagent_type='Explore' + tools_allowed."""
    _make_fixture(tmp_path, "architecture", "bad", "b1", "+++ b/a.py\n", "a.py")

    import framework_cli.cli as cli_mod
    monkeypatch.setattr(cli_mod, "realize_cached", _fake_realize_cached)

    result = runner.invoke(
        app,
        [
            "eval-prepare",
            "--mode", "tune",
            "--agent", "architecture",
            "--fixtures", str(tmp_path),
            "--repeat", "1",
        ],
    )
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    item = data["work_items"][0]
    assert item["subagent_type"] == "Explore"
    assert item["model"] == "claude-opus-4-8"
    assert item["tools_allowed"] == ["Read", "Grep", "Glob"]
    assert "root_dir" in item  # agentic items carry the rendered root for tool access
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "eval_prepare" -v`
Expected: failures — no `eval-prepare` command exists.

- [ ] **Step 3: Add the `eval-prepare` command** to `src/framework_cli/cli.py`

Place it after the existing `eval-analyze` command. Add `import tempfile` if not already at the top.

```python
@app.command(name="eval-prepare")
def eval_prepare(
    mode: str = typer.Option(
        ..., "--mode", help="'tune' (against fixtures) or 'audit' (against current code)."
    ),
    agent: str = typer.Option(
        "", "--agent", help="Single agent to prepare (default: all from registry / target)."
    ),
    fixtures: str = typer.Option(
        "tests/eval/fixtures", "--fixtures", help="Fixtures root (tune mode only)."
    ),
    repeat: int = typer.Option(
        1, "--repeat", help="Repeats per fixture (tune mode only)."
    ),
    target: str = typer.Option(
        "", "--target", help="'framework' or 'project' (audit mode; default: auto-detect)."
    ),
    output_dir: str = typer.Option(
        "", "--output-dir", help="Output dir for finalize (echoed in the prep manifest)."
    ),
) -> None:
    """Output the complete work-item list for subagent dispatch as JSON to stdout.

    Consumed by the slash command, which passes it to a Workflow tool invocation.
    """
    if mode == "tune":
        _emit_tune_prep(agent, Path(fixtures), repeat, output_dir)
    elif mode == "audit":
        _emit_audit_prep(agent, target, output_dir)
    else:
        typer.echo(f"eval-prepare: invalid --mode '{mode}' (expected 'tune' or 'audit')", err=True)
        raise typer.Exit(2)


def _emit_tune_prep(
    single_agent: str, fixtures_root: Path, repeat: int, output_dir: str
) -> None:
    import tempfile
    from framework_cli.review.context import assemble
    from framework_cli.review.evals import load_fixtures

    targets = [single_agent] if single_agent else agent_names()
    base_dir = Path(tempfile.mkdtemp(prefix="evalprep-"))
    cache: dict = {}

    by_agent: dict[str, list] = {}
    for fx in load_fixtures(fixtures_root):
        by_agent.setdefault(fx.agent, []).append(fx)

    work_items: list[dict] = []
    for a in targets:
        try:
            spec = get_agent(a)
        except KeyError:
            typer.echo(f"eval-prepare: unknown agent '{a}'", err=True)
            raise typer.Exit(1)
        for fx in by_agent.get(a, []):
            root, diff = realize_cached(fx, cache, base_dir)
            for i in range(repeat):
                work_items.append(_build_work_item(spec, fx, i, diff, root))

    manifest = {
        "mode": "tune",
        "agents_set": targets,
        "work_items": work_items,
        "output_dir": output_dir or "",
    }
    typer.echo(json.dumps(manifest, indent=2))


def _build_work_item(spec: object, fx: object, repeat_idx: int, diff: str, root: Path) -> dict:
    """Build one work item: subagent_type + model + assembled prompt + diff + root."""
    from framework_cli.review.context import assemble

    is_agentic = spec.context.strategy == "agentic"  # type: ignore[attr-defined]
    if is_agentic:
        # Agentic: pass diff + agent prompt + tool-use instruction.
        system_blocks = [
            {"text": f"Review this unified diff:\n\n{diff}"},
            {"text": spec.prompt},  # type: ignore[attr-defined]
        ]
        user_message = (
            f"You are reviewing the codebase rooted at: {root}\n\n"
            "Use the Read, Grep, and Glob tools (these only — do NOT use Bash, "
            "WebFetch, WebSearch, or any other tool) to explore the surrounding "
            "code as needed. Use absolute paths starting with the root above for "
            "all tool calls.\n\n"
            "When done, reply with ONLY a JSON array of findings:\n"
            '  [{"path": "...", "line": N, "severity": "...", "message": "...", '
            '"suggestion": "..."}]'
        )
        return {
            "agent": fx.agent,  # type: ignore[attr-defined]
            "kind": fx.kind,  # type: ignore[attr-defined]
            "case": fx.name,  # type: ignore[attr-defined]
            "repeat_idx": repeat_idx,
            "seeded_file": fx.seeded_file,  # type: ignore[attr-defined]
            "subagent_type": "Explore",
            "model": spec.model,  # type: ignore[attr-defined]
            "system_blocks": system_blocks,
            "user_message": user_message,
            "tools_allowed": ["Read", "Grep", "Glob"],
            "root_dir": str(root),
            "diff": diff,
        }
    # Bundle tier: assemble with context_files, single text completion.
    bundle = assemble(diff, root, spec.context, model=spec.model)  # type: ignore[attr-defined]
    system_blocks = [{"text": f"Review this unified diff:\n\n{bundle.diff}"}]
    if bundle.context_files:
        joined = "\n\n".join(f"=== {p} ===\n{c}" for p, c in bundle.context_files)
        note = "\n\n[context truncated to fit the budget]" if bundle.truncated else ""
        system_blocks.append({"text": f"Relevant repository files for context:\n\n{joined}{note}"})
    system_blocks.append({"text": spec.prompt})  # type: ignore[attr-defined]
    return {
        "agent": fx.agent,  # type: ignore[attr-defined]
        "kind": fx.kind,  # type: ignore[attr-defined]
        "case": fx.name,  # type: ignore[attr-defined]
        "repeat_idx": repeat_idx,
        "seeded_file": fx.seeded_file,  # type: ignore[attr-defined]
        "subagent_type": "general-purpose",
        "model": spec.model,  # type: ignore[attr-defined]
        "system_blocks": system_blocks,
        "user_message": "Return your findings as a JSON array only.",
        "tools_allowed": None,
        "root_dir": str(root),
        "diff": diff,
    }


def _emit_audit_prep(single_agent: str, target_arg: str, output_dir: str) -> None:
    # Implemented in Task 4
    raise NotImplementedError("eval-prepare --mode audit lands in Task 4")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "eval_prepare" -v`
Expected: 2 passed.

- [ ] **Step 5: Quality gate**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest tests/test_cli.py -q`
Expected: all green.

- [ ] **Step 6: Commit** (with CLAUDE.md update)

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git commit -m "feat(eval-prepare): tune-mode work-item manifest for subagent dispatch

framework eval-prepare --mode tune emits a JSON list of work items — one per
(agent × fixture × repeat) — each carrying the assembled system blocks, user
message, subagent_type (Explore for agentic, general-purpose for bundle),
model, tools_allowed, and rendered root_dir. The /reviewers:tune slash
command consumes this, passes it to the Workflow tool for fan-out, and
finalizes after.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: `framework eval-prepare` for audit mode

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_eval_prepare_audit_detects_framework_target(tmp_path, monkeypatch):
    """eval-prepare --mode audit auto-detects 'framework' target when run from the framework repo
    (presence of src/framework_cli/ + pyproject.toml name='swiftwater-framework')."""
    import framework_cli.cli as cli_mod
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff content")
    result = runner.invoke(app, ["eval-prepare", "--mode", "audit"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["mode"] == "audit"
    assert data["target"] == "framework"
    # FRAMEWORK_AGENTS: architecture, security, dependency, test-quality, documentation, application-logic
    assert set(data["agents_set"]) >= {"security", "architecture"}
    assert len(data["work_items"]) == len(data["agents_set"])
    item = data["work_items"][0]
    assert item["kind"] == "current"
    assert item["repeat_idx"] == 0


def test_eval_prepare_audit_explicit_target_override(tmp_path, monkeypatch):
    """--target flag forces the target regardless of cwd signals."""
    import framework_cli.cli as cli_mod
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    result = runner.invoke(app, ["eval-prepare", "--mode", "audit", "--target", "framework"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["target"] == "framework"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "eval_prepare_audit" -v`
Expected: failures (NotImplementedError).

- [ ] **Step 3: Implement `_emit_audit_prep` and `_detect_audit_target`** in `cli.py`

```python
def _detect_audit_target(explicit: str) -> str:
    """Return 'framework' or 'project'. Errors loudly if neither matches and no explicit override."""
    if explicit in ("framework", "project"):
        return explicit
    if explicit:
        raise typer.BadParameter(f"--target must be 'framework' or 'project' (got '{explicit}')")
    cwd = Path.cwd()
    if (cwd / "src" / "framework_cli").is_dir() and (cwd / "pyproject.toml").is_file():
        try:
            content = (cwd / "pyproject.toml").read_text()
            if 'name = "swiftwater-framework"' in content:
                return "framework"
        except OSError:
            pass
    if (cwd / ".copier-answers.yml").is_file():
        return "project"
    raise typer.BadParameter(
        "Could not auto-detect target. Pass --target framework or --target project."
    )


def _emit_audit_prep(single_agent: str, target_arg: str, output_dir: str) -> None:
    from framework_cli.review.context import FRAMEWORK_AGENTS, assemble
    from framework_cli.source import read_batteries

    target = _detect_audit_target(target_arg)
    if target == "framework":
        all_agents = sorted(FRAMEWORK_AGENTS)
    else:
        all_agents = active_agents("pull_request", read_batteries(Path(".")))
    if single_agent:
        if single_agent not in all_agents:
            typer.echo(
                f"eval-prepare: agent '{single_agent}' not active for target '{target}'",
                err=True,
            )
            raise typer.Exit(1)
        agents_set = [single_agent]
    else:
        agents_set = all_agents

    diff = _review_diff()  # the existing helper that gets the appropriate diff
    root = Path.cwd()
    work_items: list[dict] = []
    for a in agents_set:
        try:
            spec = get_agent(a)
        except KeyError:
            continue
        work_items.append(_build_audit_work_item(spec, diff, root))

    manifest = {
        "mode": "audit",
        "target": target,
        "agents_set": agents_set,
        "work_items": work_items,
        "output_dir": output_dir or ".framework/audit/latest",
    }
    typer.echo(json.dumps(manifest, indent=2))


def _build_audit_work_item(spec: object, diff: str, root: Path) -> dict:
    """Audit shape: one item per agent (no kind/case/repeat dimension)."""
    is_agentic = spec.context.strategy == "agentic"  # type: ignore[attr-defined]
    if is_agentic:
        system_blocks = [
            {"text": f"Review this unified diff:\n\n{diff}"},
            {"text": spec.prompt},  # type: ignore[attr-defined]
        ]
        user_message = (
            f"You are reviewing the codebase rooted at: {root}\n\n"
            "Use the Read, Grep, and Glob tools (these only — do NOT use Bash, "
            "WebFetch, WebSearch, or any other tool) to explore the code as "
            "needed. Use absolute paths starting with the root above.\n\n"
            "When done, reply with ONLY a JSON array of findings:\n"
            '  [{"path": "...", "line": N, "severity": "...", "message": "...", '
            '"suggestion": "..."}]'
        )
        return {
            "agent": spec.name.removeprefix("review-"),  # type: ignore[attr-defined]
            "kind": "current",
            "case": spec.name.removeprefix("review-"),  # type: ignore[attr-defined]
            "repeat_idx": 0,
            "seeded_file": None,
            "subagent_type": "Explore",
            "model": spec.model,  # type: ignore[attr-defined]
            "system_blocks": system_blocks,
            "user_message": user_message,
            "tools_allowed": ["Read", "Grep", "Glob"],
            "root_dir": str(root),
            "diff": diff,
        }
    from framework_cli.review.context import assemble
    bundle = assemble(diff, root, spec.context, model=spec.model)  # type: ignore[attr-defined]
    system_blocks = [{"text": f"Review this unified diff:\n\n{bundle.diff}"}]
    if bundle.context_files:
        joined = "\n\n".join(f"=== {p} ===\n{c}" for p, c in bundle.context_files)
        note = "\n\n[context truncated to fit the budget]" if bundle.truncated else ""
        system_blocks.append({"text": f"Relevant repository files for context:\n\n{joined}{note}"})
    system_blocks.append({"text": spec.prompt})  # type: ignore[attr-defined]
    short = spec.name.removeprefix("review-")  # type: ignore[attr-defined]
    return {
        "agent": short,
        "kind": "current",
        "case": short,
        "repeat_idx": 0,
        "seeded_file": None,
        "subagent_type": "general-purpose",
        "model": spec.model,  # type: ignore[attr-defined]
        "system_blocks": system_blocks,
        "user_message": "Return your findings as a JSON array only.",
        "tools_allowed": None,
        "root_dir": str(root),
        "diff": diff,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "eval_prepare_audit" -v`
Expected: 2 passed.

- [ ] **Step 5: Quality gate**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest tests/test_cli.py -q`
Expected: all green.

- [ ] **Step 6: Commit** (with CLAUDE.md update)

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git commit -m "feat(eval-prepare): audit-mode work items + framework/project target auto-detect

eval-prepare --mode audit emits one work item per agent (no fixture/repeat
dimension). Auto-detects 'framework' target via src/framework_cli + pyproject
name; 'project' via .copier-answers.yml; errors loudly if neither matches and
no --target is given. Consumed by the /reviewers:audit slash command.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: `framework eval-finalize`

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`

This command takes the workflow's results (passed via a JSON file or stdin) and writes per-call records, runs `eval-analyze`, generates `apply.md` and `meta.json`.

- [ ] **Step 1: Write the failing tests**

```python
def test_eval_finalize_writes_records_runs_analyze_writes_meta(tmp_path):
    """eval-finalize: given workflow results, writes per-call JSON records and a scorecard."""
    out = tmp_path / "scorecard"
    out.mkdir()

    # Simulated workflow result: list of per-call records.
    results = [
        {
            "agent": "security", "kind": "bad", "case": "b1", "repeat_idx": 0,
            "seeded_file": "a.py",
            "findings": [
                {"path": "a.py", "line": 1, "severity": "high", "message": "x", "suggestion": None}
            ],
            "usage": {"input_tokens": 100, "output_tokens": 10,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            "latency_ms": 200, "stop_reason": "end_turn", "raw_text": "[]",
            "turns": 1, "tool_calls": [],
        },
        {
            "agent": "security", "kind": "good", "case": "g1", "repeat_idx": 0,
            "seeded_file": None,
            "findings": [],
            "usage": {"input_tokens": 100, "output_tokens": 5,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            "latency_ms": 150, "stop_reason": "end_turn", "raw_text": "[]",
            "turns": 1, "tool_calls": [],
        },
    ]
    results_file = tmp_path / "results.json"
    results_file.write_text(_json.dumps({"results": results, "meta": {"slug": "test", "repeat": 1}}))

    result = runner.invoke(
        app,
        ["eval-finalize", "--mode", "tune", "--results", str(results_file),
         "--out-dir", str(out)],
    )
    assert result.exit_code == 0, result.output
    # Per-call records written under findings/
    assert (out / "findings" / "security" / "bad" / "b1__r0.json").is_file()
    assert (out / "findings" / "security" / "good" / "g1__r0.json").is_file()
    # Scorecard generated
    assert (out / "scorecard.md").is_file()
    sc = (out / "scorecard.md").read_text()
    assert "review-security" in sc
    # Thresholds proposal extracted
    assert (out / "thresholds.proposal.yaml").is_file()
    # Apply.md generated
    assert (out / "apply.md").is_file()
    # Meta.json with run metadata
    assert (out / "meta.json").is_file()
    meta = _json.loads((out / "meta.json").read_text())
    assert meta["slug"] == "test"
    assert meta["mode"] == "tune"


def test_eval_finalize_audit_mode_writes_audit_report(tmp_path):
    """In audit mode, eval-finalize writes findings/<agent>.json and audit-report.md."""
    out = tmp_path / "audit"
    out.mkdir()
    results = [
        {
            "agent": "security", "findings": [],
            "usage": {"input_tokens": 100, "output_tokens": 5,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            "latency_ms": 150, "stop_reason": "end_turn", "raw_text": "[]",
            "turns": 1, "tool_calls": [],
        },
    ]
    results_file = tmp_path / "results.json"
    results_file.write_text(_json.dumps({"results": results, "meta": {"target": "framework"}}))

    result = runner.invoke(
        app,
        ["eval-finalize", "--mode", "audit", "--results", str(results_file),
         "--out-dir", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert (out / "findings" / "security.json").is_file()
    assert (out / "audit-report.md").is_file()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "eval_finalize" -v`
Expected: failures — no `eval-finalize` command.

- [ ] **Step 3: Add `eval-finalize`** to `src/framework_cli/cli.py`

```python
@app.command(name="eval-finalize")
def eval_finalize(
    mode: str = typer.Option(..., "--mode", help="'tune' or 'audit'."),
    results: str = typer.Option(..., "--results", help="Path to JSON file from the workflow."),
    out_dir: str = typer.Option(..., "--out-dir", help="Output dir to write artifacts."),
) -> None:
    """Take the workflow's results, write per-call JSON records + scorecard/audit-report
    + apply.md (tune) + meta.json."""
    payload = json.loads(Path(results).read_text())
    records = payload["results"]
    meta_in = payload.get("meta", {})
    out = Path(out_dir)
    findings_dir = out / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)

    if mode == "tune":
        _finalize_tune(records, findings_dir, out, meta_in)
    elif mode == "audit":
        _finalize_audit(records, findings_dir, out, meta_in)
    else:
        typer.echo(f"eval-finalize: invalid --mode '{mode}'", err=True)
        raise typer.Exit(2)


def _finalize_tune(records: list, findings_dir: Path, out: Path, meta_in: dict) -> None:
    from framework_cli.review import analyze
    from framework_cli.review.evals import load_thresholds

    for r in records:
        agent_dir = findings_dir / r["agent"] / r["kind"]
        agent_dir.mkdir(parents=True, exist_ok=True)
        case = r["case"]
        i = r["repeat_idx"]
        record = {
            "agent": r["agent"], "kind": r["kind"], "case": case,
            "repeat": i, "seeded_file": r.get("seeded_file"),
            "findings": r.get("findings", []),
            "usage": r.get("usage", {}),
            "latency_ms": r.get("latency_ms"),
            "stop_reason": r.get("stop_reason"),
            "raw_text": r.get("raw_text", ""),
            "turns": r.get("turns", 1),
            "tool_calls": r.get("tool_calls", []),
        }
        (agent_dir / f"{case}__r{i}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True)
        )

    # Generate scorecard.md via analyze
    loaded = analyze.load_records(findings_dir)
    thr = load_thresholds(Path("tests/eval/fixtures/thresholds.yaml"))
    scores = analyze.scorecard(loaded, thr)
    model_map: dict[str, str] = {}
    for r in loaded:
        try:
            model_map[r.agent] = get_agent(r.agent).model
        except KeyError:
            pass
    costs = analyze.cost_report(loaded, model_map)
    recall_diag = analyze.recall_diagnosis(loaded)
    fp_diag = analyze.fp_diagnosis(loaded)
    agentic = analyze.agentic_behavior(loaded)
    proposed = analyze.propose_thresholds(scores)
    md = analyze.render_markdown(loaded, scores, costs, recall_diag, fp_diag, agentic, proposed)
    (out / "scorecard.md").write_text(md)

    # Extract thresholds proposal yaml block
    in_block = False
    yaml_lines: list[str] = []
    for line in md.splitlines():
        if line.startswith("```yaml") and not in_block:
            in_block = True
            continue
        if in_block and line.startswith("```"):
            break
        if in_block:
            yaml_lines.append(line)
    (out / "thresholds.proposal.yaml").write_text("\n".join(yaml_lines) + "\n")

    # apply.md
    (out / "apply.md").write_text(_apply_md_content())

    # meta.json
    drift_detected = len(analyze.drift_check(loaded)) > 0
    meta = {
        "mode": "tune",
        "slug": meta_in.get("slug", ""),
        "repeat": meta_in.get("repeat", 1),
        "agent_count": len({r["agent"] for r in records}),
        "subagent_call_count": len(records),
        "drift_detected": drift_detected,
        "git_ref": meta_in.get("git_ref", ""),
        "model_used": meta_in.get("model_used", ""),
        "run_duration_seconds": meta_in.get("run_duration_seconds", 0),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    typer.echo(f"eval-finalize: wrote {out}")


def _finalize_audit(records: list, findings_dir: Path, out: Path, meta_in: dict) -> None:
    from framework_cli.review import analyze

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
    loaded = analyze.load_records(findings_dir)
    model_map: dict[str, str] = {}
    for r in loaded:
        try:
            model_map[r.agent] = get_agent(r.agent).model
        except KeyError:
            pass
    costs = analyze.cost_report(loaded, model_map)
    agentic = analyze.agentic_behavior(loaded)
    md_lines = ["# Audit report", "", "## Cost (subagent-dispatched, ~$0)", ""]
    md_lines.append("| Agent | Calls | In tok | Out tok |")
    md_lines.append("|---|---|---|---|")
    for agent in sorted(costs):
        c = costs[agent]
        md_lines.append(
            f"| review-{agent} | {c['calls']} | {c['input_tokens']} | {c['output_tokens']} |"
        )
    md_lines.append("")
    md_lines.append("## Findings")
    for r in loaded:
        md_lines.append(f"### review-{r.agent}")
        if not r.findings:
            md_lines.append("_(no findings)_")
        else:
            for f in r.findings:
                md_lines.append(
                    f"- `{f.get('path')}:{f.get('line')}` "
                    f"**{f.get('severity')}** — {f.get('message')}"
                )
        md_lines.append("")
    md_lines.append("## Drift check")
    drifts = analyze.drift_check(loaded)
    if not drifts:
        md_lines.append("_(no drift detected)_")
    else:
        for d in drifts:
            tools = ", ".join(f"{t}×{d['counts'][t]}" for t in d["disallowed_tools"])
            md_lines.append(f"- ⚠ `{d['agent']}` — disallowed tools: {tools}")
    md_lines.append("")
    (out / "audit-report.md").write_text("\n".join(md_lines) + "\n")
    typer.echo(f"eval-finalize: wrote {out}")


def _apply_md_content() -> str:
    return (
        "# Applying these threshold updates\n\n"
        "To apply the proposed values from `thresholds.proposal.yaml`:\n\n"
        "1. Diff `tests/eval/fixtures/thresholds.yaml` against `thresholds.proposal.yaml`.\n"
        "2. For each changed agent, sanity-check the new values against the observed\n"
        "   `recall` / `fp` columns in `scorecard.md`. If a number looks borderline,\n"
        "   prefer the more conservative side (lower recall_min, higher fp_max).\n"
        "3. Copy approved entries into `tests/eval/fixtures/thresholds.yaml`.\n"
        "4. Commit referencing this scorecard dir.\n\n"
        "See `scorecard.md` for the source observations and `findings/` for raw records.\n"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "eval_finalize" -v`
Expected: 2 passed.

- [ ] **Step 5: Quality gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest tests/test_cli.py -q
# update CLAUDE.md
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git commit -m "feat(eval-finalize): write records + scorecard/audit-report + apply.md + meta.json

Takes the workflow's JSON results and writes the dated scorecard dir (tune)
or .framework/audit/latest/ (audit). The slash commands invoke this after
the Workflow tool returns, so the bookkeeping is all Python (no Claude
writing dozens of files via Write tool calls).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: `.gitignore` update

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add `.framework/audit/` to `.gitignore`**

```bash
echo "" >> .gitignore
echo "# Local reviewers (audit + gate) ephemeral outputs" >> .gitignore
echo ".framework/audit/" >> .gitignore
```

- [ ] **Step 2: Verify**

```bash
mkdir -p .framework/audit/latest
echo "test" > .framework/audit/latest/test.txt
git status --short | grep -q ".framework" && echo "PROBLEM" || echo "OK ignored"
rm -rf .framework/
```
Expected: `OK ignored`.

- [ ] **Step 3: Commit** (with CLAUDE.md update)

```bash
git add .gitignore CLAUDE.md
git commit -m "chore(.gitignore): ignore .framework/audit/ (ephemeral local-reviewer outputs)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: `reviewers-tune.js` workflow script

**Files:**
- Create: `.claude/workflows/reviewers-tune.js`

There are no automated tests for the workflow script (it requires the Workflow tool runtime). Verification is via Task 9's manual smoke.

- [ ] **Step 1: Create `.claude/workflows/` directory**

```bash
mkdir -p .claude/workflows
```

- [ ] **Step 2: Write the workflow script** at `.claude/workflows/reviewers-tune.js`

```javascript
export const meta = {
  name: 'reviewers-tune',
  description: 'Fan out (agent × fixture × repeat) calls to subagents and return per-call findings.',
  phases: [
    { title: 'Tune', detail: 'one subagent call per work item, in parallel' },
  ],
}

phase('Tune')

const items = args.work_items
if (!Array.isArray(items) || items.length === 0) {
  throw new Error('reviewers-tune: args.work_items must be a non-empty array')
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

const results = await parallel(items.map((item, idx) => async () => {
  const sys = item.system_blocks.map(b => b.text).join('\n\n')
  const prompt = `${sys}\n\n${item.user_message}`
  const label = `${item.agent}/${item.kind}/${item.case}__r${item.repeat_idx}`
  try {
    const out = await agent(prompt, {
      label,
      phase: 'Tune',
      schema: FINDINGS_SCHEMA,
      agentType: item.subagent_type,
    })
    return {
      agent: item.agent,
      kind: item.kind,
      case: item.case,
      repeat_idx: item.repeat_idx,
      seeded_file: item.seeded_file,
      findings: out.findings,
      // Workflow-level instrumentation: usage/latency/etc are not captured here
      // (the agent() return is just the validated schema). Future improvement.
      usage: {},
      latency_ms: null,
      stop_reason: 'end_turn',
      raw_text: JSON.stringify(out.findings),
      turns: 1,
      tool_calls: [],
    }
  } catch (e) {
    log(`agent call failed for ${label}: ${e.message}`)
    return null
  }
}))

return { results: results.filter(Boolean), meta: args.meta || {} }
```

- [ ] **Step 3: Verify the file syntax is reasonable**

```bash
node --check .claude/workflows/reviewers-tune.js 2>&1 || echo "Note: this file uses Workflow-tool-specific globals (agent, parallel, phase, log, args); node --check may report undefined names — that's expected."
```
Expected: either parses cleanly, or reports undefined globals (which is fine — those are injected by the Workflow runtime).

- [ ] **Step 4: Commit** (with CLAUDE.md update)

```bash
git add .claude/workflows/reviewers-tune.js CLAUDE.md
git commit -m "feat(workflows): reviewers-tune.js fans out per-(agent,fixture,repeat) subagent calls

Each item from eval-prepare's work list becomes one agent() call. Bundle-tier
items use general-purpose subagents (no tools, JSON-only response). Agentic
items use Explore (read-only with Read/Grep/Glob). Schema-validated response.
Returns the collected results for eval-finalize to process.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: `/reviewers:tune` slash command

**Files:**
- Create: `.claude/commands/reviewers/tune.md`

- [ ] **Step 1: Create `.claude/commands/reviewers/` directory**

```bash
mkdir -p .claude/commands/reviewers
```

- [ ] **Step 2: Write the slash command** at `.claude/commands/reviewers/tune.md`

```markdown
---
description: Tune review-agent thresholds by running them against rendered fixtures via local subagents (no paid API). Optional positional arg = single agent name.
---

You are running the `/reviewers:tune` workflow. Your job: dispatch the subagent-backed tune pipeline and produce a calibration scorecard.

**Inputs:**
- Optional positional arg: single agent name (e.g., `security`). No arg = all 18 agents.
- Optional flags: `--repeat N` (default 3), `--slug <name>` (default short git ref).

**Steps:**

1. **Parse the user's arguments** from the slash command invocation. Extract the optional agent name and any flags. Default `--repeat 3`, `--slug <git rev-parse --short HEAD>`.

2. **Compute the output dir:**
   ```bash
   DATE=$(date +%Y-%m-%d)
   SLUG=<from --slug or short git ref>
   OUT="docs/superpowers/eval-scorecards/${DATE}-${SLUG}"
   mkdir -p "${OUT}"
   ```

3. **Run eval-prepare** via Bash:
   ```bash
   uv run framework eval-prepare --mode tune \
     ${AGENT:+--agent "$AGENT"} \
     --fixtures tests/eval/fixtures \
     --repeat "$REPEAT" \
     --output-dir "$OUT" > /tmp/reviewers-tune-prep.json
   ```

4. **Read the prep manifest** (`/tmp/reviewers-tune-prep.json`) and inspect the work-item count.

5. **Print a pre-flight estimate** to the user:
   - Number of work items.
   - Estimated wall time: 10-30 min for full sweep; 1-3 min for single-agent.
   - **Subagent quota note**: scales with CC subscription tier; on constrained tiers this run may consume significant 5-hour quota. Single-agent invocation (`/reviewers:tune <reviewer>`) is much cheaper.

6. **If work item count > 30**, **confirm with the user** before proceeding. ("This will dispatch N subagent calls — proceed?")

7. **Invoke the Workflow tool**:
   - `name`: `"reviewers-tune"` (resolves to `.claude/workflows/reviewers-tune.js`)
   - `args`: the JSON loaded from the prep manifest (the whole object — Workflow exposes it as `args`)
   - This runs in the foreground; wait for the result.

8. **Write the Workflow's returned `{results, meta}` to a temp file**:
   ```bash
   # Claude writes the workflow result JSON to /tmp/reviewers-tune-results.json via Write tool.
   ```

9. **Run eval-finalize**:
   ```bash
   uv run framework eval-finalize --mode tune \
     --results /tmp/reviewers-tune-results.json \
     --out-dir "$OUT"
   ```

10. **Print a summary** to the user: the output dir path, the number of agents that PASS/FAIL, and pointers to:
    - `<OUT>/scorecard.md` for the full report.
    - `<OUT>/thresholds.proposal.yaml` for the proposed threshold values.
    - `<OUT>/apply.md` for instructions on how to apply the proposal.

11. **Suggest the next step** to the user: "Review `<OUT>/scorecard.md` (especially `## Drift check`), then say 'apply the thresholds from `<OUT>`' to update `tests/eval/fixtures/thresholds.yaml`."

**Important notes:**
- This command runs entirely on CC subagents (subscription quota), NOT the paid Anthropic API.
- If any subagent calls fail mid-workflow, the workflow still returns partial results — eval-finalize handles missing data gracefully but the scorecard will be incomplete. Re-run if needed.
- Do NOT auto-apply the proposal to `tests/eval/fixtures/thresholds.yaml`. Threshold changes are deliberate; the user invokes `apply.md`'s instructions.
- The output dir is committed to git as part of the calibration history.
```

- [ ] **Step 3: Commit** (with CLAUDE.md update)

```bash
git add .claude/commands/reviewers/tune.md CLAUDE.md
git commit -m "feat(commands): /reviewers:tune slash command — local calibration via subagents

Orchestrates eval-prepare → Workflow dispatch → eval-finalize for tune mode.
Pre-flight estimate + N>30 confirmation prompt. Produces a dated scorecard
dir under docs/superpowers/eval-scorecards/ ready for human review and
threshold application.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: Manual verification — `/reviewers:tune security`

**Files:** none (manual smoke test).

- [ ] **Step 1: Verify CC sees the slash command**

In a CC session in the framework repo, type `/reviewers:` and confirm tab-completion shows `tune` (and the file is found). If CC's convention requires a different filename (e.g., `.claude/commands/reviewers:tune.md` with a colon, no subdir), rename and retry.

- [ ] **Step 2: Invoke `/reviewers:tune security`** in a CC session

Watch for:
- Pre-flight estimate prints (calls, time, quota note).
- No confirmation prompt (security has < 30 calls).
- Workflow tool dispatches; `/workflows` shows the Tune phase running with ~6-9 agent calls in parallel.
- After completion: prep manifest is at `/tmp/reviewers-tune-prep.json`; results file at `/tmp/reviewers-tune-results.json`; output dir at `docs/superpowers/eval-scorecards/<date>-<slug>/`.

- [ ] **Step 3: Inspect the output dir**

```bash
ls -la docs/superpowers/eval-scorecards/$(date +%Y-%m-%d)-*/
# Expected:
#   findings/security/bad/*.json (one per fixture × repeat)
#   findings/security/good/*.json
#   scorecard.md
#   thresholds.proposal.yaml
#   apply.md
#   meta.json
```

- [ ] **Step 4: Read the scorecard**

```bash
cat docs/superpowers/eval-scorecards/$(date +%Y-%m-%d)-*/scorecard.md
```

Verify:
- `## Scorecard` section shows `review-security` with `recall` and `fp` values.
- `## Cost by agent` shows subagent-dispatched cost (~$0 or unpopulated).
- `## Drift check` says no drift (security is bundle tier, no tool use).
- `## Proposed thresholds.yaml` has security's proposed values.

- [ ] **Step 5: Read `meta.json`**

```bash
cat docs/superpowers/eval-scorecards/$(date +%Y-%m-%d)-*/meta.json
```

Verify: `mode: "tune"`, `agent_count: 1`, `subagent_call_count` matches the actual call count, `drift_detected: false`.

- [ ] **Step 6: If something is wrong, iterate.** Common issues:
  - Slash command file not found: try alternative naming (colon in filename vs subdir).
  - Workflow tool doesn't accept the args: check the script's `args` access pattern.
  - Subagent responses don't match the schema: tighten the user_message in `_build_work_item`.

- [ ] **Step 7: Once green, commit the scorecard dir** as the inaugural calibration artifact

```bash
git add docs/superpowers/eval-scorecards/$(date +%Y-%m-%d)-*/ CLAUDE.md
git commit -m "calibrate(security): inaugural local subagent-backed tune for review-security

First /reviewers:tune run end-to-end against the review-security agent.
Verifies the dispatch pipeline works; observed values inform threshold
calibration in a subsequent commit per apply.md's instructions.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: `reviewers-audit.js` workflow script

**Files:**
- Create: `.claude/workflows/reviewers-audit.js`

Same shape as tune, but one item per agent (no fixture/repeat dimension).

- [ ] **Step 1: Write the workflow** at `.claude/workflows/reviewers-audit.js`

```javascript
export const meta = {
  name: 'reviewers-audit',
  description: 'Fan out one subagent call per agent against the current code state.',
  phases: [
    { title: 'Audit', detail: 'one subagent call per agent, in parallel' },
  ],
}

phase('Audit')

const items = args.work_items
if (!Array.isArray(items) || items.length === 0) {
  throw new Error('reviewers-audit: args.work_items must be a non-empty array')
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
  const label = `audit:${item.agent}`
  try {
    const out = await agent(prompt, {
      label,
      phase: 'Audit',
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
    log(`agent call failed for ${label}: ${e.message}`)
    return null
  }
}))

return { results: results.filter(Boolean), meta: args.meta || {} }
```

- [ ] **Step 2: Commit** (with CLAUDE.md update)

```bash
git add .claude/workflows/reviewers-audit.js CLAUDE.md
git commit -m "feat(workflows): reviewers-audit.js fans out one subagent call per agent

Mirrors reviewers-tune.js but for audit shape: one item per agent, no
fixture/repeat dimension. Returns collected findings for eval-finalize
to write to .framework/audit/latest/.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 11: `/reviewers:audit` slash command

**Files:**
- Create: `.claude/commands/reviewers/audit.md`

- [ ] **Step 1: Write the slash command** at `.claude/commands/reviewers/audit.md`

```markdown
---
description: Hygiene review — run review agents against current code state via local subagents (no paid API). Auto-detects framework vs project target. Optional positional arg = single agent name.
---

You are running the `/reviewers:audit` workflow. Your job: dispatch the subagent-backed audit pipeline and surface what the review agents would flag in the current code state.

**Inputs:**
- Optional positional arg: single agent name (e.g., `security`).
- Optional flag: `--target {framework|project}` (default: auto-detect).

**Steps:**

1. **Parse the user's arguments**. Extract the optional agent name and optional `--target`.

2. **Run eval-prepare** via Bash:
   ```bash
   uv run framework eval-prepare --mode audit \
     ${AGENT:+--agent "$AGENT"} \
     ${TARGET:+--target "$TARGET"} \
     --output-dir .framework/audit/latest > /tmp/reviewers-audit-prep.json
   ```
   If eval-prepare errors with "Could not auto-detect target," inform the user and suggest `--target framework` or `--target project`.

3. **Read the prep manifest** and inspect the work-item count.

4. **Print a pre-flight estimate** to the user:
   - Target detected (framework or project).
   - Number of agents being run.
   - Estimated wall time: ~30s-2min per agent.
   - Subagent quota note (scales with subscription tier).

5. **If work item count > 30**, **confirm with the user** before proceeding.

6. **Invoke the Workflow tool**:
   - `name`: `"reviewers-audit"`
   - `args`: the JSON loaded from the prep manifest
   - Wait for the result in the foreground.

7. **Write the workflow's returned `{results, meta}` to a temp file**:
   ```bash
   # Claude writes /tmp/reviewers-audit-results.json via Write tool.
   ```

8. **Run eval-finalize**:
   ```bash
   uv run framework eval-finalize --mode audit \
     --results /tmp/reviewers-audit-results.json \
     --out-dir .framework/audit/latest
   ```

9. **Print a summary** to the user:
   - Findings count by severity per agent (e.g., "review-security: 2 high, 1 medium").
   - Drift check result.
   - Link: `.framework/audit/latest/audit-report.md` for the full report.

**Important notes:**
- This command runs entirely on CC subagents (subscription quota), NOT the paid Anthropic API.
- Output is **ephemeral** — `.framework/audit/latest/` is overwritten each run and gitignored. The path is stable so `/reviewers:gate` (Slice E2) knows where to look.
- For the rare case where an audit finding warrants preservation as discovery-evidence (caught a real bug being fixed), manually excerpt the relevant snippet from `audit-report.md` into the commit message or PR description.
- Auto-detection: framework target requires `src/framework_cli/` + `pyproject.toml` with `name = "swiftwater-framework"`. Project target requires `.copier-answers.yml`. Neither matches → error, pass `--target` explicitly.
```

- [ ] **Step 2: Commit** (with CLAUDE.md update)

```bash
git add .claude/commands/reviewers/audit.md CLAUDE.md
git commit -m "feat(commands): /reviewers:audit slash command — local hygiene review via subagents

Orchestrates eval-prepare → Workflow dispatch → eval-finalize for audit mode.
Auto-detects framework vs project target. Output is ephemeral
.framework/audit/latest/ (gitignored, stable path for the gate to read).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 12: Manual verification — `/reviewers:audit` (framework target)

**Files:** none.

- [ ] **Step 1: Invoke `/reviewers:audit`** in a CC session in the framework repo root.

Watch for:
- Pre-flight estimate prints: target=framework, ~6 agents (FRAMEWORK_AGENTS subset).
- Workflow dispatches; `/workflows` shows the Audit phase with ~6 agent calls.
- After completion: results file at `/tmp/reviewers-audit-results.json`; output dir at `.framework/audit/latest/`.

- [ ] **Step 2: Inspect the output**

```bash
ls -la .framework/audit/latest/
# Expected:
#   findings/security.json
#   findings/architecture.json
#   ... (one per FRAMEWORK_AGENT)
#   audit-report.md
```

- [ ] **Step 3: Read the audit report**

```bash
cat .framework/audit/latest/audit-report.md
```

Verify: sections per agent with findings (or `(no findings)`), drift check at the bottom, drift = none (most calls should be bundle tier; architecture is agentic but should stay within Read/Grep/Glob).

- [ ] **Step 4: Test single-agent**

```
/reviewers:audit security
```

Verify only `review-security` runs and the audit report has only that section.

---

## Task 13: Manual verification — render-then-audit (project target)

**Files:** none. This is the critical framework-dev dogfooding workflow.

- [ ] **Step 1: Render a fresh test project**

```bash
cd /tmp
rm -rf test-audit
uv --directory "/home/chris/Claude Code/Projects/framework/swiftwater-framework" run framework new test-audit
cd test-audit
```

- [ ] **Step 2: Invoke `/reviewers:audit`** in a CC session, in the rendered project's directory.

Watch for:
- Auto-detection: `target=project` (`.copier-answers.yml` is present).
- Pre-flight: project-active agents (typically more than FRAMEWORK_AGENTS — depends on enabled batteries).
- Workflow dispatches, results land in `.framework/audit/latest/` (in the rendered project).

- [ ] **Step 3: Inspect**

```bash
ls -la .framework/audit/latest/
cat .framework/audit/latest/audit-report.md
```

Verify: agent set matches the project's active set, findings are about the project's own (template-rendered) code, drift check is included.

- [ ] **Step 4: Clean up**

```bash
cd /
rm -rf /tmp/test-audit
```

---

## Task 14: Final quality gate + summary commit

**Files:** none (verification + commit only).

- [ ] **Step 1: Full quality gate**

```bash
cd "/home/chris/Claude Code/Projects/framework/swiftwater-framework"
uv run pytest -q --ignore=tests/acceptance
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green.

- [ ] **Step 2: Update CLAUDE.md** Current State pointer to mark Slice E1 ready-to-merge.

- [ ] **Step 3: Confirm Slice E1 acceptance criteria** from the spec:
   - [x] `/reviewers:tune` runs end-to-end against a single agent (Task 9).
   - [x] Drift check passes on bundle-tier agents (Task 9).
   - [x] `/reviewers:audit` works in framework repo (Task 12).
   - [x] `/reviewers:audit` works in a rendered project (Task 13).
   - [x] `eval-analyze` produces useful output for both tune and audit dirs (Tasks 1, 2).
   - [x] `eval-analyze --strict` exits 2 on drift (Task 1).
   - [x] All existing tests pass (Task 14 Step 1).

- [ ] **Step 4: Final commit if any state pending**

```bash
git add CLAUDE.md
git commit -m "docs(state): Slice E1 complete — local-eval infrastructure ready

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Notes for the implementing engineer

- **Subagent type names** are `general-purpose` and `Explore`. The `agent()` call's `agentType:` option is documented in the Workflow tool's description.
- **`tools_allowed`** is currently advisory only — passed in the work item for clarity but not enforced at the dispatch layer. The drift check in `eval-analyze` is the hard backstop.
- **The Workflow tool's `args`** is whatever JSON object the caller passes. Slash commands pass the prep manifest verbatim; the script accesses `args.work_items`, `args.meta`, etc.
- **Concurrency** is automatically capped at `min(16, cpu - 2)` by the Workflow tool. No manual throttling needed.
- **If the `agent()` schema-validation fails** for a particular call, agent() throws and the wrapping `try/catch` in the workflow filters it to null. Net effect: that fixture/agent shows up as missing in the scorecard. Re-run if a substantial number fail (likely indicates a prompt-construction issue).
- **CC slash command file naming** for namespaces (`reviewers:tune`): the subdirectory pattern (`.claude/commands/reviewers/tune.md` → `/reviewers:tune`) is the safest default. If CC uses a different convention in this version, Task 9 catches it on first invocation.
