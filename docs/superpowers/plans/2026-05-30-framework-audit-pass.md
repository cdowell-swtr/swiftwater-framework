# Framework Audit Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the first-ever review-agent audit against `src/framework_cli/` and preserve the result as a dated baseline artifact, after first splitting the mode-multiplexed `eval-prepare` / `eval-finalize` commands into clean per-mode pairs (`tune-*`, `audit-*`, `gate-*`).

**Architecture:** Two-stage refactor first (split shared commands without changing semantics, then add audit-only flags `--agent` repeatable and `--preserve-as`), then a single operational pass (`/reviewers:audit` against the framework, preserve to a dated dir, hand-write triage). Each task leaves the system working — the split happens in two atomic steps (prepare commands, then finalize commands), with call-site updates folded into each.

**Tech Stack:** Python (Typer CLI), pytest, ruff, mypy, `uv` package manager. Plan execution touches `src/framework_cli/cli.py`, `tests/test_cli.py`, the `.claude/commands/reviewers/*.md` slash commands, the `.claude/hooks/reviewers-gate-check.sh` PreToolUse hook, and the `template/` mirrors of each.

**Spec:** `docs/superpowers/specs/2026-05-30-framework-audit-pass-design.md`

---

## Background — current commands

The existing CLI exposes:

- `framework eval` — paid Anthropic-API tune scoring (Slice D). **Not touched** by this plan.
- `framework eval-analyze` — analyzes paid eval findings into a tune scorecard. **Not touched.**
- `framework eval-prepare --mode {tune|audit|gate} ...` — mode-multiplexed prep, ~476 LOC, branched at `cli.py:596`.
- `framework eval-finalize --mode {tune|audit|gate} ...` — mode-multiplexed finalize, ~270 LOC, branched at `cli.py:1072`.

After this plan:

- `framework eval` — unchanged.
- `framework eval-analyze` — unchanged.
- `framework tune-prepare ...` — was `eval-prepare --mode tune`.
- `framework audit-prepare ...` — was `eval-prepare --mode audit`. **Plus new repeatable `--agent`.**
- `framework gate-prepare ...` — was `eval-prepare --mode gate`.
- `framework tune-finalize ...` — was `eval-finalize --mode tune`.
- `framework audit-finalize ...` — was `eval-finalize --mode audit`. **Plus new `--preserve-as`/`--force`.**
- `framework gate-finalize ...` — was `eval-finalize --mode gate`.

The umbrella `eval-prepare` / `eval-finalize` commands are deleted. No backward-compatibility aliases — we control every call site (enumerated in Task 2 / Task 3).

---

### Task 1: Split `eval-prepare` into `tune-prepare` / `audit-prepare` / `gate-prepare`

**Goal:** Replace the single mode-multiplexed `eval-prepare` command with three per-mode commands. Migrate existing tests. Update every call site that invokes `framework eval-prepare ...` to use the appropriate new command.

**Files:**
- Modify: `src/framework_cli/cli.py` (delete `eval_prepare` at L596; add 3 new command functions)
- Modify: `tests/test_cli.py` (rename + retarget the 18 existing eval-prepare/eval-finalize tests; this task handles only the 6 prepare tests)
- Modify: `.claude/commands/reviewers/tune.md`
- Modify: `.claude/commands/reviewers/audit.md`
- Modify: `.claude/commands/reviewers/gate.md`
- Modify: `.claude/hooks/reviewers-gate-check.sh`
- Modify: `src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja`
- Modify: `src/framework_cli/template/.claude/commands/reviewers/gate.md.jinja`
- Modify: `src/framework_cli/template/.claude/hooks/reviewers-gate-check.sh.jinja`

- [ ] **Step 1: Survey the existing `eval_prepare` function**

Open `src/framework_cli/cli.py` at L596. The function has a long body with branching on `mode`. Identify the three logical sections (tune / audit / gate) and what they share (manifest loading, work-item building helpers, agent validation, target detection). The shared helpers will become module-level functions called by all three new commands.

No code change in this step — just orient.

- [ ] **Step 2: Write failing tests for the new command names**

The 6 existing prepare tests in `tests/test_cli.py` all invoke `["eval-prepare", "--mode", "tune"|"audit"|"gate", ...]`. Migrate them to invoke the new command names directly. Tests to update (line numbers from a fresh `grep -n "def test_eval_prepare" tests/test_cli.py`):

