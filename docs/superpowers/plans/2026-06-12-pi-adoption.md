# Plan 25 — Adopt the Planning Instrument Convention — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the framework's live planning state out of the bloated CLAUDE.md "Current State" essay and the 177-line dated meta-plan into the PI convention's four root artifacts (`PLAN.md`, `ACTION_LOG.md`, `_archive/`), slim CLAUDE.md to a stable Working Agreement + PI pointer, re-target the commit-gate hook, and self-register as a PI adopter.

**Architecture:** PI (`PI-convention: v1`, from `../../patterns/pi-convention.md`) is a copy-by-hand markdown convention — git + markdown only, no tool/binary/validator. The framework is a *consumer*. This is a content + config migration, not feature code, so tasks use concrete file content + explicit verification commands rather than failing-test-first TDD (there is no unit to test). Decisions are from the approved spec `docs/superpowers/specs/2026-06-12-pi-adoption-design.md`, all brainstorm option **A**: archive-wholesale + fresh log; fresh monotonic `T`-IDs for open work only with "Plan N" kept in titles; freeze the meta-plan in place; lenient hook (`PLAN.md` *or* `ACTION_LOG.md`); agent-upheld (no validator test).

**Tech Stack:** Markdown, `.claude/settings.json` (Claude Code PreToolUse hook), git (two repos: swiftwater-framework + the sibling patterns repo).

---

## Bootstrap-ordering note (read before executing)

There is a deliberate sequencing constraint, because this plan changes the very gate that guards its own commits:

- The **live** commit-gate hook currently blocks `git commit` unless **`CLAUDE.md`** is staged. Editing `.claude/settings.json` mid-session does **not** reload the hook — the old (CLAUDE.md) gate stays live for the rest of this session.
- Therefore **every framework commit in this plan also stages `CLAUDE.md`** (each framework task below genuinely edits CLAUDE.md), which satisfies the still-live old gate regardless of when the re-target takes effect. The new lenient (`PLAN.md`|`ACTION_LOG.md`) gate governs *future* sessions.
- The **second** PreToolUse hook (`reviewers-gate-check.sh`) runs `framework gate`, which **degrades skip-neutral when no AI review backend is enabled** (no `ANTHROPIC_*` key) — so these doc/config-only commits are never blocked by it. No skip-marker needed.

## File Structure

- **Create** `PLAN.md` (root) — current state only: `Next` + recent `Done`.
- **Create** `ACTION_LOG.md` (root) — append-only event narrative, seeded `#0001`.
- **Create** `_archive/ARCHIVED_PLAN.md` — thin pointer to the frozen meta-plan.
- **Create** `_archive/ARCHIVED_ACTION_LOG.md` — header-only stub.
- **Modify** `CLAUDE.md` — drop the Current State essay; reword "Keeping state current"; repoint "Source of truth"; add the PI pointer block.
- **Modify** `docs/superpowers/plans/2026-05-20-meta-plan.md` — prepend a FROZEN tombstone header (content otherwise untouched).
- **Modify** `.claude/settings.json` — re-target the inline CLAUDE.md gate to `PLAN.md`|`ACTION_LOG.md`.
- **Modify (patterns repo)** `~/Claude Code/Projects/patterns/_docs/planning-instrument/implementers.md` — append the framework's adopter row.

---

### Task 1: Scaffold the four PI artifacts + slim CLAUDE.md

Combined into one commit by the bootstrap constraint: moving Current State *out of* CLAUDE.md and *into* PLAN.md is a single atomic migration, and the commit must stage CLAUDE.md to pass the live gate.

**Files:**
- Create: `PLAN.md`, `ACTION_LOG.md`, `_archive/ARCHIVED_PLAN.md`, `_archive/ARCHIVED_ACTION_LOG.md`
- Modify: `CLAUDE.md` (remove the `## Current State` section; add the PI pointer block)

- [ ] **Step 1: Create `PLAN.md`** with exactly this content:

