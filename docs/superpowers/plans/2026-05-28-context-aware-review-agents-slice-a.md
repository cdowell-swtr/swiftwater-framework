# Context-Aware Review Agents — Slice A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the target-agnostic context spine (per-agent `ContextPolicy`, `ReviewTarget`, `ContextAssembler`, the refactored runner) and migrate the 11 static-`bundle`-tier review agents to context bundles backed by rendered-project + injected-defect fixtures — leaving the agentic tier (Slice B), the framework-repo target (Slice C), and real-key scoring (Slice D) for later.

**Architecture:** The runner receives a pre-assembled `Bundle` and is target-blind. A `ContextAssembler.assemble(diff, root, policy, *, model)` builds a bundle = the diff + (for `bundle` strategy) full content of changed files + a glob-scoped domain subtree, under a model-window-derived token budget. The only target-specific artifact is a thin `ReviewTarget(root, active)`. `ContextPolicy.strategy` defaults to `diff`, so every un-migrated agent is byte-identical to today; migration flips agents to `bundle` one at a time.

**Tech Stack:** Python 3.12, `dataclasses`, `pathlib`, `pytest`, the Anthropic SDK (mocked in tests), Copier (`render_project`), `git` (fixture diff computation). Run all tooling via `uv run`.

**Spec:** `docs/superpowers/specs/2026-05-28-context-aware-review-agents-design.md`

---

## File Structure

- `src/framework_cli/review/registry.py` (modify) — add `ContextPolicy`; add `context: ContextPolicy` field to `AgentSpec`; set `bundle` policies on the 11 static-tier agents.
- `src/framework_cli/review/context.py` (create) — `Bundle`, `ReviewTarget`, `context_budget_chars()`, `assemble()`, `generated_project_target()`.
- `src/framework_cli/review/runner.py` (modify) — `run_agent(bundle, spec, client)`; 3-block cache layout; drop `_MAX_DIFF_CHARS`.
- `src/framework_cli/cli.py` (modify) — `_review_run`/`_eval_run` assemble from a `ReviewTarget`; `review-agents` builds the target.
- `src/framework_cli/review/evals.py` (modify) — `Fixture.root`; rendered-project fixture discovery + `realize_fixture()`; keep legacy `.diff` discovery.
- `tests/eval/fixtures/<agent>/<bad|good>/<case>/` (create) — rendered-project fixtures for migrated agents (`fixture.yaml` + `change.patch` + `expect.json`).
- `tests/review/test_context.py`, `tests/review/test_runner.py` (create/modify), `tests/review/test_fixture_realize.py` (create) — hermetic tests (no LLM key).

---

## Task 1: `ContextPolicy` on the registry

**Files:**
- Modify: `src/framework_cli/review/registry.py`
- Test: `tests/review/test_context_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_context_policy.py
from framework_cli.review.registry import ContextPolicy, AgentSpec, get_agent, agent_names


def test_contextpolicy_defaults_to_diff():
    p = ContextPolicy("diff")
    assert p.strategy == "diff"
    assert p.context_globs == ()
    assert p.max_context_tokens is None


def test_agentspec_context_defaults_to_diff():
    # Every currently-registered agent defaults to the diff strategy until migrated.
    for name in agent_names():
        assert get_agent(name).context.strategy == "diff"


def test_contextpolicy_bundle_carries_globs():
    p = ContextPolicy("bundle", context_globs=("src/*/observability/*.py",))
    assert p.strategy == "bundle"
    assert p.context_globs == ("src/*/observability/*.py",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_context_policy.py -v`
Expected: FAIL — `ImportError: cannot import name 'ContextPolicy'`.

- [ ] **Step 3: Add `ContextPolicy` and the `AgentSpec.context` field**

In `src/framework_cli/review/registry.py`, add after the imports / `ActiveWhen` line:

```python
@dataclass(frozen=True)
class ContextPolicy:
    """How much repository context an agent's review call receives.

    - "diff": the unified diff only (legacy behavior; the default).
    - "bundle": diff + full content of changed files + files matching `context_globs`.
    - "agentic": a tool-using loop over the project tree (designed in Slice B).
    `max_context_tokens` overrides the model-window-derived budget when set.
    """

    strategy: Literal["diff", "bundle", "agentic"]
    context_globs: tuple[str, ...] = ()
    max_context_tokens: int | None = None
```

Add the field to `AgentSpec` (after `trigger_globs`):

```python
    context: ContextPolicy = ContextPolicy("diff")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_context_policy.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/registry.py tests/review/test_context_policy.py
git commit -m "feat(review): add ContextPolicy and AgentSpec.context (default diff)"
```