- `test_eval_prepare_tune_outputs_work_items_for_single_agent` → rename to `test_tune_prepare_outputs_work_items_for_single_agent`, change `["eval-prepare", "--mode", "tune", "--agent", "security"]` → `["tune-prepare", "--agent", "security"]`.
- `test_eval_prepare_tune_uses_explore_for_agentic_agents` → `test_tune_prepare_uses_explore_for_agentic_agents`.
- `test_eval_prepare_split_to_writes_index_and_items` → `test_tune_prepare_split_to_writes_index_and_items` (split-to is tune-only).
- `test_eval_prepare_split_to_clears_existing_dir` → `test_tune_prepare_split_to_clears_existing_dir`.
- `test_eval_prepare_audit_detects_framework_target` → `test_audit_prepare_detects_framework_target`, change `["eval-prepare", "--mode", "audit"]` → `["audit-prepare"]`.
- `test_eval_prepare_audit_explicit_target_override` → `test_audit_prepare_explicit_target_override`.
- `test_eval_prepare_audit_tolerates_pyproject_formatting_variations` → `test_audit_prepare_tolerates_pyproject_formatting_variations`.
- `test_eval_prepare_gate_affected_single_prompt` → `test_gate_prepare_affected_single_prompt`.
- `test_eval_prepare_gate_runner_change_affects_all_bundle` → `test_gate_prepare_runner_change_affects_all_bundle`.
- `test_eval_prepare_gate_thresholds_only_signals_regrade` → `test_gate_prepare_thresholds_only_signals_regrade`.

Make the textual changes only in this step. Do NOT change the implementation yet.

