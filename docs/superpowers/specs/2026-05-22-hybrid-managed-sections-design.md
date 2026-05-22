# Hybrid Managed-Section Integrity (Plan 6a-2) — Design Spec

**Date:** 2026-05-22
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 6a (framework integrity), `docs/superpowers/plans/2026-05-22-framework-integrity.md`. Roadmap row: Plan 6a-2 (a follow-on to 6a) in `docs/superpowers/plans/2026-05-20-meta-plan.md`. Realizes the **hybrid** file class of spec §17 (§702).

---

## 1. Purpose

Plan 6a shipped framework integrity for **locked** files (full-file checksum) and a gitignored **existence** tier, with the manifest schema already carrying a `cls` value of `locked | hybrid`. 6a-2 adds the **hybrid** class: files the builder is *expected* to extend, which carry a framework-owned region delimited by `FRAMEWORK:BEGIN` / `FRAMEWORK:END` markers. The delimited region is checksummed and tamper-evident; everything outside the markers is the builder's to edit freely. This protects framework guidance that fails **silently** when gutted — the TDD contract/conventions, the framework env-var contract, the framework task set — without locking files the builder must extend.

## 2. Scope & non-goals

**In scope — three files get hybrid integrity** (the cases where framework content is a naturally contiguous block):
- **`CLAUDE.md`** — the TDD contract + conventions (markers already present in the template).
- **`.env.example`** — the framework env-var contract.
- **`Taskfile.yml`** — the framework task set.

**Non-goals (deliberate):**
- **`pyproject.toml` is explicitly NOT covered.** Its framework content (the `[project.dependencies]` / `[dependency-groups]` arrays) is interleaved with content the builder *must* edit (`uv add` writes into `[project.dependencies]`), so it is not a lockable contiguous block. TOML has no include; PEP 621 forbids mixing static + dynamic for a field; the Hatchling dynamic-deps-from-file trick would break `uv add`. And pyproject breakage is **loud and self-correcting** (a removed dependency fails imports immediately), unlike the silent-failure content above — so it is both the hardest and the lowest-value to lock. Left builder-owned, by design.
- **No multiple regions per file.** Each hybrid file has exactly **one** contiguous `FRAMEWORK:BEGIN`…`FRAMEWORK:END` region. (Generalizing to N regions is unnecessary for these three files — YAGNI.)
- **No new drift mechanism.** Legitimate in-region edits use 6a's existing per-file `framework integrity --allow-drift <file>` (coarse but explicit and consistent with 6a).
- **No CI-side change.** Hybrid verification runs through the same `framework integrity` / `task integrity` paths as 6a; CI step-0 activation remains Plan 6b.

## 3. The marker model

A hybrid file contains **one** framework region delimited by marker lines whose comment syntax matches the file type:
- `CLAUDE.md` → `<!-- FRAMEWORK:BEGIN -->` … `<!-- FRAMEWORK:END -->`
- `.env.example`, `Taskfile.yml` → `# FRAMEWORK:BEGIN` … `# FRAMEWORK:END`

Markers are matched by the **tokens** `FRAMEWORK:BEGIN` / `FRAMEWORK:END` appearing on a line, so the extraction logic is comment-syntax-agnostic. The **section checksum** covers the text strictly **between** the marker lines (the markers themselves are structural delimiters, not content). Content **outside** the region is ignored by integrity — it is the builder's.

**Per-file region placement:**
- **`CLAUDE.md`** — already marked in the template (the contract + conventions block); builder area is `## Project notes` below `FRAMEWORK:END`. No marker change needed; only registration + checksumming.
- **`.env.example`** — wrap the existing framework guidance + vars (`APP_ENVIRONMENT`, the SLO thresholds, `APP_DATABASE_URL`) in one region; add a `# Your app's config below — the framework will not overwrite it.` line after `FRAMEWORK:END`.
- **`Taskfile.yml`** — `version:` and the `tasks:` key remain structural at top level; wrap the framework **task entries** in a region beginning immediately after `tasks:`; add a `# Add your project's tasks below — the framework will not overwrite them.` comment after `FRAMEWORK:END`. Builders add tasks below the marker (still under `tasks:`).

Per-project Jinja interpolation **inside** a region is fine: the checksum is computed per project at `framework new`, and `restore` re-renders with the project's recorded answers, so the section reproduces identically.

## 4. Engine changes