---

## Task 2: `Bundle` + the model-window token budget

**Files:**
- Create: `src/framework_cli/review/context.py`
- Test: `tests/review/test_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_context.py
from framework_cli.review.context import Bundle, context_budget_chars


def test_budget_derives_from_model_window_minus_reserve():
    # 200k-token window - 4096 output - 8000 margin = 187904 tokens * 4 chars.
    assert context_budget_chars("claude-sonnet-4-6") == (200_000 - 4096 - 8_000) * 4


def test_budget_unknown_model_uses_default_window():
    assert context_budget_chars("some-future-model") == (200_000 - 4096 - 8_000) * 4


def test_budget_override_is_tokens_capped_to_window():
    assert context_budget_chars("claude-sonnet-4-6", override_tokens=1_000) == 1_000 * 4
    # An override larger than the window is clamped to the derived ceiling.
    assert context_budget_chars("claude-sonnet-4-6", override_tokens=10_000_000) == (
        200_000 - 4096 - 8_000
    ) * 4


def test_bundle_is_frozen_with_defaults():
    b = Bundle(diff="d")
    assert b.diff == "d"
    assert b.context_files == ()
    assert b.truncated is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: framework_cli.review.context`.

- [ ] **Step 3: Create `context.py` with `Bundle` and the budget helper**

```python
# src/framework_cli/review/context.py
from __future__ import annotations

from dataclasses import dataclass, field

# Model context windows (input+output tokens). Unknown models use the default.
_MODEL_CONTEXT_TOKENS: dict[str, int] = {
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-7": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
}
_DEFAULT_CONTEXT_TOKENS = 200_000
_OUTPUT_RESERVE_TOKENS = 4096  # mirrors runner._MAX_TOKENS
_MARGIN_TOKENS = 8_000  # headroom for the prompt + framing + estimate slop
_CHARS_PER_TOKEN = 4  # cheap token estimate; avoids a count-tokens round trip


@dataclass(frozen=True)
class Bundle:
    """The assembled review context: the diff plus optional full-file context."""

    diff: str
    context_files: tuple[tuple[str, str], ...] = ()  # (relative path, content), in order
    truncated: bool = False


def context_budget_chars(model: str, *, override_tokens: int | None = None) -> int:
    """The character ceiling for an assembled bundle, derived from the model window.

    Selection (globs + changed files) is the primary control; this is the safety net.
    `override_tokens`, if set, caps the budget but never exceeds the derived ceiling.
    """
    window = _MODEL_CONTEXT_TOKENS.get(model, _DEFAULT_CONTEXT_TOKENS)
    ceiling = window - _OUTPUT_RESERVE_TOKENS - _MARGIN_TOKENS
    tokens = min(override_tokens, ceiling) if override_tokens is not None else ceiling
    return max(tokens, 0) * _CHARS_PER_TOKEN
```

