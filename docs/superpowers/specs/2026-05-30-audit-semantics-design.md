# Audit Semantics — Design

**Status:** spec
**Date:** 2026-05-30 21:09 PDT
**Supersedes:** the diff-source design choice from `2026-05-30-framework-audit-pass-design.md` (which inherited `pr_diff()` semantics; that choice is replaced here)
**Related:** `docs/superpowers/eval-scorecards/audit-2026-05-30-2446de8/triage.md` (the discovery that motivated this spec)

## Context

The first framework audit pass (committed in `21b8bdc` on 2026-05-30) ran `/reviewers:audit` against `src/framework_cli/` with the 6 active framework-target agents. The triage surfaced a fundamental design quirk: `audit-prepare` calls `_review_diff()` → `pr_diff()` → `git diff HEAD~1...HEAD`, so reviewers reviewed the *prior commit's diff* rather than the whole framework tree.

The user's intent for "audit" was clearly snapshot-based ("find real problems in the framework code"). The implementation inherited diff-semantics from how `/reviewers:gate` was wired. This spec resolves that mismatch and adds a delta-vs-prior-baseline mode for recurring audits.

The spec covers the framework target today; the template-audit work (deferred to a separate spec) will use the same semantics once they land.

## Goals

1. Make `/reviewers:audit` review the **whole current code state** by default (the snapshot semantic the user originally intended).
2. Add a **delta-vs-prior-baseline** mode where each agent diffs against the most-recent baseline that included that agent (auto-discovered per-(target, agent)).
3. Give users explicit overrides: `--snapshot` (force all-snapshot) and `--since <ref-or-dir>` (force all-delta against a chosen anchor).
4. Make every per-agent mode decision **visible** — recorded in `meta.json` and logged at run time, no silent skips.
5. Keep `/reviewers:gate` and `/reviewers:tune` unaffected.

## Non-goals

- The template audit pass (separate spec; will adopt these semantics).
- The 6 deferred "audit-prepare hardening" items from the 2026-05-30 triage (`tempfile.mkdtemp` ephemeral path + workflow guards) — separate slice.
- Calibration re-tune for `documentation@info` / `application-logic@info` block thresholds — separate work.
- Re-activating the 3 inactive framework-target agents (`api-design`, `contracts`, `performance`) — separate registry decision.

## Use cases (from brainstorming)

1. **First-time baseline of code that's never been reviewed** (what we just did, but now with whole-snapshot semantics).
2. **Periodic deep snapshot review** (every N months / on demand).
3. **Delta audit: "what's changed since the last preserved baseline?"** Per-agent — each reviewer sees the diff since the last time they reviewed this target.
4. *(out of scope — gate covers this)* PR-style review of a feature branch.

## Architecture

A scoped refactor of `audit-prepare` + `reviewers-audit.js` to produce **mixed snapshot/delta work-items**, where the mode is chosen per-agent based on flags + auto-discovery against prior baselines under `docs/superpowers/eval-scorecards/audit-*/`.

The data shifts from "every agent gets the same `pr_diff()` blob" to "each agent's work-item is computed independently from its own diff base (or snapshot)." The workflow's per-item dispatch branches its prompt template based on the new `review_mode` field.

`/reviewers:gate` (staged-diff) and `/reviewers:tune` (fixture-based) are unaffected.

## Components

### 1. `src/framework_cli/review/diff.py` — new helper(s)

- `snapshot_seed(target: str, root: Path) -> str` — produces the seed for snapshot mode. For bundle agents this returns an empty string (the existing `system_blocks[1]` bundled context already carries the per-agent source files via `ContextPolicy("bundle", context_globs=...)`). For agentic agents the workflow already gets `root_dir`; nothing new needed at the diff layer.
- `delta_diff(base_sha: str) -> str` — `git diff <base_sha>...HEAD`. Errors loudly via the existing typer.Exit pattern when `base_sha` isn't reachable.

`pr_diff()`, `framework_diff()`, and `staged_diff()` stay as-is — they have their own callers (runtime-review and gate respectively).

### 2. `src/framework_cli/review/baselines.py` — new module

Houses baseline-discovery logic in a small, pure, easily testable module.

- `find_latest_baseline_for_agent(target: str, agent: str, scorecards_root: Path) -> Path | None` — scans `audit-*` dirs under `scorecards_root`, reads each `meta.json`, returns the newest dir whose `target` matches and whose `agents` list includes `agent`. Tie-break is lexicographic by dir name (deterministic). Skips malformed `meta.json` entries.
- `read_baseline_sha(baseline_dir: Path) -> str | None` — returns the `git_sha` from `meta.json`, or None if missing/unreadable.
- `is_baseline_dir(path: Path) -> bool` — true iff `path` is a directory with a readable `meta.json` containing a `git_sha`. Used by `_resolve_audit_base` to disambiguate `--since <ref>` from `--since <dir>`.

### 3. `src/framework_cli/cli.py` — `audit-prepare` changes

