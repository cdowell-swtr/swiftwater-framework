# Reviewer prompt + threshold re-tuning + fixture quality — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the review agents internally consistent and correctly calibrated by rewriting their prompts against one shared severity+scope rubric, fixing the eval fixtures they're scored against, and re-deriving `thresholds.yaml` last — all on the Plan-20 parity'd path.

**Architecture:** Six sequential phases. **0a** adds a static fixture well-formedness guard and fixes the malformed-patch/truncation class (deterministic, no LLM). **0b** validates that each `good` fixture exhibits the codebase's own patterns (the load-bearing assumption behind the consistency oracle). **0c** runs a fresh baseline eval on the free `claude -p` backend to get representative current scores + per-finding evidence. **Phase 1** is an ultracode Workflow that fans an Opus audit agent over every prompt, synthesizes findings through a 3-way judge panel + meta-synthesis, and adversarially verifies every proposed change — emitting a vetted changelist + a finalized shared rubric, all file-backed for quota-reset resume. **Phase 2** applies each vetted change per-agent and re-tunes. **Phase 3** re-sweeps the full set, re-derives thresholds, and runs a branch-end review before merge.

**Tech Stack:** Python 3.12, `uv`, Typer CLI (`framework eval` / `framework eval-analyze`), pytest, the in-process review engine (`src/framework_cli/review/`), the free subagent backend (`claude -p`), and the Workflow (ultracode) tool for Phase 1.

---

## Execution conventions (read before starting)

**Branch:** `plan-21-reviewer-tuning` off `master`. Use the superpowers:using-git-worktrees skill to create the isolated workspace.

**Review-model policy (RESTATED per CLAUDE.md — do not let the generic "least powerful model" guidance collapse these):**
- Implementers (writing code/fixtures): **Sonnet** (Haiku only for truly trivial mechanical edits).
- Spec-compliance review: **Sonnet**. Code-quality review: **Opus**. Final/branch-end whole-branch review: **Opus**.
- **Phase 1 audit-workflow judgment agents (fan-out audit, judge-panel synthesis, meta-synthesis, adversarial): Opus** — these are code-quality-grade agentic reviewers ([[subagent-review-model-pattern]] + the standard-case rule).
- **Reviewers-under-test in every `framework eval` sweep run on their own `spec.model`** (Sonnet for bundle/diff agents, `claude-opus-4-8` for the 7 agentic agents) — this is the eval default; never pass a model override that would lower an agentic agent, or you repeat the Plan-18 mistake at the model level.

**Backend for all sweeps:** the free subagent backend — `framework eval … --backend subagent`. Reserve `--backend api` (paid) for the sparse Phase 3 spot-confirmation only.

