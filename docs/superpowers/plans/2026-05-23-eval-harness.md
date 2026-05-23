# Review-Agent Eval Harness (Plan 7d) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every review agent golden fixtures and a `framework eval` command that runs them through the real Anthropic API and scores recall/precision against per-agent thresholds, plus a scheduled/on-change workflow.

**Architecture:** A pure, hermetically-tested scorer (`src/framework_cli/review/evals.py`: fixture discovery, the file+blocking-severity detection rule, set-level recall/precision scoring) sits under a `framework eval` CLI command that performs the real `run_agent` calls (gated by `ANTHROPIC_API_KEY`). Fixtures live under `tests/eval/fixtures/<agent>/{bad,good}/` (not shipped). The harness iterates the registry (`agent_names()`), so adding an agent needs no harness change. A framework-repo `agent-evals.yml` runs it on a schedule and on agent/logic changes.

**Tech Stack:** Python 3.12, Typer CLI, `dataclasses`, `statistics.mean`, PyYAML, pytest + `typer.testing.CliRunner`, the existing `framework_cli.review` modules (`findings`, `registry`, `runner`, `diff`), GitHub Actions.

**Source spec:** `docs/superpowers/specs/2026-05-23-eval-harness-design.md`

---

## Standing rules for every task

- **TDD:** failing test → red → minimum code → green → commit.
- **Commit-gate hook:** a `PreToolUse` hook blocks `git commit` unless a **change to `CLAUDE.md` is staged**. In every commit step: edit the `**Last updated:**` line near the top of `CLAUDE.md` to the current datetime + `PDT` with a one-clause note, then `git add CLAUDE.md` with the task files. A `git add` of an unmodified `CLAUDE.md` does **not** satisfy the hook. Don't rewrite the longer narrative per task; the controller finalizes it at merge.
- **`git add` and `git commit` are two separate Bash calls** (the hook inspects the staged index before the commit runs). Avoid the literal word "commit" in Bash `description` fields for read-only git inspection — the hook pattern-matches the description too.
- Run only targeted tests during a task (`uv run pytest tests/review/test_evals.py -q`, etc.). Do **not** run the full Docker acceptance suite mid-task (it has exhausted `/tmp`).
- Per-task gate before commit: `uv run pytest -q <touched test files>`, `uv run ruff check .`, `uv run mypy src`.
- **No real Anthropic call in the test suite.** Every test here is hermetic — the scorer is pure, and the command tests monkeypatch the `_eval_run` seam. Real calls happen only when `framework eval` runs at runtime (the workflow, or the controller's final real-eval pass).

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/framework_cli/review/evals.py` (create) | The scorer: `Fixture`, `load_fixtures`, `flags` (detection rule), `Thresholds`/`DEFAULT_THRESHOLDS`/`load_thresholds`, `AgentScore`/`score_agent`. Pure (file reads only in `load_fixtures`; no network). | 1, 2, 3 |
| `src/framework_cli/cli.py` (modify) | `_eval_run` seam + the `framework eval` command. | 4 |
| `tests/review/test_evals.py` (create) | Scorer unit tests + the fixture well-formedness + coverage gates. | 1, 2, 3, 5, 7 |
| `tests/test_cli.py` (modify) | `framework eval` command tests (mocked `_eval_run`). | 4 |
| `tests/eval/fixtures/<agent>/{bad,good}/*.diff` (+ `bad/*.expect.json`) (create) | Golden fixtures, all 12 agents, 3 bad + 1 good each. Not shipped in the wheel. | 5, 6, 7 |
| `tests/eval/fixtures/thresholds.yaml` (create) | Optional per-agent threshold overrides (created empty/minimal). | 7 |
| `.github/workflows/agent-evals.yml` (create) | Framework-repo workflow: schedule + on-agent/logic-change. | 8 |
| `tests/test_workflows.py` (create) | Assert `agent-evals.yml` parses as YAML and has the expected triggers/step. | 8 |

---

## Task 1: Fixture model + `load_fixtures`

**Files:** Create `src/framework_cli/review/evals.py`; Test `tests/review/test_evals.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/review/test_evals.py`:

```python
import json
from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_load_fixtures_discovers_bad_and_good(tmp_path):
    from framework_cli.review.evals import load_fixtures

    _write(tmp_path / "security" / "bad" / "sqli.diff", "+++ b/app.py\n")
    _write(tmp_path / "security" / "bad" / "sqli.expect.json", json.dumps({"file": "app.py"}))
    _write(tmp_path / "security" / "good" / "ok.diff", "+++ b/app.py\n")

    fx = load_fixtures(tmp_path)
    assert [(f.agent, f.kind, f.name, f.seeded_file) for f in fx] == [
        ("security", "bad", "sqli", "app.py"),
        ("security", "good", "ok", None),
    ]


def test_load_fixtures_skips_bad_without_valid_sidecar(tmp_path):
    from framework_cli.review.evals import load_fixtures

    _write(tmp_path / "security" / "bad" / "no-sidecar.diff", "+++ b/app.py\n")  # no .expect.json
    _write(tmp_path / "security" / "bad" / "bad-json.diff", "+++ b/app.py\n")
    _write(tmp_path / "security" / "bad" / "bad-json.expect.json", "{ not json")

    assert load_fixtures(tmp_path) == []  # both bad fixtures skipped, no good fixtures


def test_load_fixtures_ignores_non_dir_entries(tmp_path):
    from framework_cli.review.evals import load_fixtures

    _write(tmp_path / "thresholds.yaml", "security: {recall_min: 0.5, fp_max: 0.5}\n")
    assert load_fixtures(tmp_path) == []
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/review/test_evals.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.review.evals`.

- [ ] **Step 3: Create `evals.py` with the fixture model + loader**

Create `src/framework_cli/review/evals.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Fixture:
    agent: str
    kind: Literal["bad", "good"]
    name: str
    diff: str
    seeded_file: str | None  # the path the detection rule matches; set for bad fixtures


def load_fixtures(root: Path) -> list[Fixture]:
    """Discover `<root>/<agent>/{bad,good}/*.diff`. A bad fixture without a valid
    `<slug>.expect.json` (naming the seeded `file`) is skipped — it can't be scored."""
    fixtures: list[Fixture] = []
    for agent_dir in sorted(p for p in root.glob("*") if p.is_dir()):
        agent = agent_dir.name
        for kind in ("bad", "good"):
            for diff_path in sorted((agent_dir / kind).glob("*.diff")):
                try:
                    diff = diff_path.read_text()
                except OSError:
                    continue
                seeded_file: str | None = None
                if kind == "bad":
                    sidecar = diff_path.with_suffix(".expect.json")
                    try:
                        seeded_file = str(json.loads(sidecar.read_text())["file"])
                    except (OSError, json.JSONDecodeError, KeyError, TypeError):
                        continue  # unscoreable bad fixture
                fixtures.append(Fixture(agent, kind, diff_path.stem, diff, seeded_file))
    return fixtures
```

Note: `diff_path.with_suffix(".expect.json")` on `sqli.diff` yields `sqli.expect.json` (Path replaces the final suffix `.diff`). The glob `(agent_dir / kind).glob("*.diff")` on a missing `kind` dir yields nothing (no error).

- [ ] **Step 4: Run green**

Run: `uv run pytest tests/review/test_evals.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** — note "7d Task 1: Fixture + load_fixtures"
git add src/framework_cli/review/evals.py tests/review/test_evals.py CLAUDE.md
```
```bash
git commit -m "feat(eval): Fixture model + load_fixtures discovery

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: The detection rule (`flags`)

**Files:** Modify `src/framework_cli/review/evals.py`; Test `tests/review/test_evals.py`.

- [ ] **Step 1: Write the failing test**

Add to `tests/review/test_evals.py`:

```python
def _spec(threshold):
    from framework_cli.review.registry import AgentSpec

    return AgentSpec("review-x", "prompt", threshold, "always", "m")


def test_flags_blocking_finding_on_file_is_detected():
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    spec = _spec("high")
    assert flags([Finding("a.py", 1, "high", "x")], spec, file="a.py") is True


def test_flags_finding_on_other_file_is_not_detected():
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    spec = _spec("high")
    assert flags([Finding("b.py", 1, "high", "x")], spec, file="a.py") is False


def test_flags_below_threshold_is_not_a_block():
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    spec = _spec("high")
    assert flags([Finding("a.py", 1, "low", "x")], spec, file="a.py") is False


def test_flags_advisory_agent_counts_any_finding():
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    spec = _spec(None)  # advisory: never blocks in prod, so evals score on surfacing
    assert flags([Finding("a.py", 1, "low", "x")], spec, file="a.py") is True
    assert flags([], spec, file="a.py") is False


def test_flags_no_file_restriction_scans_all():
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    spec = _spec("high")
    assert flags([Finding("z.py", 9, "critical", "x")], spec) is True  # good-fixture block check
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/review/test_evals.py -k flags -q`
Expected: FAIL — `cannot import name 'flags'`.

- [ ] **Step 3: Implement `flags`**

Add to `src/framework_cli/review/evals.py` (add the imports `from framework_cli.review.findings import Finding, severity_rank` and `from framework_cli.review.registry import AgentSpec` at the top):

```python
def flags(findings: list[Finding], spec: AgentSpec, *, file: str | None = None) -> bool:
    """True if the agent raised a blocking concern, optionally restricted to `file`.

    Blocking agent (`block_threshold` set): a finding at/above the threshold. Advisory agent
    (`block_threshold is None` — never blocks in production): any finding counts as 'surfaced',
    so its evals score detection on surfacing rather than blocking.
    """
    for f in findings:
        if file is not None and f.path != file:
            continue
        if spec.block_threshold is None or severity_rank(f.severity) >= severity_rank(spec.block_threshold):
            return True
    return False
```

- [ ] **Step 4: Run green**

Run: `uv run pytest tests/review/test_evals.py -k flags -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** — note "7d Task 2: flags detection rule"
git add src/framework_cli/review/evals.py tests/review/test_evals.py CLAUDE.md
```
```bash
git commit -m "feat(eval): file + blocking-severity detection rule

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Thresholds + `score_agent`

**Files:** Modify `src/framework_cli/review/evals.py`; Test `tests/review/test_evals.py`.

- [ ] **Step 1: Write the failing test**

Add to `tests/review/test_evals.py`:

```python
def test_default_thresholds():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS

    assert DEFAULT_THRESHOLDS.recall_min == 0.67 and DEFAULT_THRESHOLDS.fp_max == 0.34


def test_load_thresholds_overrides_and_missing(tmp_path):
    from framework_cli.review.evals import Thresholds, load_thresholds

    assert load_thresholds(tmp_path / "nope.yaml") == {}
    (tmp_path / "thresholds.yaml").write_text("security: {recall_min: 0.5, fp_max: 0.5}\n")
    got = load_thresholds(tmp_path / "thresholds.yaml")
    assert got == {"security": Thresholds(0.5, 0.5)}


def test_score_agent_passes_when_recall_high_and_fp_low():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS, score_agent

    s = score_agent("security", [1.0, 1.0, 0.0], [0.0], DEFAULT_THRESHOLDS)
    assert s.recall == 2 / 3 and s.fp_rate == 0.0 and s.passed and s.reason == ""


def test_score_agent_fails_on_low_recall():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS, score_agent

    s = score_agent("x", [1.0, 0.0, 0.0], [0.0], DEFAULT_THRESHOLDS)
    assert not s.passed and "recall" in s.reason


def test_score_agent_fails_on_high_fp():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS, score_agent

    s = score_agent("x", [1.0, 1.0], [1.0], DEFAULT_THRESHOLDS)
    assert not s.passed and "fp" in s.reason


def test_score_agent_vacuous_when_no_fixtures():
    from framework_cli.review.evals import DEFAULT_THRESHOLDS, score_agent

    s = score_agent("x", [], [], DEFAULT_THRESHOLDS)
    assert s.recall == 1.0 and s.fp_rate == 0.0 and s.passed
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/review/test_evals.py -k "thresholds or score_agent" -q`
Expected: FAIL — `cannot import name 'DEFAULT_THRESHOLDS'`.

- [ ] **Step 3: Implement thresholds + scoring**

Add to `src/framework_cli/review/evals.py` (add `from statistics import mean` to the imports):

```python
@dataclass(frozen=True)
class Thresholds:
    recall_min: float
    fp_max: float


DEFAULT_THRESHOLDS = Thresholds(recall_min=0.67, fp_max=0.34)


def load_thresholds(path: Path) -> dict[str, Thresholds]:
    """Parse the optional per-agent threshold override file; missing file → {}."""
    if not path.is_file():
        return {}
    import yaml

    data = yaml.safe_load(path.read_text()) or {}
    return {
        agent: Thresholds(float(v["recall_min"]), float(v["fp_max"]))
        for agent, v in data.items()
    }


@dataclass(frozen=True)
class AgentScore:
    agent: str
    recall: float
    fp_rate: float
    bad_total: int
    good_total: int
    passed: bool
    reason: str  # empty when passed


def score_agent(
    agent: str,
    bad_detect_rates: list[float],
    good_block_rates: list[float],
    thr: Thresholds,
) -> AgentScore:
    """Set-level recall/precision. Each rate is a per-fixture hit fraction (hits/repeat)."""
    recall = mean(bad_detect_rates) if bad_detect_rates else 1.0
    fp_rate = mean(good_block_rates) if good_block_rates else 0.0
    reasons: list[str] = []
    if recall < thr.recall_min:
        reasons.append(f"recall {recall:.2f} < {thr.recall_min:.2f}")
    if fp_rate > thr.fp_max:
        reasons.append(f"fp {fp_rate:.2f} > {thr.fp_max:.2f}")
    return AgentScore(
        agent, recall, fp_rate, len(bad_detect_rates), len(good_block_rates), not reasons, "; ".join(reasons)
    )
```

- [ ] **Step 4: Run green**

Run: `uv run pytest tests/review/test_evals.py -q`
Expected: PASS (all Task 1-3 tests).

- [ ] **Step 5: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** — note "7d Task 3: thresholds + score_agent"
git add src/framework_cli/review/evals.py tests/review/test_evals.py CLAUDE.md
```
```bash
git commit -m "feat(eval): per-agent thresholds + set-level recall/precision scoring

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: The `framework eval` command

**Files:** Modify `src/framework_cli/cli.py`; Test `tests/test_cli.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` (`runner`, `app`, `import json as _json` are already at the top). These build a tiny fixtures tree and monkeypatch the `_eval_run` seam so no API call happens:

```python
def _make_fixture(tmp_path, agent, kind, slug, diff, seeded_file=None):
    d = tmp_path / agent / kind
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.diff").write_text(diff)
    if seeded_file is not None:
        (d / f"{slug}.expect.json").write_text(_json.dumps({"file": seeded_file}))


def test_eval_skips_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["eval", "security"])
    assert result.exit_code == 0
    assert "skipped" in result.output


def test_eval_require_key_fails_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["eval", "security", "--require-key"])
    assert result.exit_code == 1
    assert "required" in result.output


def test_eval_passes_when_agent_catches_bad_and_clean_on_good(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "bad", "b2", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    # catch the bad diffs (a high finding on a.py), stay clean on the good diff
    monkeypatch.setattr(
        cli_mod,
        "_eval_run",
        lambda diff, spec: [Finding("a.py", 1, "high", "danger")] if "good" not in diff else [],
    )
    # NB: the good diff text differs only by content; here both diffs are identical, so make the
    # mock depend on the spec call count instead:
    result = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output


def test_eval_fails_when_agent_misses(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod

    _make_fixture(tmp_path, "security", "bad", "b1", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "bad", "b2", "+++ b/a.py\n", "a.py")
    _make_fixture(tmp_path, "security", "good", "g1", "+++ b/a.py\n")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "_eval_run", lambda diff, spec: [])  # never catches anything
    result = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_eval_no_fixtures_skipped_unless_required(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    # empty fixtures dir → security has no fixtures
    assert runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path)]).exit_code == 0
    r = runner.invoke(app, ["eval", "security", "--fixtures", str(tmp_path), "--require-fixtures"])
    assert r.exit_code == 1
    assert "no fixtures" in r.output
```

> **Authoring note for the implementer:** in `test_eval_passes_...` the bad and good diffs must be distinguishable by the mock. Make the good diff a different string (e.g. `"+++ b/a.py\n# clean\n"`) and have the mock return findings only when the diff is one of the bad ones (e.g. key off `"clean" not in diff`). Adjust the fixture text + lambda so the mock catches the two bad diffs and returns `[]` for the good one. Keep the asserted behavior (PASS, exit 0).

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/test_cli.py -k eval -q`
Expected: FAIL — no such command `eval`.

- [ ] **Step 3: Add the seam + command to `cli.py`**

In `src/framework_cli/cli.py`, extend the registry import to include `agent_names`:

```python
from framework_cli.review.registry import active_agents, agent_names, get_agent
```

Add a module-level seam next to `_review_diff`/`_review_run`:

```python
def _eval_run(diff: str, spec: object) -> list:
    return run_agent(diff, spec, default_client())  # type: ignore[arg-type]
```

Add the command (after the `review-aggregate` command):

```python
@app.command(name="eval")
def eval_agents(
    agent: str = typer.Argument("", help="Evaluate only this agent (default: all registered)."),
    fixtures: str = typer.Option("tests/eval/fixtures", "--fixtures", help="Fixtures root directory."),
    repeat: int = typer.Option(1, "--repeat", help="Runs per fixture; rates are averaged."),
    require_fixtures: bool = typer.Option(
        False, "--require-fixtures", help="Fail if an evaluated agent has no fixtures."
    ),
    require_key: bool = typer.Option(
        False, "--require-key", help="Fail (not skip) if ANTHROPIC_API_KEY is unset."
    ),
) -> None:
    """Run golden fixtures through the review agents and score recall/precision (spec §20)."""
    from framework_cli.review.evals import (
        DEFAULT_THRESHOLDS,
        flags,
        load_fixtures,
        load_thresholds,
        score_agent,
    )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        if require_key:
            typer.echo("eval: ANTHROPIC_API_KEY is required but unset", err=True)
            raise typer.Exit(1)
        typer.echo("eval: skipped (no ANTHROPIC_API_KEY)")
        raise typer.Exit(0)

    root = Path(fixtures)
    thresholds = load_thresholds(root / "thresholds.yaml")
    by_agent: dict[str, list] = {}
    for fx in load_fixtures(root):
        by_agent.setdefault(fx.agent, []).append(fx)

    known = set(agent_names())
    for a in sorted(by_agent):
        if a not in known:
            typer.echo(f"warning: fixtures for unknown agent '{a}' (not in registry)", err=True)

    targets = [agent] if agent else agent_names()
    failing = 0
    missing: list[str] = []
    for a in targets:
        spec = get_agent(a)
        fx_list = by_agent.get(a, [])
        if not fx_list:
            missing.append(a)
            typer.echo(f"{spec.name}    no fixtures (skipped)")
            continue
        bad_rates: list[float] = []
        good_rates: list[float] = []
        for fx in fx_list:
            hits = 0
            for _ in range(repeat):
                try:
                    found = _eval_run(fx.diff, spec)
                except Exception:  # noqa: BLE001 - a failed run counts as a non-detection
                    found = []
                blocked = flags(found, spec, file=fx.seeded_file) if fx.kind == "bad" else flags(found, spec)
                hits += 1 if blocked else 0
            (bad_rates if fx.kind == "bad" else good_rates).append(hits / repeat)
        score = score_agent(a, bad_rates, good_rates, thresholds.get(a, DEFAULT_THRESHOLDS))
        status = "PASS" if score.passed else f"FAIL ({score.reason})"
        typer.echo(
            f"{spec.name}    recall {score.recall:.2f}  fp {score.fp_rate:.2f}    {status}"
        )
        if not score.passed:
            failing += 1

    summary = f"{len(targets)} agent(s) · {failing} failing"
    if missing:
        summary += f" · {len(missing)} without fixtures"
    typer.echo(summary)
    coverage_fail = bool(missing) and require_fixtures
    raise typer.Exit(1 if failing or coverage_fail else 0)
```

- [ ] **Step 4: Run green**

Run: `uv run pytest tests/test_cli.py -k eval -q`
Expected: PASS. Then `uv run pytest tests/test_cli.py tests/review/test_evals.py -q` → all green.

- [ ] **Step 5: Smoke the help**

Run: `uv run framework eval --help`
Expected: shows `--fixtures`, `--repeat`, `--require-fixtures`, `--require-key`.

- [ ] **Step 6: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** — note "7d Task 4: framework eval command"
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(eval): framework eval command runs fixtures + scores agents

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Fixture authoring (Tasks 5-7) — shared conventions

Each fixture is a **real unified diff** in the `+++ b/<path>` shape the runner consumes (so `framework_cli.review.diff.changed_files` parses it). The seeded file named in a bad fixture's `.expect.json` **must appear** as a changed file in that diff (the well-formedness gate checks this). Author each `bad` fixture to seed exactly one defect in the agent's domain, severe enough to clear the agent's block threshold; author each `good` fixture as a clean change in the same domain that should **not** trip the agent.

**Worked example — `security` (the canonical pattern; reuse for the rest):**

`tests/eval/fixtures/security/bad/sql-injection.diff`:
```diff
--- a/src/app/users.py
+++ b/src/app/users.py
@@ -1,4 +1,9 @@
 from app.db import connection
 
 
+def find_user(request):
+    raw_id = request.query_params["id"]
+    query = f"SELECT * FROM users WHERE id = '{raw_id}'"
+    return connection.execute(query).fetchone()
+
+
 def list_users():
     return connection.execute("SELECT * FROM users").fetchall()
```
`tests/eval/fixtures/security/bad/sql-injection.expect.json`:
```json
{"file": "src/app/users.py"}
```
`tests/eval/fixtures/security/good/parameterized-query.diff`:
```diff
--- a/src/app/users.py
+++ b/src/app/users.py
@@ -1,4 +1,9 @@
 from app.db import connection
 
 
+def find_user(request):
+    raw_id = request.query_params["id"]
+    query = "SELECT * FROM users WHERE id = %s"
+    return connection.execute(query, (raw_id,)).fetchone()
+
+
 def list_users():
     return connection.execute("SELECT * FROM users").fetchall()
```
(no sidecar for good fixtures)

**Per agent: author 3 bad + 1 good.** Each batch task lists the agents and the defect to seed per bad fixture (slug → defect, severity should clear the block threshold; the seeded file is yours to name but keep it realistic and consistent within the fixture). Commit each batch as one commit. The well-formedness test (added in Task 5) runs after each batch and must stay green.

---

## Task 5: Well-formedness gate + fixtures batch 1

**Files:** Modify `tests/review/test_evals.py`; Create fixtures for `security`, `data-integrity`, `data-lineage`, `application-logic`.

- [ ] **Step 1: Write the well-formedness gate test**

Add to `tests/review/test_evals.py`:

```python
_FIXTURES_ROOT = Path(__file__).parent.parent / "eval" / "fixtures"


def test_fixtures_are_wellformed():
    from framework_cli.review.diff import changed_files
    from framework_cli.review.evals import load_fixtures

    fixtures = load_fixtures(_FIXTURES_ROOT)
    assert fixtures, "no fixtures discovered"
    for fx in fixtures:
        label = f"{fx.agent}/{fx.kind}/{fx.name}"
        assert fx.diff.strip(), f"{label}: empty diff"
        changed = changed_files(fx.diff)
        assert changed, f"{label}: diff has no '+++ b/' paths"
        if fx.kind == "bad":
            assert fx.seeded_file in changed, (
                f"{label}: seeded_file {fx.seeded_file!r} not among changed files {changed}"
            )
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/review/test_evals.py -k wellformed -q`
Expected: FAIL — `assert fixtures` fails (no fixtures dir yet).

- [ ] **Step 3: Author the `security` fixtures**

Create the worked-example `security` fixtures above, plus two more bad fixtures:
- `bad/hardcoded-secret.diff` (+ `.expect.json`): a module that assigns an AWS-style secret key as a string literal (`AWS_SECRET_ACCESS_KEY = "AKIA...."`) used to construct a client. Severity: high.
- `bad/disabled-tls.diff` (+ `.expect.json`): an HTTP client call passing `verify=False` (TLS verification disabled). Severity: high.

So `security` has `bad/sql-injection`, `bad/hardcoded-secret`, `bad/disabled-tls`, `good/parameterized-query`.

- [ ] **Step 4: Author `data-integrity` (block threshold `info` — any finding blocks)**

- `bad/write-without-transaction.diff`: a multi-step DB write (two `session.add` + `session.commit`) with no transaction/rollback so a mid-failure leaves partial state.
- `bad/float-for-money.diff`: a money column/field declared as `float`/`Float` instead of `Decimal`/`Numeric`.
- `bad/missing-unique-constraint.diff`: an upsert/get-or-create that races because the table has no unique constraint on the natural key.
- `good/transactional-write.diff`: the multi-step write wrapped in `with session.begin():` (atomic).

- [ ] **Step 5: Author `data-lineage` (block `high`)**

- `bad/pii-to-new-store.diff`: user email written to a new analytics table/file with no lineage documentation.
- `bad/pii-to-third-party.diff`: forwarding `user.email`/`user.ssn` to an external API client.
- `bad/pii-in-log.diff`: logging a full PII record at info level.
- `good/documented-lineage.diff`: PII accessed through the sanctioned repository with a lineage docstring/comment and no new sink.

- [ ] **Step 6: Author `application-logic` (block threshold `info` — any finding blocks)**

- `bad/off-by-one.diff`: a range/slice boundary error (e.g. `range(1, len(xs))` dropping the first element, or `xs[: n - 1]` losing the last).
- `bad/inverted-conditional.diff`: a guard with the condition negated (e.g. `if not user.is_active: grant_access()`).
- `bad/wrong-operator.diff`: a calculation using `+` where `-` (or `*`/`/`) is intended, changing the result.
- `good/correct-discount.diff`: a correct, clearly-bounded calculation.

- [ ] **Step 7: Run the gate green**

Run: `uv run pytest tests/review/test_evals.py -k wellformed -q`
Expected: PASS (every authored bad fixture's seeded file appears in its diff; diffs parse).

- [ ] **Step 8: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** — note "7d Task 5: well-formedness gate + fixtures batch 1"
git add tests/review/test_evals.py tests/eval/fixtures/security tests/eval/fixtures/data-integrity tests/eval/fixtures/data-lineage tests/eval/fixtures/application-logic CLAUDE.md
```
```bash
git commit -m "test(eval): well-formedness gate + golden fixtures (security, data-integrity, data-lineage, application-logic)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Fixtures batch 2

**Files:** Create fixtures for `observability`, `test-quality`, `architecture`, `performance` (3 bad + 1 good each), following the shared conventions. The well-formedness gate (Task 5) covers them.

- [ ] **Step 1: Author `observability` (block `high`)**

- `bad/uninstrumented-path.diff`: a new external call / branch with no log line or span.
- `bad/swallowed-exception.diff`: `try: ... except Exception: pass` with no logging.
- `bad/no-correlation-id.diff`: a new request handler that logs without the correlation/trace id the scaffold provides.
- `good/instrumented-call.diff`: the same external call wrapped with a structured log + span and error logging.

- [ ] **Step 2: Author `test-quality` (block `high`)**

- `bad/asserts-nothing.diff`: a test that calls the function but has no assert (or `assert True`).
- `bad/mocks-under-test.diff`: a test that mocks the very unit it claims to test, so it asserts the mock.
- `bad/tautological.diff`: a test asserting a literal against itself (`assert 2 == 2`) dressed as a behavior test.
- `good/behavioral-test.diff`: a test that drives real behavior and asserts the outcome.

- [ ] **Step 3: Author `architecture` (block `high`)**

- `bad/domain-imports-web.diff`: a domain/business module importing FastAPI/`Request` (layering violation).
- `bad/circular-import.diff`: introduce a circular import between two modules.
- `bad/god-module.diff`: a single new module mixing HTTP routing, DB access, and business rules.
- `good/depends-on-interface.diff`: the domain depending on an injected protocol/interface, not the web layer.

- [ ] **Step 4: Author `performance` (block `high`)**

- `bad/n-plus-one.diff`: a loop issuing one query per item (N+1).
- `bad/load-entire-table.diff`: `select(Model)` loading a whole table into memory to count/filter in Python.
- `bad/sync-call-in-loop.diff`: a blocking network call inside a hot loop.
- `good/bulk-query.diff`: a single bulk/`IN` query replacing the per-item loop.

- [ ] **Step 5: Run the gate green**

Run: `uv run pytest tests/review/test_evals.py -k wellformed -q`
Expected: PASS.

- [ ] **Step 6: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** — note "7d Task 6: fixtures batch 2"
git add tests/eval/fixtures/observability tests/eval/fixtures/test-quality tests/eval/fixtures/architecture tests/eval/fixtures/performance CLAUDE.md
```
```bash
git commit -m "test(eval): golden fixtures (observability, test-quality, architecture, performance)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Fixtures batch 3 + thresholds.yaml + coverage gate

**Files:** Create fixtures for `compliance`, `privacy`, `documentation`, `dependency`; create `tests/eval/fixtures/thresholds.yaml`; add the coverage gate to `tests/review/test_evals.py`.

- [ ] **Step 1: Author `compliance` (block `high`)**

- `bad/logs-card-number.diff`: logging a full PAN/credit-card number (retention/PII violation).
- `bad/no-audit-log.diff`: a sensitive state change (role grant, deletion) with no audit-log entry.
- `bad/pii-retention.diff`: storing PII with no retention/expiry where policy requires it.
- `good/masked-logging.diff`: logging a masked card (`****1234`) and writing an audit entry.

- [ ] **Step 2: Author `privacy` (block `high`)**

- `bad/over-collection.diff`: a form/model collecting more PII than the feature needs.
- `bad/pii-in-response.diff`: an API response serializer exposing PII (SSN, full DOB).
- `bad/no-consent-gate.diff`: tracking/analytics on personal data with no consent check.
- `good/minimized-fields.diff`: a response model exposing only the minimal necessary fields.

- [ ] **Step 3: Author `documentation` (advisory — `block_threshold` None; detection = any finding on the file, good = no findings)**

- `bad/undocumented-public-api.diff`: a new public function/class with no docstring.
- `bad/stale-readme.diff`: a code change that contradicts an unchanged README claim (the diff includes the contradicting code).
- `bad/no-module-docstring.diff`: a new module with no module docstring and non-obvious purpose.
- `good/documented-api.diff`: the same public function with a clear docstring.

- [ ] **Step 4: Author `dependency` (advisory, file-trigger — the diff MUST modify a dependency file or the agent self-skips)**

- `bad/unpinned-dep.diff`: add a dependency to `pyproject.toml` with an unbounded spec (`requests = "*"`). `expect.json` file = `pyproject.toml`.
- `bad/known-vuln-pin.diff`: pin `pyproject.toml` to a version with a well-known CVE (e.g. an old `cryptography`/`requests`). file = `pyproject.toml`.
- `bad/abandoned-package.diff`: add an obscure/unmaintained package to `pyproject.toml`. file = `pyproject.toml`.
- `good/pinned-reputable-dep.diff`: add a reputable, bounded dependency (`httpx = ">=0.28,<1.0"`) to `pyproject.toml`.

> Every `dependency` fixture diff must touch `pyproject.toml` (the `+++ b/pyproject.toml` path) so the agent's `trigger_globs` fire.

- [ ] **Step 5: Create `thresholds.yaml` (start with defaults documented, no overrides yet)**

`tests/eval/fixtures/thresholds.yaml`:
```yaml
# Per-agent overrides for the eval pass thresholds. Agents omitted here use the defaults
# (recall_min 0.67, fp_max 0.34). Add an entry only when a real eval run shows an agent's
# healthy behavior doesn't fit the defaults (e.g. a noisier domain). Example:
# documentation:
#   recall_min: 0.5
#   fp_max: 0.5
```
(An all-comments file parses to `None` → `load_thresholds` returns `{}`. The well-formedness/`load_fixtures` glob ignores it because it is not a directory.)

- [ ] **Step 6: Add the coverage gate test**

Add to `tests/review/test_evals.py`:

```python
def test_every_registered_agent_has_fixtures():
    from framework_cli.review.evals import load_fixtures
    from framework_cli.review.registry import agent_names

    counts: dict[tuple[str, str], int] = {}
    for fx in load_fixtures(_FIXTURES_ROOT):
        counts[(fx.agent, fx.kind)] = counts.get((fx.agent, fx.kind), 0) + 1
    for a in agent_names():
        bad = counts.get((a, "bad"), 0)
        good = counts.get((a, "good"), 0)
        assert bad >= 2, f"{a}: needs >= 2 bad fixtures, has {bad}"
        assert good >= 1, f"{a}: needs >= 1 good fixture, has {good}"
```

- [ ] **Step 7: Run both gates green**

Run: `uv run pytest tests/review/test_evals.py -q`
Expected: PASS — well-formedness + coverage (all 12 registered agents now have ≥2 bad + ≥1 good).

- [ ] **Step 8: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** — note "7d Task 7: fixtures batch 3 + coverage gate"
git add tests/eval/fixtures/compliance tests/eval/fixtures/privacy tests/eval/fixtures/documentation tests/eval/fixtures/dependency tests/eval/fixtures/thresholds.yaml tests/review/test_evals.py CLAUDE.md
```
```bash
git commit -m "test(eval): golden fixtures (compliance, privacy, documentation, dependency) + coverage gate

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: The `agent-evals.yml` workflow

**Files:** Create `.github/workflows/agent-evals.yml` (framework repo root, NOT the template); Create `tests/test_workflows.py`.

> This is the framework repo's *own* workflow — `.github/workflows/` at the repo root, not under `src/framework_cli/template/`. It contains no Copier/Jinja templating, so no `{% raw %}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_workflows.py`:

```python
from pathlib import Path

import yaml

_WF = Path(__file__).parent.parent / ".github" / "workflows" / "agent-evals.yml"


def test_agent_evals_workflow_is_valid():
    wf = yaml.safe_load(_WF.read_text())
    triggers = wf[True] if True in wf else wf["on"]  # PyYAML parses `on:` as the bool True
    assert "schedule" in triggers
    # path-filtered push/PR on agent prompts or review logic
    push_paths = triggers["push"]["paths"]
    assert any("agents" in p for p in push_paths)
    assert any("review" in p for p in push_paths)

    steps = wf["jobs"]["eval"]["steps"]
    run = " ".join(str(s.get("run", "")) for s in steps)
    assert "framework eval" in run and "--require-key" in run
    # the key is supplied from secrets
    env_blocks = [s.get("env", {}) for s in steps]
    assert any("ANTHROPIC_API_KEY" in e for e in env_blocks)
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/test_workflows.py -q`
Expected: FAIL — the workflow file doesn't exist.

- [ ] **Step 3: Create the workflow**

Create `.github/workflows/agent-evals.yml`:

```yaml
# Review-agent evals (framework design spec §20). Runs the golden fixtures through the real
# review agents and scores recall/precision per agent. Opt-in via the ANTHROPIC_API_KEY secret;
# --require-key makes a missing secret fail loudly rather than silently skip. Triggers: a weekly
# schedule, and any change to an agent prompt or the review logic.
name: agent-evals

on:
  schedule:
    - cron: "0 7 * * 1" # Mondays 07:00 UTC
  push:
    paths:
      - "src/framework_cli/review/agents/**"
      - "src/framework_cli/review/**.py"
      - "tests/eval/fixtures/**"
  pull_request:
    paths:
      - "src/framework_cli/review/agents/**"
      - "src/framework_cli/review/**.py"
      - "tests/eval/fixtures/**"

permissions:
  contents: read

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - name: run agent evals
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: uv run framework eval tests/eval/fixtures --require-key
```

- [ ] **Step 4: Run green**

Run: `uv run pytest tests/test_workflows.py -q`
Expected: PASS.

- [ ] **Step 5: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** — note "7d Task 8: agent-evals workflow"
git add .github/workflows/agent-evals.yml tests/test_workflows.py CLAUDE.md
```
```bash
git commit -m "ci(eval): agent-evals workflow (schedule + on agent/logic change)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Final whole-branch review (controller, after all tasks)

- [ ] `uv run pytest -q` — full suite (incl. the Docker acceptance suite), expected all green. The eval suite is hermetic, so it adds no API cost here.
- [ ] `uv run ruff check .`, `uv run mypy src`, `uv lock --check` — clean (no new runtime deps; PyYAML is already a dependency).
- [ ] Build a wheel and confirm `evals.py` ships **and** that `tests/eval/fixtures/**` is **NOT** in the wheel (fixtures are test content): `uv build` then `python -m zipfile -l dist/*.whl | grep -E "evals|fixtures"` → `evals.py` present, no fixtures.
- [ ] `framework eval --help` shows the new options.
- [ ] **Real eval pass (the point of 7d):** if `ANTHROPIC_API_KEY` is available in the environment, run `uv run framework eval tests/eval/fixtures` for real and capture the scorecard. Any agent that *fails its thresholds because a fixture is mis-seeded or the threshold is mistuned* (not because the agent is genuinely weak) → fix the fixture or add a `thresholds.yaml` override, and re-run. Record the scorecard in the merge state note. If no key is available locally, say so — the first scheduled `agent-evals.yml` run validates real quality post-merge, and the controller flags that the thresholds are provisional until then.

Then use **superpowers:finishing-a-development-branch**: finalize the CLAUDE.md narrative + the meta-plan 7d row, FF-merge to `master`, push.

---

## Self-review (against the spec)

**Spec coverage:**
- §3 fixtures (layout, sidecar, not-shipped) — Tasks 5-7 author them under `tests/eval/fixtures/`; the final review confirms the wheel excludes them. ✔
- §4 scorer (`Fixture`/`load_fixtures`, `flags`, `Thresholds`/`load_thresholds`, `AgentScore`/`score_agent`) — Tasks 1-3. ✔
- §5 `framework eval` command (all flags, scorecard, skip/require-key, coverage report, exit codes, per-fixture error→non-detection, `_eval_run` seam) — Task 4. ✔
- §6 extensibility (registry-driven via `agent_names()`, coverage visibility, `--require-fixtures`, optional `thresholds.yaml`) — Task 4 (iteration + coverage) + Task 7 (`thresholds.yaml`); the coverage gate proves all registered agents are covered. ✔
- §7 workflow (`agent-evals.yml`, schedule + path-filtered push/PR, `--require-key`, secret) — Task 8. ✔
- §8 testing (hermetic: `load_fixtures`, `flags`, `load_thresholds`, `score_agent`, command with mocked `_eval_run`, workflow YAML parse; no real call in the suite) — Tasks 1-4, 8; the well-formedness + coverage gates (5/7). ✔

**Placeholder scan:** the scorer, command, workflow, and tests carry full code. Fixture *diffs* are specified per-fixture (agent, defect to seed, severity, seeded file) with a fully-worked `security` example and a structural well-formedness gate + a coverage gate — concrete and verifiable, not hand-waved. The one explicit authoring note (Task 4's mock must distinguish bad vs good diffs) is called out with the fix.

**Type consistency:** `Fixture(agent, kind, name, diff, seeded_file)`, `flags(findings, spec, *, file=None) -> bool`, `Thresholds(recall_min, fp_max)`, `load_thresholds(path) -> dict[str, Thresholds]`, `AgentScore(agent, recall, fp_rate, bad_total, good_total, passed, reason)`, `score_agent(agent, bad_detect_rates, good_block_rates, thr) -> AgentScore`, the `_eval_run(diff, spec)` seam — names/signatures are consistent across the command (Task 4), the scorer (Tasks 1-3), and the tests. The detection rule reuses production `block_threshold` + `severity_rank`. The harness iterates `agent_names()` (no hardcoded list).