```markdown
# PLAN — swiftwater-framework

> Current state only (Next + recent Done). Full history: git + the frozen
> meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) + `_archive/`.
> Maintained per `../../patterns/pi-convention.md` (PI-convention: v1).

## Next
- [ ] T1 — Plan 25: adopt the PI convention (this plan)  → docs/superpowers/plans/2026-06-12-pi-adoption.md
- [ ] T2 — Plan 26: adopt the Committed Memory convention — migrate the public-safe project subset of the native store  deps: T1
- [ ] T3 — Plan 22c: per-agent reviewer reference docs (the 19 reviewers; retire the two promissory notes in working/review-system.md)
- [ ] T4 — Plan 23: agent self-improvement tooling (capture the Plan 21 audit→synthesis→adversarial method as repeatable tooling)
- [ ] T5 — Plan 27: refactor the review/eval engine onto LiteLLM (re-target SubagentBackend as an in-process claude -p CustomLLM provider)
- [ ] T6 — Plan 29: data-store runtime parity (services.yml/dev.yml; unblock the hardcoded co-located-container assumption)
- [ ] T7 — Plan 30: full reverse integrity-coverage check + 23-file battery-infra classification  deps: consumes INTENTIONALLY_UNLOCKED (shipped v0.2.4)
- [ ] T8 — Traefik docker-provider acceptance coverage (the gap that hid the v3.1 → Docker 27 `task dev` break)
- [ ] T9 — Propagate the PI + MEMORY conventions into generated projects (template payload)  deps: T1, T2

## Done
- (recent pre-adoption milestones — no PI task IDs; full record in the frozen meta-plan)
  Plan 28: lock-taxonomy + task doctor + Traefik fix (v0.2.4, `3f166dc`/`da7ea65`); Plan 24: framework upgrade (v0.2.3, `bb31bac`).
```

(T1 is ticked into the PI-tracked `Done` list by Task 5.)

- [ ] **Step 2: Create `ACTION_LOG.md`** with exactly this content:

```markdown
# ACTION_LOG — swiftwater-framework

> Append-only event narrative, task grain. Never edit or truncate existing
> entries. Closed taxonomy: completed · inserted · reordered · dep-found ·
> amended · superseded · discarded · milestone · note.
> Maintained per `../../patterns/pi-convention.md` (PI-convention: v1).

#### #0001 · note · 2026-06-12
Adopted the Planning Instrument convention (PI-convention: v1). Scaffolded
`PLAN.md` + `ACTION_LOG.md` + `_archive/`; migrated live planning state out of
CLAUDE.md's Current State essay and the dated meta-plan into `PLAN.md` (current
state only) and slimmed CLAUDE.md to the Working Agreement + a PI pointer.
Archive-wholesale + fresh log — no back-dated reconstruction; pre-adoption
history stays in git + the frozen meta-plan. Open work re-keyed to fresh
monotonic T-IDs (T1–T9), with the legacy "Plan N" preserved in each title.
```

- [ ] **Step 3: Create `_archive/ARCHIVED_PLAN.md`** with exactly this content:

```markdown
# Archived Plan

> Per PI ("relocation, not duplication"), full historical plan content is **not
> copied here**. The complete pre-adoption record of plans through v0.2.4 lives,
> intact and frozen, in `../docs/superpowers/plans/2026-05-20-meta-plan.md`.
> Git history is the authoritative timeline.
```

- [ ] **Step 4: Create `_archive/ARCHIVED_ACTION_LOG.md`** with exactly this content:

```markdown
# Archived Action Log

> Overflow for old `ACTION_LOG.md` sections. Empty until the live log grows large
> enough to roll entries off. Append-only; never truncate.
```

- [ ] **Step 5: Slim `CLAUDE.md`** — remove the entire `## Current State` section (the `>` blockquote line plus all of its bullet list: "Last updated", "Where we are", "Env parity", "Model facts", "Reviewer system"). Replace the removed section with the PI pointer block:

```markdown
<!-- PI-convention: v1 -->
## Planning Instrument
Read `PLAN.md` first — it holds current state (Next + recent Done). As you work,
maintain `PLAN.md` + `ACTION_LOG.md` at task grain (tick tasks; append a log
entry on every completion and every deviation), per `../../patterns/pi-convention.md`.
Full history: git + the frozen meta-plan + `_archive/`.
```

Leave the "Env parity (this box)", "Model facts", and "Reviewer system" operational notes that were in Current State by moving them verbatim into the Working-Agreement body — append them as a short `## Operating environment` section after the PI pointer (they are durable working-agreement facts, not transient state):