(The `field` import is used in Task 3; leave it imported.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_context.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/context.py tests/review/test_context.py
git commit -m "feat(review): add Bundle and model-window-derived context budget"
```

---

## Task 3: `ReviewTarget` + `assemble()`

**Files:**
- Modify: `src/framework_cli/review/context.py`
- Test: `tests/review/test_context.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/review/test_context.py
from pathlib import Path

from framework_cli.review.context import ReviewTarget, assemble
from framework_cli.review.registry import ContextPolicy

_DIFF = (
    "--- a/src/demo/observability/metrics.py\n"
    "+++ b/src/demo/observability/metrics.py\n"
    "@@ -1,2 +1,3 @@\n"
    " import x\n"
    "+y = 1\n"
)


def _tree(root: Path) -> None:
    obs = root / "src" / "demo" / "observability"
    obs.mkdir(parents=True)
    (obs / "metrics.py").write_text("import x\ny = 1\nFULL_METRICS_FILE = True\n")
    (obs / "tracing.py").write_text("TRACING = True\n")
    (root / "src" / "demo" / "main.py").write_text("APP = True\n")


def test_diff_strategy_returns_diff_only(tmp_path: Path):
    _tree(tmp_path)
    b = assemble(_DIFF, tmp_path, ContextPolicy("diff"), model="claude-sonnet-4-6")
    assert b.diff == _DIFF
    assert b.context_files == ()
    assert b.truncated is False


def test_bundle_includes_changed_files_and_glob_subtree(tmp_path: Path):
    _tree(tmp_path)
    policy = ContextPolicy("bundle", context_globs=("src/*/observability/*.py",))
    b = assemble(_DIFF, tmp_path, policy, model="claude-sonnet-4-6")
    paths = [p for p, _ in b.context_files]
    # The changed file is included (full content, not just the hunk)...
    assert "src/demo/observability/metrics.py" in paths
    assert any("FULL_METRICS_FILE" in c for p, c in b.context_files if p.endswith("metrics.py"))
    # ...and the glob subtree sibling is too.
    assert "src/demo/observability/tracing.py" in paths
    # main.py is outside the glob and unchanged → excluded.
    assert "src/demo/main.py" not in paths


def test_changed_file_appears_once_even_if_glob_also_matches(tmp_path: Path):
    _tree(tmp_path)
    policy = ContextPolicy("bundle", context_globs=("src/*/observability/*.py",))
    b = assemble(_DIFF, tmp_path, policy, model="claude-sonnet-4-6")
    paths = [p for p, _ in b.context_files]
    assert paths.count("src/demo/observability/metrics.py") == 1


def test_budget_truncates_subtree_keeping_priority(tmp_path: Path):
    _tree(tmp_path)
    policy = ContextPolicy(
        "bundle", context_globs=("src/*/observability/*.py",), max_context_tokens=1
    )  # 1 token * 4 = 4 chars: nothing but the diff fits
    b = assemble(_DIFF, tmp_path, policy, model="claude-sonnet-4-6")
    assert b.truncated is True
    assert b.context_files == ()  # the diff is always kept; files dropped under budget
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_context.py -v`
Expected: FAIL — `ImportError: cannot import name 'ReviewTarget'`.

- [ ] **Step 3: Add `ReviewTarget` and `assemble()` to `context.py`**

Add to `src/framework_cli/review/context.py`:

```python
from pathlib import Path

from framework_cli.review.diff import changed_files
from framework_cli.review.registry import ContextPolicy


@dataclass(frozen=True)
class ReviewTarget:
    """A review target. The ONLY target-specific artifact: the runner/assembler are blind to it."""

    root: Path
    active: tuple[str, ...] = field(default_factory=tuple)


def assemble(
    diff: str, root: Path, policy: ContextPolicy, *, model: str
) -> Bundle:
    """Assemble the review bundle for `policy` against the tree at `root`.

    Priority order under the budget: the diff (always), then full content of changed
    files, then files matching `context_globs`. On overflow we stop adding and mark the
    bundle truncated — the diff is never dropped.
    """
    if policy.strategy != "bundle":
        return Bundle(diff=diff)

    budget = context_budget_chars(model, override_tokens=policy.max_context_tokens)
    used = len(diff)
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(rel: str) -> None:
        if rel not in seen:
            seen.add(rel)
            ordered.append(rel)

    for rel in changed_files(diff):
        _add(rel)
    for pattern in policy.context_globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                _add(str(path.relative_to(root)))

    files: list[tuple[str, str]] = []
    truncated = False
    for rel in ordered:
        fp = root / rel
        if not fp.is_file():
            continue
        content = fp.read_text(errors="replace")
        if used + len(content) > budget:
            truncated = True
            break  # respect priority: stop rather than skip-ahead to smaller files
        files.append((rel, content))
        used += len(content)

    return Bundle(diff=diff, context_files=tuple(files), truncated=truncated)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_context.py -v`
Expected: PASS (8 passed total in the file).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/context.py tests/review/test_context.py
git commit -m "feat(review): add ReviewTarget and the context assembler"
```

---

## Task 4: Refactor `run_agent` to take a `Bundle` (3-block cache layout)

**Files:**
- Modify: `src/framework_cli/review/runner.py`
- Test: `tests/review/test_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_runner.py
from dataclasses import dataclass

from framework_cli.review.context import Bundle
from framework_cli.review.registry import get_agent
from framework_cli.review.runner import run_agent


@dataclass
class _Block:
    type: str = "text"
    text: str = "[]"


class _FakeMessage:
    content = [_Block(text="[]")]


class _FakeMessages:
    def __init__(self) -> None:
        self.captured: dict = {}

    def create(self, **kwargs):
        self.captured = kwargs
        return _FakeMessage()


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def test_diff_only_bundle_sends_two_blocks_diff_first():
    client = _FakeClient()
    run_agent(Bundle(diff="THE DIFF"), get_agent("security"), client)
    system = client.messages.captured["system"]
    assert len(system) == 2  # diff + prompt; no context block
    assert system[0]["text"].startswith("Review this unified diff:")
    assert "THE DIFF" in system[0]["text"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert system[1]["text"] == get_agent("security").prompt


def test_bundle_with_context_inserts_cached_context_block():
    client = _FakeClient()
    bundle = Bundle(diff="D", context_files=(("src/demo/x.py", "CONTENT"),))
    run_agent(bundle, get_agent("security"), client)
    system = client.messages.captured["system"]
    assert len(system) == 3  # diff + context + prompt
    assert "src/demo/x.py" in system[1]["text"]
    assert "CONTENT" in system[1]["text"]
    assert system[1]["cache_control"] == {"type": "ephemeral"}
    assert system[2]["text"] == get_agent("security").prompt


def test_truncation_note_added_when_truncated():
    client = _FakeClient()
    bundle = Bundle(diff="D", context_files=(("a.py", "x"),), truncated=True)
    run_agent(bundle, get_agent("security"), client)
    assert "truncated" in client.messages.captured["system"][1]["text"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_runner.py -v`
Expected: FAIL — `run_agent` signature mismatch / `TypeError` (it currently takes `diff`, not `Bundle`).

- [ ] **Step 3: Rewrite `run_agent` to consume a `Bundle`**

Replace the body of `src/framework_cli/review/runner.py` (keep `parse_findings`/`Finding`/`AgentSpec` imports, `default_client`):

```python
from __future__ import annotations

from typing import Any

from framework_cli.review.context import Bundle
from framework_cli.review.findings import Finding, parse_findings
from framework_cli.review.registry import AgentSpec

_MAX_TOKENS = 4096


def run_agent(bundle: Bundle, spec: AgentSpec, client: Any) -> list[Finding]:
    """Call the LLM with `spec`'s prompt over an assembled `bundle`; return findings.

    System blocks, in cache-prefix order: (1) the diff — identical across agents on the
    same target, so its cache prefix is shared; (2) optional per-agent context files; (3)
    the agent prompt. A diff-only bundle omits block 2, byte-identical to the legacy call.
    """
    system: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Review this unified diff:\n\n{bundle.diff}",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if bundle.context_files:
        joined = "\n\n".join(
            f"=== {path} ===\n{content}" for path, content in bundle.context_files
        )
        note = "\n\n[context truncated to fit the budget]" if bundle.truncated else ""
        system.append(
            {
                "type": "text",
                "text": f"Relevant repository files for context:\n\n{joined}{note}",
                "cache_control": {"type": "ephemeral"},
            }
        )
    system.append({"type": "text", "text": spec.prompt})

    message = client.messages.create(
        model=spec.model,
        max_tokens=_MAX_TOKENS,
        system=system,
        messages=[
            {"role": "user", "content": "Return your findings as a JSON array only."}
        ],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )
    return parse_findings(text)


def default_client() -> Any:  # pragma: no cover - thin SDK wrapper
    import anthropic

    return anthropic.Anthropic()
```

The `_MAX_DIFF_CHARS = 200_000` constant is intentionally **removed** (the budget now lives in `context.py`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_runner.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/runner.py tests/review/test_runner.py
git commit -m "refactor(review): run_agent consumes a Bundle; 3-block cache layout"
```

---

## Task 5: Wire the CLI to assemble from a `ReviewTarget`

**Files:**
- Modify: `src/framework_cli/cli.py` (`_review_run` ~line 270, `_eval_run` ~line 274, and the `review-agents`/`review` paths)
- Test: `tests/review/test_cli_review_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_cli_review_wiring.py
from pathlib import Path

from framework_cli.review.context import generated_project_target


def test_generated_project_target_uses_root_and_active(tmp_path: Path):
    t = generated_project_target(tmp_path, ("security", "performance"))
    assert t.root == tmp_path
    assert t.active == ("security", "performance")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_cli_review_wiring.py -v`
Expected: FAIL — `ImportError: cannot import name 'generated_project_target'`.

- [ ] **Step 3: Add the factory and route `_review_run`/`_eval_run` through `assemble`**

Add to `src/framework_cli/review/context.py`:

```python
def generated_project_target(root: Path, active: tuple[str, ...]) -> ReviewTarget:
    """The shipped-use target: a checked-out generated project at `root`."""
    return ReviewTarget(root=root, active=tuple(active))
```

In `src/framework_cli/cli.py`, replace `_review_run` and `_eval_run`:

```python
def _review_run(diff: str, spec: object) -> list:
    from framework_cli.review.context import assemble
    from framework_cli.review.runner import default_client, run_agent

    bundle = assemble(diff, Path.cwd(), spec.context, model=spec.model)  # type: ignore[attr-defined]
    return run_agent(bundle, spec, default_client())  # type: ignore[arg-type]


def _eval_run(diff: str, root: object, spec: object) -> list:
    from framework_cli.review.context import assemble
    from framework_cli.review.runner import default_client, run_agent

    base = root if isinstance(root, Path) else Path.cwd()
    bundle = assemble(diff, base, spec.context, model=spec.model)  # type: ignore[attr-defined]
    return run_agent(bundle, spec, default_client())  # type: ignore[arg-type]
```

Update the `eval_agents` call site (currently `found = _eval_run(fx.diff, spec)`) to pass the fixture root:

```python
                    found = _eval_run(fx.diff, getattr(fx, "root", None), spec)
```

- [ ] **Step 4: Run the new test and the existing review/eval tests**

Run: `uv run pytest tests/review/test_cli_review_wiring.py tests/ -k "review or eval" -v`
Expected: PASS — the new test passes and no existing review/eval test regresses (diff-strategy agents assemble a diff-only bundle ⇒ unchanged calls).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/context.py src/framework_cli/cli.py tests/review/test_cli_review_wiring.py
git commit -m "feat(review): assemble bundles from a ReviewTarget in the CLI paths"
```

---

## Task 6: Rendered-project fixture realization primitive (`realize_fixture`)

> **Scope refinement (during execution):** Three gate tests (`test_every_registered_agent_has_fixtures`, `test_contracts_has_full_fixture_set`, `test_fixtures_are_wellformed`) call `load_fixtures` and rely on `fx.diff`. Rendering new-format fixtures eagerly inside `load_fixtures` would render dozens of projects on every suite run as Task 8 migrates agents. So Slice A does **not** modify `load_fixtures`: migrated agents **keep their legacy `.diff` fixtures** (the existing `load_fixtures` ignores case-subdirectories, so the gate + scoring path stay green) and **add** rendered-project fixtures consumed only by the new assembly tests via `realize_fixture`. Migrating the eval harness to consume rendered fixtures + retiring the `.diff` ones is **Slice D**. Task 6 therefore ships only the `realize_fixture` primitive + its test; `Fixture`/`load_fixtures` are untouched.

**Files:**
- Modify: `src/framework_cli/review/evals.py` (add `realize_fixture`)
- Test: `tests/review/test_fixture_realize.py`

The new fixture layout (per migrated agent case):
```
tests/eval/fixtures/<agent>/<bad|good>/<case>/fixture.yaml   # {batteries: [...]}
tests/eval/fixtures/<agent>/<bad|good>/<case>/change.patch   # unified diff applied to the render
tests/eval/fixtures/<agent>/<bad|good>/<case>/expect.json    # (bad) {"file": "src/demo/.../x.py"}
```
Legacy `<case>.diff` + `<case>.expect.json` files stay supported (the agentic tier keeps them until Slice B).

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_fixture_realize.py
from pathlib import Path

import pytest

from framework_cli.review.evals import realize_fixture

_PATCH = """\
--- a/src/demo/observability/metrics.py
+++ b/src/demo/observability/metrics.py
@@ -1,1 +1,2 @@
 \"\"\"Application metrics.\"\"\"
+UNINSTRUMENTED = True  # seeded defect
"""


def test_realize_fixture_renders_patches_and_diffs(tmp_path: Path):
    root, diff = realize_fixture(tmp_path, batteries=[], patch=_PATCH)
    # The render exists and the patch was applied to the real tree.
    assert (root / "src" / "demo" / "observability" / "metrics.py").is_file()
    assert "UNINSTRUMENTED = True" in (
        root / "src" / "demo" / "observability" / "metrics.py"
    ).read_text()
    # The computed diff names the seeded file.
    assert "src/demo/observability/metrics.py" in diff
    assert "UNINSTRUMENTED = True" in diff
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_fixture_realize.py -v`
Expected: FAIL — `ImportError: cannot import name 'realize_fixture'`.

- [ ] **Step 3: Implement `realize_fixture` and extend the loader**

Add to `src/framework_cli/review/evals.py`:

```python
import subprocess
from framework_cli.copier_runner import render_project

_FIXTURE_ANSWERS = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def realize_fixture(
    dest: Path, *, batteries: list[str], patch: str
) -> tuple[Path, str]:
    """Render the template into `dest`, apply `patch`, and return (root, computed diff).

    The render is a real generated project, so the same assembler used in production runs
    against it. The patch is the seeded bad/good change; the returned diff is what the
    review sees. `dest` must be an empty directory the caller owns (e.g. a tmp_path).
    """
    root = dest / "demo"
    render_project(root, {**_FIXTURE_ANSWERS, "batteries": batteries})
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "apply", "-"], cwd=root, input=patch, text=True, check=True)
    diff = subprocess.run(
        ["git", "diff"], cwd=root, capture_output=True, text=True, check=True
    ).stdout
    return root, diff
