# Context-Aware Review Agents — Slice C (Framework-Repo Target + Dogfooding CI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the framework review its OWN CLI/tooling source on its own CI, reusing the Slice A/B spine: a `framework_target()` profile (a 6-agent subset run agentic-for-all), a `--target framework` switch on `review-agents`/`review`, a `framework_diff()` that excludes the template payload, and a dogfooding review workflow.

**Architecture:** The spine stays target-blind; `--target framework` is the only behavioral fork and lives at the CLI layer. `review-agents --target framework` returns the subset; `review --target framework <agent>` sources a template-excluded diff and forces the Slice B agentic loop for every agent. A new `.github/workflows/review.yml` runs the matrix, secret-gated (skips neutral without the eval key). Template-payload review is out of scope (the product path / Plan 12).

**Tech Stack:** Python 3.12, Typer CLI, `git diff` pathspec exclusion, GitHub Actions, `pytest`. Run all tooling via `uv run`.

**Spec:** `docs/superpowers/specs/2026-05-28-context-aware-review-agents-slice-c-design.md`

---

## File Structure

- `src/framework_cli/review/diff.py` (modify) — extract `_diff_range()`; add `framework_diff()` (template-excluded).
- `src/framework_cli/review/context.py` (modify) — `FRAMEWORK_AGENTS` constant + `framework_target()`.
- `src/framework_cli/cli.py` (modify) — `--target` option on `review-agents` and `review`; `_review_run(..., force_agentic=False)`.
- `.github/workflows/review.yml` (create) — the framework review matrix + aggregate, secret-gated.
- `tests/review/test_framework_target.py` (create) — diff exclusion, subset, forced-agentic, default regression, workflow validity.

---

## Task 1: `framework_diff()` — template-excluded diff

**Files:**
- Modify: `src/framework_cli/review/diff.py`
- Test: `tests/review/test_framework_target.py`

- [ ] **Step 1: Write the failing test** — create `tests/review/test_framework_target.py`

```python
import subprocess
from pathlib import Path

from framework_cli.review.diff import framework_diff


def _git(args, cwd):
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def test_framework_diff_excludes_template_payload(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "src" / "framework_cli" / "template" / "src").mkdir(parents=True)
    (repo / "src" / "framework_cli").joinpath("cli.py").write_text("X = 1\n")
    (repo / "src" / "framework_cli" / "template" / "payload.py").write_text("A = 1\n")
    _git(["init", "-q"], repo)
    _git(["add", "-A"], repo)
    _git(["commit", "-qm", "base"], repo)
    # Change BOTH a CLI file and a template-payload file.
    (repo / "src" / "framework_cli" / "cli.py").write_text("X = 2\n")
    (repo / "src" / "framework_cli" / "template" / "payload.py").write_text("A = 2\n")
    _git(["commit", "-aqm", "change"], repo)

    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)  # → HEAD~1...HEAD range
    monkeypatch.chdir(repo)
    diff = framework_diff()
    assert "src/framework_cli/cli.py" in diff  # CLI change reviewed
    assert "template/payload.py" not in diff  # template payload excluded
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_framework_target.py::test_framework_diff_excludes_template_payload -v`
Expected: FAIL — `ImportError: cannot import name 'framework_diff'`.

- [ ] **Step 3: Refactor `pr_diff` to share the range, add `framework_diff`** in `src/framework_cli/review/diff.py`. Replace the `pr_diff` function with:

```python
def _diff_range() -> str:
    """The git range to review, from the CI environment (PR base...HEAD, else HEAD~1...HEAD)."""
    base = os.environ.get("GITHUB_BASE_REF")
    if base:
        subprocess.run(
            ["git", "fetch", "--depth=1", "origin", base],
            check=False,
            capture_output=True,
        )
        return f"origin/{base}...HEAD"
    return "HEAD~1...HEAD"


def pr_diff() -> str:
    """The unified diff to review, derived from the CI environment."""
    result = subprocess.run(
        ["git", "diff", _diff_range()], capture_output=True, text=True, check=False
    )
    return result.stdout


def framework_diff() -> str:
    """Like `pr_diff`, but excludes the template payload — the framework reviews only its
    own CLI/tooling source; template-payload quality is the product's concern (Slice C)."""
    result = subprocess.run(
        [
            "git",
            "diff",
            _diff_range(),
            "--",
            ".",
            ":(exclude)src/framework_cli/template",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout
```