```markdown
## Operating environment
- **Env parity (this box, Ubuntu/WSL2):** native Linux Node 22 + docker buildx + shellcheck (`~/.local/bin`); dind works under `--privileged` + `--storage-driver=vfs`. `/tmp` is RAM tmpfs (16 GB), `/` ext4 936 GB. Docker acceptance tier is host-UID clean. Second machine (laptop) for reviewer eval/audit: `docs/maintenance/laptop-dev-parity.md`.
- **Model facts:** Opus 4.8 = `claude-opus-4-8` (agentic); Sonnet 4.6 = `claude-sonnet-4-6` (bundle default); Haiku 4.5 = `claude-haiku-4-5-20251001`.
- **Reviewer system = source of truth for review state:** commit history, agent prompts under `src/framework_cli/review/agents/`, calibrated `tests/eval/fixtures/thresholds.yaml`, dated scorecards under `docs/superpowers/eval-scorecards/`.
```

- [ ] **Step 6: Verify the artifacts exist and are well-formed**

Run: `ls -1 PLAN.md ACTION_LOG.md _archive/ARCHIVED_PLAN.md _archive/ARCHIVED_ACTION_LOG.md && grep -c '^- \[ \] T' PLAN.md`
Expected: all four paths listed; the `grep -c` prints `9` (T1–T9 in Next).

- [ ] **Step 7: Verify CLAUDE.md no longer carries transient state**

Run: `grep -n 'Last updated' CLAUDE.md; grep -c 'PI-convention: v1' CLAUDE.md`
Expected: no "Last updated" line remains; the `grep -c` prints `1`.

- [ ] **Step 8: Commit** (stage CLAUDE.md to satisfy the live gate; see bootstrap note)

```bash
git add PLAN.md ACTION_LOG.md _archive/ARCHIVED_PLAN.md _archive/ARCHIVED_ACTION_LOG.md CLAUDE.md
git commit -m "feat(plan-25): scaffold PI artifacts; migrate state out of CLAUDE.md"
```

---

### Task 2: Freeze the dated meta-plan + repoint CLAUDE.md "Source of truth"

**Files:**
- Modify: `docs/superpowers/plans/2026-05-20-meta-plan.md` (prepend tombstone only)
- Modify: `CLAUDE.md` ("Source of truth" list + "Known follow-ups" pointer)
- Modify: `PLAN.md` (no change yet) / `ACTION_LOG.md` (append `#0002`)

- [ ] **Step 1: Prepend the FROZEN tombstone** to `docs/superpowers/plans/2026-05-20-meta-plan.md` as the very first lines (before `# Framework Build — Meta-Plan / Roadmap`):

```markdown
> **FROZEN — historical record (PI adoption, 2026-06-12).** Live planning state
> moved to `/PLAN.md` + `/ACTION_LOG.md` per the Planning Instrument convention
> (`pi-convention.md` in the sibling `patterns` repo).
> This file is no longer updated; it is preserved intact as the detailed record of
> plans through v0.2.4. Do not edit. One forward plan was recorded after the
> freeze: "Propagate PI + MEMORY into generated projects (template payload)" —
> tracked as `/PLAN.md` T9.

```

Do not modify any other line of the meta-plan.

- [ ] **Step 2: Repoint CLAUDE.md "Source of truth"** — replace the existing block:

```markdown
**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.
```

with:

```markdown
**Source of truth:**
- Current state / what's next: `PLAN.md` (+ `ACTION_LOG.md` for history) — read first.
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap (FROZEN historical record through v0.2.4): `docs/superpowers/plans/2026-05-20-meta-plan.md`
```

- [ ] **Step 3: Repoint the CLAUDE.md "Known follow-ups" pointer** — in the `## Known follow-ups` section, replace any "meta-plan status table" phrasing that implies the meta-plan is live with: "their record of record is `PLAN.md` (open work) plus the FROZEN meta-plan status table and the FF SHAs in git." Leave the rest of the section intact.

- [ ] **Step 4: Append the log entry** `#0002` to `ACTION_LOG.md`:

```markdown

#### #0002 · note · 2026-06-12
Froze the dated meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) in
place with a tombstone header and repointed CLAUDE.md's "Source of truth" at
`PLAN.md`. `_archive/ARCHIVED_PLAN.md` points to the frozen file rather than
copying it (relocation, not duplication).
```

- [ ] **Step 5: Verify the freeze**

Run: `head -1 docs/superpowers/plans/2026-05-20-meta-plan.md; grep -c 'FROZEN' docs/superpowers/plans/2026-05-20-meta-plan.md CLAUDE.md`
Expected: first line is the `> **FROZEN …` tombstone; both files report ≥1 match.

- [ ] **Step 6: Commit** (CLAUDE.md staged → live gate satisfied)