```

Add a `root` field to `Fixture` (default `None`, keeping legacy construction valid):

```python
    root: Path | None = None
```

Extend `load_fixtures` to also discover the new directory format. After the existing `.diff` discovery loop inside the `for kind in ("bad", "good"):` block, add:

```python
            for case_dir in sorted(p for p in (agent_dir / kind).glob("*") if p.is_dir()):
                patch_file = case_dir / "change.patch"
                spec_file = case_dir / "fixture.yaml"
                if not patch_file.is_file() or not spec_file.is_file():
                    continue
                import yaml

                batteries = (yaml.safe_load(spec_file.read_text()) or {}).get(
                    "batteries", []
                )
                seeded_file = None
                if kind == "bad":
                    try:
                        seeded_file = str(
                            json.loads((case_dir / "expect.json").read_text())["file"]
                        )
                    except (OSError, json.JSONDecodeError, KeyError, TypeError):
                        continue
                dest = Path(tempfile.mkdtemp(prefix="evalfx-"))
                root, diff = realize_fixture(
                    dest, batteries=batteries, patch=patch_file.read_text()
                )
                fixtures.append(
                    Fixture(agent, kind, case_dir.name, diff, seeded_file, root=root)
                )
```

Add `import tempfile` at the top of `evals.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_fixture_realize.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/evals.py tests/review/test_fixture_realize.py
git commit -m "feat(review): rendered-project fixture format + realize_fixture"
```

---

## Task 7: Migrate the exemplar agent — `observability` (app) → `bundle`

This is the fully-worked template for Task 8. The app `observability` agent reviews instrumentation that spans `observability/`, `main.py`, and the routes.

**Files:**
- Modify: `src/framework_cli/review/registry.py` (set `observability`'s `context`)
- Create: `tests/eval/fixtures/observability/bad/uninstrumented-route/{fixture.yaml,change.patch,expect.json}`
- Create: `tests/eval/fixtures/observability/good/instrumented-route/{fixture.yaml,change.patch}`
- Test: `tests/review/test_migrated_agent_assembly.py`

- [ ] **Step 1: Write the failing assembly test**

```python
# tests/review/test_migrated_agent_assembly.py
from pathlib import Path

