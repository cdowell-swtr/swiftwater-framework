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

#### #0002 · note · 2026-06-12
Froze the dated meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) in
place with a tombstone header and repointed CLAUDE.md's "Source of truth" at
`PLAN.md`. `_archive/ARCHIVED_PLAN.md` points to the frozen file rather than
copying it (relocation, not duplication).

#### #0003 · amended · 2026-06-12
Re-targeted the commit-gate PreToolUse hook in `.claude/settings.json` from
"CLAUDE.md staged" to the lenient "PLAN.md or ACTION_LOG.md staged", and reworded
CLAUDE.md's "Keeping state current" section to match. Note: settings.json hook
edits do not reload mid-session, so the new gate governs future sessions.
(Correction observed during execution: the hook re-reads settings.json per
invocation, so the new gate went live immediately; it checks the session cwd's
repo, so cross-repo commits need this repo's PLAN.md/ACTION_LOG.md staged.)

#### #0004 · note · 2026-06-12
Self-registered swiftwater-framework as a PI adopter: appended the adopter row to
the patterns repo's `_docs/planning-instrument/implementers.md` and ticked its T4.
Cross-repo commit made from this session.

#### #0005 · completed · T1 · 2026-06-12
Plan 25 complete: PI convention adopted — four artifacts scaffolded, CLAUDE.md
slimmed, meta-plan frozen, commit-gate hook re-targeted, framework registered as
a PI adopter. Quality gate green (ruff/format/mypy); PI invariants confirmed.
Plan 26 (Committed Memory) is next.

#### #0006 · note · 2026-06-13
T2 (Plan 26, Committed Memory) brainstormed; spec written
(`docs/superpowers/specs/2026-06-13-committed-memory-adoption-design.md`).
Decisions: conservative curation (clearly-safe framework memories only, no
rewording) + copy-not-move (native store untouched). Branch
`plan-26-committed-memory` off master (Plan 25 merged, `db5cdb9`).

#### #0007 · completed · T2 · 2026-06-13
Wired gitleaks in the framework's own repo (it previously shipped a backstop to
consumers but ran none itself): root `.pre-commit-config.yaml` (gitleaks v8.21.2)
+ `pre-commit install` + a `security` job in `ci.yml` (pinned binary, full-repo
scan). Full-repo scan clean before any memory was committed.

#### #0008 · note · 2026-06-13
Scaffolded the committed memory store: empty `MEMORY.md` index + `_memory/`, and
added the MEMORY-convention block + `@MEMORY.md` autoload import to CLAUDE.md.

#### #0009 · completed · T2 · 2026-06-13
Copied the 43 public-safe project memories into `_memory/` (+ `scope: project`);
native store untouched (copy, not move). 13 excluded (3 name Meridian, the rest
machine/personal/preference). Boundary spot-check clean (no Meridian / no
private paths in the copies).

#### #0010 · completed · T2 · 2026-06-13
Repaired 11 migrated memories whose `[[links]]` pointed at non-committed
(excluded/nonexistent) slugs — reworded those references to prose per the
convention's cross-store rule. All 25 distinct committed `[[slug]]` targets now
resolve within `_memory/`. Native links untouched (copy approach).

#### #0011 · completed · T2 · 2026-06-13
Built `MEMORY.md` (43 entries, reusing the native index's curated titles/hooks,
paths rewritten to `_memory/`). Index ↔ files bidirectionally complete (43 ↔ 43).