```bash
git add docs/superpowers/plans/2026-05-20-meta-plan.md CLAUDE.md ACTION_LOG.md
git commit -m "docs(plan-25): freeze the dated meta-plan; repoint CLAUDE.md at PLAN.md"
```

---

### Task 3: Re-target the commit-gate hook + reword "Keeping state current"

**Files:**
- Modify: `.claude/settings.json` (inline CLAUDE.md gate command + statusMessage)
- Modify: `CLAUDE.md` (`## Keeping state current` section)
- Modify: `ACTION_LOG.md` (append `#0003`)

- [ ] **Step 1: Confirm no automated test asserts the old gate string**

Run: `grep -rIn "stage it (git add CLAUDE.md)" tests; grep -rIn "diff --cached" tests`
Expected: no hits referencing the framework's own gate (the `tests/` CLAUDE.md hits are about the *template's* rendered CLAUDE.md, not `.claude/settings.json`). If any test asserts the old string, update it in this task.

- [ ] **Step 2: Re-target the inline gate** in `.claude/settings.json` — in the first `PreToolUse` hook, replace the `command` value's CLAUDE.md check. Change this fragment:

```
git -C "$root" diff --cached --name-only 2>/dev/null | grep -qx 'CLAUDE.md' && exit 0; echo 'Commit blocked: update the Current State pointer in CLAUDE.md and stage it (git add CLAUDE.md) before committing.' >&2; exit 2
```

to:

```
git -C "$root" diff --cached --name-only 2>/dev/null | grep -qxE 'PLAN\.md|ACTION_LOG\.md' && exit 0; echo 'Commit blocked: update PLAN.md (tick the task; append to ACTION_LOG.md as needed) and stage it before committing.' >&2; exit 2
```

And change that hook's `statusMessage` from `"Checking CLAUDE.md is current before commit"` to `"Checking PLAN.md/ACTION_LOG.md is current before commit"`.

- [ ] **Step 3: Reword the CLAUDE.md `## Keeping state current` section** — replace its body with:

```markdown
## Keeping state current (required before every commit)

Before every commit, update `PLAN.md` (tick the task; move finished items to
`Done`) and append an `ACTION_LOG.md` entry for every completion and every
deviation, per `../../patterns/pi-convention.md`. A `PreToolUse` hook in
`.claude/settings.json` enforces this — it blocks `git commit` until `PLAN.md`
or `ACTION_LOG.md` is staged. Run `/hooks` to review or disable it.
```

- [ ] **Step 4: Verify the new gate command parses and matches the right files**

Run: `python3 -c "import json; json.load(open('.claude/settings.json')); print('settings.json valid')"`
Then dry-run the matcher logic against a sample staged set:
Run: `printf 'PLAN.md\n' | grep -qxE 'PLAN\.md|ACTION_LOG\.md' && echo MATCH-PLAN; printf 'CLAUDE.md\n' | grep -qxE 'PLAN\.md|ACTION_LOG\.md' || echo NOMATCH-CLAUDE`
Expected: `settings.json valid`, then `MATCH-PLAN` and `NOMATCH-CLAUDE` (the new gate accepts PLAN.md, no longer accepts CLAUDE.md alone).

- [ ] **Step 5: Append the log entry** `#0003` to `ACTION_LOG.md`:

```markdown

#### #0003 · amended · 2026-06-12
Re-targeted the commit-gate PreToolUse hook in `.claude/settings.json` from
"CLAUDE.md staged" to the lenient "PLAN.md or ACTION_LOG.md staged", and reworded
CLAUDE.md's "Keeping state current" section to match. Note: settings.json hook
edits do not reload mid-session, so the new gate governs future sessions.
```

- [ ] **Step 6: Commit** (CLAUDE.md is edited in Step 3, so it is staged → live old gate still satisfied)

```bash
git add .claude/settings.json CLAUDE.md ACTION_LOG.md
git commit -m "feat(plan-25): re-target commit-gate hook to PLAN.md|ACTION_LOG.md"
```

---

### Task 4: Self-register in the patterns PI implementer registry (cross-repo)

This is a commit in the **separate patterns repo** — the framework's commit-gate hook does not apply there.

**Files:**
- Modify (patterns repo): `~/Claude Code/Projects/patterns/_docs/planning-instrument/implementers.md`
- Optionally modify (patterns repo): `~/Claude Code/Projects/patterns/PLAN.md` (tick T4), `ACTION_LOG.md`