from framework_cli.review.context import assemble
from framework_cli.review.evals import realize_fixture
from framework_cli.review.registry import get_agent

_FIXTURES = Path("tests/eval/fixtures")


def test_observability_bundle_pulls_obs_subtree(tmp_path: Path):
    case = _FIXTURES / "observability" / "bad" / "uninstrumented-route"
    import yaml

    batteries = (yaml.safe_load((case / "fixture.yaml").read_text()) or {}).get(
        "batteries", []
    )
    root, diff = realize_fixture(
        tmp_path, batteries=batteries, patch=(case / "change.patch").read_text()
    )
    spec = get_agent("observability")
    assert spec.context.strategy == "bundle"
    bundle = assemble(diff, root, spec.context, model=spec.model)
    paths = [p for p, _ in bundle.context_files]
    # The assembler reaches the observability subtree, not just the changed route.
    assert any("observability/metrics.py" in p for p in paths)
    assert any("observability/tracing.py" in p for p in paths)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_migrated_agent_assembly.py -v`
Expected: FAIL — fixture files don't exist / `spec.context.strategy` is still `"diff"`.

- [ ] **Step 3: Set the `observability` context policy**

In `src/framework_cli/review/registry.py`, change the `observability` entry to add `context`:

```python
    "observability": AgentSpec(
        "review-observability",
        _prompt("observability"),
        "high",
        "always",
        DEFAULT_MODEL,
        on_push=True,
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "src/*/observability/*.py",
                "src/*/main.py",
                "src/*/routes/*.py",
            ),
        ),
    ),
