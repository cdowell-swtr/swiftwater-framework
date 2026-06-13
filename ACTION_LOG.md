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
