# `litellm-claude-cli` Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the in-tree `claude -p` LiteLLM provider into a standalone, git-tag-distributed package (`cdowell-swtr/litellm-claude-cli`) that the framework depends on and (later, FWK13) generated projects install.

**Architecture:** Two phases. **Phase A** stands up the new package repo (the provider module + tests moved verbatim, a `litellm`-dispatch integration test, optional entry-point auto-registration, lean Node-24 CI) and cuts a real `v0.1.0` tag. **Phase B** flips the framework to depend on that tag, deletes its in-tree copy, repoints two imports, and proves the gate + render stay green. The provider keeps its zero-`framework_cli`-imports property throughout.

**Tech Stack:** Python 3.12, `uv`, hatchling, `litellm` (1.88.1), `pytest`/`ruff`/`mypy`, GitHub (`gh` CLI), the local `claude` CLI for the live smoke.

**Design spec:** `docs/superpowers/specs/2026-06-14-litellm-claude-cli-extraction-design.md` — read it first.

---

## Pre-flight (read before Task 1)

- **Two repos.** The package lives in a **sibling** checkout: `/home/chris/Claude Code/Projects/framework/litellm-claude-cli` (sibling of `swiftwater-framework`). The GitHub repo is `cdowell-swtr/litellm-claude-cli`, **public** (matches the framework; a private repo would force gh-token auth into the framework's CI and every consumer project — avoid).
- **Cross-repo commit-gate.** The framework's `PreToolUse` commit-gate hook fires on *any* `git commit` in this session and checks the **framework** repo's staged `PLAN.md`/`ACTION_LOG.md` ([[cross-repo-commit-needs-local-plan-staged]]). So every commit — package repo *or* framework — must have a framework `ACTION_LOG.md` change staged. This is natural: each task appends an FWK11 `ACTION_LOG` entry in the framework. Stage `git add` and `git commit` as **separate** Bash calls, and keep "commit" out of Bash command descriptions ([[commit-gate-hook-timing]]).
- **Behavior must not change.** This is a pure extraction + dependency swap. The framework's review behavior is unchanged; the proof is its unchanged seam tests (`test_backend.py` exhaustion test, `test_litellm_spike.py`, the live smoke) staying green in Phase B.
- The source of truth being moved: `src/framework_cli/review/litellm_provider.py` (359 lines) and `tests/review/test_litellm_provider.py` (403 lines).

## File structure

**Package repo `litellm-claude-cli/`:**
- Create: `pyproject.toml` — package metadata, `litellm>=1.88.1` dep, entry point (Task 1 outcome), hatchling build.
- Create: `src/litellm_claude_cli/__init__.py` — the provider, moved verbatim (`ClaudeCliLLM`, `ClaudeExhausted`, `register()`, private helpers).
- Create: `tests/test_provider.py` — the moved unit tests (the 17 from `test_litellm_provider.py`).
- Create: `tests/test_litellm_dispatch.py` — the new litellm-dispatch integration test + entry-point variant.
- Create: `tests/test_live_smoke.py` — gated real-`claude` smoke.
- Create: `.github/workflows/ci.yml`, `.gitignore`, `.python-version`, `README.md`.

**Framework repo `swiftwater-framework/`:**
- Modify: `pyproject.toml` (+ `uv.lock`) — add the git-tag dependency.
- Modify: `src/framework_cli/review/backend.py` — repoint two imports.
- Delete: `src/framework_cli/review/litellm_provider.py`, `tests/review/test_litellm_provider.py`.
- Modify: `PLAN.md` + `ACTION_LOG.md` per task.

---

## Phase A — the `litellm-claude-cli` package repo

### Task 1: Entry-point auto-registration spike (GO/NO-GO gate)

**Files:** none yet (exploratory, run in the framework's venv where `litellm` is installed).

Decide whether litellm 1.88.1 supports registering a `CustomLLM` via a `pyproject` entry point. The rest of Task 5 depends on the outcome.

- [ ] **Step 1: Discover the mechanism**

Run: `cd "/home/chris/Claude Code/Projects/framework/swiftwater-framework" && uv run python -c "import litellm, inspect, pathlib; p=pathlib.Path(litellm.__file__).parent; import subprocess; print(subprocess.run(['grep','-rn','entry_point','-l',str(p)],capture_output=True,text=True).stdout)"`
Then `grep -rn "entry_points\|custom_provider" <litellm pkg dir>/__init__.py <matching files>` to find the entry-point **group name** litellm reads for custom providers (the PR is BerriAI/litellm#15881).
Expected: either a group name (e.g. `litellm.custom_provider` — **confirm the exact string**) or no entry-point loading code at all.

- [ ] **Step 2: Empirically confirm (only if Step 1 found a group)**

Create a throwaway package in `/tmp/ep-spike` with a `pyproject` declaring `[project.entry-points."<GROUP>"]` → `claude-cli = "ep_spike:Probe"` where `Probe(litellm.CustomLLM)` sets a flag, `uv pip install -e`, then in a fresh interpreter: `import litellm; litellm.anthropic_messages(model="claude-cli/x", ...)` and assert the probe was invoked **without** any manual `custom_provider_map` assignment.

- [ ] **Step 3: Record the decision**

Append a framework `ACTION_LOG.md` entry: **GO** (record the exact entry-point group string) or **NO-GO** (entry-point loading absent in 1.88.1). Stage `ACTION_LOG.md`; commit `git commit -m "spike(fwk11): litellm entry-point auto-registration GO/NO-GO"`.

> Tasks 2–4, 6, 7 are unaffected by the outcome. Only Task 5 branches.

### Task 2: Scaffold the package repo

**Files:** `litellm-claude-cli/pyproject.toml`, `.gitignore`, `.python-version`, `README.md`

- [ ] **Step 1: Create the GitHub repo + local sibling checkout**

```bash
cd "/home/chris/Claude Code/Projects/framework"
gh repo create cdowell-swtr/litellm-claude-cli --public --description "A LiteLLM CustomLLM provider backed by the local claude CLI subscription." --clone
cd litellm-claude-cli
```
Expected: an empty repo cloned at `/home/chris/Claude Code/Projects/framework/litellm-claude-cli`.

- [ ] **Step 2: Write `pyproject.toml`** (entry-point line added in Task 5 if GO)

```toml
[project]
name = "litellm-claude-cli"
version = "0.1.0"
description = "A LiteLLM CustomLLM provider backed by the local `claude` CLI subscription."
readme = "README.md"
requires-python = ">=3.12"
dependencies = ["litellm>=1.88.1"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/litellm_claude_cli"]

[dependency-groups]
dev = ["pytest>=8.3", "ruff>=0.8", "mypy>=1.13"]

[[tool.mypy.overrides]]
module = ["litellm.*"]
ignore_missing_imports = true
```

- [ ] **Step 3: Write `.python-version` (`3.12`), `.gitignore` (`.venv/`, `__pycache__/`, `*.egg-info/`, `dist/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`), and a short `README.md`** describing the provider, the `claude-cli/<model>` namespace, and install via `git+https://github.com/cdowell-swtr/litellm-claude-cli@<tag>`.

- [ ] **Step 4: Sync + commit**

```bash
uv sync
```
Then stage a framework `ACTION_LOG.md` entry (per pre-flight), and in the package repo: `git add -A` (separate call) then `git commit -m "chore: scaffold litellm-claude-cli package"`.

### Task 3: Move the provider module + unit tests; green standalone

**Files:** `src/litellm_claude_cli/__init__.py`, `tests/test_provider.py`

- [ ] **Step 1: Copy the provider verbatim**

```bash
mkdir -p src/litellm_claude_cli tests
cp "/home/chris/Claude Code/Projects/framework/swiftwater-framework/src/framework_cli/review/litellm_provider.py" src/litellm_claude_cli/__init__.py
```
The module already has zero `framework_cli` imports, so no edits are needed. Confirm: `grep -c "framework_cli" src/litellm_claude_cli/__init__.py` → `0`.

- [ ] **Step 2: Copy + re-point the unit tests**

```bash
cp "/home/chris/Claude Code/Projects/framework/swiftwater-framework/tests/review/test_litellm_provider.py" tests/test_provider.py
```
Then edit `tests/test_provider.py`: change the import `from framework_cli.review.litellm_provider import (...)` → `from litellm_claude_cli import (...)`. That import line is the **only** framework-coupled line (the tests use a fake runner, not the framework).

- [ ] **Step 3: Run the unit tests**

Run: `uv run pytest tests/test_provider.py -v`
Expected: PASS (the same 17 tests, incl. the `MAX_ARG_STRLEN` argv guard and exhaustion→`ClaudeExhausted`).

- [ ] **Step 4: Gate + commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: clean (the targeted `type: ignore`s travelled with the module; the mypy override is in `pyproject`). Stage a framework `ACTION_LOG.md` entry; package repo `git add -A` then `git commit -m "feat: claude-cli CustomLLM provider + unit tests (moved from framework)"`.

### Task 4: litellm-dispatch integration test (the critical layer)

**Files:** `tests/test_litellm_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_litellm_dispatch.py
"""Proves the provider actually plugs into litellm: anthropic_messages(model="claude-cli/...")
must dispatch to ClaudeCliLLM and round-trip a well-formed response. Fully offline
(fake subprocess runner — no network, no key, no real `claude`)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import litellm
from litellm_claude_cli import ClaudeCliLLM


def _run(awaitable_or_value: Any) -> Any:
    if asyncio.iscoroutine(awaitable_or_value):
        return asyncio.run(awaitable_or_value)
    return awaitable_or_value


def _fake_runner(argv, *, input_text):
    return json.dumps(
        {
            "is_error": False,
            "stop_reason": "end_turn",
            "result": '[{"path":"a.py","line":1,"severity":"high","message":"boom"}]',
            "usage": {"input_tokens": 5, "output_tokens": 7, "cache_read_input_tokens": 3},
        }
    )


def test_anthropic_messages_dispatches_to_provider():
    saved = litellm.custom_provider_map
    litellm.custom_provider_map = [
        {"provider": "claude-cli", "custom_handler": ClaudeCliLLM(runner=_fake_runner)}
    ]
    try:
        out = _run(
            litellm.anthropic_messages(
                model="claude-cli/claude-haiku-4-5-20251001",
                max_tokens=64,
                system=[{"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": "Return findings as JSON."}],
            )
        )
    finally:
        litellm.custom_provider_map = saved

    content = out["content"] if isinstance(out, dict) else out.content
    text = content[0]["text"] if isinstance(content[0], dict) else content[0].text
    assert '"path":"a.py"' in text
    usage = out["usage"] if isinstance(out, dict) else out.usage
    cache_read = usage.get("cache_read_input_tokens") if isinstance(usage, dict) else getattr(usage, "cache_read_input_tokens", 0)
    assert cache_read == 3
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/test_litellm_dispatch.py -v`
Expected: PASS — litellm dispatches `claude-cli/…` to our handler and round-trips the response (this is FWK5's S2 probe, now a kept, stronger test). If it FAILS, the provider's litellm contract is broken — stop and fix the provider, not the test.

- [ ] **Step 3: Commit**

Stage a framework `ACTION_LOG.md` entry; package repo `git add -A` then `git commit -m "test: litellm-dispatch integration (anthropic_messages -> provider)"`.

### Task 5: Entry-point auto-registration (branches on Task 1)

**Files:** `litellm-claude-cli/pyproject.toml`, `tests/test_litellm_dispatch.py`, `README.md`

- [ ] **Step 1 (GO path): declare the entry point**

Add to `pyproject.toml` using the exact group string recorded in Task 1:

```toml
[project.entry-points."<GROUP FROM TASK 1>"]
claude-cli = "litellm_claude_cli:ClaudeCliLLM"
```
Run `uv sync` (re-installs with the entry point).

- [ ] **Step 2 (GO path): registration-presence test via the entry point**

Add to `tests/test_litellm_dispatch.py` a `test_entrypoint_autoregisters` that does **not** touch `custom_provider_map` and asserts the provider is auto-registered after the entry-point load — i.e. `claude-cli` is recognized by litellm **without** any manual registration. Assert on *registration presence*, NOT dispatch (don't run real `claude`): after triggering the load (per the exact mechanism Task 1 recorded — eager at `import litellm`, or via `litellm.get_llm_provider("claude-cli/x")`), assert `"claude-cli"` appears among the registered custom providers (e.g. `assert any(p.get("provider") == "claude-cli" for p in (litellm.custom_provider_map or []))`). Do not monkeypatch `_default_runner` — Python binds the constructor's default at def-time, so it wouldn't affect the entry-point-built handler; dispatch behavior is already covered by Task 4. Run: `uv run pytest tests/test_litellm_dispatch.py -v` → PASS. Document auto-registration in `README.md`.

- [ ] **Step 1 (NO-GO path): document explicit registration**

No entry point. In `README.md`, document that consumers call `from litellm_claude_cli import register; register()` once at startup. (The framework already registers explicitly in its seam; FWK13 will add the one-liner to generated projects.)

- [ ] **Step 3: Commit**

Stage a framework `ACTION_LOG.md` entry; package repo `git add -A` then `git commit -m "feat: entry-point auto-registration"` (GO) or `git commit -m "docs: explicit register() usage (entry-point unavailable in litellm 1.88.1)"` (NO-GO).

### Task 6: Gated live smoke

**Files:** `tests/test_live_smoke.py`

- [ ] **Step 1: Write the gated smoke**

```python
# tests/test_live_smoke.py
"""Real `claude` CLI end-to-end through litellm. Opt-in: set RUN_LIVE_SMOKE=1 with the
`claude` CLI on PATH (subscription). The package owns the claude -p mechanics, so it
verifies them independently of the framework."""
from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any

import litellm
import pytest
from litellm_claude_cli import ClaudeCliLLM


def _run(v: Any) -> Any:
    return asyncio.run(v) if asyncio.iscoroutine(v) else v


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_SMOKE") != "1" or shutil.which("claude") is None,
    reason="live: set RUN_LIVE_SMOKE=1 with the `claude` CLI on PATH",
)
def test_live_claude_cli_dispatch():
    big = "x = 1\n" + ("# pad\n" * 40000)  # > MAX_ARG_STRLEN; must go via temp file + stdin
    assert len(big) > 131072
    saved = litellm.custom_provider_map
    litellm.custom_provider_map = [{"provider": "claude-cli", "custom_handler": ClaudeCliLLM()}]
    try:
        out = _run(
            litellm.anthropic_messages(
                model="claude-cli/claude-haiku-4-5-20251001",
                max_tokens=64,
                system=[{"type": "text", "text": f"Reply with []. Context:\n{big}"}],
                messages=[{"role": "user", "content": "Return [] as a JSON array."}],
            )
        )
    finally:
        litellm.custom_provider_map = saved
    content = out["content"] if isinstance(out, dict) else out.content
    assert content  # produced a response without blowing the argv limit
```

- [ ] **Step 2: Run it (if the subscription is available)**

Run: `RUN_LIVE_SMOKE=1 uv run pytest tests/test_live_smoke.py -v`
Expected: PASS (skips cleanly if `claude` absent or the flag unset). Record the result in the framework `ACTION_LOG`.

- [ ] **Step 3: Commit**

Stage a framework `ACTION_LOG.md` entry; package repo `git add -A` then `git commit -m "test: gated live claude-cli smoke"`.

### Task 7: CI, push, branch protection, and the v0.1.0 tag

**Files:** `litellm-claude-cli/.github/workflows/ci.yml`

- [ ] **Step 1: Write the CI workflow** (Node-24-pinned actions; no framework tiers)

```yaml
name: ci
on:
  push:
    branches: [master]
  pull_request:
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
        with:
          python-version: "3.12"
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest -q
```

- [ ] **Step 2: Push and confirm CI green**

```bash
git add .github/workflows/ci.yml
```
(stage a framework `ACTION_LOG.md` entry too) then `git commit -m "ci: lint/type/test on push + PR"` and `git push -u origin master`.
Run: `gh run watch` (or `gh run list`) until the `ci` job passes.

- [ ] **Step 3: Light branch protection**

Require the `ci` check on `master` (a small lib — no heavier ruleset):
```bash
gh api -X PUT repos/cdowell-swtr/litellm-claude-cli/branches/master/protection \
  -f "required_status_checks[strict]=true" -f "required_status_checks[contexts][]=ci" \
  -f "enforce_admins=false" -F "required_pull_request_reviews=" -F "restrictions="
```
(Adjust to the minimal accepted payload; the goal is just "ci must pass to merge.")

- [ ] **Step 4: Cut the real v0.1.0 tag**

```bash
git tag v0.1.0
git push origin v0.1.0
```
Expected: `gh release` not required; the tag is enough for a `git+…@v0.1.0` dependency. Record `v0.1.0` in the framework `ACTION_LOG`.

---

## Phase B — framework cutover

### Task 8: Depend on the package; delete the in-tree copy

**Files:** `swiftwater-framework/pyproject.toml`, `src/framework_cli/review/backend.py`; delete `src/framework_cli/review/litellm_provider.py` + `tests/review/test_litellm_provider.py`

- [ ] **Step 1: Add the git-tag dependency**

In `swiftwater-framework/pyproject.toml`, add `litellm-claude-cli` to `[project].dependencies` and pin it via uv sources:

```toml
# in [project].dependencies:
    "litellm-claude-cli",
```
```toml
[tool.uv.sources]
litellm-claude-cli = { git = "https://github.com/cdowell-swtr/litellm-claude-cli", tag = "v0.1.0" }
```

- [ ] **Step 2: Repoint the two imports in `backend.py`**

`backend.py` currently imports from the in-tree module in two places (the `_SubagentMessages.__init__` handler construction and the `create` exhaustion mapping). Change both:

```python
# was: from framework_cli.review.litellm_provider import ClaudeCliLLM
from litellm_claude_cli import ClaudeCliLLM
```
```python
# was: from framework_cli.review.litellm_provider import ClaudeExhausted
from litellm_claude_cli import ClaudeExhausted
```

- [ ] **Step 3: Delete the moved files**

```bash
git rm src/framework_cli/review/litellm_provider.py tests/review/test_litellm_provider.py
```
(The unit tests now live in the package; the framework keeps its *seam* tests — `test_backend.py`, `test_litellm_spike.py`, `test_litellm_live_smoke.py`.)

- [ ] **Step 4: Sync**

Run: `uv lock && uv sync`
Expected: `litellm-claude-cli` resolves from the git tag; `uv run python -c "import litellm_claude_cli; print('ok')"` prints `ok`.

### Task 9: Prove the cutover; finalize

**Files:** `PLAN.md`, `ACTION_LOG.md`

- [ ] **Step 1: Framework gate**

Run: `uv run pytest tests/review tests/test_cli.py -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: green. The seam tests (`test_backend.py` exhaustion, `test_litellm_spike.py` S2, `test_litellm_live_smoke.py` gated) pass unchanged — the proof that behavior is preserved with the provider now external.

- [ ] **Step 2: Render check**

Run a baseline + a touched render (`framework new demo` in `/tmp`, then `uv sync` in it) to confirm the framework still scaffolds and installs with the new git dependency present. (Generated projects do NOT yet depend on the package — that's FWK13 — so a render only needs to prove the framework itself is healthy.)

- [ ] **Step 3: Update state**

`PLAN.md`: tick **FWK11 → Done** (`→ log:#NNNN`). `ACTION_LOG.md`: completion entry recording the `v0.1.0` tag, the GO/NO-GO entry-point outcome, and that the framework gate stayed green on the external dependency.

- [ ] **Step 4: Commit + PR**

```bash
git add pyproject.toml uv.lock src/framework_cli/review/backend.py PLAN.md ACTION_LOG.md
```
(the `git rm` from Task 8 is already staged) then `git commit -m "refactor(review): depend on external litellm-claude-cli package (FWK11)"` and open a PR (master is protected; PR required — [[master-branch-protection-ruleset]]).

---

## Execution

**Review-model policy** (restated per [[subagent-review-model-pattern]]): implementers → Sonnet (Haiku for the trivial scaffold/copy steps); spec-compliance review → Sonnet; **code-quality review → Opus**; **final/whole-branch review → Opus**. Pass `model` explicitly per role.

**Gate cadence** ([[gate-cadence-framework-slices]]): the package repo is small — review per-task lightly, one Opus review at the end of Phase A. The framework cutover (Phase B) is two contained tasks; one Opus review before the framework PR. Controller runs Task 1 (the spike) directly since it gates Task 5. Implementers stage + pass the commit-gate but stop before `git commit` ([[subagent-implementers-stop-before-commit]]); the controller finishes commits (and handles the cross-repo gate by keeping a framework `ACTION_LOG` change staged).

**Branches:** the package repo work happens on its `master` (new repo, no protection until Task 7); the framework cutover is a feature branch off the framework's `master` → PR.