```

- [ ] **Step 4: Author the fixtures**

`tests/eval/fixtures/observability/bad/uninstrumented-route/fixture.yaml`:
```yaml
batteries: []
```

`tests/eval/fixtures/observability/bad/uninstrumented-route/change.patch` — a new route handler with no span/metric/log (the seeded defect). Render a baseline project first (`uv run python -c "from framework_cli.copier_runner import render_project; from pathlib import Path; render_project(Path('/tmp/insp/demo'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12','batteries':[]})"`) to copy the exact surrounding lines of `src/demo/routes/` for accurate hunk context, then write a patch that adds, e.g.:
```diff
--- a/src/demo/routes/items.py
+++ b/src/demo/routes/items.py
@@ <hunk matching the real file> @@
+@router.get("/items/{item_id}/raw")
+def get_item_raw(item_id: int):
+    # seeded defect: no span, no metric, no structured log on a new request path
+    return {"id": item_id}
```

`tests/eval/fixtures/observability/bad/uninstrumented-route/expect.json`:
```json
{"file": "src/demo/routes/items.py"}
```

`tests/eval/fixtures/observability/good/instrumented-route/fixture.yaml`:
```yaml
batteries: []
```

`tests/eval/fixtures/observability/good/instrumented-route/change.patch` — the same shape but properly instrumented (tracer span + metric increment + structured log), so a healthy agent does NOT flag it. Mirror the instrumentation idioms already in the rendered `observability/` package.

(Author the patches against the real rendered file contents from the inspection render. Keep hunks minimal and valid for `git apply`.)

- [ ] **Step 5: Run the assembly test to verify it passes**

Run: `uv run pytest tests/review/test_migrated_agent_assembly.py -v`
Expected: PASS — the bundle contains the obs subtree files.

- [ ] **Step 6: Verify `load_fixtures` still finds `observability` fixtures (coverage gate)**

Run: `uv run pytest tests/ -k "fixture" -v`
Expected: PASS — the registered-agent fixture coverage gate accepts the new directory-format fixtures.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/review/registry.py tests/eval/fixtures/observability tests/review/test_migrated_agent_assembly.py
git commit -m "feat(review): migrate observability agent to bundle context (exemplar)"
```

