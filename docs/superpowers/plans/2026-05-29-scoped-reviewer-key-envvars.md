# Scope-Specific Reviewer-Key Env Vars Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the shared `ANTHROPIC_API_KEY` with scope-specific consumed env vars — `framework eval` reads `ANTHROPIC_EVAL_API_KEY`, `framework review` reads `ANTHROPIC_RUNTIME_API_KEY` — identically in dev and CI (hard cutover, no shared var, no path-selection by ambient env).

**Architecture:** The command fixes the scope, hence the var. `default_client(api_key_env)` builds the Anthropic client from a named var; `_eval_run`/`_review_run` and the two no-key skips use their scope's var. The framework workflows and the generated `ci.yml` map each scoped GH secret into the matching env var; `SECRETS.md`(.jinja) document it. Also fixes a latent template mismatch (the generated review job read `secrets.ANTHROPIC_API_KEY` while its `SECRETS.md` named the secret `ANTHROPIC_<PKG>_CI_RUNTIME`).

**Tech Stack:** Python 3.12, Typer, the Anthropic SDK, GitHub Actions, Copier/Jinja, `pytest`. Run all tooling via `uv run`.

**Spec:** `docs/superpowers/specs/2026-05-29-scoped-reviewer-key-envvars-design.md`

---

## File Structure

- `src/framework_cli/review/runner.py` (modify) — `EVAL_KEY_ENV`/`RUNTIME_KEY_ENV` constants; `default_client(api_key_env)`.
- `src/framework_cli/cli.py` (modify) — import the constants; `_eval_run`/`_review_run` client construction; the `eval`/`review` no-key skips + `--require-key` text.
- `.github/workflows/agent-evals.yml`, `.github/workflows/review.yml` (modify) — set the scoped env var from the scoped secret.
- `src/framework_cli/template/.github/workflows/ci.yml.jinja`, `src/framework_cli/template/SECRETS.md.jinja` (modify) — generated review job + convention doc.
- `SECRETS.md` (modify) — repo-root consumed-as + local-dev section.
- Tests: `tests/test_cli.py`, `tests/review/test_framework_target.py`, `tests/test_workflows.py`, `tests/test_copier_runner.py`.

---

## Task 1: Scope-aware client + CLI key resolution

**Files:**
- Modify: `src/framework_cli/review/runner.py`, `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`, `tests/review/test_framework_target.py`

- [ ] **Step 1: Add a failing test** to `tests/test_cli.py` (append near the other review tests)

```python
def test_review_reads_runtime_key_not_shared_or_eval(monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.cli import app
    from typer.testing import CliRunner

    runner = CliRunner()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_EVAL_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(
        cli_mod, "_review_run", lambda diff, spec, force_agentic=False: []
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    # Runtime key present → the review runs (not the no-key skip).
    assert runner.invoke(app, ["review", "security"]).exit_code == 0
    # Only a bare ANTHROPIC_API_KEY (no runtime var) → skip-neutral (exit 0, "skipped").
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    res = runner.invoke(app, ["review", "security"])
    assert res.exit_code == 0 and "skipped" in res.stdout.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_review_reads_runtime_key_not_shared_or_eval -v`
