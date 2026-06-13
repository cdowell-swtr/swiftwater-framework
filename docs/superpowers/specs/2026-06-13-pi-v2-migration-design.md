# PI v2 Migration + gh-only Reference Re-pointing

**Date:** 2026-06-13
**Status:** Design (brainstorm approved; pending spec review → plan)
**Conventions:** PI `v2` (`cdowell-swtr/patterns` HEAD, `pi-convention-v2.md` @ `2c88543`) + MEMORY `v1` (tag `memory/v1`)
**PI task:** authored as `FWK10` (the framework's first task under v2)

## Purpose

Two coupled changes landed in the sibling `patterns` repo and both touch the framework:

1. **PI v2** — task IDs moved from the fixed `T` to a **per-repo uppercase prefix** (`<PFX>N`). The framework's reserved prefix is **`FWK`**. Migration is advisory; we do it now to minimize future migration workload while the instrument is small.
2. **The patterns repo is gh-only for consumers** — it is no longer a reliable local sibling on every machine, so the framework's 6 `../../patterns/…` convention references are broken. The fix (per the v2 runbook) is to **vendor** the convention files locally, pulled from GitHub.

A hotfix on patterns HEAD (not yet tagged) updated the access pattern to require the pointer in `AGENTS.md` **plus** an `@AGENTS.md` import in `CLAUDE.md` (Claude Code autoloads `CLAUDE.md`, not `AGENTS.md`), and to make **registration a PR** to the home repo. This plan follows the HEAD pattern.

This is a content/config migration, not feature code.

## Scope

**In scope:**
- **Vendor conventions** into the repo root: `pi-convention.md` (from patterns `main` HEAD) + `memory-convention.md` (from tag `memory/v1`), each with a provenance comment. Re-point all 6 `../../patterns/…` references to the local vendored copies.
- **PI v1→v2:** prefix `FWK`; rewrite `PLAN.md` IDs `T<n>`→`FWK<n>` (keep numbers; update `deps:`); append one migration remap note to `ACTION_LOG.md` (history NOT rewritten).
- **Pointer relocation:** new `AGENTS.md` with the v2 PI pointer block; `@AGENTS.md` import added to `CLAUDE.md`; the inline `<!-- PI-convention: v1 -->` "Planning Instrument" section removed from CLAUDE.md.
- **Register by PR** to `cdowell-swtr/patterns`: flip the framework's PI registry row `v1 / FWK (reserved)` → `v2 / FWK`; notify home.

**Out of scope (YAGNI):**
- **MEMORY stays v1** — only its *reference path* changes (vendored `memory-convention.md`), no version bump. Its GitHub registry row already reads `v1` and needs no change.
- **No template payload** (`src/framework_cli/template/` untouched). Generated projects don't get PI/MEMORY — that's the existing `FWK9` (PI+MEMORY into templates).
- **No commit-gate hook change** — the gate keys on the `PLAN.md`/`ACTION_LOG.md` filenames, which the ID rewrite does not change.
- **No renumbering from 1** — keep the original task numbers so historical `log:#` refs still line up.

## Decisions (from the approved brainstorm)

1. **Pointer location — option A:** `AGENTS.md` (canonical, `<!-- PI-convention: v2 -->`) **+** `@AGENTS.md` import in `CLAUDE.md` so Claude Code autoloads it. Matches the hotfixed runbook step 4.
2. **Convention re-pointing scope — both PI and MEMORY** (both broken by gh-only); vendor both. MEMORY is not version-bumped.
3. **Registration — by PR** to `cdowell-swtr/patterns` (hotfixed runbook step 7 "register by PR (recommended)"; SwiftwaterLib did this via PR #1). A reviewable single-line PR avoids the concurrent-edit collision a direct clone-edit can cause, and avoids a direct `git commit` against patterns master from our session.
4. **Pull source — patterns HEAD for PI** (`ref=main`) to capture the un-tagged `@AGENTS.md` hotfix; **tag `memory/v1` for MEMORY** (released, no pending hotfix). Record the exact source ref+SHA as a provenance comment in each vendored file for reproducibility despite a moving HEAD.

## Design

### Vendored conventions (repo root)

- `pi-convention.md` ← `gh api repos/cdowell-swtr/patterns/contents/pi-convention-v2.md?ref=main -H "Accept: application/vnd.github.raw"`, prepended with `<!-- vendored from cdowell-swtr/patterns pi-convention-v2.md @ <sha> (main HEAD, PI v2) on 2026-06-13 -->`.
- `memory-convention.md` ← same, from `...contents/memory-convention.md?ref=memory/v1`, provenance comment noting the tag.
- Re-point the 6 references to the bare root-relative names `pi-convention.md` / `memory-convention.md`:
  - `CLAUDE.md` (×3: the PI pointer — superseded by the AGENTS.md move; the "Keeping state current" line; the MEMORY block line)
  - `PLAN.md` preamble (×1), `ACTION_LOG.md` preamble (×1), `MEMORY.md` (×1)

### `AGENTS.md` (new)

```
<!-- PI-convention: v2 -->
## Planning Instrument
Read `PLAN.md` first. Maintain `PLAN.md` + `ACTION_LOG.md` at task grain as you
work (tick tasks; append a log entry on every completion and every deviation),
per `pi-convention.md`. Task IDs use this repo's prefix **`FWK`** (`FWK1, FWK2, …`).

Full working agreement & conventions: see `CLAUDE.md`.
```

### `CLAUDE.md`

- Remove the inline `<!-- PI-convention: v1 -->` "## Planning Instrument" section (its content is now in `AGENTS.md`).
- Add `@AGENTS.md` near the existing `@MEMORY.md` import so CC autoloads the pointer.
- Keep the "Source of truth: `PLAN.md` first" line.
- The "Keeping state current" line and the MEMORY block's convention reference switch from `../../patterns/…` to the vendored bare names.

### `PLAN.md`

- Preamble marker `PI-convention: v1` → `v2`; convention ref → vendored `pi-convention.md`.
- Rewrite IDs keeping numbers: `Next` `T3…T9` → `FWK3…FWK9`; `Done` `T1`→`FWK1` (`→ log:#0005`), `T2`→`FWK2` (`→ log:#0013`). `FWK9` `deps: FWK1, FWK2`.
- Add `FWK10` (this migration) to `Next` (top — done next), ticked to `Done` at close-out (`→ log:#0017`).

### `ACTION_LOG.md`

- Preamble convention ref → vendored `pi-convention.md` (+ note v2). The preamble is metadata, not a `#### #NNNN` event entry, so updating it does not violate append-only.
- Append `#0016 · note · 2026-06-13`: the T→FWK remap (`T1=FWK1 … T9=FWK9`); historical entries keep their `T`-form; the join holds via the remap.
- Append `#0017 · completed · FWK10 · 2026-06-13` at close-out.

### Registration PR (`cdowell-swtr/patterns`)

One-line change to `_docs/planning-instrument/implementers.md`: `| swiftwater-framework | … | v1 | FWK (reserved) | 2026-06-12 |` → `| swiftwater-framework | … | v2 | FWK | 2026-06-13 |`. Open via a branch + `gh pr create`. The MEMORY registry row already reads `v1` on GitHub HEAD — no change. Notify home to tick its rollout task.

## Verification

1. **Runbook compliance self-check** — the exact script from `adoption-runbook-v2.md` with `PFX=FWK`: pointer in `AGENTS.md`; `@AGENTS.md` in `CLAUDE.md`; the four PI files present; each task defined once; all `PLAN.md` task IDs use `FWK`; `log:#` refs resolve.
2. **No stale references** — `grep -rn "\.\./\.\./patterns" CLAUDE.md PLAN.md ACTION_LOG.md MEMORY.md AGENTS.md` returns nothing; no bare `T<n>` task IDs remain in `PLAN.md`.
3. **PI invariants** — IDs unique/monotonic/all-`FWK`; each task in PLAN xor archive; log IDs contiguous `#0001…#0017`; remap note present; LOG history unedited.
4. **gitleaks** clean (vendored markdown is public-safe); full quality gate (`ruff` / `ruff format --check` / `mypy src`) green; no template payload touched.

## Risks & notes

- **Vendoring from a moving HEAD** — the provenance comment (source ref + SHA) makes the exact vendored version reproducible/auditable even though `main` moves. Re-vendor when a later PI tag supersedes the hotfix.
- **Append-only respected** — only the `ACTION_LOG.md` *preamble* (metadata) and new entries are written; no historical `#### #NNNN` entry is edited.
- **Cross-repo PR, not a direct write** — registration is a reviewable PR to the home repo; the local-clone commit-gate gotcha does not apply.
- **`FWK10` recursion** — the migration task lives in the very `PLAN.md` it migrates; it is added under the new `FWK` scheme and closed out normally.
