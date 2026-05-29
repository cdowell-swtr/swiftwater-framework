# Scope-specific reviewer-key env vars — design

**Date:** 2026-05-29
**Status:** Approved (brainstorm).
**Prerequisite to:** Slice D of the context-aware review agents (real-key eval scoring) — Slice D consumes these keys, so the consumption model must be right first.
**Relates to:** the repo-root `SECRETS.md` + `src/framework_cli/template/SECRETS.md.jinja` two-tier secret convention.

## 1. Problem

The framework has two distinct LLM uses with two scope-distinct keys (eval, runtime — see `SECRETS.md`), but both are consumed through the **same** env var `ANTHROPIC_API_KEY` (the SDK default). Isolation then depends on *which value happens to be in that one var* — set per-job on CI, and (as last proposed) swapped per-invocation locally. Selecting behavior by mutating a shared ambient env var is an antipattern: the two scopes can't coexist, and running the wrong path with the wrong key in your shell silently uses the wrong credential.

**Fix:** make the *consumed* name scope-specific, identically in dev and CI, so each execution path reads its own fixed var and both keys coexist:

- `framework eval` reads **`ANTHROPIC_EVAL_API_KEY`**
- `framework review` (project target *and* `--target framework`) reads **`ANTHROPIC_RUNTIME_API_KEY`**

This is the dev↔CI parity the framework is built on: CI isolates the two scopes by separate jobs; dev isolates them by separate var names — nothing is swapped.

## 2. Decisions (locked in brainstorm)

1. **Hard cutover** — no fallback to `ANTHROPIC_API_KEY`. The shared var disappears from the framework's review/eval paths. Safe: the eval/review CI is brand-new (no secret set, no live consumers); generated projects re-render on `framework upskill`.
2. **Fix the latent template mismatch here** — `ci.yml.jinja`'s review job currently reads `secrets.ANTHROPIC_API_KEY` while `SECRETS.md.jinja` says the secret is `ANTHROPIC_<PKG>_CI_RUNTIME`. This slice makes them agree.

## 3. Goals / non-goals

**Goals:** scope-specific consumed env vars (`ANTHROPIC_EVAL_API_KEY`, `ANTHROPIC_RUNTIME_API_KEY`) across framework code, framework workflows, template payload, and docs; hard cutover; the template secret-name fix.

**Non-goals:** GH *secret* names are unchanged (`ANTHROPIC_FRAMEWORK_CI_EVAL`/`_RUNTIME`; generated `ANTHROPIC_<PKG>_CI_RUNTIME`). No agent/spine/registry logic change. Not creating the actual keys (the human does that per `SECRETS.md`). Not Slice D scoring.

## 4. Architecture

The **command** determines the scope, hence the var:

| Command | Scope | Consumed env var |
|---|---|---|
| `framework eval` | eval | `ANTHROPIC_EVAL_API_KEY` |
| `framework review` (project + `--target framework`) | runtime | `ANTHROPIC_RUNTIME_API_KEY` |

### 4.1 Code (`review/runner.py`, `cli.py`)
- `runner.py`: add constants `EVAL_KEY_ENV = "ANTHROPIC_EVAL_API_KEY"` and `RUNTIME_KEY_ENV = "ANTHROPIC_RUNTIME_API_KEY"`. Change `default_client()` → `default_client(api_key_env: str)` returning `anthropic.Anthropic(api_key=os.environ.get(api_key_env))`.
- `cli.py`:
  - `_eval_run(...)` constructs the client with `EVAL_KEY_ENV`; `_review_run(...)` (both review paths) with `RUNTIME_KEY_ENV`.
  - The `eval` command's no-key skip checks `os.environ.get(EVAL_KEY_ENV)`; the `review` command's checks `os.environ.get(RUNTIME_KEY_ENV)`.
  - `--require-key` help text + the skip/echo messages name the scoped var for that command.
- Import `EVAL_KEY_ENV`/`RUNTIME_KEY_ENV` into `cli.py` from `runner.py`.

