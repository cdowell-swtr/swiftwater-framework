# PI v2 Migration + gh-only Re-pointing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the framework's Planning Instrument from v1 (`T` IDs) to v2 (`FWK` prefix), vendor the PI + MEMORY convention files locally (the patterns repo is now gh-only), relocate the PI pointer to `AGENTS.md` with a `@AGENTS.md` import in CLAUDE.md, and register the v2/FWK adoption by PR.

**Architecture:** A content/config migration, not feature code — concrete file edits + explicit verification (the runbook's compliance self-check), not failing-test-first TDD. Follows the hotfixed v2 access pattern on `cdowell-swtr/patterns` HEAD. Decisions from the approved spec `docs/superpowers/specs/2026-06-13-pi-v2-migration-design.md`: prefix `FWK`; vendor both conventions (PI from `main` HEAD, MEMORY from tag `memory/v1`); pointer in `AGENTS.md` + `@AGENTS.md` in CLAUDE.md; register by PR; keep task numbers; never rewrite log history.

**Tech Stack:** Markdown, `gh` CLI (GitHub Contents + Git-refs APIs for the cross-repo registration PR), git.

---

## Gate notes (read before executing)

- The commit-gate hook needs `PLAN.md` or `ACTION_LOG.md` staged; **stage `git add` and run `git commit` as SEPARATE tool calls** (chaining trips the hook before the add runs); keep the literal words `git`+`commit` out of `grep`/`echo` args. Each framework task below touches `PLAN.md`/`ACTION_LOG.md`, so the gate is satisfied naturally.
- **The registration (Task 3) is done entirely via `gh api`/`gh pr create` — no local `git commit` against the patterns repo** — so the cross-repo gate gotcha does not apply.
- **Append-only:** never edit an existing `#### #NNNN` log entry. Only the `ACTION_LOG.md` *preamble* (metadata) and new entries are written.

## File Structure

- **Create** `pi-convention.md`, `memory-convention.md` (root) — vendored convention copies with provenance comments.
- **Create** `AGENTS.md` (root) — canonical PI v2 pointer block.
- **Modify** `CLAUDE.md` — re-point convention refs; replace the inline PI section with `@AGENTS.md`; fix the `T1–T9` mention.
- **Modify** `PLAN.md` — preamble ref+marker → v2; rewrite IDs `T`→`FWK`; close out `FWK10`.
- **Modify** `ACTION_LOG.md` — preamble ref+marker → v2; append the remap note (`#0016`) and close-out (`#0017`).
- **Modify** `MEMORY.md` — re-point the convention ref.
- **Modify (patterns repo, via PR)** `_docs/planning-instrument/implementers.md` — flip our row to `v2 / FWK`.

---

### Task 1: Vendor the conventions + re-point references

**Files:**
- Create: `pi-convention.md`, `memory-convention.md`
- Modify: `CLAUDE.md`, `MEMORY.md`, `PLAN.md`, `ACTION_LOG.md`

- [ ] **Step 1: Vendor `pi-convention.md` from patterns `main` HEAD** (captures the un-tagged `@AGENTS.md` hotfix), with a provenance comment:

```bash
SHA=$(gh api "repos/cdowell-swtr/patterns/commits?path=pi-convention-v2.md&per_page=1" --jq '.[0].sha')
{ echo "<!-- vendored from cdowell-swtr/patterns pi-convention-v2.md @ ${SHA} (main HEAD, PI v2) on 2026-06-13; re-vendor when a later pi/v tag supersedes the hotfix -->"; echo; gh api "repos/cdowell-swtr/patterns/contents/pi-convention-v2.md?ref=main" -H "Accept: application/vnd.github.raw"; } > pi-convention.md
head -2 pi-convention.md
```
Expected: the provenance comment line, then the convention's `<!-- PI-convention: v2 -->` line.

- [ ] **Step 2: Vendor `memory-convention.md` from tag `memory/v1`** with provenance:

```bash
MSHA=$(gh api "repos/cdowell-swtr/patterns/commits?path=memory-convention.md&sha=memory/v1&per_page=1" --jq '.[0].sha')
{ echo "<!-- vendored from cdowell-swtr/patterns memory-convention.md @ ${MSHA} (tag memory/v1) on 2026-06-13 -->"; echo; gh api "repos/cdowell-swtr/patterns/contents/memory-convention.md?ref=memory/v1" -H "Accept: application/vnd.github.raw"; } > memory-convention.md
head -2 memory-convention.md
```
Expected: provenance comment, then `<!-- MEMORY-convention: v1 -->`.

- [ ] **Step 3: Re-point the surviving references** (the CLAUDE.md PI-section ref on its line 14 is NOT touched here — Task 2 deletes that whole section). Use the Edit tool for each:

`CLAUDE.md` — "Keeping state current" line:
- old: ``append an `ACTION_LOG.md` entry for every completion and every deviation, per `../../patterns/pi-convention.md`.``
- new: ``append an `ACTION_LOG.md` entry for every completion and every deviation, per `pi-convention.md`.``

`CLAUDE.md` — MEMORY block ref:
- old: ``When in doubt, native. Full rule + never-commit list in\n`../../patterns/memory-convention.md`.``  (the ref token only)
- replace ``../../patterns/memory-convention.md`` → ``memory-convention.md``

`MEMORY.md` — preamble ref:
- replace ``../../patterns/memory-convention.md`` → ``memory-convention.md``

`PLAN.md` — preamble (ref **and** version marker, both on the same line):
- old: ``> Maintained per `../../patterns/pi-convention.md` (PI-convention: v1).``
- new: ``> Maintained per `pi-convention.md` (PI-convention: v2).``

`ACTION_LOG.md` — preamble (ref **and** marker):
- old: ``> Maintained per `../../patterns/pi-convention.md` (PI-convention: v1).``
- new: ``> Maintained per `pi-convention.md` (PI-convention: v2).``

- [ ] **Step 4: Verify the two convention files are public-safe (no secrets) and refs are re-pointed**

Run: `/tmp/gitleaks detect --source . --redact --no-banner 2>&1 | tail -1` (reuse the binary from Plan 26; if absent, `curl -sSL https://github.com/gitleaks/gitleaks/releases/download/v8.21.2/gitleaks_8.21.2_linux_x64.tar.gz | tar -xz -C /tmp gitleaks`)
Expected: `no leaks found`.
Run: `grep -rn "patterns/pi-convention\|patterns/memory-convention" CLAUDE.md MEMORY.md ACTION_LOG.md; echo "rc=$?"`
Expected: only the CLAUDE.md line-14 PI-section ref remains (removed in Task 2); the MEMORY/PLAN/ACTION_LOG refs are gone.

- [ ] **Step 5: Commit**

```bash
git add pi-convention.md memory-convention.md CLAUDE.md MEMORY.md PLAN.md ACTION_LOG.md
git commit -m "feat(pi-v2): vendor PI+MEMORY conventions locally; re-point references"
```

---

### Task 2: PI v2 — pointer relocation + ID rewrite + remap note

**Files:**
- Create: `AGENTS.md`
- Modify: `CLAUDE.md`, `PLAN.md`, `ACTION_LOG.md`

- [ ] **Step 1: Create `AGENTS.md`** with exactly:

```markdown
<!-- PI-convention: v2 -->
## Planning Instrument
Read `PLAN.md` first. Maintain `PLAN.md` + `ACTION_LOG.md` at task grain as you
work (tick tasks; append a log entry on every completion and every deviation),
per `pi-convention.md`. Task IDs use this repo's prefix **`FWK`** (`FWK1, FWK2, …`).

Full working agreement & conventions: see `CLAUDE.md`.
```

- [ ] **Step 2: In `CLAUDE.md`, replace the inline PI section with the `@AGENTS.md` import.** Replace this block (the `<!-- PI-convention: v1 -->` heading through "Full history…"):

```
<!-- PI-convention: v1 -->
## Planning Instrument
Read `PLAN.md` first — it holds current state (Next + recent Done). As you work,
maintain `PLAN.md` + `ACTION_LOG.md` at task grain (tick tasks; append a log
entry on every completion and every deviation), per `../../patterns/pi-convention.md`.
Full history: git + the frozen meta-plan + `_archive/`.
```

with:

```
@AGENTS.md
```

- [ ] **Step 3: Fix the stale `T1–T9` mention in CLAUDE.md "Known follow-ups".** Replace:
- old: ``Open work is tracked as `PLAN.md` `Next` items (T1–T9); there are no standalone open follow-ups at present.``
- new: ``Open work is tracked as `PLAN.md` `Next` items (the repo's `FWK`-prefixed task IDs); there are no standalone open follow-ups at present.``

- [ ] **Step 4: Rewrite `PLAN.md` task IDs `T<n>` → `FWK<n>`** (keep numbers; covers `Next`, `Done`, and `deps:`):

```bash
sed -i -E 's/\bT([0-9]+)\b/FWK\1/g' PLAN.md
echo "--- remaining bare T-ids (expect none) ---"; grep -nE '\bT[0-9]+\b' PLAN.md || echo "NONE"
echo "--- task ids ---"; grep -oE '- \[[ x]\] FWK[0-9]+' PLAN.md
```
Expected: `NONE` remaining bare `T<n>`; task IDs show `FWK10, FWK3…FWK9` (Next) and `FWK2, FWK1` (Done). (The `sed` is safe: PLAN.md contains no other `T<digit>` tokens — SHAs and "Plan 24/28" don't match `\bT[0-9]`.)

- [ ] **Step 5: Append the migration remap note `#0016` to `ACTION_LOG.md`:**

```markdown

#### #0016 · note · 2026-06-13
Migrated task IDs T→FWK (PI v1→v2). Remap: T1=FWK1, T2=FWK2, T3=FWK3, T4=FWK4,
T5=FWK5, T6=FWK6, T7=FWK7, T8=FWK8, T9=FWK9, T10=FWK10. Historical log entries
above keep their T-form (append-only — never rewritten); the join holds via this
remap. New entries use FWK. (FWK10 = this migration; see
`docs/superpowers/plans/2026-06-13-pi-v2-migration.md`.)
```

- [ ] **Step 6: Verify the pointer relocation**

Run: `test -f AGENTS.md && grep -q "PI-convention: v2" AGENTS.md && grep -q "@AGENTS.md" CLAUDE.md && echo "OK: AGENTS.md + import"`
Expected: `OK: AGENTS.md + import`.
Run: `grep -c "PI-convention" CLAUDE.md`
Expected: `0` (the inline PI marker is gone; it now lives in AGENTS.md).

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md CLAUDE.md PLAN.md ACTION_LOG.md
git commit -m "feat(pi-v2): adopt FWK prefix; relocate pointer to AGENTS.md + @import"
```

---

### Task 3: Register the v2/FWK adoption by PR (gh API, no local commit)

The patterns repo is gh-only; register via a single-line PR to its registry, entirely through the GitHub API so no local `git commit` against patterns is needed.

**Files:**
- Modify (patterns repo, on a PR branch): `_docs/planning-instrument/implementers.md`

- [ ] **Step 1: Create a PR branch on the patterns repo from `main`:**

```bash
REPO=cdowell-swtr/patterns; BR=register-swiftwater-framework-v2
BASE_SHA=$(gh api repos/$REPO/git/ref/heads/main --jq .object.sha)
gh api --method POST repos/$REPO/git/refs -f ref="refs/heads/$BR" -f sha="$BASE_SHA" --jq .ref
```
Expected: `refs/heads/register-swiftwater-framework-v2`. (If it already exists, reuse it.)

- [ ] **Step 2: Fetch the registry file, flip our row, and PUT it on the branch:**

```bash
REPO=cdowell-swtr/patterns; BR=register-swiftwater-framework-v2; FILE=_docs/planning-instrument/implementers.md
FSHA=$(gh api "repos/$REPO/contents/$FILE?ref=main" --jq .sha)
gh api "repos/$REPO/contents/$FILE?ref=main" -H "Accept: application/vnd.github.raw" > /tmp/pi-impl.md
sed -i '/swiftwater-framework |/ s#| v1 | FWK (reserved) | 2026-06-12 |#| v2 | FWK | 2026-06-13 |#' /tmp/pi-impl.md
grep "swiftwater-framework |" /tmp/pi-impl.md   # confirm the row now reads: v2 | FWK | 2026-06-13
gh api --method PUT "repos/$REPO/contents/$FILE" \
  -f message="chore(pi): swiftwater-framework → PI v2 (FWK prefix)" \
  -f branch="$BR" -f sha="$FSHA" \
  -f content="$(base64 -w0 /tmp/pi-impl.md)" --jq .commit.sha
```
Expected: the `grep` shows `| swiftwater-framework | … | v2 | FWK | 2026-06-13 |`; the PUT returns a commit sha.

- [ ] **Step 3: Open the PR (notifies home to tick its rollout task):**

```bash
gh pr create --repo cdowell-swtr/patterns --base main --head register-swiftwater-framework-v2 \
  --title "Register swiftwater-framework: PI v2 (FWK prefix)" \
  --body "swiftwater-framework migrated to PI v2 (prefix FWK) per the v2 adoption runbook. Flips its registry row v1/FWK(reserved) → v2/FWK. Please tick the home rollout task + log. (No MEMORY change — already v1 on the registry.)"
```
Expected: a PR URL is printed. Record the PR number.

- [ ] **Step 4: Confirm the PR exists**

Run: `gh pr list --repo cdowell-swtr/patterns --head register-swiftwater-framework-v2 --json number,title`
Expected: one open PR.

(No framework commit in this task.)

---

### Task 4: Verify + close out FWK10

**Files:**
- Modify: `PLAN.md` (tick `FWK10` → Done), `ACTION_LOG.md` (append `#0017`)

- [ ] **Step 1: Run the v2 runbook compliance self-check** (`PFX=FWK`):

```bash
PFX=FWK
test -f AGENTS.md && grep -q "PI-convention:" AGENTS.md && echo "[OK] pointer in AGENTS.md" || echo "[FAIL] PI pointer must be in AGENTS.md"
grep -q "@AGENTS.md" CLAUDE.md && echo "[OK] CLAUDE.md autoloads AGENTS.md" || echo "[FAIL] add @AGENTS.md to CLAUDE.md"
for f in PLAN.md ACTION_LOG.md _archive/ARCHIVED_PLAN.md _archive/ARCHIVED_ACTION_LOG.md; do test -f "$f" || echo "[FAIL] missing $f"; done
grep -oE "^\s*- \[[ x]\] ${PFX}[0-9]+" PLAN.md | grep -oE "${PFX}[0-9]+" | sort | uniq -d | grep . && echo "[FAIL] task defined twice" || echo "[OK] each task once"
grep -oE "^\s*- \[[ x]\] [A-Za-z]+[0-9]+" PLAN.md | grep -vE "\] ${PFX}[0-9]+" && echo "[FAIL] task ID not using ${PFX}" || echo "[OK] all task IDs use ${PFX}"
comm -23 <(grep -oE 'log:#[0-9]+' PLAN.md | sed 's/log://' | sort -u) <(grep -oE '#[0-9]{4}' ACTION_LOG.md | sort -u) | grep . && echo "[FAIL] dangling log ref" || echo "[OK] log refs resolve"
```
Expected: all `[OK]` lines, no `[FAIL]`.

- [ ] **Step 2: Confirm no stale `../../patterns` references and no bare T-ids remain**

Run: `grep -rn "\.\./\.\./patterns" CLAUDE.md PLAN.md ACTION_LOG.md MEMORY.md AGENTS.md; echo "rc=$?"`
Expected: nothing printed (rc=1).
Run: `grep -nE '\bT[0-9]+\b' PLAN.md AGENTS.md || echo "NONE"`
Expected: `NONE`.

- [ ] **Step 3: Full quality gate (no regression)**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all clean. (No Python/template changes.)

- [ ] **Step 4: Tick `FWK10` → Done in `PLAN.md`** — remove `- [ ] FWK10 — …` from `Next`, add to `Done` (top):

```markdown
- [x] FWK10 — PI v2 migration + gh-only convention re-pointing  → log:#0017
```

- [ ] **Step 5: Append the close-out `#0017` to `ACTION_LOG.md`** (fill the PR number from Task 3):

```markdown

#### #0017 · completed · FWK10 · 2026-06-13
PI v2 migration complete: vendored pi-convention.md (patterns main HEAD) +
memory-convention.md (memory/v1) and re-pointed all references; adopted the FWK
prefix (T→FWK, numbers kept; remap #0016); relocated the PI pointer to AGENTS.md
with @AGENTS.md autoloaded by CLAUDE.md; registered v2/FWK by PR to
cdowell-swtr/patterns (PR #<N>). Runbook compliance self-check all-OK; gate green.
```

- [ ] **Step 6: Commit**

```bash
git add PLAN.md ACTION_LOG.md
git commit -m "docs(pi-v2): complete migration — close out FWK10"
```

---

## Notes for the executor

- **Review model policy:** doc/config-only → spec-compliance review = Sonnet; branch-end whole-branch review = **Opus**. No per-task code-quality review needed.
- **No template payload** — do not touch `src/framework_cli/template/`.
- **MEMORY stays v1** — only its reference path changed; do not bump its marker or registry row.
- **Branch:** `pi-v2-migration` (already created; spec committed there). Finish via `superpowers:finishing-a-development-branch` → PR → merge (clears `gate` + `build` + `render-complete` + `security`).
- **After merge:** the patterns registration PR (Task 3) is owned by the patterns CC to merge; the framework's adoption is complete regardless of when they merge it.