---

## Task 8: Migrate the remaining 10 static-tier agents

Repeat Task 7's procedure for each agent below — one commit per agent. For each: (a) set the agent's `context=ContextPolicy("bundle", context_globs=(...))` in `registry.py` using the globs in the table; (b) convert its existing `tests/eval/fixtures/<agent>/{bad,good}/*.diff` cases into the rendered-project directory format (`fixture.yaml` + `change.patch` + `expect.json`), preserving each case's *defect intent* but re-expressing it against a real rendered file (render a project, find the real path, write a minimal valid patch); (c) add the agent to the parametrized assembly test (Step below); (d) run the assembly + fixture-coverage tests; (e) commit.

**Per-agent globs (resolved against the project root):**

| agent | `context_globs` | fixture `batteries` |
|---|---|---|
| accessibility | `frontend/src/**/*.tsx`, `frontend/src/**/*.ts`, `frontend/index.html` | `[react]` |
| usability | `frontend/src/**/*.tsx`, `frontend/src/**/*.css` | `[react]` |
| application-logic | `src/*/routes/*.py`, `src/*/db/*.py` | `[]` |
| performance | `src/*/routes/*.py`, `src/*/db/*.py` | `[]` |
| data-integrity | `src/*/db/*.py`, `migrations/versions/*.py` | `[]` |
| security | `src/*/**/*.py`, `src/*/config/*.py` | `[]` |
| compliance | `src/*/routes/*.py`, `src/*/middleware/*.py`, `src/*/config/*.py` | `[]` |
| test-quality | `tests/**/*.py`, `src/*/**/*.py` | `[]` |
| documentation | `README.md`, `docs/**/*.md`, `src/*/**/*.py` | `[]` |
| dependency | `pyproject.toml`, `uv.lock` | `[]` |

- [ ] **Step 1: Generalize the assembly test to be parametrized**

Replace the single test in `tests/review/test_migrated_agent_assembly.py` body with a parametrized version that, for each migrated agent + its first `bad` case, asserts (a) `get_agent(agent).context.strategy == "bundle"` and (b) the assembled bundle's `context_files` is non-empty and includes at least one path matching one of the agent's `context_globs` directories. Drive the parametrization from a list of the 11 migrated agent names.

```python
import pytest
from framework_cli.review.registry import get_agent

_MIGRATED = [
    "observability", "accessibility", "usability", "application-logic",
    "performance", "data-integrity", "security", "compliance",
    "test-quality", "documentation", "dependency",
]

@pytest.mark.parametrize("agent", _MIGRATED)
def test_migrated_agent_assembles_nonempty_bundle(agent, tmp_path):
    spec = get_agent(agent)
    assert spec.context.strategy == "bundle"
    # ... load the agent's first bad case dir, realize_fixture, assemble, assert context_files
```

- [ ] **Step 2: For each agent, set the policy + convert fixtures + commit**