### 4.2 Framework workflows
- `.github/workflows/agent-evals.yml`: `ANTHROPIC_EVAL_API_KEY: ${{ secrets.ANTHROPIC_FRAMEWORK_CI_EVAL }}` (was `ANTHROPIC_API_KEY`).
- `.github/workflows/review.yml`: `ANTHROPIC_RUNTIME_API_KEY: ${{ secrets.ANTHROPIC_FRAMEWORK_CI_RUNTIME }}` (was `ANTHROPIC_API_KEY`). Update the header comment's "skips neutral" line to the new var.

### 4.3 Template payload
- `src/framework_cli/template/.github/workflows/ci.yml.jinja` review job env: `ANTHROPIC_RUNTIME_API_KEY: {% raw %}${{ secrets.ANTHROPIC_{{ package_name | upper }}_CI_RUNTIME }}{% endraw %}` (was `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}`) — fixes the var name **and** the secret-name mismatch. Update the nearby step-9/10 comment (line ~196) that references the `ANTHROPIC_API_KEY` secret.
- `src/framework_cli/template/SECRETS.md.jinja`: the review-agent row's **"Consumed as"** → `ANTHROPIC_RUNTIME_API_KEY`; the convention prose example and the framework-own-CI note updated to the scoped vars (e.g. eval → `ANTHROPIC_EVAL_API_KEY`, runtime → `ANTHROPIC_RUNTIME_API_KEY`).
- **Integrity:** `ci.yml` is LOCKED/integrity-tracked and the review job renders for every project, so this is a deliberate **one-time baseline manifest shift** (precedented by OBS-PROD/SVC-PROD/8f-w). `SECRETS.md` is not integrity-tracked.

### 4.4 Repo-root `SECRETS.md`
- The two-CI-secret table's **"Consumed as"** column → `ANTHROPIC_EVAL_API_KEY` / `ANTHROPIC_RUNTIME_API_KEY`.
- Add the corrected **"Local development (`env = dev`)"** section: **two** dev keys (`…_dev_<host>_eval_…` and `…_dev_<host>_runtime_…`), consumed as `ANTHROPIC_EVAL_API_KEY` / `ANTHROPIC_RUNTIME_API_KEY` — **both exported, neither swapped** (true dev↔CI parity; CI isolates by job, dev by var name).

## 5. Testing

- `tests/test_cli.py`: the `review` and `eval` no-key-skip tests + any test that sets `ANTHROPIC_API_KEY` switch to the scoped var for that command (`eval` → `ANTHROPIC_EVAL_API_KEY`, `review` → `ANTHROPIC_RUNTIME_API_KEY`). A new assertion: with only the *wrong*-scope var set, the command still skips (it reads only its own var).
- `tests/review/test_framework_target.py`: `review.yml` asserts `ANTHROPIC_RUNTIME_API_KEY` is set from `secrets.ANTHROPIC_FRAMEWORK_CI_RUNTIME`, and that bare `ANTHROPIC_API_KEY` does **not** appear; the `--target framework` command test sets `ANTHROPIC_RUNTIME_API_KEY`.
- Template: the copier-render / acceptance check for the generated `ci.yml` asserts the review job carries `ANTHROPIC_RUNTIME_API_KEY` + `secrets.ANTHROPIC_<PKG>_CI_RUNTIME` (no bare `ANTHROPIC_API_KEY`). Regenerate the integrity baseline for the one-time shift; confirm `framework integrity --ci` green.
- `agent-evals.yml`: if a workflow test covers it, assert `ANTHROPIC_EVAL_API_KEY`.
- Full gate (ex-acceptance) + ruff/format/mypy green.

## 6. Risks

- **One-time `ci.yml` baseline manifest shift** — expected, regenerated in-slice; verified green both ways.
- **Hard cutover** — anything already consuming `ANTHROPIC_API_KEY` (a hand-set local key, an already-generated project's CI) must switch to the scoped var; for generated projects that's the `framework upskill` re-render, documented in `SECRETS.md`. No live consumers today.
- **Components/files touched:** `runner.py`, `cli.py`, two framework workflows, `ci.yml.jinja` + `SECRETS.md.jinja` (payload), repo-root `SECRETS.md`, and the tests above — one coherent slice.
