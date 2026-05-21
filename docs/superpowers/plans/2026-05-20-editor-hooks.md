# Layer-2 Editor Hooks Implementation Plan (Plan 2b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generated projects ship a `.claude/settings.json` PostToolUse hook so that when Claude Code edits a Python file in the project, ruff and mypy run on that file immediately and any findings are surfaced back to Claude to fix — surgical, per-file, during the inner loop.

**Architecture:** Adds two files to the bundled Copier template at `src/framework_cli/template/`: a static `.claude/settings.json` registering a `PostToolUse` hook on `Edit|Write|MultiEdit`, and a `.claude/hooks/lint_changed.py` Python script the hook invokes. The script reads the Claude Code hook payload from stdin, and if the edited file is a `.py` file, runs `ruff check` and `mypy` on it; on findings it prints them to stderr and exits 2 (which Claude Code surfaces to the model). Non-Python files and unparsable payloads are silent no-ops. A Python script (rather than the docs' bash+jq example) keeps the hook cross-platform with no extra dependencies, since every generated project already has Python + uv.

**Tech Stack:** Claude Code hooks (PostToolUse), Python stdlib (json/subprocess/sys/pathlib), ruff, mypy, uv, Copier.

**Spec reference:** §4 (Layer 2 — Dev Intelligence Layer, Claude Code Hooks). This plan implements the `.py → ruff + mypy` surgical hook. Deliberately deferred to later plans (noted so they are not mistaken for gaps): the test-file → pytest-on-save hook; hooks for other file types (`.ts/.css/.yml/Dockerfile/.sh/.toml`) which arrive with the batteries/files that introduce those types; the `pyproject/requirements → pip-audit` and `.env → gitleaks` hooks.

**Verified hook schema (Claude Code docs, confirmed 2026-05-20):**
- `settings.json` shape: `hooks` → `PostToolUse` (array) → `{ "matcher": "<regex on tool name>", "hooks": [ { "type": "command", "command": "<shell>" } ] }`.
- `matcher` matches the tool *name* as a regex; `"Edit|Write|MultiEdit"` matches all three edit tools.
- Hook stdin payload (JSON) includes `tool_name`, `tool_input` (for edits, `tool_input.file_path` is the absolute path), `tool_response`, `cwd`, `hook_event_name`.
- Exit 0 = silent success; **exit 2 = blocking error, stderr is fed back to Claude**; other non-zero = non-blocking error shown in the transcript.
- Commands run via shell (`sh -c` on macOS/Linux, Git Bash on Windows); `${CLAUDE_PROJECT_DIR}` expands to the project root.

**Prerequisites:** `uv` on PATH. Repo on `master` with Plans 1 and 2 merged. Create a feature branch before implementing. Run commands from the repo root.

---

## File Structure

Template additions (the only changes):

```
src/framework_cli/template/
  .claude/
    settings.json               # NEW: PostToolUse hook on Edit|Write|MultiEdit (static JSON)
    hooks/
      lint_changed.py           # NEW: reads hook payload, runs ruff+mypy on edited .py (static)
  CLAUDE.md.jinja               # EDIT: note the editor hook under "Quality commands"
  README.md.jinja               # EDIT: one line documenting the hook
```

Framework test changes:

```
tests/
  test_copier_runner.py         # EDIT: assert settings.json + hook script render, settings.json is valid
  acceptance/
    test_rendered_project.py    # EDIT: behavioral tests that the hook flags bad py / passes clean / skips non-py
```

**Responsibility split:** `settings.json` wires the event→command; `lint_changed.py` owns all the logic (payload parsing, file-type filtering, running tools, deciding pass/block). The hook script must itself be ruff-clean and ruff-format-clean, because a generated project's pre-commit (from Plan 2) lints it — the existing `test_rendered_project_precommit_runs_clean` acceptance test will enforce that automatically.

---

## Task 1: Hook script + settings.json in the template

**Files:**
- Create: `src/framework_cli/template/.claude/hooks/lint_changed.py`
- Create: `src/framework_cli/template/.claude/settings.json`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Add the failing render-test assertions**

At the top of `tests/test_copier_runner.py`, ensure `import json` is present (add it if not). Then add:

```python
def test_render_includes_claude_hooks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    settings = dest / ".claude" / "settings.json"
    assert settings.is_file()
    data = json.loads(settings.read_text())
    matchers = [group["matcher"] for group in data["hooks"]["PostToolUse"]]
    assert any("Edit" in m and "Write" in m for m in matchers)

    hook = dest / ".claude" / "hooks" / "lint_changed.py"
    assert hook.is_file()
    assert "tool_input" in hook.read_text()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_claude_hooks -v`
Expected: FAIL — `.claude/settings.json` not in the rendered project.

- [ ] **Step 3: Create the hook script**

Create `src/framework_cli/template/.claude/hooks/lint_changed.py` (static, no Jinja). Write it exactly as below — it is formatted to be ruff-format-clean:

```python
"""PostToolUse hook: lint the Python file Claude Code just edited.

Reads the hook payload from stdin. If the edited file is a Python file, runs
ruff and mypy on it; on findings, prints them to stderr and exits 2 so Claude
Code surfaces them to the model to fix immediately. Non-Python files, missing
files, and unparsable payloads are silent no-ops (exit 0).

Invoked via `uv run python`, so ruff and mypy resolve from the project venv.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def edited_path(payload: dict) -> str | None:
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path")
    if isinstance(path, str) and path:
        return path
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    path = edited_path(payload)
    if path is None or not path.endswith(".py") or not Path(path).is_file():
        return 0

    findings: list[str] = []
    for cmd in (["ruff", "check", path], ["mypy", path]):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            if output:
                findings.append(output)

    if findings:
        print("\n\n".join(findings), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Create the settings.json**

Create `src/framework_cli/template/.claude/settings.json` (static JSON). The `command` runs the script under `uv run python` so the venv's ruff/mypy are on PATH; `${CLAUDE_PROJECT_DIR}` is expanded by the shell:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "uv run python \"${CLAUDE_PROJECT_DIR}/.claude/hooks/lint_changed.py\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_claude_hooks -v`
Expected: PASS.

- [ ] **Step 6: Confirm the framework's own gate is still clean**

The new hook script lives under `src/framework_cli/template/`. The framework's mypy already excludes that directory (`[tool.mypy] exclude`); confirm the framework's ruff is happy with the script too:

Run: `uv run ruff check .`
Expected: `All checks passed!` If ruff reports the template hook script, the script is not format/lint-clean — fix it until clean (it must be, because generated projects lint it via pre-commit). Run `uv run ruff format --check src/framework_cli/template/.claude/hooks/lint_changed.py` to confirm format-cleanliness.

- [ ] **Step 7: Commit**

```bash
git add "src/framework_cli/template/.claude/settings.json" "src/framework_cli/template/.claude/hooks/lint_changed.py" tests/test_copier_runner.py
git commit -m "feat: scaffold Claude Code lint-on-edit hook in generated projects"
```

---

## Task 2: Behavioral tests for the hook

These prove the hook actually does its job: blocks on a bad Python file, passes a clean one, and ignores non-Python files. They invoke the script the same way Claude Code does (under `uv run python`, payload on stdin).

**Files:**
- Test: `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Add the behavioral acceptance tests**

Ensure `import json` is present at the top of `tests/acceptance/test_rendered_project.py` (add it if missing). Then append:

```python
def _run_hook(dest: Path, file_path: Path) -> subprocess.CompletedProcess[str]:
    payload = json.dumps(
        {"tool_name": "Write", "tool_input": {"file_path": str(file_path)}}
    )
    return subprocess.run(
        ["uv", "run", "python", ".claude/hooks/lint_changed.py"],
        cwd=dest,
        input=payload,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_lint_hook_blocks_on_bad_python(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    bad = dest / "src" / "demo" / "scratch_bad.py"
    bad.write_text("import os\n")  # unused import -> ruff F401

    result = _run_hook(dest, bad)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "F401" in (result.stdout + result.stderr)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_lint_hook_passes_clean_python(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    clean = dest / "src" / "demo" / "scratch_clean.py"
    clean.write_text("VALUE: int = 1\n")

    result = _run_hook(dest, clean)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_lint_hook_ignores_non_python(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    note = dest / "notes.txt"
    note.write_text("not python\n")

    result = _run_hook(dest, note)
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 2: Run the behavioral tests (slow; need uv on PATH)**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -k lint_hook -v`
Expected: 3 passed, none skipped. The bad-file test asserts exit 2 + an `F401` finding; the clean and non-python tests assert exit 0.

If the bad-file test does NOT see `F401`: confirm the rendered project's ruff flags unused imports by default (it does — pyflakes `F` rules are on by default). If the clean test fails with exit 2, inspect `result.stdout/stderr` — most likely mypy emitted an error; adjust the clean file to something mypy and ruff both accept (a typed module-level constant, as written).

- [ ] **Step 3: Commit**

```bash
git add tests/acceptance/test_rendered_project.py
git commit -m "test: behavioral tests for the lint-on-edit hook"
```

---

## Task 3: Document the hook and verify the whole project

**Files:**
- Modify: `src/framework_cli/template/CLAUDE.md.jinja`
- Modify: `src/framework_cli/template/README.md.jinja`
- Test: full suite + manual verification

- [ ] **Step 1: Note the hook in CLAUDE.md**

Edit `src/framework_cli/template/CLAUDE.md.jinja`. In the framework-owned block, under the `## Quality commands` list, add a final bullet (inside the `FRAMEWORK:BEGIN/END` markers):

```markdown
- An editor hook runs ruff + mypy on each Python file as it is edited; fix what it reports before moving on.
```

- [ ] **Step 2: Note the hook in the README**

Edit `src/framework_cli/template/README.md.jinja`. In the `## Quality gates` section, add a bullet:

```markdown
- A Claude Code hook lints each Python file right after it is edited (`.claude/settings.json`).
```

- [ ] **Step 3: Add render assertions for the doc updates**

Add to `tests/test_copier_runner.py`:

```python
def test_render_docs_mention_editor_hook(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "editor hook" in (dest / "CLAUDE.md").read_text().lower()
    assert ".claude/settings.json" in (dest / "README.md").read_text()
```

Run: `uv run pytest tests/test_copier_runner.py::test_render_docs_mention_editor_hook -v` → expect PASS (after the edits in Steps 1-2).

- [ ] **Step 4: Run the full framework gate**

Run: `uv run pytest -q` — all tests pass, including the existing `test_rendered_project_precommit_runs_clean` (which now also lints `.claude/hooks/lint_changed.py` inside the rendered project — proving the hook script is itself gate-clean) and the three new `lint_hook` tests.
Run: `uv run ruff check .` → no errors. Run: `uv run mypy src` → `Success`.

- [ ] **Step 5: Manual verification**

In a scratch dir outside the repo, scaffold a project and exercise the hook directly:

```bash
uv run --project /path/to/swiftwater-framework framework new "Hook Demo"
cd hook-demo
uv sync
# Simulate a PostToolUse payload for a bad file:
echo '{"tool_name":"Write","tool_input":{"file_path":"src/hook_demo/x.py"}}' > /tmp/payload.json
printf 'import os\n' > src/hook_demo/x.py
uv run python .claude/hooks/lint_changed.py < /tmp/payload.json ; echo "exit=$?"   # expect F401 on stderr, exit=2
```

Confirm exit=2 with an `F401` message. Delete the scratch dir; confirm `git status` in the framework repo is clean.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/CLAUDE.md.jinja src/framework_cli/template/README.md.jinja tests/test_copier_runner.py
git commit -m "docs: document the lint-on-edit hook in generated projects"
```

---

## Self-Review

**1. Spec coverage (Plan 2b subset):** §4 Claude Code hooks — the `.py → ruff + mypy` surgical PostToolUse hook is implemented (Task 1) and behaviorally verified (Task 2). The other hooks listed in §4 (test→pytest, other file types, pip-audit, gitleaks) are explicitly deferred in the scope note — not silent omissions.

**2. Placeholder scan:** No TBD/TODO. The hook script and settings.json are given in full; the schema is the doc-verified form (matcher regex on tool name, `tool_input.file_path`, exit 2 to surface to Claude). Every run step has an exact command and expected result.

**3. Type/consistency check:** The hook reads `tool_input.file_path` (matches the verified payload schema and the `_run_hook` test helper, which sends exactly that shape). The settings.json `command` invokes `.claude/hooks/lint_changed.py` — the same path asserted in the render test and used by the behavioral tests. `import json` is ensured present in both test files before use. The behavioral tests invoke the script via `uv run python` so ruff/mypy resolve from the venv, consistent with how the real hook command runs it.

**4. Cross-cutting safety:** The hook script must stay ruff/ruff-format-clean because a generated project's pre-commit lints it; this is enforced automatically by the pre-existing `test_rendered_project_precommit_runs_clean` acceptance test (Plan 2), so a regression here fails the suite rather than shipping silently.

---

*End of plan.*