Expected: FAIL — the review command still keys on `ANTHROPIC_API_KEY` (the first invoke skips because it's unset; the second runs).

- [ ] **Step 3: Implement the scoped client** in `src/framework_cli/review/runner.py`. Add `import os` to the imports, and replace `default_client`:

```python
EVAL_KEY_ENV = "ANTHROPIC_EVAL_API_KEY"
RUNTIME_KEY_ENV = "ANTHROPIC_RUNTIME_API_KEY"


def default_client(api_key_env: str) -> Any:  # pragma: no cover - thin SDK wrapper
    import anthropic

    return anthropic.Anthropic(api_key=os.environ.get(api_key_env))
```

- [ ] **Step 4: Wire `cli.py`.** Change the import at `cli.py:24`:

```python
from framework_cli.review.runner import EVAL_KEY_ENV, RUNTIME_KEY_ENV, default_client
```

In `_review_run`, both `default_client()` calls → `default_client(RUNTIME_KEY_ENV)`. In `_eval_run`, both `default_client()` calls → `default_client(EVAL_KEY_ENV)`.

Replace the `eval` command's no-key skip:

```python
    if not os.environ.get(EVAL_KEY_ENV):
        if require_key:
            typer.echo("eval: ANTHROPIC_EVAL_API_KEY is required but unset", err=True)
            raise typer.Exit(1)
        typer.echo("eval: skipped (no ANTHROPIC_EVAL_API_KEY)")
        raise typer.Exit(0)
```

Replace the `review` command's no-key skip:

```python
    if not os.environ.get(RUNTIME_KEY_ENV):
        payload = neutral_payload(
            spec.name, "review skipped — set ANTHROPIC_RUNTIME_API_KEY to enable."
        )
        post_or_skip(payload, token=token, repo=repo, sha=sha)
        _emit(payload.conclusion, [])
        typer.echo(f"{spec.name}: skipped (no ANTHROPIC_RUNTIME_API_KEY)")
        raise typer.Exit(0)
```

Update the `--require-key` option help on the `eval` command from `"Fail (not skip) if ANTHROPIC_API_KEY is unset."` to `"Fail (not skip) if ANTHROPIC_EVAL_API_KEY is unset."`.

- [ ] **Step 5: Keep the existing tests green** — they set/unset the old shared var. In `tests/test_cli.py`, for each listed line replace `ANTHROPIC_API_KEY` with the scope var for that test's command:
  - **review** tests (commands `["review", …]`) — lines 110, 127, 144, 160, 185, 202, 221, 252, 268 → `ANTHROPIC_RUNTIME_API_KEY` (this includes the `delenv` at 110 and 268).
  - **eval** tests (commands `["eval", …]`) — lines 323, 330, 344, 365, 375, 388, 395, 530 → `ANTHROPIC_EVAL_API_KEY` (includes `delenv` at 323, 330).

  In `tests/review/test_framework_target.py`, `test_review_command_target_framework_sources_framework_diff` sets `ANTHROPIC_API_KEY` (a `review` command) → change it to `ANTHROPIC_RUNTIME_API_KEY`.

- [ ] **Step 6: Run + verify**

Run: `uv run pytest tests/test_cli.py tests/review/test_framework_target.py -q` → all pass (incl. the new test).
Then `uv run pytest -q --ignore=tests/acceptance` → green; `uv run ruff check . && uv run ruff format --check . && uv run mypy src` → clean.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/review/runner.py src/framework_cli/cli.py tests/test_cli.py tests/review/test_framework_target.py
git commit -m "feat(review): scope-specific reviewer keys (eval→ANTHROPIC_EVAL_API_KEY, review→ANTHROPIC_RUNTIME_API_KEY)"
```

---

## Task 2: Framework workflows map scoped secret → scoped var

**Files:**
- Modify: `.github/workflows/agent-evals.yml`, `.github/workflows/review.yml`
- Test: `tests/test_workflows.py`, `tests/review/test_framework_target.py`

- [ ] **Step 1: Update the failing test(s) first.** In `tests/test_workflows.py`, the assertion at line 28 is `assert any("ANTHROPIC_API_KEY" in e for e in env_blocks)`. Read the surrounding test to see which workflow it covers; change it to assert the **scoped** var that workflow now sets (`ANTHROPIC_EVAL_API_KEY` for `agent-evals.yml`, `ANTHROPIC_RUNTIME_API_KEY` for `review.yml`) and that bare `ANTHROPIC_API_KEY` is **absent**. If the test covers both workflows, assert each scoped var in its own workflow.

In `tests/review/test_framework_target.py::test_review_workflow_is_valid_and_uses_framework_target`, the existing assertions check `ANTHROPIC_FRAMEWORK_CI_RUNTIME` present + bare `ANTHROPIC_API_KEY` absent — keep those, and add `assert "ANTHROPIC_RUNTIME_API_KEY" in text` (the env-var name the secret now maps into).

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_workflows.py tests/review/test_framework_target.py -q`
Expected: FAIL — the workflows still set `ANTHROPIC_API_KEY`.

- [ ] **Step 3: Edit `.github/workflows/agent-evals.yml`** — the `env:` line under the eval step:

```yaml
          ANTHROPIC_EVAL_API_KEY: ${{ secrets.ANTHROPIC_FRAMEWORK_CI_EVAL }}
```

(Also update the header comment that says "mapped into the ANTHROPIC_API_KEY env var the CLI reads" → "the ANTHROPIC_EVAL_API_KEY env var".)

- [ ] **Step 4: Edit `.github/workflows/review.yml`** — the review step `env:`:

```yaml
          ANTHROPIC_RUNTIME_API_KEY: ${{ secrets.ANTHROPIC_FRAMEWORK_CI_RUNTIME }}
```

(Also update the top comment line "with ANTHROPIC_FRAMEWORK_CI_RUNTIME unset the agents skip neutral" stays accurate; if it mentions `ANTHROPIC_API_KEY` anywhere, change to `ANTHROPIC_RUNTIME_API_KEY`.)

- [ ] **Step 5: Run + verify**

Run: `uv run pytest tests/test_workflows.py tests/review/test_framework_target.py -q` → pass.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/agent-evals.yml .github/workflows/review.yml tests/test_workflows.py tests/review/test_framework_target.py
git commit -m "ci: map the framework's scoped reviewer secrets into the scoped env vars"
```

---

## Task 3: Template payload (generated review job + SECRETS.md.jinja)

**Files:**
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja`, `src/framework_cli/template/SECRETS.md.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Update the failing render assertions.** In `tests/test_copier_runner.py`:
  - line 917 `assert "ANTHROPIC_API_KEY" in ci` → assert the generated `ci.yml` review job carries the scoped var **and** the runtime secret, and not the bare var:
    ```python
    assert "ANTHROPIC_RUNTIME_API_KEY" in ci
    assert "secrets.ANTHROPIC_DEMO_CI_RUNTIME" in ci
    assert "ANTHROPIC_API_KEY" not in ci
    ```
  - line 3014 `assert "ANTHROPIC_API_KEY" in secrets` → `assert "ANTHROPIC_RUNTIME_API_KEY" in secrets`.
  - line 3020 `assert "ANTHROPIC_DEMO_CI_RUNTIME" in secrets` → keep unchanged.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -k "ci or secrets or anthropic" -v`
Expected: FAIL — the rendered `ci.yml`/`SECRETS.md` still use `ANTHROPIC_API_KEY`.

- [ ] **Step 3: Edit `ci.yml.jinja`'s review step `env:`** (currently `ANTHROPIC_API_KEY: {% raw %}${{ secrets.ANTHROPIC_API_KEY }}{% endraw %}`). Replace with the scoped var mapped from the package-specific runtime secret:

```jinja
          ANTHROPIC_RUNTIME_API_KEY: {% raw %}${{ secrets.ANTHROPIC_{% endraw %}{{ package_name | upper }}{% raw %}_CI_RUNTIME }}{% endraw %}
```

This renders (for package `demo`) to `ANTHROPIC_RUNTIME_API_KEY: ${{ secrets.ANTHROPIC_DEMO_CI_RUNTIME }}`. Also update the nearby step-9/10 comment that says "set the ANTHROPIC_API_KEY secret to enable" → "set the `ANTHROPIC_<PKG>_CI_RUNTIME` secret to enable" (a plain comment; you may interpolate `{{ package_name | upper }}` or keep it generic as `ANTHROPIC_<PKG>_CI_RUNTIME`).

- [ ] **Step 4: Edit `SECRETS.md.jinja`:**
  - The convention prose (line ~28): the parenthetical example `(e.g. `ANTHROPIC_API_KEY`)` → `(e.g. `ANTHROPIC_RUNTIME_API_KEY`)`.
  - The table row "Review-agent LLM key" **Consumed as** cell: `` `ANTHROPIC_API_KEY` env `` → `` `ANTHROPIC_RUNTIME_API_KEY` env ``.
  - The closing note: `mapped to `ANTHROPIC_API_KEY`` → `mapped to `ANTHROPIC_EVAL_API_KEY` (and the runtime key to `ANTHROPIC_RUNTIME_API_KEY`)`.

- [ ] **Step 5: Run + verify the render + integrity stays green**

Run:
```bash
uv run pytest tests/test_copier_runner.py -q
uv run pytest tests/integrity -q   # render-generated manifest tracks the new ci.yml; no committed golden to update
```
Expected: pass. (The integrity manifest is generated from the rendered LOCKED files, so the new `ci.yml` bytes are reflected automatically — there is no committed baseline file to regenerate. The real-world effect is only that existing projects' `ci.yml` changes on their next `framework upskill`.)

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/.github/workflows/ci.yml.jinja src/framework_cli/template/SECRETS.md.jinja tests/test_copier_runner.py
git commit -m "feat(template): generated review job uses ANTHROPIC_RUNTIME_API_KEY from the _CI_RUNTIME secret"
```

---

## Task 4: Repo-root SECRETS.md (consumed-as + local dev)

**Files:**
- Modify: `SECRETS.md`

- [ ] **Step 1: Update the "This repo's secrets" table** — change the **Consumed as** column for the two rows from `ANTHROPIC_API_KEY` to the scoped vars: the eval row → `ANTHROPIC_EVAL_API_KEY`, the runtime row → `ANTHROPIC_RUNTIME_API_KEY`. Update the surrounding prose that says "Both map to the `ANTHROPIC_API_KEY` env var" → "Each maps into its scoped env var (`ANTHROPIC_EVAL_API_KEY` / `ANTHROPIC_RUNTIME_API_KEY`) in its workflow."

- [ ] **Step 2: Add the "Local development" section** (after the closing note):

```markdown
## Local development (`env = dev`) — mirrors the CI scope split

Running the agents/eval locally uses **dev-scoped, per-machine** keys, keeping the SAME two
scopes as CI — `eval` for `framework eval`, `runtime` for `framework review` — so dev mirrors
CI rather than collapsing the boundary:

```
anthropic_framework_<owner>_dev_<host>_eval_<YYYYMMDD>_<rand>
anthropic_framework_<owner>_dev_<host>_runtime_<YYYYMMDD>_<rand>
```

**Personal and never committed** — not GitHub secrets. Each consumes its own scoped env var,
so both coexist and nothing is swapped (CI isolates the scopes by separate jobs; dev by separate
var names):

```bash
export ANTHROPIC_EVAL_API_KEY=sk-ant-…      # read by: framework eval
export ANTHROPIC_RUNTIME_API_KEY=sk-ant-…   # read by: framework review (incl. --target framework)
```

Put them in a gitignored `.env` you source, or your shell profile. Rotate/revoke independently
of the CI keys; blast-radius is one developer's machine.
```

- [ ] **Step 2b:** If the SECRETS.md prose still claims the keys map to `ANTHROPIC_API_KEY` anywhere else, fix those mentions too (grep `ANTHROPIC_API_KEY SECRETS.md`).

- [ ] **Step 3: Verify + Commit**

Run: `grep -n "ANTHROPIC_API_KEY" SECRETS.md` → expect no stale "consumed as ANTHROPIC_API_KEY" claims remain.
```bash
git add SECRETS.md
git commit -m "docs(secrets): scoped consumed env vars + local-dev (two dev keys, no shared var)"
```

---

## Task 5: Branch finalize — full gate + state

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/plans/2026-05-20-meta-plan.md`

- [ ] **Step 1: Full gate**

Run:
```bash
uv run pytest -q --ignore=tests/acceptance
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
Expected: green. (Docker acceptance tier not run; note it. Optionally run `tests/acceptance` for the rendered-project review job if convenient.)

- [ ] **Step 2: Sanity-check no stale shared-var references remain**

Run: `grep -rn "ANTHROPIC_API_KEY" src/ .github/ --include=*.py --include=*.yml --include=*.jinja`
Expected: no occurrences in the framework's review/eval code paths or workflows (the only acceptable hits, if any, are unrelated comments — review each).

- [ ] **Step 3: Update state docs** — CLAUDE.md Current State (this slice done: scoped reviewer-key vars, hard cutover, template secret-name fix; Slice D next) + the meta-plan. Stage `CLAUDE.md` (the commit-gate hook requires it).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
git commit -m "docs(state): scope-specific reviewer-key env vars complete"
```

---

## Self-review notes

- **Spec coverage:** §4.1 code → T1; §4.2 framework workflows → T2; §4.3 template payload (incl. the secret-name fix) → T3; §4.4 repo SECRETS.md (incl. two-dev-key local section) → T4; §5 testing → spread across T1–T3 (cli, workflow, render assertions) + T5 gate; §2 hard cutover (no fallback) → T1's `default_client(api_key_env)` reads only the named var + T5's grep guard; §6 one-time ci.yml shift → T3 Step 5 (clarified: render-generated manifest, no committed golden).
- **Placeholder scan:** none — every code/edit step shows the exact content; the test line-number lists are explicit.
- **Type consistency:** `EVAL_KEY_ENV`/`RUNTIME_KEY_ENV` (str constants in `runner.py`), `default_client(api_key_env: str)`, the `eval`→EVAL / `review`→RUNTIME mapping used consistently across code, workflows, template, docs, and tests.
- **No scope creep:** GH secret names unchanged; no agent/spine/registry logic touched; no real-key scoring (Slice D); the env-parity reviewer is only a recorded follow-up, not built here.