For agent in the table (do these one at a time, committing each):
  - Set `context=ContextPolicy("bundle", context_globs=(...))` in `registry.py`.
  - ADD rendered-project fixtures (do NOT delete the legacy `.diff`/`.expect.json` — they keep the eval-harness gate/scoring green until Slice D migrates the harness). For each defect intent, create a `<case>/` dir with `fixture.yaml` (`batteries:` from the table), `change.patch` (the defect re-expressed against the rendered file), and `expect.json` (the rendered seeded path) for `bad`; `fixture.yaml` + `change.patch` for `good`.
  - Run: `uv run pytest tests/review/test_migrated_agent_assembly.py -k <agent> tests/ -k fixture -v` — Expected: PASS.
  - Commit: `git add src/framework_cli/review/registry.py tests/eval/fixtures/<agent> && git commit -m "feat(review): migrate <agent> agent to bundle context"`.

- [ ] **Step 3: Confirm all 11 migrated, the 7 agentic agents still on diff**

Run:
```bash
uv run python -c "from framework_cli.review.registry import agent_names, get_agent; \
print({n: get_agent(n).context.strategy for n in agent_names()})"
```
Expected: the 11 table+exemplar agents print `bundle`; `architecture`, `data-lineage`, `privacy`, `api-design`, `observability-infra`, `observability-db`, `contracts` print `diff`.

---

## Task 9: Target-agnostic invariant + full gate + state update

**Files:**
- Test: `tests/review/test_target_agnostic.py`
- Modify: `CLAUDE.md`, `docs/superpowers/plans/2026-05-20-meta-plan.md`

- [ ] **Step 1: Write the invariant test**

```python
# tests/review/test_target_agnostic.py
from pathlib import Path

from framework_cli.review.context import ReviewTarget, assemble, generated_project_target
from framework_cli.review.registry import ContextPolicy


def test_assemble_is_target_blind(tmp_path: Path):
    """assemble() depends only on (diff, root, policy) — never on target identity.

    Two ReviewTargets pointing at the same tree produce identical bundles; this is the
    invariant Slice C relies on when it adds the framework-repo target.
    """
    (tmp_path / "a.py").write_text("X = 1\n")
    diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n X = 1\n+Y = 2\n"
    policy = ContextPolicy("bundle", context_globs=("*.py",))
    t1 = generated_project_target(tmp_path, ("security",))
    t2 = ReviewTarget(root=tmp_path, active=("performance", "security"))
    b1 = assemble(diff, t1.root, policy, model="claude-sonnet-4-6")
    b2 = assemble(diff, t2.root, policy, model="claude-sonnet-4-6")
    assert b1 == b2
```

- [ ] **Step 2: Run the invariant test**

Run: `uv run pytest tests/review/test_target_agnostic.py -v`
Expected: PASS.

- [ ] **Step 3: Run the full quality gate**

Run:
```bash
uv run pytest -q --ignore=tests/acceptance
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green. (Acceptance tier ignored per the repo convention; run it separately if needed, cleaning `/tmp` after.)

- [ ] **Step 4: Update state docs**

Update `CLAUDE.md` Current State (bump **Last updated**; note Slice A merged — the context spine + 11 bundle-tier agents) and the meta-plan Plan 11 row (mark Slice A done, Slice B next). Stage `CLAUDE.md` (the commit-gate hook requires it).

- [ ] **Step 5: Commit**

```bash
git add tests/review/test_target_agnostic.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
git commit -m "test(review): target-agnostic assembler invariant; Slice A complete"
```

---

## Self-review notes

- **Spec coverage:** §3.1 ContextPolicy → T1; §3.3 assemble + budget → T2/T3; §3.4 runner 3-block + diff byte-identity → T4; §3.2 ReviewTarget + the generated-project profile → T3/T5; §4 rendered-project fixtures → T6; §6 static-tier migration (11 agents) → T7/T8; §8.2 hermetic assembly test + the target-agnostic invariant → T7/T9. Agentic tier (7 agents), framework-repo target, and real-key scoring are explicitly Slices B/C/D — not in this plan.
- **Byte-identity:** for `diff`-strategy agents the bundle has no context block ⇒ `run_agent` emits the same 2 system blocks as today (asserted in T4); diffs under the old 200K cap are unchanged (the cap removal only affects oversized diffs, intentional).
- **Type consistency:** `Bundle(diff, context_files, truncated)`, `ContextPolicy(strategy, context_globs, max_context_tokens)`, `ReviewTarget(root, active)`, `assemble(diff, root, policy, *, model)`, `context_budget_chars(model, *, override_tokens)`, `realize_fixture(dest, *, batteries, patch) -> (root, diff)`, `generated_project_target(root, active)` are used consistently across tasks.