#### New options
- `--snapshot` (boolean) — force all agents into snapshot mode; skip discovery entirely.
- `--since <ref-or-dir>` (string) — force-delta against a chosen anchor (a git ref/SHA or a baseline directory under `eval-scorecards/`).
- Mutually exclusive — passing both → exit 2 with `audit-prepare: --snapshot and --since are mutually exclusive`.

#### New module-level helper

```python
def _resolve_audit_base(
    agent: str,
    target: str,
    *,
    snapshot_flag: bool,
    since_arg: str | None,
    scorecards_root: Path,
) -> tuple[str, str | None, str | None]:
    """Return (review_mode, base_sha, base_baseline_name).

    review_mode is "snapshot" or "delta".
    base_sha is the commit to diff HEAD against (None for snapshot).
    base_baseline_name is the dated-dir name of the resolved baseline, if any.
    """
```

Logic by case:
- **`snapshot_flag=True`** → `("snapshot", None, None)` for every agent.
- **`since_arg` is a baseline dir** (via `is_baseline_dir`) → read its `meta.json`; if `agent` ∈ `agents` → `("delta", sha, dirname)`; else → `("snapshot", None, None)` (per-agent fallback with a logged note).
- **`since_arg` is a ref/SHA** (anything that doesn't pass `is_baseline_dir`) → resolve via `git rev-parse`; if it resolves → `("delta", resolved_sha, None)`; if it doesn't → exit 2 loudly.
- **Bare (auto-discover)** → `find_latest_baseline_for_agent(target, agent, scorecards_root)`; if found → `("delta", sha, dirname)`; if not → `("snapshot", None, None)` with logged note.

#### `_emit_audit_prep` body changes

For each active agent in `agents_set`:
1. `(mode, base_sha, base_dir) = _resolve_audit_base(agent, target, ...)`
2. If `mode == "delta"`: `diff = delta_diff(base_sha)` → used as `system_blocks[0]` text.
3. If `mode == "snapshot"`: `diff = snapshot_seed(target, root)` (empty for bundle); `system_blocks[0]` is omitted entirely (the existing bundled-context block at `system_blocks[1]` becomes `[0]`).
4. Build work-item with `review_mode`, `base_sha`, `base_baseline` set.
5. If `mode == "snapshot"` and the fallback was logged, the audit-prepare stdout summary includes a brief "fell back to snapshot" note per agent.

### 4. `.claude/workflows/reviewers-audit.js` — per-item prompt branching

The per-item dispatch reads `item.review_mode` and picks one of two prompt templates:

**`delta`:**
```
You are acting as a code reviewer reviewing changes to a project. The
diff below is the change between the prior baseline (commit <base_sha>,
recorded in baseline <base_baseline_name>) and the current HEAD. Focus
on what is new or changed; the rest of the codebase has been reviewed
previously and is out of scope for this run.

Read the JSON file at <items/item-NNNN.json>. The reviewer's instructions
are in system_blocks; the diff is in system_blocks[0]; the user_message
asks for findings in JSON.
```

**`snapshot`:**
```
You are acting as a code reviewer reviewing a project from scratch.
There is no prior review baseline; this is a fresh review of the
current code state. Focus on real issues you can find in the bundled
files (or, for agentic reviewers, the code at root_dir).

Read the JSON file at <items/item-NNNN.json>. The reviewer's instructions
are in system_blocks; the user_message asks for findings in JSON.
```

The two prompts are static templates with placeholder substitution for `base_sha` and `base_baseline_name`. No conditional branches inside the prompt.

### 5. `audit-finalize` — per-agent traceability in `meta.json`

`_finalize_audit` extends `meta.json` to include per-agent records:

```json
{
  "target": "framework",
  "git_sha": "...",
  "timestamp": "...",
  "agents": ["..."],
  "per_agent": {
    "application-logic": {
      "review_mode": "delta",
      "base_sha": "abc1234...",
      "base_baseline": "audit-2026-05-30-2446de8"
    },
    "architecture": {
      "review_mode": "snapshot",
      "base_sha": null,
      "base_baseline": null
    }
  }
}
```

The per-agent block lives at the top level alongside the run-level fields. Per-agent finding records under `findings/<agent>.json` also gain `review_mode` and `base_sha` for self-contained traceability.

### 6. `/reviewers:audit` slash command — flag passthrough

`.claude/commands/reviewers/audit.md` (and the template mirror) get two new Inputs:
- `--snapshot` (boolean) — passed through to `audit-prepare --snapshot`.
- `--since <ref-or-dir>` — passed through to `audit-prepare --since <ref-or-dir>`.

Mutual-exclusion enforcement happens at the CLI layer; the slash command just forwards.

## Data flow

```
1. /reviewers:audit [--target T] [--agents a,b,c] [--snapshot | --since <ref-or-dir>]
                    [--preserve-as <dir>] [--force]
   └─> audit-prepare:
       for each active agent A:
         (mode, base_sha, base_dir) = _resolve_audit_base(A, T, ...)
         diff = delta_diff(base_sha) if mode=="delta" else ""
         work_item = {agent: A, review_mode: mode, base_sha, base_baseline: base_dir,
                      system_blocks, user_message, ...}
       writes prep manifest (stdout) + split-manifest layout under --split-to

2. Workflow "reviewers-audit" loads {indexPath, itemsDir, meta}
   └─> per-item: reads item from disk, branches prompt on item.review_mode,
       dispatches the appropriate subagent

3. Each subagent returns its findings JSON

4. audit-finalize writes:
   - findings/<agent>.json  (per-agent records, includes review_mode + base_sha)
   - audit-report.md        (grouped by agent; severity ranked)
   - meta.json              (run-level + per_agent.{agent}.{review_mode, base_sha, base_baseline})

5. (Optional) audit-finalize --preserve-as <dated-dir>
   └─> copies findings/, audit-report.md, meta.json into the dated baseline dir

6. Future audits auto-discover this baseline per-(target, agent) and produce
   deltas against it.
```

## Error handling

- **Mutually-exclusive flags** (`--snapshot` + `--since`): exit 2 with `audit-prepare: --snapshot and --since are mutually exclusive`.
- **Bad `--since <ref>`** (`git rev-parse` fails): exit 2 with the git error + `...is that ref reachable?`.
- **Bad `--since <baseline-dir>`** (path is not a baseline dir per `is_baseline_dir`): exit 2 with `audit-prepare: <dir> doesn't look like an audit baseline (missing/unreadable meta.json)`.
- **Per-agent fallback to snapshot** (no prior baseline OR not in named `--since` baseline): NOT an error — emit one `typer.echo(...)` info line per agent (`"audit-prepare: <agent> has no prior baseline; running snapshot"`). Records per-agent visibility; differentiates "intentional fallback" from "silently skipped."
- **`delta_diff(base_sha)` returns empty string** (base_sha == HEAD, or genuinely no changes since base): record `review_mode: "delta"` but with empty diff; the prompt template handles "no changes since baseline X" gracefully. Not an error.
- **Multiple baselines for the same agent at identical mtime**: tie-break is lexicographic by dir name (deterministic).
- **`meta.json` schema drift**: `baselines.py` skips entries missing required fields rather than crashing. Logs at info level when it skips one.

## Testing

- **`framework_cli.review.baselines`** — small, pure, unit-tested.
  - `find_latest_baseline_for_agent` returns newest matching baseline; returns None when none.
  - Skips malformed `meta.json` (broken JSON, missing fields, missing `git_sha`) gracefully.
  - Tie-break is deterministic against fixtures with identical timestamps.
- **`_resolve_audit_base`** — unit-tested for the 4 branches: snapshot-flag, since-as-ref, since-as-baseline-dir, auto-discover. Each verifies the fallback path.
- **`audit-prepare` integration tests**:
  - `--snapshot` produces all work-items with `review_mode == "snapshot"` and empty `system_blocks[0]` diff text.
  - `--since <SHA>` produces all work-items with `review_mode == "delta"` and `base_sha == <SHA>`.
  - `--since <baseline-dir>` per-agent: agents in baseline get `delta`; agents not in baseline get `snapshot` (with the info log captured via typer's stderr).
  - Bare invocation with one prior baseline present → auto-discover hits, delta mode.
  - Bare invocation with NO prior baselines → all snapshot.
  - `--snapshot` + `--since` together → exit 2 with the expected error.
- **Workflow per-item prompt branching** — using the existing per-item mock pattern in `test_cli.py` (extended to `test_reviewers_audit_workflow_*`), verify that delta items get the delta prompt and snapshot items get the snapshot prompt.

## Definition of done

1. `framework_cli/review/baselines.py` exists with `find_latest_baseline_for_agent`, `read_baseline_sha`, `is_baseline_dir` + unit tests.
2. `audit-prepare` accepts `--snapshot` and `--since`, enforces mutual exclusion, and produces per-agent mixed-mode work-items.
3. `.claude/workflows/reviewers-audit.js` (and template mirror) branches prompts on `item.review_mode`.
4. `audit-finalize` records per-agent `review_mode`/`base_sha`/`base_baseline` in `meta.json` and in `findings/<agent>.json`.
5. `/reviewers:audit` slash command (and template mirror) exposes `--snapshot` and `--since` and forwards them.
6. All existing audit tests still pass; new tests for mode resolution + flag handling pass.
7. The "audit-prepare reuses pr_diff" entry in CLAUDE.md's Known follow-ups is removed (resolved by this spec).

## Open questions

None.

## Out-of-band notes

- This spec is small enough to fit in one implementation plan (one task per component, ~6 tasks). No decomposition needed.
- The new `baselines.py` module is a useful primitive that the future template-audit spec will reuse without changes.
- The per-agent traceability in `meta.json` enables future analyses (e.g., "how often does each agent run in snapshot vs delta mode? has agent X reviewed this target in the last N months?") without re-instrumenting.