- [ ] **Step 1: Append the adopter row** to the patterns registry table (after the existing `meridian` row):

```
| swiftwater-framework | ~/Claude Code/Projects/framework/swiftwater-framework | v1 | 2026-06-12 |
```

- [ ] **Step 2: Close the loop in the patterns PLAN** (courtesy) — in `~/Claude Code/Projects/patterns/PLAN.md`, tick `T4` from `- [ ]` to `- [x]` and move it to `Done` with `→ log:#0007`; append to the patterns `ACTION_LOG.md`:

```markdown

#### #0007 · completed · T4 · 2026-06-12
swiftwater-framework adopted the PI convention (v1) via the pull model and
registered in the implementer registry.
```

(If the patterns repo has its own commit gate, staging its `PLAN.md`/`ACTION_LOG.md` here satisfies it.)

- [ ] **Step 3: Verify the registry row**

Run: `grep -c 'swiftwater-framework' ~/"Claude Code/Projects/patterns/_docs/planning-instrument/implementers.md"`
Expected: `1`.

- [ ] **Step 4: Commit in the patterns repo**

```bash
cd ~/"Claude Code/Projects/patterns"
git add _docs/planning-instrument/implementers.md PLAN.md ACTION_LOG.md
git commit -m "chore(pi): register swiftwater-framework as a PI adopter (T4)"
cd -
```

---

### Task 5: Final verification + close out T1

**Files:**
- Modify: `PLAN.md` (tick T1 → Done), `ACTION_LOG.md` (append `#0004`)

- [ ] **Step 1: Run the full quality gate** (framework source unaffected, but confirm nothing regressed)

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all clean. (Markdown/JSON changes do not touch Python, so `pytest` is not required for correctness here; run `uv run pytest -q tests/integrity -q` if you want to confirm integrity tests are unaffected.)

- [ ] **Step 2: Grep for stale references to the removed Current State**

Run: `grep -rIn "Current State" CLAUDE.md; grep -rIn "update the Current State pointer" . --include=*.md --include=*.json | grep -v docs/superpowers/plans/2026-05-20-meta-plan.md | grep -v docs/superpowers/specs/ | grep -v _archive`
Expected: no live (non-frozen, non-spec, non-archive) reference instructs updating a "Current State" in CLAUDE.md.

- [ ] **Step 3: Manually confirm PI invariants** — eyeball `PLAN.md` + `ACTION_LOG.md`:
  - Task IDs T1–T9 unique + monotonic; each task in `PLAN.md` exactly once (Next xor Done).
  - Log IDs `#0001`–`#0004` unique + contiguous (framework repo).
  - Every `deps:` (`T1`, `T2`) resolves to a real task.
  - Every event `type` is in the closed taxonomy.

- [ ] **Step 4: Tick T1 → Done** — in `PLAN.md`, remove `- [ ] T1 — Plan 25 …` from `Next` and add to `Done`:

```markdown
- [x] T1 — Plan 25: adopt the PI convention  → log:#0004
```

- [ ] **Step 5: Append the closing log entry** `#0004` to `ACTION_LOG.md`:

```markdown

#### #0004 · completed · T1 · 2026-06-12
Plan 25 complete: PI convention adopted — four artifacts scaffolded, CLAUDE.md
slimmed, meta-plan frozen, commit-gate hook re-targeted, framework registered as
a PI adopter. Quality gate green; PI invariants confirmed. Plan 26 (Committed
Memory) is next.
```

- [ ] **Step 6: Commit**

```bash
git add PLAN.md ACTION_LOG.md
git commit -m "docs(plan-25): complete PI adoption — close out T1"
```

(This final commit stages `PLAN.md`/`ACTION_LOG.md` — it passes under *either* gate version, so it is the clean handoff to the new lenient gate.)

---

## Notes for the executor

- **Review model policy** (per the working agreement): this plan is doc/config-only, so spec-compliance review = Sonnet and the branch-end whole-branch review = Opus. There is no app/template code, so no per-task code-quality review is required beyond the branch-end Opus pass.
- **No template payload changes** — do not touch `src/framework_cli/template/`. Generated projects are out of scope (that is the recorded T9 future plan).
- **Branch:** work continues on `plan-25-adopt-pi` (already created; the brainstorm spec is committed there). Finish via `superpowers:finishing-a-development-branch` → PR → merge (clears `gate` + `build` + `render-complete`).