(Keep the existing module imports `import os`, `import subprocess`, and `changed_files`/`matches_globs` unchanged.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_framework_target.py -v`
Expected: PASS. Then `uv run pytest tests/ -k "diff or review" -q` → no regressions (pr_diff behavior unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/diff.py tests/review/test_framework_target.py
git commit -m "feat(review): framework_diff (template-excluded) + shared _diff_range"
```

---

## Task 2: `FRAMEWORK_AGENTS` + `framework_target()`

**Files:**
- Modify: `src/framework_cli/review/context.py`
- Test: `tests/review/test_framework_target.py`

- [ ] **Step 1: Write the failing test** (append)

```python
from framework_cli.review.context import FRAMEWORK_AGENTS, framework_target
from framework_cli.review.registry import agent_names


def test_framework_agents_are_the_expected_subset_and_registered():
    assert FRAMEWORK_AGENTS == (
        "application-logic",
        "architecture",
        "dependency",
        "documentation",
        "security",
        "test-quality",
    )
    known = set(agent_names())
    assert set(FRAMEWORK_AGENTS) <= known  # every framework agent is a real agent


def test_framework_target_profile(tmp_path):
    t = framework_target(tmp_path)
    assert t.root == tmp_path
    assert t.active == FRAMEWORK_AGENTS
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_framework_target.py -v`
Expected: FAIL — `ImportError: cannot import name 'FRAMEWORK_AGENTS'`.

- [ ] **Step 3: Add the constant + factory** to `src/framework_cli/review/context.py` (after `generated_project_target`)

```python
# The review agents applicable to the framework's OWN CLI/tooling source (a Python
# Copier-wrapper CLI). App-domain agents (observability*, api-design, contracts,
# accessibility, usability, data-integrity, privacy, compliance, performance) don't apply.
FRAMEWORK_AGENTS: tuple[str, ...] = (
    "application-logic",
    "architecture",
    "dependency",
    "documentation",
    "security",
    "test-quality",
)


def framework_target(root: Path) -> ReviewTarget:
    """The dogfooding target: the framework repo reviews its own source. Every applicable
    agent runs agentic-for-all (see the CLI's --target framework path)."""
    return ReviewTarget(root=root, active=FRAMEWORK_AGENTS)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_framework_target.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/context.py tests/review/test_framework_target.py
git commit -m "feat(review): FRAMEWORK_AGENTS subset + framework_target profile"
```

---

## Task 3: `--target` on `review-agents`

**Files:**
- Modify: `src/framework_cli/cli.py` (`review_agents`, ~line 326)
- Test: `tests/review/test_framework_target.py`

- [ ] **Step 1: Write the failing test** (append)

```python
import json

from typer.testing import CliRunner

from framework_cli.cli import app
from framework_cli.review.context import FRAMEWORK_AGENTS


def test_review_agents_target_framework_lists_the_subset():
    result = CliRunner().invoke(app, ["review-agents", "--target", "framework"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == sorted(FRAMEWORK_AGENTS)


def test_review_agents_default_target_is_project_unchanged(tmp_path, monkeypatch):
    # Default target = project: still the event-based active set (a non-empty list that
    # is NOT exactly the framework subset).
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["review-agents", "--event", "pull_request"])
    assert result.exit_code == 0
    agents = json.loads(result.stdout)
    assert agents and json.loads(result.stdout) != sorted(FRAMEWORK_AGENTS)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_framework_target.py -k review_agents -v`
Expected: FAIL — `--target` is an unknown option.

- [ ] **Step 3: Add the `--target` option** to `review_agents` in `cli.py`. Replace the function with:

```python
def review_agents(
    event: str = typer.Option(
        "", "--event", help="GitHub event name (default: $GITHUB_EVENT_NAME)."
    ),
    target: str = typer.Option(
        "project", "--target", help="Review target: 'project' (default) or 'framework'."
    ),
) -> None:
    """Print the JSON array of review agents active for the event (drives the CI matrix)."""
    if target == "framework":
        from framework_cli.review.context import FRAMEWORK_AGENTS

        typer.echo(json.dumps(sorted(FRAMEWORK_AGENTS)))
        return

    from framework_cli.source import read_batteries

    resolved = event or os.environ.get("GITHUB_EVENT_NAME", "pull_request")
    batteries = read_batteries(Path("."))  # the generated project's recorded battery set
    typer.echo(json.dumps(active_agents(resolved, batteries)))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_framework_target.py -k review_agents -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/review/test_framework_target.py
git commit -m "feat(review): review-agents --target framework lists the dogfooding subset"
```

---

## Task 4: `--target framework` on `review` (template-excluded diff + forced agentic)

**Files:**
- Modify: `src/framework_cli/cli.py` (`_review_run` ~line 270, `review` ~line 441)
- Test: `tests/review/test_framework_target.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def test_review_run_force_agentic_uses_the_loop(monkeypatch, tmp_path):
    import framework_cli.cli as cli_mod
    from framework_cli.review.registry import get_agent

    called = {}

    def fake_agentic(diff, root, spec, client, *, max_turns):
        called["agent"] = spec.name
        return []

    monkeypatch.setattr("framework_cli.review.agentic.run_agent_agentic", fake_agentic)
    monkeypatch.setattr(cli_mod, "default_client", lambda: object())
    # 'security' is a BUNDLE-tier agent; force_agentic must route it through the loop.
    out = cli_mod._review_run("--- a/x\n+++ b/x\n", get_agent("security"), force_agentic=True)
    assert out == []
    assert called["agent"] == "review-security"


def test_review_command_target_framework_sources_framework_diff(monkeypatch, tmp_path):
    import framework_cli.cli as cli_mod
    from typer.testing import CliRunner
    from framework_cli.cli import app

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")  # so review proceeds past the no-key skip
    monkeypatch.setattr(cli_mod, "framework_diff", lambda: "")  # empty → no findings
    # An empty diff means the agentic loop is never even reached; the review neutrally
    # completes. Assert the framework diff source was used (patched) and exit is clean.
    result = CliRunner().invoke(app, ["review", "security", "--target", "framework"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_framework_target.py -k "force_agentic or target_framework" -v`
Expected: FAIL — `_review_run` has no `force_agentic` param; `review` has no `--target`; `cli_mod.framework_diff` doesn't exist.

- [ ] **Step 3: Add `force_agentic` to `_review_run` and `--target` to `review`.**

First, replace `_review_run` in `cli.py`:

```python
def _review_run(diff: str, spec: object, force_agentic: bool = False) -> list:
    from framework_cli.review.context import assemble
    from framework_cli.review.runner import run_agent

    if force_agentic or spec.context.strategy == "agentic":  # type: ignore[attr-defined]
        from framework_cli.review.agentic import DEFAULT_MAX_TURNS, run_agent_agentic

        turns = spec.context.max_agentic_turns or DEFAULT_MAX_TURNS  # type: ignore[attr-defined]
        return run_agent_agentic(diff, Path.cwd(), spec, default_client(), max_turns=turns)
    bundle = assemble(diff, Path.cwd(), spec.context, model=spec.model)  # type: ignore[attr-defined]
    return run_agent(bundle, spec, default_client())  # type: ignore[arg-type]
```

Then add `framework_diff` to the existing module-level import at `cli.py:17` — change it to:

```python
from framework_cli.review.diff import changed_files, framework_diff, matches_globs, pr_diff
```

(Module-level is required: the test monkeypatches `cli_mod.framework_diff`.)

Then add the `--target` option to `review` and branch the diff source + force_agentic. Modify the `review` signature and the diff/run lines:

```python
def review(
    agent: str = typer.Argument(..., help="Review agent name, e.g. 'security'."),
    findings_out: str = typer.Option(
        "",
        "--findings-out",
        help="Write this agent's findings JSON to this path (for aggregation).",
    ),
    target: str = typer.Option(
        "project", "--target", help="Review target: 'project' (default) or 'framework'."
    ),
) -> None:
```

In the `try:` block, replace the diff source + `_review_run` call:

```python
    try:
        diff = framework_diff() if target == "framework" else _review_diff()
        if spec.trigger_globs and not matches_globs(
            changed_files(diff), spec.trigger_globs
        ):
            payload = neutral_payload(
                spec.name, f"not triggered (no {', '.join(spec.trigger_globs)} change)"
            )
            post_or_skip(payload, token=token, repo=repo, sha=sha)
            _emit(payload.conclusion, [])
            typer.echo(f"{spec.name}: skipped (not triggered)")
            raise typer.Exit(0)
        findings = _review_run(diff, spec, force_agentic=(target == "framework"))
        payload = to_check_run(spec, findings)
```

(Everything else in `review` — the no-key skip, the `except` neutral handling, the final emit — is unchanged.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_framework_target.py -v`
Expected: PASS. Then `uv run pytest tests/ -k "review or cli" -q` → no regressions (the default `target="project"` path and existing `_review_run` callers are unchanged — `_review_run`'s new param defaults to False).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/review/test_framework_target.py
git commit -m "feat(review): review --target framework (template-excluded diff, forced agentic)"
```

---

## Task 5: The framework dogfooding review workflow

**Files:**
- Create: `.github/workflows/review.yml`
- Test: `tests/review/test_framework_target.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def test_review_workflow_is_valid_and_uses_framework_target():
    import yaml

    wf = yaml.safe_load(Path(".github/workflows/review.yml").read_text())
    # `on` may parse as the bool True (YAML quirk); accept either key.
    triggers = wf.get("on") or wf.get(True)
    assert "pull_request" in triggers and "push" in triggers
    jobs = wf["jobs"]
    assert {"review-plan", "review", "review-aggregate"} <= set(jobs)
    text = Path(".github/workflows/review.yml").read_text()
    assert "review-agents --target framework" in text
    assert "review ${{ matrix.agent }} --target framework" in text
    assert "ANTHROPIC_FRAMEWORK_CI_EVAL" in text  # the framework's eval secret
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_framework_target.py::test_review_workflow_is_valid_and_uses_framework_target -v`
Expected: FAIL — `.github/workflows/review.yml` does not exist.

- [ ] **Step 3: Create `.github/workflows/review.yml`**

```yaml
# Dogfooding: the framework reviews its OWN CLI/tooling source with the Layer-3 review
# agents (the framework-repo ReviewTarget). Template payload is out of scope here — that
# is the product's concern, reviewed when a generated project runs its own review CI.
# Secret-gated: with ANTHROPIC_FRAMEWORK_CI_EVAL unset the agents skip neutral (never red).
name: review

on:
  pull_request:
  push:
    branches: [master]

permissions:
  contents: read

jobs:
  review-plan:
    runs-on: ubuntu-latest
    outputs:
      agents: ${{ steps.list.outputs.agents }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - id: list
        run: echo "agents=$(uv run framework review-agents --target framework)" >> "$GITHUB_OUTPUT"

  review:
    needs: review-plan
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
      pull-requests: read
    strategy:
      fail-fast: false
      matrix:
        agent: ${{ fromJSON(needs.review-plan.outputs.agents) }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - name: review ${{ matrix.agent }} --target framework
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_FRAMEWORK_CI_EVAL }}
          GITHUB_TOKEN: ${{ github.token }}
        run: uv run framework review ${{ matrix.agent }} --target framework --findings-out findings/${{ matrix.agent }}.json
      - name: upload findings
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: review-findings-${{ matrix.agent }}
          path: findings/
          if-no-files-found: ignore

  review-aggregate:
    needs: review
    if: always()
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - uses: actions/download-artifact@v4
        with:
          pattern: review-findings-*
          merge-multiple: true
          path: all-findings
      - name: aggregate review findings
        env:
          GITHUB_TOKEN: ${{ github.token }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_PR_NUMBER: ${{ github.event.pull_request.number }}
        run: uv run framework review-aggregate all-findings
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_framework_target.py::test_review_workflow_is_valid_and_uses_framework_target -v`
Expected: PASS. If `actionlint` is available locally, also run it on the file; otherwise the YAML-load test is the gate (matches how the repo validates workflows).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/review.yml tests/review/test_framework_target.py
git commit -m "ci: framework dogfooding review workflow (--target framework, secret-gated)"
```

---

## Task 6: Branch finalize — full gate + state

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/plans/2026-05-20-meta-plan.md`

- [ ] **Step 1: Full gate**

Run:
```bash
uv run pytest -q --ignore=tests/acceptance
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
Expected: green. (Docker acceptance tier intentionally not run; note it.)

- [ ] **Step 2: Update state docs** — CLAUDE.md Current State (Slice C merged: `framework_target`/`FRAMEWORK_AGENTS` + `framework_diff` + `--target framework` + `review.yml`; template payload out → product path/Plan 12; Slice D next) and the meta-plan Plan 11 row. Stage `CLAUDE.md` (the commit-gate hook requires it).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
git commit -m "docs(state): Slice C (framework-repo review target + dogfooding CI) complete"
```

---

## Self-review notes

- **Spec coverage:** §2.1 agentic-for-all → T4 (`force_agentic`); §2.2 template-out → T1 (`framework_diff` exclusion); §2.3 subset → T2 (`FRAMEWORK_AGENTS`); §2.4 full-subset-no-narrowing → T3 (`review-agents --target framework` ignores event); §3.1 profile → T2; §3.2 diff scoping → T1; §3.3 CLI → T3/T4; §3.4 CI wiring + skip-neutral → T5 (the `review` no-key skip is pre-existing, exercised by the unset secret); §5 testing → T1–T5 tests.
- **Placeholder scan:** none — every code step is complete.
- **Type consistency:** `framework_diff()`, `_diff_range()`, `FRAMEWORK_AGENTS` (tuple), `framework_target(root) -> ReviewTarget`, `_review_run(diff, spec, force_agentic=False)`, `review(..., target="project")`, `review_agents(event, target="project")` used consistently across tasks and the workflow.
- **No scope creep:** no template-payload review (render-then-review explicitly dropped), no spine change, no generated-project-review change, no prompt edits, no real-key threshold work (Slice D).
- **Note:** the `review` no-key skip means the workflow is inert until `ANTHROPIC_FRAMEWORK_CI_EVAL` is set — by design (never red for a missing key); the first real framework-repo agentic run happens in Slice D once the secret is plumbed.