- [ ] **Step 3: Run prepare tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -k "tune_prepare or audit_prepare or gate_prepare" -v
```

Expected: FAIL — typer reports "No such command 'tune-prepare'" (and similar for audit/gate).

- [ ] **Step 4: Implement the three new prepare commands**

In `src/framework_cli/cli.py`, immediately above the existing `eval_prepare` definition (around L595), add three new commands. Each is the per-mode branch body of `eval_prepare`, lifted out and given its own `@app.command()` decorator.

Pseudocode shape (don't copy literally — extract from the actual function body):

```python
@app.command(name="tune-prepare")
def tune_prepare(
    fixtures: Path = typer.Option(..., "--fixtures"),
    agent: str | None = typer.Option(None, "--agent"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    split_to: Path | None = typer.Option(None, "--split-to"),
):
    # Body = the tune branch of the existing eval_prepare (validation,
    # work-item building, manifest write or split-manifest write).
    ...

@app.command(name="audit-prepare")
def audit_prepare(
    target: str | None = typer.Option(None, "--target"),
    agent: str | None = typer.Option(None, "--agent"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
):
    # Body = the audit branch of the existing eval_prepare (auto-detect target,
    # build work-items for the active agents, write manifest).
    ...

@app.command(name="gate-prepare")
def gate_prepare(
    output_dir: Path | None = typer.Option(None, "--output-dir"),
):
    # Body = the gate branch of the existing eval_prepare (affected-only,
    # staged-diff inspection, manifest write).
    ...
```

Shared logic (manifest write, agent name validation, target detection, work-item builders) factors into module-level functions named without a mode prefix. If a helper is currently a closure inside `eval_prepare`, hoist it to module scope.

This task adds the new commands. `eval_prepare` itself is still present and will be removed in Step 6.

- [ ] **Step 5: Run prepare tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -k "tune_prepare or audit_prepare or gate_prepare" -v
```

Expected: PASS (all 10 migrated prepare tests).

- [ ] **Step 6: Delete the old `eval_prepare` command**

In `src/framework_cli/cli.py`, delete the entire `@app.command(name="eval-prepare")` decorator and `def eval_prepare(...)` function body that was at L596-L1071. Run:

```bash
uv run pytest tests/test_cli.py -v 2>&1 | tail -30
```

Expected: All prepare tests still pass; finalize tests still pass (they still reference `eval-finalize --mode ...` — Task 2 will migrate them).

If any test references `eval-prepare` and was missed, it will fail here with "No such command 'eval-prepare'". Fix the reference and re-run.

- [ ] **Step 7: Update slash-command call sites**

In `.claude/commands/reviewers/tune.md`, find every occurrence of `framework eval-prepare --mode tune` and replace with `framework tune-prepare`. Strip the `--mode tune` flag. Preserve all other flags as-is.

In `.claude/commands/reviewers/audit.md`, replace `framework eval-prepare --mode audit` with `framework audit-prepare`. Strip `--mode audit`.

In `.claude/commands/reviewers/gate.md`, replace `framework eval-prepare --mode gate` with `framework gate-prepare`. Strip `--mode gate`.

In `.claude/hooks/reviewers-gate-check.sh`, find any invocation of `framework eval-prepare ...` and replace with the appropriate per-mode command (almost certainly `framework gate-prepare`).

In the three template mirrors (`src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja`, `gate.md.jinja`, and `src/framework_cli/template/.claude/hooks/reviewers-gate-check.sh.jinja`), apply the same substitutions.

Search for stragglers:

```bash
git grep -nE "eval-prepare|--mode (tune|audit|gate)" -- ':!docs/superpowers/specs/' ':!docs/superpowers/plans/'
```

Expected: zero hits outside the spec/plans (those describe history and should keep the old names). Fix any straggler before continuing.

- [ ] **Step 8: Run the full test suite + quality gate**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 9: Update CLAUDE.md and commit**

Update the **Last updated** line in `CLAUDE.md` with the current datetime (e.g. `2026-05-30 HH:MM PDT`) and a one-sentence note: "Split `eval-prepare` into `tune-prepare` / `audit-prepare` / `gate-prepare`; finalize split pending."

```bash
git add src/framework_cli/cli.py tests/test_cli.py \
        .claude/commands/reviewers/tune.md \
        .claude/commands/reviewers/audit.md \
        .claude/commands/reviewers/gate.md \
        .claude/hooks/reviewers-gate-check.sh \
        src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja \
        src/framework_cli/template/.claude/commands/reviewers/gate.md.jinja \
        src/framework_cli/template/.claude/hooks/reviewers-gate-check.sh.jinja \
        CLAUDE.md
```

Then a separate `git commit` invocation (the commit-gate hook fails on chained git commands — see memory `commit-gate-hook-timing`):

```bash
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
refactor(cli): split eval-prepare into tune-prepare/audit-prepare/gate-prepare

Removes the mode-multiplexed eval-prepare command. Each per-mode branch
becomes its own first-class command. Migrates 10 existing tests and updates
all slash-command + hook call sites (and their template mirrors).

Finalize side (eval-finalize) split is the next task.
EOF
)"
```

---

### Task 2: Split `eval-finalize` into `tune-finalize` / `audit-finalize` / `gate-finalize`

**Goal:** Mirror Task 1 for the finalize side. After this task no command takes `--mode`.

**Files:**
- Modify: `src/framework_cli/cli.py` (delete `eval_finalize` at L1072; add 3 new command functions)
- Modify: `tests/test_cli.py` (rename + retarget the remaining 8 finalize tests)
- Modify: `.claude/commands/reviewers/tune.md`
- Modify: `.claude/commands/reviewers/audit.md`
- Modify: `.claude/commands/reviewers/gate.md`
- Modify: `.claude/hooks/reviewers-gate-check.sh`
- Modify: `src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja`
- Modify: `src/framework_cli/template/.claude/commands/reviewers/gate.md.jinja`
- Modify: `src/framework_cli/template/.claude/hooks/reviewers-gate-check.sh.jinja`

- [ ] **Step 1: Rename the 8 finalize tests**

Tests to migrate (find with `grep -n "def test_eval_finalize" tests/test_cli.py`):

- `test_eval_finalize_writes_records_runs_analyze_writes_meta` → `test_tune_finalize_writes_records_runs_analyze_writes_meta`, change `["eval-finalize", "--mode", "tune", ...]` → `["tune-finalize", ...]`.
- `test_eval_finalize_audit_mode_writes_audit_report` → `test_audit_finalize_writes_audit_report`.
- `test_eval_finalize_gate_writes_marker_pass` → `test_gate_finalize_writes_marker_pass`.
- (plus the other ~5 finalize tests visible in the grep — apply the same rename pattern based on `_tune_` / `_audit_` / `_gate_` in their current name).

If a test name doesn't encode the mode (e.g. `test_eval_finalize_writes_records...`), check the test body for which `--mode` it uses and rename accordingly.

- [ ] **Step 2: Run finalize tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -k "tune_finalize or audit_finalize or gate_finalize" -v
```

Expected: FAIL — typer reports "No such command 'tune-finalize'" etc.

- [ ] **Step 3: Implement the three new finalize commands**

In `src/framework_cli/cli.py`, immediately above the existing `eval_finalize` definition (around L1071), add three new commands. Each is the per-mode branch body of `eval_finalize`, lifted out.

Pseudocode shape:

```python
@app.command(name="tune-finalize")
def tune_finalize(
    results: Path = typer.Option(..., "--results"),
    fixtures: Path = typer.Option(..., "--fixtures"),
    out: Path = typer.Option(..., "--out"),
):
    # Body = the tune branch of eval_finalize (per-call record writing,
    # invokes eval-analyze, writes scorecard.md).
    ...

@app.command(name="audit-finalize")
def audit_finalize(
    results: Path = typer.Option(..., "--results"),
    out_dir: Path = typer.Option(..., "--out-dir"),
):
    # Body = the audit branch of eval_finalize (per-agent JSON records,
    # writes audit-report.md, meta.json).
    ...

@app.command(name="gate-finalize")
def gate_finalize(
    results: Path = typer.Option(..., "--results"),
    out_dir: Path = typer.Option(..., "--out-dir"),
):
    # Body = the gate branch of eval_finalize (writes marker.json with PASS/FAIL).
    ...
```

Shared helpers (results loading, record formatting) factor to module scope as in Task 1.

- [ ] **Step 4: Run finalize tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -k "tune_finalize or audit_finalize or gate_finalize" -v
```

Expected: PASS.

- [ ] **Step 5: Delete the old `eval_finalize` command**

Remove the `@app.command(name="eval-finalize")` decorator and `def eval_finalize(...)` function body. Run:

```bash
uv run pytest tests/test_cli.py -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 6: Update slash-command and hook call sites**

In each of the three slash commands (`tune.md`, `audit.md`, `gate.md`) and the gate hook (and the three template mirrors), replace `framework eval-finalize --mode <m>` with `framework <m>-finalize`. Strip `--mode <m>`.

Search for stragglers:

```bash
git grep -nE "eval-finalize|--mode (tune|audit|gate)" -- ':!docs/superpowers/specs/' ':!docs/superpowers/plans/'
```

Expected: zero hits.

- [ ] **Step 7: Run the full test suite + quality gate**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 8: Update CLAUDE.md and commit**

Update **Last updated** to reflect the finalize split. Then:

```bash
git add src/framework_cli/cli.py tests/test_cli.py \
        .claude/commands/reviewers/tune.md \
        .claude/commands/reviewers/audit.md \
        .claude/commands/reviewers/gate.md \
        .claude/hooks/reviewers-gate-check.sh \
        src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja \
        src/framework_cli/template/.claude/commands/reviewers/gate.md.jinja \
        src/framework_cli/template/.claude/hooks/reviewers-gate-check.sh.jinja \
        CLAUDE.md
```

Separate commit:

```bash
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
refactor(cli): split eval-finalize into tune-finalize/audit-finalize/gate-finalize

Removes the mode-multiplexed eval-finalize command. Each per-mode branch
becomes its own first-class command; --mode is gone everywhere.
EOF
)"
```

---

### Task 3: Add repeatable `--agent` to `audit-prepare`

**Goal:** `audit-prepare --agent X --agent Y --agent Z` produces a manifest with the union of work-items for X, Y, Z (deduplicated). Single-agent and all-agents paths stay unchanged.

**Files:**
- Modify: `src/framework_cli/cli.py` (the `audit_prepare` function from Task 1)
- Modify: `tests/test_cli.py` (add new tests)

- [ ] **Step 1: Write failing tests**

In `tests/test_cli.py`, add three new tests near the existing audit-prepare tests:

```python
def test_audit_prepare_multiple_agents_produces_union(tmp_path, monkeypatch):
    """audit-prepare with two --agent flags produces work-items for both, deduplicated."""
    _seed_framework_workspace(monkeypatch, tmp_path)  # use the existing helper
    result = runner.invoke(
        app,
        [
            "audit-prepare",
            "--target", "framework",
            "--agent", "security",
            "--agent", "dependency",
        ],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads(result.stdout)
    agent_names = {item["agent"] for item in manifest["items"]}
    assert agent_names == {"security", "dependency"}


def test_audit_prepare_duplicate_agents_deduped(tmp_path, monkeypatch):
    """Passing the same agent twice does not produce duplicate work-items."""
    _seed_framework_workspace(monkeypatch, tmp_path)
    result = runner.invoke(
        app,
        [
            "audit-prepare",
            "--target", "framework",
            "--agent", "security",
            "--agent", "security",
        ],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads(result.stdout)
    security_items = [i for i in manifest["items"] if i["agent"] == "security"]
    assert len(security_items) == 1


def test_audit_prepare_unknown_agent_errors_clearly():
    """audit-prepare --agent <unknown> errors with a clear message listing valid names."""
    result = runner.invoke(app, ["audit-prepare", "--target", "framework", "--agent", "bogus"])
    assert result.exit_code != 0
    assert "bogus" in result.output
    assert "unknown agent" in result.output.lower() or "valid agents" in result.output.lower()
```

If a helper called `_seed_framework_workspace` doesn't exist, look at how the existing `test_audit_prepare_*` tests set up their environment (probably a tmp_path with `src/framework_cli/` and a `pyproject.toml` written in) and inline that setup, or factor it into a fixture.

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
uv run pytest tests/test_cli.py::test_audit_prepare_multiple_agents_produces_union \
              tests/test_cli.py::test_audit_prepare_duplicate_agents_deduped \
              tests/test_cli.py::test_audit_prepare_unknown_agent_errors_clearly -v
```

Expected: the first two FAIL because typer rejects the second `--agent` (Option doesn't accept repeats by default); the third may pass if the existing validator already errors clearly.

- [ ] **Step 3: Make `--agent` repeatable in `audit-prepare`**

In `src/framework_cli/cli.py`, change the `audit_prepare` signature so `--agent` accepts a list:

```python
@app.command(name="audit-prepare")
def audit_prepare(
    target: str | None = typer.Option(None, "--target"),
    agent: list[str] = typer.Option(
        None,
        "--agent",
        help="Restrict to this agent. Repeat for multiple agents. Omit for all active agents.",
    ),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
):
    selected = list(dict.fromkeys(agent or []))  # dedupe, preserve order
    if selected:
        valid = _active_audit_agents_for(target)  # existing helper
        unknown = [a for a in selected if a not in valid]
        if unknown:
            typer.echo(
                f"audit-prepare: unknown agent(s): {', '.join(unknown)}. "
                f"Valid agents: {', '.join(sorted(valid))}",
                err=True,
            )
            raise typer.Exit(2)
        active_agents = selected
    else:
        active_agents = _active_audit_agents_for(target)
    # ... continue with existing work-item construction over active_agents
```

Adjust to match the actual helper names you find while doing Task 1. The dedupe (`dict.fromkeys`) preserves insertion order, which keeps determinism.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -k "audit_prepare" -v
```

Expected: all audit_prepare tests pass (the three new ones plus the originals from Task 1).

- [ ] **Step 5: Run the full quality gate**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 6: Update CLAUDE.md and commit**

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(audit-prepare): repeatable --agent for multi-agent audits

audit-prepare --agent X --agent Y produces a manifest with the union of
work-items for X and Y, deduplicated. Unknown agents error clearly.
Single-agent and all-agents paths unchanged.
EOF
)"
```

---

### Task 4: Add `--preserve-as` (+ `--force`) to `audit-finalize`

**Goal:** `audit-finalize --preserve-as <dated-dir>` copies `.framework/audit/latest/` into the dated dir. Refuses non-empty target without `--force`.

**Files:**
- Modify: `src/framework_cli/cli.py` (the `audit_finalize` function from Task 2)
- Modify: `tests/test_cli.py` (add new tests)

- [ ] **Step 1: Write failing tests**

```python
def test_audit_finalize_preserve_as_copies_into_fresh_dir(tmp_path):
    """audit-finalize --preserve-as copies findings/, audit-report.md, meta.json into target."""
    out_dir = tmp_path / "latest"
    out_dir.mkdir()
    (out_dir / "findings").mkdir()
    (out_dir / "findings" / "security.json").write_text("{}")
    (out_dir / "audit-report.md").write_text("# Audit\n")
    (out_dir / "meta.json").write_text("{}")

    target = tmp_path / "preserved"
    # Provide a minimal results file so the command's core path runs without error
    results = tmp_path / "results.json"
    results.write_text('{"results": []}')

    result = runner.invoke(
        app,
        ["audit-finalize", "--results", str(results), "--out-dir", str(out_dir),
         "--preserve-as", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert (target / "findings" / "security.json").exists()
    assert (target / "audit-report.md").exists()
    assert (target / "meta.json").exists()


def test_audit_finalize_preserve_as_refuses_non_empty_target(tmp_path):
    """--preserve-as refuses to overwrite a non-empty target dir without --force."""
    out_dir = tmp_path / "latest"
    out_dir.mkdir()
    (out_dir / "audit-report.md").write_text("# Audit\n")

    target = tmp_path / "preserved"
    target.mkdir()
    (target / "existing.txt").write_text("not empty")

    results = tmp_path / "results.json"
    results.write_text('{"results": []}')

    result = runner.invoke(
        app,
        ["audit-finalize", "--results", str(results), "--out-dir", str(out_dir),
         "--preserve-as", str(target)],
    )
    assert result.exit_code != 0
    assert str(target) in result.output
    assert "non-empty" in result.output.lower() or "exists" in result.output.lower()


def test_audit_finalize_preserve_as_force_overwrites_non_empty(tmp_path):
    """--force allows --preserve-as to overwrite a non-empty target."""
    out_dir = tmp_path / "latest"
    out_dir.mkdir()
    (out_dir / "audit-report.md").write_text("# Audit\n")

    target = tmp_path / "preserved"
    target.mkdir()
    (target / "existing.txt").write_text("will be replaced")

    results = tmp_path / "results.json"
    results.write_text('{"results": []}')

    result = runner.invoke(
        app,
        ["audit-finalize", "--results", str(results), "--out-dir", str(out_dir),
         "--preserve-as", str(target), "--force"],
    )
    assert result.exit_code == 0, result.output
    assert (target / "audit-report.md").exists()
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -k "preserve_as" -v
```

Expected: FAIL — `--preserve-as` flag doesn't exist.

- [ ] **Step 3: Implement `--preserve-as` and `--force`**

In `src/framework_cli/cli.py`, extend the `audit_finalize` signature:

```python
@app.command(name="audit-finalize")
def audit_finalize(
    results: Path = typer.Option(..., "--results"),
    out_dir: Path = typer.Option(..., "--out-dir"),
    preserve_as: Path | None = typer.Option(
        None, "--preserve-as",
        help="After writing out_dir, copy its tree into this dated baseline directory.",
    ),
    force: bool = typer.Option(False, "--force", help="Required to overwrite a non-empty --preserve-as target."),
):
    # ... existing body (writes findings/, audit-report.md, meta.json into out_dir) ...

    if preserve_as is not None:
        _preserve_audit_tree(out_dir, preserve_as, force=force)


def _preserve_audit_tree(src: Path, dst: Path, *, force: bool) -> None:
    import shutil
    if dst.exists() and any(dst.iterdir()):
        if not force:
            typer.echo(
                f"audit-finalize: --preserve-as target exists and is non-empty: {dst}. "
                f"Pass --force to overwrite.",
                err=True,
            )
            raise typer.Exit(2)
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for item in ("findings", "audit-report.md", "meta.json"):
        s = src / item
        if not s.exists():
            continue
        if s.is_dir():
            shutil.copytree(s, dst / item)
        else:
            shutil.copy2(s, dst / item)
    typer.echo(f"audit-finalize: preserved to {dst}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -k "audit_finalize" -v
```

Expected: all audit_finalize tests pass (the three new ones plus originals from Task 2).

- [ ] **Step 5: Run the full quality gate**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 6: Update CLAUDE.md and commit**

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(audit-finalize): --preserve-as for dated baseline artifacts

audit-finalize --preserve-as <dir> copies findings/, audit-report.md, and
meta.json into a target dated dir. Refuses non-empty targets without --force.
EOF
)"
```

---

### Task 5: Update `/reviewers:audit` slash command to support repeatable `--agent` and `--preserve-as`

**Goal:** A single `/reviewers:audit` invocation can dispatch an arbitrary subset of agents and (optionally) preserve the result into a dated baseline dir.

**Files:**
- Modify: `.claude/commands/reviewers/audit.md`
- Modify: `src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja` (mirror)

- [ ] **Step 1: Read the current command body**

Open `.claude/commands/reviewers/audit.md`. The current input model has one optional positional agent argument and an optional `--target` flag. Look for the section where it builds the `framework audit-prepare ...` invocation (post-Task 1 it's already audit-prepare).

- [ ] **Step 2: Extend the input model**

Update the **Inputs** section of `.claude/commands/reviewers/audit.md` to read:

```markdown
**Inputs:**
- Optional positional agent name (single agent shortcut, e.g. `security`).
- Optional flag: `--target {framework|project}` (default: auto-detect).
- Optional flag: `--agents a,b,c` — comma-separated list to run a specific subset (overrides the positional argument). Each name is validated against the active roster for the target.
- Optional flag: `--preserve-as <dir>` — after finalize, copy `.framework/audit/latest/` into `<dir>` (treated as a dated baseline dir). Refuses non-empty target unless `--force` is also passed.
- Optional flag: `--force` — overwrite a non-empty `--preserve-as` target.
```

- [ ] **Step 3: Extend the dispatch step**

Update the `audit-prepare` step in the command's body to translate `--agents a,b,c` into repeated `--agent` flags:

```markdown
2. **Run audit-prepare** via Bash. Build the agent flag list from the `--agents` arg (comma-split) and pass each as a separate `--agent` flag:
   ```bash
   AGENT_FLAGS=""
   if [ -n "$AGENTS" ]; then
     IFS=',' read -ra ARR <<< "$AGENTS"
     for a in "${ARR[@]}"; do AGENT_FLAGS="$AGENT_FLAGS --agent $a"; done
   elif [ -n "$AGENT" ]; then
     AGENT_FLAGS="--agent $AGENT"
   fi
   uv run framework audit-prepare \
     ${TARGET:+--target "$TARGET"} \
     $AGENT_FLAGS \
     --output-dir .framework/audit/latest > /tmp/reviewers-audit-prep.json
   ```
```

- [ ] **Step 4: Extend the finalize step**

Update the `audit-finalize` step to include `--preserve-as` and `--force` when set, and add a final cleanup step so transient review-findings JSON files don't accumulate in `/tmp` across runs:

```markdown
8. **Run audit-finalize**:
   ```bash
   uv run framework audit-finalize \
     --results /tmp/reviewers-audit-results.json \
     --out-dir .framework/audit/latest \
     ${PRESERVE_AS:+--preserve-as "$PRESERVE_AS"} \
     ${FORCE:+--force}
   ```

9. **Clean up transient `/tmp` artifacts**:
   ```bash
   rm -f /tmp/reviewers-audit-prep.json /tmp/reviewers-audit-results.json 2>/dev/null || true
   ```
```

The cleanup step removes the per-run prep manifest and results payload — these are intermediate state, not artifacts. The preserved baseline (under `docs/superpowers/eval-scorecards/audit-…/`) and the ephemeral `.framework/audit/latest/` (gitignored) remain the only persisted outputs.

- [ ] **Step 5: Mirror the change in the template**

Apply the same edits to `src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja`. The Jinja file may use template variables for parts of the body — preserve those and only edit the inputs / dispatch / finalize sections.

- [ ] **Step 6: Sanity check**

```bash
uv run framework audit-prepare --help
uv run framework audit-finalize --help
```

Expected: both `--help` outputs include the new flags and reasonable help text.

- [ ] **Step 7: Render-time check (template mirror)**

The template change must not break a generated project. Render a minimal project into a tmp dir and confirm the rendered slash command is well-formed:

```bash
TMP=$(mktemp -d)
uv run framework new --no-input --output "$TMP/proj" project_name=demo description="demo"
test -f "$TMP/proj/.claude/commands/reviewers/audit.md" && head -30 "$TMP/proj/.claude/commands/reviewers/audit.md"
rm -rf "$TMP"
```

Adjust the `framework new` invocation to whatever the CLI actually accepts (check `framework new --help`). Expected: the rendered file contains the new `--agents` and `--preserve-as` inputs.

- [ ] **Step 8: Update CLAUDE.md and commit**

```bash
git add .claude/commands/reviewers/audit.md \
        src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja \
        CLAUDE.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(/reviewers:audit): expose --agents (subset) and --preserve-as (dated baseline)

The slash command now accepts a comma-separated --agents list (translated into
repeated --agent flags on audit-prepare) and forwards --preserve-as/--force to
audit-finalize. Template mirror updated.
EOF
)"
```

---

### Task 6: Run the framework audit (Phase 1)

**Goal:** Execute the audit against `src/framework_cli/` with the 9-agent roster and produce `.framework/audit/latest/` containing `findings/`, `audit-report.md`, and `meta.json`.

**Files:** No source files modified. This task produces ephemeral output in `.framework/audit/latest/` (gitignored).

The 9-agent roster: `application-logic, api-design, architecture, contracts, dependency, documentation, performance, security, test-quality`.

- [ ] **Step 1: Clean any stale audit state**

```bash
rm -rf .framework/audit/latest
rm -f /tmp/pytest-of-chris/* 2>/dev/null || sudo rm -rf /tmp/pytest-of-chris/* 2>/dev/null || true
```

The `/tmp` clean prevents the documented mass-failure pattern (memory `reviewers-tune-pytest-tmp-accumulation`).

- [ ] **Step 2: Confirm git working tree is clean**

```bash
git status --short
```

Expected: no modifications. The audit captures findings against a specific SHA; a dirty tree muddies the baseline.

If dirty, either commit or stash before continuing.

- [ ] **Step 3: Dispatch the audit**

Invoke the slash command:

```
/reviewers:audit --target framework --agents application-logic,api-design,architecture,contracts,dependency,documentation,performance,security,test-quality
```

This runs `audit-prepare` with 9 repeated `--agent` flags, dispatches 9 subagents in parallel via the `reviewers-audit` workflow, then runs `audit-finalize`.

Expected wall time: ~5-15 minutes depending on subagent quota and how much code each agent reads. Quota throttling can extend this dramatically (memory `reviewers-tune-quota-throttling`).

- [ ] **Step 4: Verify all 9 subagents returned results**

After the slash command completes, inspect `.framework/audit/latest/meta.json`:

```bash
cat .framework/audit/latest/meta.json
```

Expected: `work_item_count == 9` and `results_received == 9`. If `results_received < 9`, identify the missing agents (compare `agents` list in meta.json against the per-agent JSON files under `.framework/audit/latest/findings/`) and re-dispatch only the missing subset:

```
/reviewers:audit --target framework --agents <missing-csv>
```

Repeat until all 9 are present.

- [ ] **Step 5: Skim `audit-report.md`**

```bash
less .framework/audit/latest/audit-report.md
```

Expected: a consolidated markdown report grouping findings by agent, with severity, file:line, and a short description for each. Note any obvious malformed entries (empty fields, missing severities) — these are bugs in the report generator, not findings, and warrant a separate fix-up task before triage.

If the report looks structurally OK, this task is complete. Do **not** triage findings yet — that's Task 7.

This task ends with `.framework/audit/latest/` populated. Nothing is committed because the directory is gitignored.

---

### Task 7: Preserve + triage (Phase 2)

**Goal:** Copy `.framework/audit/latest/` into a dated baseline dir under `docs/superpowers/eval-scorecards/audit-YYYY-MM-DD-<sha>/`, hand-write `triage.md` walking every finding, and commit.

**Files:**
- Create: `docs/superpowers/eval-scorecards/audit-YYYY-MM-DD-<sha>/findings/` (copied from latest)
- Create: `docs/superpowers/eval-scorecards/audit-YYYY-MM-DD-<sha>/audit-report.md` (copied)
- Create: `docs/superpowers/eval-scorecards/audit-YYYY-MM-DD-<sha>/meta.json` (copied)
- Create: `docs/superpowers/eval-scorecards/audit-YYYY-MM-DD-<sha>/triage.md` (hand-written)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Compute the baseline dir name**

```bash
DATE=$(date +%Y-%m-%d)
SHA=$(git rev-parse --short HEAD)
DIR=docs/superpowers/eval-scorecards/audit-${DATE}-${SHA}
echo "$DIR"
```

Note the resolved `$DIR` value for later steps. Confirm the dir doesn't already exist:

```bash
test ! -e "$DIR" && echo "OK, will create" || echo "EXISTS — pick a different slug"
```

- [ ] **Step 2: Preserve via the new flag**

```bash
uv run framework audit-finalize \
  --results /tmp/reviewers-audit-results.json \
  --out-dir .framework/audit/latest \
  --preserve-as "$DIR"
```

This re-runs finalize idempotently (writing the same latest/) and additionally copies the tree into `$DIR`.

Expected stdout: `audit-finalize: preserved to docs/superpowers/eval-scorecards/audit-YYYY-MM-DD-<sha>/`.

Verify:

```bash
ls "$DIR"
```

Expected: `findings/  audit-report.md  meta.json`.

Then clean the transient `/tmp` artifacts left from Task 6's run:

```bash
rm -f /tmp/reviewers-audit-prep.json /tmp/reviewers-audit-results.json 2>/dev/null || true
```

Persisted state at this point: the preserved baseline at `$DIR` (about to be committed) and the gitignored `.framework/audit/latest/` (ephemeral).

- [ ] **Step 3: Write `triage.md`**

Create `$DIR/triage.md` by walking `$DIR/audit-report.md`. For each finding, fill one row of this table:

```markdown
# Triage — framework audit YYYY-MM-DD-<sha>

**Audit run:** see `audit-report.md` (raw findings) and `meta.json` (run metadata).
**Roster:** application-logic, api-design, architecture, contracts, dependency, documentation, performance, security, test-quality.

| # | Agent | Severity | File:line | Summary | Decision | Rationale | Fixed-in |
|---|---|---|---|---|---|---|---|
| 1 | review-security | high | <file>:<line> | <one-line summary> | fix-now | <one-line why> | — |
| 2 | review-architecture | medium | <file>:<line> | <one-line summary> | defer | <one-line why> | — |
| 3 | review-documentation | low | <file>:<line> | <one-line summary> | false-positive | <one-line why> | — |
```

Decision values: `fix-now`, `defer`, `false-positive`. Rationale is one line. `Fixed-in` stays `—` for defer and false-positive; for fix-now it stays `—` until Phase 3 lands the fix.

Be honest: not every finding is real. The 9-agent roster minimizes domain mismatch, but agents still over-fire on minor stylistic things or pattern-match outside their wheelhouse. False-positive is a valid decision.

If the audit produced no findings at all (unlikely but possible), `triage.md` still gets created, with the table header followed by a "no findings" note. Commit it anyway — the absence is the baseline.

- [ ] **Step 4: Commit the dated baseline dir**

Update CLAUDE.md **Last updated** with the audit completion note (e.g., "First framework audit baseline committed — `audit-YYYY-MM-DD-<sha>/` with N findings, M fix-now / K defer / L false-positive").

```bash
git add "$DIR" CLAUDE.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(audit): first framework audit baseline — YYYY-MM-DD-<sha>

First-ever audit pass of src/framework_cli/ via the 9-agent roster.
Preserved as a dated artifact parallel to tune scorecards. triage.md
records fix-now / defer / false-positive decisions per finding.

Phase 3 (implementing fix-now items) will be planned per-finding via
writing-plans in subsequent sessions.
EOF
)"
```

(Substitute the actual date+sha in the subject line.)

- [ ] **Step 5: Update the meta-plan status table**

Open `docs/superpowers/plans/2026-05-20-meta-plan.md`. Find the row that tracks Plan 11 / reviewer-system work (or add a new row for "Framework audit baseline"). Update the status to reflect the baseline being committed and reference the dated dir.

```bash
git add docs/superpowers/plans/2026-05-20-meta-plan.md CLAUDE.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(meta-plan): record framework audit baseline as a completed milestone
EOF
)"
```

This task is complete when the dated dir is committed and the meta-plan reflects the baseline. **Phase 3 (implementing fix-now findings) is out of scope for this plan** — each fix-now item gets its own plan via writing-plans when worked.

---

## Self-Review

**Spec coverage check (against `docs/superpowers/specs/2026-05-30-framework-audit-pass-design.md`):**

- Component 0 (split shared commands) → **Tasks 1, 2** ✓
- Component 1 (repeatable `--agent` on `audit-prepare`) → **Task 3** ✓
- Component 2 (`--preserve-as` on `audit-finalize`) → **Task 4** ✓
- Component 3 (`triage.md` hand-written) → **Task 7, Step 3** ✓
- Component 4 (`meta.json` auto-generated) → already produced by the existing `audit-finalize` logic; Task 6 verifies; meta-format requirements (work_item_count vs results_received) are visible in the spec's error-handling section and used by Task 6 Step 4 ✓
- Phase 1 (Run) → **Task 6** ✓
- Phase 2 (Preserve + triage) → **Task 7** ✓
- Phase 3 (Fix-now) → explicitly out of scope per spec; deferred to future per-finding plans ✓
- Call-site updates (slash commands, hooks, template mirrors) → folded into **Tasks 1 and 2** ✓
- Quality gate (pytest + ruff + ruff format --check + mypy) → run at end of every Task that touches Python source ✓
- Commit-gate hook timing (separate add/commit) → encoded in every commit step ✓

**Placeholder scan:** No "TBD", "TODO", "fill in", or unspecified pieces. Every test step has actual test code. Every implementation step shows the contract (signature + body shape) with explicit guidance to extract from the existing function bodies — this is appropriate because the existing function bodies ARE the source of truth for what to extract; duplicating them inline would be lossy and risk drift.

**Type consistency:** New commands use consistent option names (`--results`, `--out-dir`, `--target`, `--agent`, `--preserve-as`, `--force`). `audit-prepare`'s repeatable `--agent` is `list[str]`. `audit-finalize`'s `--preserve-as` is `Path | None`. Helper `_preserve_audit_tree(src, dst, *, force)` is keyword-only on `force` for clarity.

No issues to fix.

---

## Notes for the executing agent

- **Memory `reviewers-tune-quota-throttling`** is load-bearing for Task 6. If the audit dispatch silently drops subagents, the symptom is `results_received < work_item_count` in meta.json — re-dispatch only the missing subset; do not assume the run succeeded.
- **Memory `reviewers-tune-pytest-tmp-accumulation`** is the first thing to check if pytest produces mass spurious failures at any quality-gate step.
- **Memory `commit-gate-hook-timing`**: `git add` and `git commit` must be separate Bash invocations; chaining fails the PreToolUse hook.
- The framework's pre-commit hook also requires CLAUDE.md to be staged on every commit. Each commit step in this plan explicitly stages CLAUDE.md.
- `eval-prepare` and `eval-finalize` exist nowhere after Task 2 ends. If any code path you encounter still references them, it's a straggler — fix it under the appropriate Task's call-site step.