A new module `src/framework_cli/integrity/sections.py` (single responsibility), reused by generation, checker, and restore:
- `section_content(text: str) -> str | None` — text strictly between the BEGIN and END marker lines; `None` if markers are absent or unbalanced (not both present, or END before BEGIN).
- `section_span(text: str) -> tuple[int, int] | None` — the line span **inclusive** of both marker lines, for splicing during restore.

**Manifest** (`manifest.py`): no schema change. For a `cls: "hybrid"` entry, the existing `sha256` field holds the hash of the *extracted section*; `cls` tells the checker how to interpret it.

**Generation** (`generate.py` `build_manifest`): for a hybrid rule, read the rendered file, extract the section, hash it, store as `sha256` with `cls="hybrid"`. If a hybrid file has no/garbled markers at render time → `AuthoringError` (a framework authoring bug — the template should be marked). The §712 gitignore invariant continues to apply (hybrid files are tracked, not gitignored).

**Checker** (`checker.py` `check`), new hybrid branch (a tracked-tier entry with `cls == "hybrid"`):
- file missing → **fatal** "locked file is missing" (existing logic).
- markers missing/damaged → **fatal** "managed-section markers missing or damaged — `framework restore <file>`".
- `section_content` hash ≠ recorded `sha256` → **fatal** "framework-managed section altered — `framework restore <file>` (or `--allow-drift`)".
- otherwise no finding. Content outside the markers is never hashed.
- `drift` entries are skipped (existing logic).

**Restore** (`restore.py` `restore_file`), hybrid path: re-render the canonical file with the project's recorded answers (as in 6a); take the canonical file's inclusive `section_span`; locate the **project** file's inclusive `section_span` and replace it with the canonical span text, preserving everything outside. If the project file's markers are missing/damaged (can't locate the span) → raise `ValueError` with guidance (do **not** clobber builder content). Then refresh the entry's section hash + clear `drift` (as in 6a). Locked restore (full-file overwrite) is unchanged.

## 5. Registry & failure modes

`classes.py`: add `HYBRID_TRACKED: tuple[str, ...] = ("CLAUDE.md", ".env.example", "Taskfile.yml")` (rendered paths); `rules()` yields each as `Rule(path, "hybrid", "tracked")`. The existing authoring tests extend automatically: "every registered path renders" and "no registered path is gitignored" now also cover the hybrid files.

Failure modes (all carry `framework restore <file>` guidance, all fatal): section altered; markers missing/damaged; whole file missing. The one-directional-coverage limitation documented in 6a (a *new* framework file isn't auto-detected as unregistered) is unchanged.

## 6. Testing

- **Unit** `tests/integrity/test_sections.py`: `section_content` returns the between-markers text; `None` on missing/unbalanced markers; `section_span` returns the correct inclusive bounds.
- **generate**: a hybrid entry records a section hash (≠ the full-file hash); `AuthoringError` when a hybrid file lacks markers.
- **checker** (the heart): hybrid clean → no findings; edit **inside** the block → fatal; edit **outside** the block (builder area) → **clean** (defines hybrid; satisfies the spec §20 "edit outside a managed section → pass" case); markers deleted → fatal.
- **restore**: rewrites the block and **preserves** outside content (builder edits outside survive); damaged markers → `ValueError`.
- **Template-payload validation** (we modify `.env.example` + `Taskfile.yml`): the existing acceptance suite must stay green — the freshly generated project still makes a **clean first pre-commit pass**, and `task` still parses the rendered `Taskfile.yml` (the `#` markers are valid YAML comments). A render-assertion confirms all three files carry the markers.
- **Acceptance** (no Docker): render a project + write the manifest; edit CLAUDE.md **inside** the block → `check` fatal; edit the `## Project notes` area → `check` clean; `restore_file` fixes the block while keeping the project notes.

## 7. Self-review

- **Placeholders:** none — every decision (scope = 3 files, pyproject excluded with rationale, one region per file, reuse `sha256`, restore-errors-on-damaged-markers, per-file drift) is settled.
- **Internal consistency:** the checksum is over the between-markers content while restore splices the inclusive span — consistent because the marker lines are constant (and re-rendered identically), so replacing the inclusive span restores the same between-markers content the hash expects.
- **Scope:** one cohesive subsystem (the hybrid class), additive on 6a's engine; no schema change; `pyproject` explicitly out.
- **Ambiguity:** the three failure modes (altered / damaged markers / missing file) and the builder-content-preserving restore are stated explicitly.

---

*End of design. Next step (when ready): `superpowers:writing-plans` to produce the Plan 6a-2 implementation plan.*
