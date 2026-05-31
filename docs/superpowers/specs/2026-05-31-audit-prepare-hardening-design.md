# audit-prepare hardening — design

**Date:** 2026-05-31
**Status:** approved (brainstorm), ready for plan
**Source:** the 6 `defer` findings in `docs/superpowers/eval-scorecards/audit-2026-05-30-2446de8/triage.md`

## Problem

The first framework audit baseline (`audit-2026-05-30-2446de8`) produced 6 deferred
findings, grouped in the triage as a coherent "audit-prepare hardening" follow-up slice.
All 6 are still live in current `master`. Two facts found during this brainstorm change
the framing:

1. **The split-dir block is now triplicated.** The audit flagged one location
   (`cli.py:268` at the time). The audit-semantics / split-manifest work has since
   copy-pasted the identical block into three `_emit_*_prep` helpers in `cli.py`:
   `_emit_gate_prep`, `_emit_tune_prep`, `_emit_audit_prep`.
2. **The code ships beyond single-user dev.** The gate + audit slash commands,
   workflows, and the PreToolUse hook ship in the template into generated projects,
   which install `framework_cli` as a dependency. So `framework gate-prepare --split-to …`
   runs on **whatever host runs a generated project's pre-commit gate** — potentially a
   shared CI runner, not just a single-user dev box. This elevates the security findings
   (#6/#7) above the "dev-only, ignore" rationale the triage used to defer them.

The findings split into two clusters:

### Cluster A — split-dir handling (Python, `cli.py`) — findings #3, #6, #7
The current block in each `_emit_*_prep`:
```python
split_dir = Path(split_to)
if split_dir.exists():
    shutil.rmtree(split_dir)        # #3: raises NotADirectoryError if a stale FILE sits here
items_dir = split_dir / "items"
items_dir.mkdir(parents=True, exist_ok=True)
split_dir.chmod(0o700)              # #7: umask window — mkdir then chmod = brief world-listable gap
items_dir.chmod(0o700)
```
- **#6 (security, low):** TOCTOU + symlink coercion between `exists()` and `rmtree`/`mkdir`
  on a predictable, caller-supplied `/tmp` path.
- **#7 (security, low):** umask window — the dir is world-listable for an instant before
  `chmod(0o700)`; the per-item files it holds carry the diff (load-bearing).
- **#3 (app-logic, low):** `rmtree` raises opaquely if a stale *file* (not dir) is at the path.

### Cluster B — workflow guards (JS) — findings #1, #2
- **#1 (app-logic, medium):** the empty-items path silently `return { results: [], meta }`
  with no `log()` — a valid noop (e.g. an unknown-agents filter consumes the whole roster)
  but invisible to the operator.
- **#2 (app-logic, low):** no `!Array.isArray(items)` guard. Mostly defense-in-depth since
  `INDEX_SCHEMA` already constrains `items` to an array via the schema'd loader.

### Findings that are now stale (not part of this slice)
- The triage's "review surface caveat" (`HEAD~1...HEAD`) and the open "diff- vs
  snapshot-based audit?" question were **resolved by the audit-semantics work** — audit is
  now snapshot-primary.
- The "3 inactive agents" note (api-design/contracts/performance) was revisited → no change
  (the gate caught they're app-domain-scoped, not CLI-applicable).

## Decision

**Proportionate in-place hardening** (chosen over an ephemeral-mkdtemp-emit-path rewrite and
over a minimal correctness-only patch). Keep the predictable `/tmp` paths the slash commands
depend on; harden the create path so it is safe even on a multi-user host; DRY the three
copies into one helper. Add the two JS guards across all four workflow copies for consistency.

## Components

### Component 1 — shared `_prepare_split_dir()` helper (`cli.py`)
Replaces the identical block in `_emit_gate_prep`, `_emit_tune_prep`, and `_emit_audit_prep`:

```python
def _prepare_split_dir(split_to: str) -> tuple[Path, Path]:
    """Create a clean, private (0o700) split-manifest dir at `split_to`; return (split_dir, items_dir).

    Hardening (audit 2026-05-30 #3/#6/#7): refuse a symlink or non-directory at the target;
    build the tree under a private mkdtemp staging dir and os.replace() it into place, so the
    published dir is 0o700 with no umask window and the publish is atomic.
    """
    split_dir = Path(split_to)
    if split_dir.is_symlink():                       # #6: don't rmtree/replace through a symlink
        raise RuntimeError(f"--split-to target is a symlink, refusing: {split_dir}")
    if split_dir.exists():
        if not split_dir.is_dir():                   # #3: non-dir collision (rmtree would raise opaquely)
            raise RuntimeError(f"--split-to target exists and is not a directory: {split_dir}")
        shutil.rmtree(split_dir)
    parent = split_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".split-staging-", dir=parent))  # #7: 0o700, atomic, no umask gap
    items_dir = staging / "items"
    items_dir.mkdir()
    items_dir.chmod(0o700)
    os.replace(staging, split_dir)                   # atomic publish; preserves 0o700
    return split_dir, split_dir / "items"
```

Each call site collapses to:
```python
split_dir, items_dir = _prepare_split_dir(split_to)
```

Rationale for the mkdtemp-then-`os.replace` shape:
- `tempfile.mkdtemp` creates the staging dir `0o700` **atomically** — no umask gap (#7).
- The unpredictable staging name + `os.replace` (a same-filesystem atomic rename; the staging
  dir is a sibling under the same `parent`) narrows the TOCTOU / symlink-coercion window
  dramatically (#6).
- The `is_symlink()` / `is_dir()` guards close the non-dir collision and refuse to `rmtree`
  through a symlink (#3, #6).
- The per-item write loops keep their `chmod(0o600)`, but the files are now born inside a
  `0o700` dir → no world-readable window.

**Predictable paths stay** (`/tmp/reviewers-{audit,gate}-prep-split`, `/tmp/reviewers-tune-items/`),
so the three slash commands and their later metadata-read / cleanup steps are byte-unchanged.

**Residual:** a narrow `rmtree`→`os.replace` race remains. If a racer recreates `split_dir` as
an empty dir, `os.replace` replaces it; as a non-empty dir, `os.replace` raises (we error rather
than clobber). Honest framing: "meaningfully reduced," not "eliminated" — proportionate for the
surface.

### Component 2 — JS workflow guards (4 files, kept in sync)
In `reviewers-audit.js`, `reviewers-gate.js`, **and** their `.jinja` template copies
(`src/framework_cli/template/.claude/workflows/reviewers-{audit,gate}.js.jinja`), after
`const items = index.items`:

```js
if (!Array.isArray(items)) {                                  // #2: defense-in-depth
  throw new Error('reviewers-<x>: index.items must be an array')
}
if (items.length === 0) {
  log('reviewers-<x>: no work items — nothing to review')     // #1: make the valid noop visible
  return { results: [], meta: ARGS.meta || {} }
}
```

Findings #1/#2 were filed against `audit.js` only, but `gate.js` carries the identical pattern
and the `.jinja` copies ship to generated projects. Fixing all four avoids drift between the
repo workflows and their template copies (they are meant to be identical modulo jinja).

## Testing (TDD)

Python (`tests/test_cli.py`):
- `_prepare_split_dir` → `split_dir` and `items_dir` both `0o700`; returns the correct
  `(split_dir, items_dir)` tuple.
- raises `RuntimeError` on a **symlink** target.
- raises `RuntimeError` on a **non-dir (file)** at the target.
- replaces a pre-populated existing dir cleanly (the existing
  `test_audit_prepare_split_to_clears_existing_dir` already exercises this through the audit
  path; the helper is now the shared code path under it).
- regression: the gate / tune / audit `--split-to` paths still emit an identical index +
  items layout and retain the existing `0o700` (dirs) / `0o600` (files) permission assertions.

JS:
- No JS unit harness exists in-repo; the guards are exercised through the workflow integration,
  and the empty/array behavior is trivial. Stated plainly to match existing repo practice.
- The `.jinja` render is covered by the acceptance render test (`tests/test_copier_runner.py`),
  confirming the edited template workflows still render.

## Non-goals
- No switch to unpredictable emitted paths (rejected: would churn all three slash commands —
  including audit.md's later by-name metadata-read + cleanup steps — and drop the
  predictable-path ergonomics).
- No new repo↔template workflow parity test (noted as a possible future hygiene add).

## Integrity / manifest impact
**None.** `.claude/workflows/*.js` are not in `LOCKED_TRACKED`, `HYBRID_TRACKED`, or
`GITIGNORED_EXISTENCE` (verified in `src/framework_cli/integrity/classes.py`). Editing the
template `.jinja` workflow copies does **not** bump the baseline integrity manifest. This is a
clean, framework-side-only slice.

## Verification
`uv run pytest -q` (all tests), `uv run ruff check .`, `uv run mypy src` green; render +
acceptance unaffected.

## Estimated size
~30 lines of production change + the 3-site DRY collapse, ~4 new/extended tests.
