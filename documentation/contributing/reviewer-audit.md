# Runbook: auditing the review agents

This page is for maintainers of the **framework itself**. It describes
`framework reviewer-audit` — an in-process tool that captures the Plan 21
audit→synthesis→adversarial method as a repeatable capability, so adding or
retuning a reviewer doesn't re-incur a manual sweep (or skip one and let the
shared severity bar drift).

**When to run it:** after adding or retuning a review agent, or periodically to
catch rubric drift across the roster.

**What it does (and doesn't):** it audits one-or-more reviewers against the shared
rubric (`src/framework_cli/review/rubric.md`, composed into every agent's prompt at
runtime), reconciles severity bars across the *full* roster, adversarially refutes
each proposed change, and emits a **vetted changelist + a dry-run apply-preview
patch**. It does **not** apply any edit — you inspect and apply, with `framework
eval` as the gate.

## The flow

### 1. Baseline (evidence)

```bash
framework eval --repeat 3 --findings-out .framework/eval-baseline --backend subagent
```

The audit reasons *from* these findings (with their `--repeat 3` variance) and
beyond them — they are evidence, not ground truth.

### 2. Audit

```bash
framework reviewer-audit --baseline .framework/eval-baseline --out .framework/reviewer-audit
# or a subset (the full roster is still loaded as the consistency baseline):
framework reviewer-audit coverage-gap security --baseline .framework/eval-baseline
```

Audit, reconcile, and skeptic agents run on Opus. The run is resumable across
quota resets with `--resume` (agent-granularity checkpoints under `--out`,
including a pinned `stage2-reconcile.json` so a resume can't desync verdicts).
Progress streams to stderr as it runs (`--quiet` to silence); the fan-out stages
run in parallel — tune with `--concurrency N` (default 4; `1` = serial). Without a
review backend the command is skip-neutral (exits 0).

### 3. Inspect

- `.framework/reviewer-audit/changelist.json` — the **vetted** changes (those the
  majority of skeptics failed to refute).
- `.framework/reviewer-audit/changelist-full.json` — **every** proposed change with
  its adversarial verdict + refutation log (the kicked-back set, never silently
  dropped).
- `.framework/reviewer-audit/apply-preview.patch` — a git-applyable patch of the
  validated textual edits (`domain_prompt`/`rubric`). Each hunk is checked with
  `git apply --check` (cumulatively), so the file always applies; it is written only
  when at least one hunk applies.
- `.framework/reviewer-audit/apply-preview.notes.txt` — the edits that are **not**
  auto-applied: `fixture` rewrites (a fixture's `change.patch` is itself a diff —
  apply by hand), `block_threshold` changes (edit `registry.py`), and any hunk that
  did not apply cleanly. Each points back to `changelist-full.json`.

```bash
git apply --check .framework/reviewer-audit/apply-preview.patch
```

### 4. Apply + re-confirm (the gate)

```bash
git apply .framework/reviewer-audit/apply-preview.patch
framework eval <agent> --repeat 3 --backend subagent   # good stays clean, bad stays caught
```

Apply `block_threshold` changes by hand in `src/framework_cli/review/registry.py`
(they are called out in the patch header). A rubric change lands as a single edit
to `rubric.md` and is re-propagated to every agent by runtime assembly — never as N
per-prompt diffs.

### 5. Re-derive thresholds + scorecard (whole-set retune only)

```bash
framework eval --repeat 3 --findings-out .framework/eval-after --backend subagent
framework eval-analyze .framework/eval-after   # re-derive thresholds.yaml with margin
```

Commit a dated scorecard under `docs/superpowers/eval-scorecards/`.

## Notes

- **Consistency oracle.** Even when you target one agent, the tool always loads the
  full roster's `block_threshold`s — auditing a reviewer in isolation has no baseline
  to assess its severity bar against.
- **No Claude Code dependency.** The pipeline runs in-process on the LiteLLM backend
  seam (the same `--backend api|subagent` the reviewers use), not a Claude Code
  Workflow.