**Quota + resume:** every LLM-bearing step burns subscription quota fast.
- `framework eval` sweeps resume from the engine checkpoint automatically — re-run the same command and it picks up where the loud `APIError` abort left off (Plan 20b: `checkpoint.py` + `tree_signature`).
- The Phase 1 Workflow is file-backed (`.framework/plan21/<stage>/<id>.json`, skip-if-exists) — re-invoke with `resumeFromRunId` (same session) or just re-run (cross-session; completed agents' output files are skipped).
- If a sweep/workflow aborts on quota, wait for the ~5-hour reset (optionally schedule a wake-up) and re-run the identical command.

**Commit/gate cadence ([[gate-cadence-framework-slices]]):** these files are review-infra/agent prompts; the per-commit reviewers-gate hook over-fires ~18 app-agents on them. Use lighter per-task review + **controller skip-marker commits** ([[controller-skip-marker-recipe]]) + **one branch-end full Opus review** (Phase 3). Subagent implementers stop before the final commit ([[subagent-implementers-stop-before-commit]]); the controller verifies and commits. Per [[commit-gate-hook-timing]]: `git add` and `git commit` are **separate** Bash calls, and keep the word "commit" out of Bash command descriptions.

**Before every commit:** update CLAUDE.md Current State (with a `Last updated` datetime+TZ) and the meta-plan status row, then `git add CLAUDE.md` (the PreToolUse hook blocks the commit otherwise).

**Scratch dirs:** `.framework/plan21/` (workflow artifacts) is gitignored like the rest of `.framework/`. Eval findings that we keep go under `docs/superpowers/eval-scorecards/<date>-<slug>/`.

---

## Phase 0a — Fixture well-formedness guard (deterministic, zero quota)

**File structure:**
- Modify: `src/framework_cli/review/evals.py` — add `validate_patch_hunks(patch: str) -> list[str]`.
- Create: `tests/review/test_fixtures_wellformed.py` — unit tests for the validator + the suite-wide guard.
- Modify: any malformed `tests/eval/fixtures/*/*/*/change.patch` discovered.

### Task 1: `validate_patch_hunks` — detect wrong hunk-header counts

The truncation class ([[eval-fixture-patch-truncation]]): a unified-diff hunk header `@@ -a,b +c,d @@` whose declared counts disagree with the hunk body. `b` must equal (context lines + removed lines); `d` must equal (context lines + added lines). When they disagree, `git apply` silently truncates the realized code.

**Files:**
- Modify: `src/framework_cli/review/evals.py`
- Test: `tests/review/test_fixtures_wellformed.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/review/test_fixtures_wellformed.py
from framework_cli.review.evals import validate_patch_hunks

_WELLFORMED = """\
--- a/src/demo/x.py
+++ b/src/demo/x.py
@@ -1,3 +1,4 @@
 import os
+import sys
 import json
 import math
"""

_MALFORMED = """\
--- a/src/demo/x.py
+++ b/src/demo/x.py
@@ -1,3 +1,3 @@
 import os
+import sys
 import json
 import math
"""  # header claims +1,3 (3 new lines) but body has 4 new-side lines (3 context + 1 add)


def test_validate_passes_a_wellformed_patch():
    assert validate_patch_hunks(_WELLFORMED) == []


def test_validate_flags_a_miscounted_hunk():
    errors = validate_patch_hunks(_MALFORMED)
    assert errors, "expected a hunk-count error"
    assert "@@ -1,3 +1,3 @@" in errors[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/review/test_fixtures_wellformed.py -v`
Expected: FAIL — `ImportError: cannot import name 'validate_patch_hunks'`.

- [ ] **Step 3: Implement `validate_patch_hunks`**

Add to `src/framework_cli/review/evals.py` (top-level function; `import re` is already used elsewhere — add if missing):

```python
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def validate_patch_hunks(patch: str) -> list[str]:
    """Return a list of error strings for any unified-diff hunk whose declared
    line counts disagree with its body. An empty list means well-formed.

    Catches the truncation class: a `@@ -a,b +c,d @@` header where `b` != (context
    + removed) or `d` != (context + added) makes `git apply` silently truncate.
    """
    errors: list[str] = []
    lines = patch.splitlines()
    i = 0
    while i < len(lines):
        m = _HUNK_RE.match(lines[i])
        if not m:
            i += 1
            continue
        header = lines[i]
        old_decl = int(m.group(2)) if m.group(2) is not None else 1
        new_decl = int(m.group(4)) if m.group(4) is not None else 1
        i += 1
        ctx = rem = add = 0
        while i < len(lines):
            ln = lines[i]
            if ln.startswith("@@") or ln.startswith("--- ") or ln.startswith("+++ "):
                break
            if ln.startswith("\\"):  # "\ No newline at end of file"
                i += 1
                continue
            if ln.startswith("+"):
                add += 1
            elif ln.startswith("-"):
                rem += 1
            else:  # context (leading space) or a blank context line
                ctx += 1
            i += 1
        if ctx + rem != old_decl or ctx + add != new_decl:
            errors.append(
                f"{header}: declared (-{old_decl},+{new_decl}) but body has "
                f"old={ctx + rem}, new={ctx + add}"
            )
    return errors
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/review/test_fixtures_wellformed.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Stage (controller commits later in Task 3)**

```bash
git add src/framework_cli/review/evals.py tests/review/test_fixtures_wellformed.py
```

### Task 2: Suite-wide guard over every committed fixture

**Files:**
- Test: `tests/review/test_fixtures_wellformed.py` (append)

- [ ] **Step 1: Write the failing/guarding test**

Append:

```python
from pathlib import Path

import pytest

_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "tests" / "eval" / "fixtures"
_PATCHES = sorted(_FIXTURES_ROOT.glob("*/*/*/change.patch"))


def test_fixture_corpus_is_present():
    # Guard against a glob that silently matches nothing (e.g. a moved fixtures root).
    assert _PATCHES, f"no change.patch files found under {_FIXTURES_ROOT}"


@pytest.mark.parametrize("patch_path", _PATCHES, ids=lambda p: str(p.relative_to(_FIXTURES_ROOT)))
def test_fixtures_are_wellformed(patch_path: Path):
    errors = validate_patch_hunks(patch_path.read_text())
    assert errors == [], f"{patch_path} has malformed hunks: {errors}"
```

- [ ] **Step 2: Run the guard to see the current state**

Run: `uv run pytest tests/review/test_fixtures_wellformed.py -v`
Expected: PASS for well-formed fixtures; **FAIL for any fixture still carrying the truncation bug**. Record the failing fixtures — they are Task 3's worklist. (If all pass, Task 3 is a no-op confirmation.)

- [ ] **Step 3: Stage**

```bash
git add tests/review/test_fixtures_wellformed.py
```

### Task 3: Fix every malformed fixture, then commit Phase 0a

For each fixture flagged by Task 2's guard, regenerate its `change.patch` from a real render so the counts are correct ([[eval-fixtures-coupled-to-template]], [[template-payload-tdd-loop]]) — never hand-edit the counts.

**Files:**
- Modify: each flagged `tests/eval/fixtures/<agent>/<kind>/<case>/change.patch`

- [ ] **Step 1: For each flagged fixture, regenerate the patch**

Procedure (per fixture):
```bash
# 1. Render the fixture's battery combo into a scratch dir (read fixture.yaml `batteries`).
#    Use a tmp working dir on a disk-backed path to avoid the /tmp tmpfs trap:
export TMPDIR=/var/tmp
# 2. Apply the *intended* change by hand-editing the rendered file to match what the
#    fixture means to test (use the old change.patch as the intent reference).
# 3. Regenerate the patch from the real tree:
git -C <render_root> diff > tests/eval/fixtures/<agent>/<kind>/<case>/change.patch
```
The realized diff carries correct hunk counts by construction.

- [ ] **Step 2: Re-run the guard until green**

Run: `uv run pytest tests/review/test_fixtures_wellformed.py -v`
Expected: PASS for all fixtures.

- [ ] **Step 3: Confirm the fixtures still realize + the eval harness still loads them**

Run: `uv run pytest tests/review/test_fixture_realize.py tests/review/test_evals.py -q`
Expected: PASS (no regression in realization/scoring plumbing).

- [ ] **Step 4: Controller commits Phase 0a**

Update CLAUDE.md + meta-plan row first, then (separate calls):
```bash
git add tests/eval/fixtures CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```
```bash
git commit -m "test(plan21): fixture well-formedness guard + fix truncation class (Phase 0a)"
```

---

## Phase 0b — Good-fixture representativeness validation (Opus, quota)

The consistency oracle assumes each `good` fixture exhibits the codebase's *own* patterns. Validate that assumption and fix unrepresentative good fixtures before anchoring.

**File structure:**
- Create: `.framework/plan21/representativeness/<agent>.json` (per-agent verdict; gitignored scratch).
- Modify: unrepresentative `tests/eval/fixtures/<agent>/good/<case>/change.patch` (+ `fixture.yaml` if battery combo changes).

### Task 4: Audit good-fixture representativeness

**Files:**
- Create: `.framework/plan21/representativeness/<agent>.json`

- [ ] **Step 1: For each agent with a `good` fixture, dispatch an Opus subagent**

One subagent per agent (or a small Workflow fan-out). Each receives: the agent's `good` fixture(s) realized code (render the fixture's battery combo, apply the patch), and read/grep access to `src/framework_cli/template/`. Brief:

> Judge whether this `good` fixture's changed code mirrors a pattern the template itself actually uses (a representative clean example for `<agent>`'s domain), or whether it is arbitrary clean code that the agent would never plausibly see. Return JSON: `{"representative": bool, "reason": str, "suggested_pattern": str}`. If not representative, name the concrete template pattern the fixture should be re-authored to exhibit.

Write each verdict to `.framework/plan21/representativeness/<agent>.json` (skip-if-exists for resume).

- [ ] **Step 2: Collate the verdicts**

Run a quick read over `.framework/plan21/representativeness/*.json`; list every `representative: false`. That list is Task 5's worklist.

### Task 5: Fix unrepresentative good fixtures + commit Phase 0b

**Files:**
- Modify: each flagged `tests/eval/fixtures/<agent>/good/<case>/change.patch`

- [ ] **Step 1: Re-author each flagged good fixture**

Re-author to exhibit the named template pattern, regenerating the patch via render→edit→`git diff` (same procedure as Task 3 Step 1; `TMPDIR=/var/tmp`).

- [ ] **Step 2: Re-run the well-formedness guard + realization**

Run: `uv run pytest tests/review/test_fixtures_wellformed.py tests/review/test_fixture_realize.py -q`
Expected: PASS.

- [ ] **Step 3: Controller commits Phase 0b**

```bash
git add tests/eval/fixtures CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```
```bash
git commit -m "test(plan21): re-author unrepresentative good fixtures (Phase 0b)"
```

---

## Phase 0c — Baseline anchor (free backend, quota)

Run the fresh baseline on the now-correct + representative fixtures. This is the trustworthy evidence fed to Phase 1.

### Task 6: Run + commit the baseline scorecard

**Files:**
- Create: `docs/superpowers/eval-scorecards/2026-06-10-plan21-baseline/` (findings + scorecard).

- [ ] **Step 1: Run the full baseline sweep (resumable)**

```bash
export TMPDIR=/var/tmp
uv run framework eval --repeat 3 --backend subagent \
  --findings-out .framework/plan21/baseline-findings
```
Reviewers run on their own `spec.model` (do not override). If it aborts on `APIError` (quota), wait for reset and re-run the identical command — it resumes from the checkpoint.

- [ ] **Step 2: Produce the baseline scorecard**

```bash
uv run framework eval-analyze .framework/plan21/baseline-findings \
  --scorecard-dir docs/superpowers/eval-scorecards/2026-06-10-plan21-baseline
```
This writes `scorecard.md`, `thresholds.proposal.yaml`, `apply.md`, `meta.json`.

- [ ] **Step 3: Copy the per-finding evidence in for Phase 1**

The Phase 1 audit agents need the per-(agent,fixture,repeat) findings. Keep them with the scorecard:
```bash
cp -r .framework/plan21/baseline-findings docs/superpowers/eval-scorecards/2026-06-10-plan21-baseline/findings
```

- [ ] **Step 4: Controller commits the baseline**

```bash
git add docs/superpowers/eval-scorecards/2026-06-10-plan21-baseline CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```
```bash
git commit -m "docs(plan21): baseline scorecard on parity'd path (Phase 0c anchor)"
```

> **Natural merge checkpoint.** Phases 0a–0c are self-contained and low-risk (a new guard, cleaner fixtures, a committed baseline). They may be merged to `master` here before the heavier Phase 1+ work, or carried on the same branch — controller's call.

---

## Phase 1 — Prompt + fixture audit workflow (ultracode, Opus, file-backed)

**This phase is run as an ultracode Workflow** (explicit multi-agent orchestration). The Workflow is authored once (Task 7) and run/resumed (Task 8); the controller then sanity-checks against the Plan 18 regression checklist (Task 9).

**File structure:**
- Create: `docs/superpowers/specs/plan21-rubric-draft.md` — the draft shared rubric (input to the workflow; the workflow emits the finalized version).
- Create (scratch, gitignored): `.framework/plan21/audit/<agent>.json`, `.framework/plan21/synthesis/<n>.json`, `.framework/plan21/changelist.json`, `.framework/plan21/verdicts/<id>.json`.

### Task 7: Author the draft rubric + the Workflow script

**Files:**
- Create: `docs/superpowers/specs/plan21-rubric-draft.md`

- [ ] **Step 1: Write the draft shared rubric**

Author `docs/superpowers/specs/plan21-rubric-draft.md` with concrete starting content (the workflow refines it):

```markdown
# Shared reviewer rubric (draft — Plan 21)

Every `review-*` agent prompt inherits these rules.

## Severity (consistent across all agents)
- **high** — blocks a builder: a concrete, demonstrable defect that will cause incorrect
  behavior, data loss, a security/privacy breach, or a broken contract in the changed code.
- **medium** — should fix before merge but does not block: a real issue with a plausible
  path to harm, or a clear violation of an established project convention.
- **low** — advisory: style, minor clarity, or a non-urgent improvement.
- **info** — observation only; never implies an action is required.

## Codebase-bar principle
Do not hold new code to a stricter standard than the surrounding codebase already meets.
Before flagging a pattern, check whether the template/baseline already does the same thing
unflagged; if it does, do not flag the new instance.

## Internal consistency within one review
Apply one standard to every instance of a pattern you see in the same diff. If you do not
flag instance A, do not flag an identical instance B (the `create_item`/bulk-insert lesson).

## Scope discipline
Stay within this agent's domain (stated per-agent). Do not flag issues another agent owns.

## Output
Return JSON ONLY — an array of {"path","line","severity","message","suggestion"}; [] if none.
```

- [ ] **Step 2: Author the Workflow script (do not run yet)**

Write the script inline to the Workflow tool in Task 8. Its shape (pipeline-by-default, file-backed via agent-written outputs, batched adversarial). The literal `meta` + body is given in Task 8 Step 1 so the executor pastes it directly.

### Task 8: Run the audit Workflow (resumable)

- [ ] **Step 1: Invoke the Workflow**

Run the Workflow tool with this script (agents read inputs from disk and write outputs to disk so re-runs skip completed work; all judgment agents on Opus):

```javascript
export const meta = {
  name: 'plan21-reviewer-audit',
  description: 'Audit every review-agent prompt + fixtures, synthesize via judge panel, adversarially verify each proposed change',
  phases: [
    { title: 'Audit', detail: 'one Opus agent per prompt' },
    { title: 'Synthesis', detail: '3-way judge panel' },
    { title: 'Meta', detail: 'merge candidate syntheses' },
    { title: 'Adversarial', detail: 'refute each proposed change, batched' },
  ],
}

// args = { agents: ["accessibility", ...], baselineDir: "docs/.../findings", rubric: "docs/.../plan21-rubric-draft.md" }
const AGENTS = args.agents

phase('Audit')
const audits = await parallel(AGENTS.map(a => () =>
  agent(
    `You are auditing the prompt for review agent "${a}".\n` +
    `Read: src/framework_cli/review/agents/${a}.md (the prompt); its fixtures under ` +
    `tests/eval/fixtures/${a}/; its baseline per-finding evidence under ` +
    `${args.baselineDir} (filter to agent=${a}); and the draft rubric at ${args.rubric}.\n` +
    `Use read/grep over src/framework_cli/template/ to check the codebase-bar.\n` +
    `Report: severity-bar issues; scope-creep; hallucination/over-reach; ` +
    `stricter-than-codebase and internal-consistency violations; fixture-validity ` +
    `verdicts (is each good genuinely clean? each bad an unambiguous defect?); and ` +
    `proposed COUPLED prompt+fixture edits + a proposed block_threshold.\n` +
    `Write your JSON report to .framework/plan21/audit/${a}.json . If that file ` +
    `already exists with valid content, do nothing and report "cached".`,
    { label: `audit:${a}`, phase: 'Audit', model: 'opus' }
  )
)).then(r => r.filter(Boolean))

phase('Synthesis')
const panel = await parallel([1, 2, 3].map(n => () =>
  agent(
    `Synthesis judge #${n}. Read ALL per-agent audit reports under ` +
    `.framework/plan21/audit/*.json and the draft rubric at ${args.rubric}.\n` +
    `Produce ONE candidate consolidated changelist: reconcile severity bars ACROSS ` +
    `agents (flag where agent X calls a class high but agent Y calls it low), enforce ` +
    `scope boundaries, and propose a refined shared rubric.\n` +
    `Write your candidate to .framework/plan21/synthesis/${n}.json (skip if it exists).`,
    { label: `synthesis:${n}`, phase: 'Synthesis', model: 'opus' }
  )
)).then(r => r.filter(Boolean))

phase('Meta')
await agent(
  `Meta-synthesis. Read the 3 candidate syntheses under .framework/plan21/synthesis/*.json. ` +
  `Judge and MERGE them into ONE changelist: the finalized shared rubric, and per-agent ` +
  `{prompt_rewrite, fixture_edits, block_threshold, needs_second_good_fixture}. Base ` +
  `needs_second_good_fixture on which agents the baseline shows borderline-on-precision.\n` +
  `Write .framework/plan21/changelist.json (an array of per-change objects, each with a ` +
  `stable "id"). Write the finalized rubric to .framework/plan21/rubric.final.md.`,
  { label: 'meta-synthesis', phase: 'Meta', model: 'opus' }
)

phase('Adversarial')
// Read the changelist the meta agent wrote, then refute each change in batches of <=24.
const changelist = JSON.parse(await agent(
  `Read .framework/plan21/changelist.json and return its raw contents verbatim.`,
  { label: 'load-changelist', phase: 'Adversarial', model: 'opus' }
))
const BATCH = 24
for (let start = 0; start < changelist.length; start += BATCH) {
  const slice = changelist.slice(start, start + BATCH)
  await parallel(slice.map(c => () =>
    agent(
      `Adversarially REFUTE this proposed reviewer change (default to refuted=true if ` +
      `uncertain): ${JSON.stringify(c)}.\n` +
      `Argue concretely: does the rewrite now UNDER-flag a real defect class? Does a ` +
      `loosened bar let a bad fixture slip? Was it tuned against a dirty good fixture? ` +
      `Does a fixture edit make the bad case ambiguous? Verify against the actual files.\n` +
      `Return JSON {"id","refuted":bool,"reason"} and write it to ` +
      `.framework/plan21/verdicts/${c.id}.json (skip if it exists).`,
      { label: `refute:${c.id}`, phase: 'Adversarial', model: 'opus' }
    )
  ))
  log(`adversarial batch ${start}-${start + slice.length} of ${changelist.length} done`)
}
return { changelist: '.framework/plan21/changelist.json', verdicts: '.framework/plan21/verdicts/' }
```

Pass `args` = `{ agents: [...all registered agent tokens...], baselineDir: "docs/superpowers/eval-scorecards/2026-06-10-plan21-baseline/findings", rubric: "docs/superpowers/specs/plan21-rubric-draft.md" }`.

- [ ] **Step 2: On quota abort, resume**

If the run stops on quota, wait for reset and re-invoke (same session: `resumeFromRunId`; otherwise re-run — completed agents' output files are skipped). Confirm every `.framework/plan21/audit/*.json`, `synthesis/*.json`, `changelist.json`, and one `verdicts/*.json` per change exist before proceeding.

- [ ] **Step 3: Build the surviving changelist**

A change *ships* only if its verdict is `refuted: false`. List refuted changes with their reasons (these are kicked back for a human/next-round call — do NOT silently drop them). Record the surviving set + the kicked-back set in `.framework/plan21/changelist.vetted.json` (controller writes this by filtering).

### Task 9: Controller regression-checklist review

- [ ] **Step 1: Check the audit independently surfaced the known Plan 18 classes**

The Plan 18 paid defect classes (the controller's checklist — NOT fed to the auditors): `data-integrity` over-strict/internally-inconsistent on a clean bulk insert; `observability` per-endpoint-SLO over-reach; good-fixture over-flagging on `compliance`, `data-integrity`, `env-parity`, `observability`, `observability-infra`. Confirm the surviving changelist addresses each, or has an explicit reasoned verdict for why not. If a known class was missed entirely, re-run that agent's audit with the class named as a prompt (this is the only place the Plan 18 evidence enters, and only after the independent pass).

- [ ] **Step 2: Commit the workflow artifacts kept in-repo**

Keep the draft + final rubric and the vetted changelist summary in `docs/`:
```bash
cp .framework/plan21/rubric.final.md docs/superpowers/specs/plan21-rubric-final.md
git add docs/superpowers/specs/plan21-rubric-draft.md docs/superpowers/specs/plan21-rubric-final.md CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```
```bash
git commit -m "docs(plan21): audit workflow output — finalized rubric + vetted changelist (Phase 1)"
```

---

## Phase 2 — Apply + per-agent re-tune (subagent-driven)

For **each agent with a surviving change** in `.framework/plan21/changelist.vetted.json`, run the task below. The *content* of each edit is data — it comes from the changelist — but the procedure is fixed. Process one agent fully before the next (tight feedback loop).

### Task 10 (repeat per agent): Apply + re-tune one agent

**Files (per agent `<a>`):**
- Modify: `src/framework_cli/review/agents/<a>.md` (prompt rewrite + inherit the finalized rubric)
- Modify: `src/framework_cli/review/registry.py` (only if `block_threshold` changed for `<a>`)
- Modify/Create: `tests/eval/fixtures/<a>/...` (coupled fixture edits + any 2nd good fixture)

- [ ] **Step 1: Apply the prompt rewrite**

Edit `src/framework_cli/review/agents/<a>.md` to the changelist's `prompt_rewrite`, prepending/inheriting the finalized rubric's shared clauses. Keep the JSON-output contract intact.

- [ ] **Step 2: Apply coupled fixture edits**

Apply the changelist's `fixture_edits` for `<a>` (regenerate patches via render→edit→`git diff`, `TMPDIR=/var/tmp`). If `needs_second_good_fixture`, add a 2nd `good/<case>/` with `fixture.yaml` + `change.patch` exhibiting a second representative clean pattern.

- [ ] **Step 3: Apply any block_threshold change**

If the changelist sets a new `block_threshold` for `<a>`, update its `AgentSpec` in `src/framework_cli/review/registry.py`. **Advisory agents (documentation/dependency/usability) must stay advisory** — `_finalize_gate` skips `block_threshold is None` agents ([[flags-is-dual-use-gate-skips-advisory]]); do not give an advisory agent a blocking threshold.

- [ ] **Step 4: Re-run the well-formedness guard + this agent's eval**

```bash
uv run pytest tests/review/test_fixtures_wellformed.py -q
export TMPDIR=/var/tmp
uv run framework eval <a> --repeat 3 --backend subagent --findings-out .framework/plan21/retune-<a>
```
Expected: well-formedness PASS; the agent's `good` fixtures come back clean (low fp) and `bad` fixtures caught (recall up). If not, iterate the prompt/fixture (the `expect.json` is the test).

- [ ] **Step 5: Per-task review (Opus code-quality) + controller skip-marker commit**

Dispatch an Opus code-quality review of the prompt+fixture diff for `<a>` (scope: rubric-conformance, no scope-creep, fixture validity). Then controller commits past the gate via the skip-marker recipe ([[controller-skip-marker-recipe]]): write `.framework/audit/marker.json` from `framework gate-prepare`'s `staged_hash` (verdict PASS, drift false) as one `git add`+marker call, then `git commit` as a separate call:
```bash
git add src/framework_cli/review/agents/<a>.md tests/eval/fixtures/<a> src/framework_cli/review/registry.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```
```bash
git commit -m "refactor(review): retune <a> prompt+fixtures to shared rubric (Phase 2)"
```

---

## Phase 3 — Whole-set re-sweep, thresholds, branch-end review

### Task 11: Re-sweep + re-derive thresholds

**Files:**
- Modify: `tests/eval/fixtures/thresholds.yaml`
- Create: `docs/superpowers/eval-scorecards/2026-06-10-plan21-final/`

- [ ] **Step 1: Full re-sweep on the free backend**

```bash
export TMPDIR=/var/tmp
uv run framework eval --repeat 3 --backend subagent \
  --findings-out .framework/plan21/final-findings
```
(Resumable on quota abort.)

- [ ] **Step 2: Re-derive thresholds with margin**

```bash
uv run framework eval-analyze .framework/plan21/final-findings \
  --margin 0.10 \
  --scorecard-dir docs/superpowers/eval-scorecards/2026-06-10-plan21-final
```
Apply `thresholds.proposal.yaml` into `tests/eval/fixtures/thresholds.yaml`. **Re-derive every value — do not trust the carried-over provisional edits from `e365a29`.** Keep the comment convention (observed value + margin) and update the header history block.

- [ ] **Step 3: Spot-confirm on the paid backend (sparingly)**

Pick 2–3 agents that moved the most and confirm parity on paid:
```bash
uv run framework eval <agent> --repeat 3 --backend api --findings-out .framework/plan21/paid-spot-<agent>
```
Expected: free and paid land on the same pass/fail side of the re-derived thresholds (dev = prod). If they diverge, investigate before merge — that would be a parity regression.

- [ ] **Step 4: Full gate + commit**

```bash
export TMPDIR=/var/tmp
uv run pytest -q && uv run ruff check . && uv run mypy src
```
Expected: all green. Then commit:
```bash
git add tests/eval/fixtures/thresholds.yaml docs/superpowers/eval-scorecards/2026-06-10-plan21-final CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```
```bash
git commit -m "test(plan21): re-derive thresholds on parity'd path + final scorecard (Phase 3)"
```

### Task 12: Branch-end whole-branch review + merge

- [ ] **Step 1: Opus whole-branch review**

Dispatch an Opus final review of the entire branch diff (superpowers:requesting-code-review): rubric conformance across all prompts, no agent left internally inconsistent, fixtures genuinely good/bad, thresholds honestly derived (recall floors not propped up), advisory agents still advisory, no scope-creep. Address any findings (receiving-code-review skill).

- [ ] **Step 2: Verify release readiness ([[release-readiness-needs-render-not-local-gate]])**

The local gate misses ruff-format + template-payload mypy + generated-project drift. Confirm the render-matrix path is green (these changes are framework-source + fixtures, not template payload, but the CI review/agent-evals workflows exercise the agents):
```bash
git push -u origin plan-21-reviewer-tuning
# watch ci + render-matrix + review + agent-evals to green (poll by headSha, not --commit)
```

- [ ] **Step 3: Merge to `master`**

Fast-forward merge once CI is all-green; update the meta-plan row to ✅ Done with the FF SHA, and CLAUDE.md Current State. Per [[finishing-a-development-branch]], present merge options to the user rather than auto-merging.

---

## Self-review notes (author)

- **Spec coverage:** 0a guard+truncation → Tasks 1–3; 0b representativeness → Tasks 4–5; 0c anchor → Task 6; shared rubric → Task 7 (draft) + Task 8 Meta stage (final); fan-out/judge-panel/meta/adversarial → Task 8; Plan-18-as-checklist-not-input → Task 9; apply+retune → Task 10; thresholds-last + paid spot-confirm → Task 11; branch-end review → Task 12. All spec sections mapped.
- **Data-driven tasks:** Phase 2's edit *content* is produced by Phase 1 (it cannot be literal in the plan); the *procedure*, files, commands, and gates are fully concrete — not placeholders.
- **Type consistency:** `validate_patch_hunks(patch: str) -> list[str]` is referenced identically in Tasks 1, 2, 10. Eval commands use the confirmed real flags (`--repeat`, `--backend`, `--findings-out`, `eval-analyze --scorecard-dir --margin`).
