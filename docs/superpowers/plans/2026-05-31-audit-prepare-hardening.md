# audit-prepare hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 6 deferred findings from the `audit-2026-05-30-2446de8` baseline by DRYing the triplicated split-dir block into one hardened `_prepare_split_dir()` helper and adding two guards across the four workflow copies.

**Architecture:** A new private `_prepare_split_dir(split_to) -> (split_dir, items_dir)` helper in `src/framework_cli/cli.py` replaces the identical ~7-line block in `_emit_gate_prep`, `_emit_tune_prep`, and `_emit_audit_prep`. It refuses a symlink/non-dir at the target and builds the tree under a private `tempfile.mkdtemp` staging dir that is atomically `os.replace`d into place (0o700, no umask window). Separately, `reviewers-audit.js` / `reviewers-gate.js` and their `.jinja` template copies get an `Array.isArray` guard and a `log()` on the empty-items noop.

**Tech Stack:** Python 3 (Typer CLI, `pathlib`, `tempfile`, `shutil`, `os`), pytest; JS Workflow scripts (`.claude/workflows/*.js` + Copier `.jinja` copies). All tooling via `uv run`.

**Spec:** `docs/superpowers/specs/2026-05-31-audit-prepare-hardening-design.md`

---

## File Structure

- **Modify** `src/framework_cli/cli.py` — add `_prepare_split_dir()` (defined just before `_emit_gate_prep`, ~line 831, so it precedes all three callers); rewire the three `_emit_*_prep` split blocks to call it; drop the now-unused local `import shutil` in each (keep tune's local `import tempfile`).
- **Modify** `tests/test_cli.py` — add direct unit tests for `_prepare_split_dir` (private-dir creation, symlink refusal, non-dir refusal, clean replace of a pre-populated dir). The existing `*_split_to_writes_index_and_items` / `*_clears_existing_dir` / perm-assertion / gate-noop tests stay as the regression net for the rewired call sites.
- **Modify** 4 workflow files (identical guard edit, kept in sync):
  - `.claude/workflows/reviewers-audit.js`
  - `.claude/workflows/reviewers-gate.js`
  - `src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja`
  - `src/framework_cli/template/.claude/workflows/reviewers-gate.js.jinja`

**Integrity note:** `.claude/workflows/*.js` are not in `LOCKED_TRACKED`/`HYBRID_TRACKED`/`GITIGNORED_EXISTENCE` — no baseline manifest shift.

---

## Task 1: Add the hardened `_prepare_split_dir()` helper (TDD)

**Files:**
- Test: `tests/test_cli.py`
- Modify: `src/framework_cli/cli.py` (insert new helper immediately before `def _emit_gate_prep` at ~line 831)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` (it already has `import stat`, `import os`, `from pathlib import Path`, and imports from `framework_cli.cli`; add `_prepare_split_dir` to whatever import style the file uses — e.g. `from framework_cli.cli import _prepare_split_dir`, or reference it via the existing module import):

```python
def test_prepare_split_dir_creates_private_dirs(tmp_path):
    """_prepare_split_dir returns (split_dir, items_dir), both 0o700."""
    from framework_cli.cli import _prepare_split_dir

    target = tmp_path / "sd"
    split_dir, items_dir = _prepare_split_dir(str(target))

    assert split_dir == target
    assert items_dir == target / "items"
    assert split_dir.is_dir()
    assert items_dir.is_dir()
    assert stat.S_IMODE(split_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(items_dir.stat().st_mode) == 0o700


def test_prepare_split_dir_rejects_symlink_target(tmp_path):
    """A symlink at the target is refused (don't rmtree/replace through it)."""
    from framework_cli.cli import _prepare_split_dir

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)

    with pytest.raises(RuntimeError, match="symlink"):
        _prepare_split_dir(str(link))


def test_prepare_split_dir_rejects_nondir_target(tmp_path):
    """A plain file at the target is refused, not rmtree'd opaquely."""
    from framework_cli.cli import _prepare_split_dir

    target = tmp_path / "afile"
    target.write_text("stale")

    with pytest.raises(RuntimeError, match="not a directory"):
        _prepare_split_dir(str(target))


def test_prepare_split_dir_replaces_pre_populated_dir(tmp_path):
    """A pre-existing dir (with stale contents) is cleanly replaced."""
    from framework_cli.cli import _prepare_split_dir

    target = tmp_path / "sd"
    (target / "items").mkdir(parents=True)
    (target / "items" / "item-9999.json").write_text("stale")
    (target / "stray.txt").write_text("stale")

    split_dir, items_dir = _prepare_split_dir(str(target))

    assert items_dir.is_dir()
    assert not (split_dir / "stray.txt").exists()
    assert not (items_dir / "item-9999.json").exists()
    assert stat.S_IMODE(split_dir.stat().st_mode) == 0o700
```

(If `pytest` is not already imported at the top of `tests/test_cli.py`, add `import pytest`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k prepare_split_dir -v`
Expected: FAIL — `ImportError` / `AttributeError` (`_prepare_split_dir` does not exist yet).

- [ ] **Step 3: Implement the helper**

Insert this function in `src/framework_cli/cli.py` immediately before `def _emit_gate_prep(split_to: str = "") -> None:` (~line 831). `os` and `Path` are already module-level; `shutil`/`tempfile` are imported locally to match the file's existing per-function import style:

```python
def _prepare_split_dir(split_to: str) -> tuple[Path, Path]:
    """Create a clean, private (0o700) split-manifest directory at ``split_to``.

    Returns ``(split_dir, items_dir)``. Hardening for the deferred findings in the
    2026-05-30 audit (#3/#6/#7): refuse a symlink or non-directory at the target —
    so we never rmtree/replace through a symlink or raise opaquely on a file
    collision — and build the tree under a private ``tempfile.mkdtemp`` staging dir
    that is atomically ``os.replace``d into place, so the published directory is
    0o700 with no umask window and the publish is atomic. A narrow rmtree->replace
    race remains (proportionate for this surface); a hostile racer recreating the
    target as a non-empty dir makes ``os.replace`` raise rather than clobber.
    """
    import shutil
    import tempfile

    split_dir = Path(split_to)
    if split_dir.is_symlink():
        raise RuntimeError(f"--split-to target is a symlink, refusing: {split_dir}")
    if split_dir.exists():
        if not split_dir.is_dir():
            raise RuntimeError(
                f"--split-to target exists and is not a directory: {split_dir}"
            )
        shutil.rmtree(split_dir)
    parent = split_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".split-staging-", dir=parent))
    items_dir = staging / "items"
    items_dir.mkdir()
    items_dir.chmod(0o700)
    os.replace(staging, split_dir)
    return split_dir, split_dir / "items"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k prepare_split_dir -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint + type-check the new code**

Run: `uv run ruff check src/framework_cli/cli.py && uv run ruff format --check src/framework_cli/cli.py && uv run mypy src`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add tests/test_cli.py src/framework_cli/cli.py CLAUDE.md
git commit -m "feat(cli): hardened _prepare_split_dir() helper (audit #3/#6/#7)"
```

(Update the **Current State** pointer + **Last updated** datetime in `CLAUDE.md` before staging — the PreToolUse gate hook blocks the commit otherwise.)

---

## Task 2: Rewire the three `_emit_*_prep` call sites to the helper (refactor, stay green)

**Files:**
- Modify: `src/framework_cli/cli.py`
  - `_emit_gate_prep` split block (~lines 882-889) + its local `import shutil` (~line 833)
  - `_emit_tune_prep` split block (~lines 959-966) + its local `import shutil` (~line 924; **keep** `import tempfile` at ~line 925)
  - `_emit_audit_prep` split block (~lines 1270-1277) + its local `import shutil` (~line 1192)
- Test: `tests/test_cli.py` (existing tests act as the regression net — no new tests here)

- [ ] **Step 1: Replace the gate-prep split block**

In `_emit_gate_prep`, replace:
```python
    if split_to:
        split_dir = Path(split_to)
        if split_dir.exists():
            shutil.rmtree(split_dir)
        items_dir = split_dir / "items"
        items_dir.mkdir(parents=True, exist_ok=True)
        split_dir.chmod(0o700)
        items_dir.chmod(0o700)
```
with:
```python
    if split_to:
        split_dir, items_dir = _prepare_split_dir(split_to)
```

- [ ] **Step 2: Replace the tune-prep split block**

In `_emit_tune_prep`, replace:
```python
    if split_to:
        split_dir = Path(split_to)
        if split_dir.exists():
            shutil.rmtree(split_dir)
        items_dir = split_dir / "items"
        items_dir.mkdir(parents=True, exist_ok=True)
        split_dir.chmod(0o700)
        items_dir.chmod(0o700)
```
with:
```python
    if split_to:
        split_dir, items_dir = _prepare_split_dir(split_to)
```

- [ ] **Step 3: Replace the audit-prep split block**

In `_emit_audit_prep`, replace:
```python
    if split_to:
        split_dir = Path(split_to)
        if split_dir.exists():
            shutil.rmtree(split_dir)
        items_dir = split_dir / "items"
        items_dir.mkdir(parents=True, exist_ok=True)
        split_dir.chmod(0o700)
        items_dir.chmod(0o700)
```
with:
```python
    if split_to:
        split_dir, items_dir = _prepare_split_dir(split_to)
```

- [ ] **Step 4: Drop the now-unused local `import shutil` lines**

Remove `import shutil` from `_emit_gate_prep` (~line 833), `_emit_tune_prep` (~line 924), and `_emit_audit_prep` (~line 1192). **Keep** `_emit_tune_prep`'s `import tempfile` (still used for the `evalprep-` base dir). If ruff/mypy reports `shutil` is still referenced elsewhere inside one of these functions, keep that import.

- [ ] **Step 5: Run the existing split-to regression tests**

Run: `uv run pytest tests/test_cli.py -k "split_to" -v`
Expected: PASS — all of `test_gate_prepare_split_to_writes_index_and_items`, `test_gate_prepare_split_to_clears_existing_dir`, `test_gate_prepare_split_to_noop_writes_empty_index`, `test_tune_prepare_split_to_writes_index_and_items`, `test_tune_prepare_split_to_clears_existing_dir`, `test_audit_prepare_split_to_writes_index_and_items` (incl. its 0o700/0o600 perm assertions), `test_audit_prepare_split_to_clears_existing_dir`.

- [ ] **Step 6: Lint + type-check (catches any leftover unused import)**

Run: `uv run ruff check . && uv run ruff format --check src/framework_cli/cli.py && uv run mypy src`
Expected: clean (ruff F401 would flag a stray `import shutil` if one slipped through).

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/cli.py CLAUDE.md
git commit -m "refactor(cli): route the 3 split-prep blocks through _prepare_split_dir"
```

(Update `CLAUDE.md` Current State + Last updated before staging.)

---

## Task 3: Add the workflow guards (#1 log, #2 Array.isArray) across all 4 copies

**Files:**
- Modify: `.claude/workflows/reviewers-audit.js` (after `const items = index.items`, ~line 60)
- Modify: `.claude/workflows/reviewers-gate.js` (after `const items = index.items`, ~line 45)
- Modify: `src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja` (~line 60)
- Modify: `src/framework_cli/template/.claude/workflows/reviewers-gate.js.jinja` (~line 45)

**Note:** There is no JS unit harness in-repo (matches existing repo practice). Verification for this task is (a) the Copier acceptance render test still passes — confirming the edited `.jinja` files render — and (b) a visual diff confirming all four files carry the identical guard.

- [ ] **Step 1: Edit `reviewers-audit.js`**

The current code is:
```js
const items = index.items

if (items.length === 0) {
  return { results: [], meta: ARGS.meta || {} }
}
```
Replace with:
```js
const items = index.items

if (!Array.isArray(items)) {
  throw new Error('reviewers-audit: index.items must be an array')
}
if (items.length === 0) {
  log('reviewers-audit: no work items — nothing to review')
  return { results: [], meta: ARGS.meta || {} }
}
```

- [ ] **Step 2: Edit `reviewers-gate.js`**

The current code is:
```js
const items = index.items

if (items.length === 0) {
  return { results: [], meta: ARGS.meta || {} }
}
```
Replace with:
```js
const items = index.items

if (!Array.isArray(items)) {
  throw new Error('reviewers-gate: index.items must be an array')
}
if (items.length === 0) {
  log('reviewers-gate: no work items — nothing to review')
  return { results: [], meta: ARGS.meta || {} }
}
```

- [ ] **Step 3: Mirror the audit edit into the template `.jinja` copy**

Apply the **exact same** change as Step 1 to `src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja` (the surrounding lines are identical; the `log()` message stays `reviewers-audit: …`).

- [ ] **Step 4: Mirror the gate edit into the template `.jinja` copy**

Apply the **exact same** change as Step 2 to `src/framework_cli/template/.claude/workflows/reviewers-gate.js.jinja` (the `log()` message stays `reviewers-gate: …`).

- [ ] **Step 5: Confirm all four copies match**

Run: `grep -n "Array.isArray\|no work items" .claude/workflows/reviewers-audit.js .claude/workflows/reviewers-gate.js src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja src/framework_cli/template/.claude/workflows/reviewers-gate.js.jinja`
Expected: each file shows one `Array.isArray` guard line and one `no work items` log line (audit files say `reviewers-audit`, gate files say `reviewers-gate`).

- [ ] **Step 6: Verify the `.jinja` copies still render**

Run: `uv run pytest tests/test_copier_runner.py -v`
Expected: PASS (the render exercises the edited template workflows).

- [ ] **Step 7: Commit**

```bash
git add .claude/workflows/reviewers-audit.js .claude/workflows/reviewers-gate.js \
        src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja \
        src/framework_cli/template/.claude/workflows/reviewers-gate.js.jinja CLAUDE.md
git commit -m "fix(workflows): log() empty-items noop + Array.isArray guard (audit #1/#2)"
```

(Update `CLAUDE.md` Current State + Last updated before staging.)

---

## Task 4: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full fast suite + quality gate**

Run: `uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all pass / clean. (The Docker `tests/acceptance` tier is excluded per the repo convention — run it separately only if a render path changed materially; it did not here.)

- [ ] **Step 2: Confirm no integrity manifest shift**

Run: `git diff --stat HEAD~3 -- src/framework_cli/template`
Expected: only the two `.jinja` workflow files changed; no change to `src/framework_cli/integrity/` and no LOCKED-file payload change → no baseline manifest bump (the `.js` workflows are untracked by integrity).

- [ ] **Step 3: Update the meta-plan + CLAUDE.md, then final commit if anything is outstanding**

Mark the "audit-prepare hardening slice" resolved in the meta-plan / CLAUDE.md outstanding-roadmap bullet and note the 6 findings are closed. Stage `CLAUDE.md` (+ the meta-plan if edited) and commit.

```bash
git add CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
git commit -m "docs(state): audit-prepare hardening complete — 6 deferred findings closed"
```

---

## Self-Review

**Spec coverage:**
- #3 (non-dir collision) → Task 1 `is_dir()` guard + `test_prepare_split_dir_rejects_nondir_target`. ✓
- #6 (TOCTOU/symlink) → Task 1 `is_symlink()` guard + mkdtemp/`os.replace` + `test_prepare_split_dir_rejects_symlink_target`. ✓
- #7 (umask window) → Task 1 mkdtemp(0o700) + atomic replace + `test_prepare_split_dir_creates_private_dirs` (0o700 assertions). ✓
- DRY refactor (3 sites) → Task 2. ✓
- #1 (empty-items log) → Task 3 `log()` lines. ✓
- #2 (Array.isArray) → Task 3 guards. ✓
- 4-file JS sync (repo + template) → Task 3 Steps 1-5. ✓
- No manifest shift → Task 4 Step 2. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code; commands have expected output. ✓

**Type consistency:** `_prepare_split_dir(split_to: str) -> tuple[Path, Path]` is used identically (`split_dir, items_dir = _prepare_split_dir(split_to)`) at all three call sites and in the tests. Return is `(split_dir, split_dir / "items")` — the published paths, not the stale staging paths. ✓
