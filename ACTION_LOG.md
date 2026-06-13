# ACTION_LOG — swiftwater-framework

> Append-only event narrative, task grain. Never edit or truncate existing
> entries. Closed taxonomy: completed · inserted · reordered · dep-found ·
> amended · superseded · discarded · milestone · note.
> Maintained per `pi-convention.md` (PI-convention: v2).

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

#### #0012 · note · 2026-06-13
Self-registered swiftwater-framework as a Committed Memory adopter in the patterns
registry (`_docs/committed-memory/implementers.md`); ticked its T8 (patterns log
`#0010`). Cross-repo commit; the framework session gate is satisfied by staging
this entry.

#### #0013 · completed · T2 · 2026-06-13
Plan 26 complete: Committed Memory convention adopted — gitleaks wired in the
framework's own repo, store scaffolded, 43 public-safe memories migrated (copy,
not move), 11 cross-store links reworded to prose, 43-entry index built, framework
registered as an adopter. gitleaks clean (with memories present); boundary
self-audit clean (only self-referential public `cdowell-swtr` repo coordinates,
which are safe to publish); convention invariants hold; gate green.

#### #0014 · amended · T2 · 2026-06-13
The CI `security` job (full-history `gitleaks detect`) surfaced 2 findings the
local hook missed — both are the intentional fake AWS key in
`tests/eval/fixtures/security/bad/hardcoded-secret.diff` (the payload the security
reviewer is meant to flag), not real secrets. The pre-commit gitleaks hook scans
staged diffs only; CI's full-history `detect` is the authoritative scan. Added
`.gitleaks.toml` allowlisting `tests/eval/fixtures/security/`; full-history scan
now clean — which also re-confirms the 43 migrated memories are clean under the
authoritative scan (it flagged only the fixtures, nothing in `_memory/`).

#### #0015 · note · 2026-06-13
First organic additions to the committed memory store (now 45): two gotchas
learned this session — `gitleaks-staged-vs-history-and-fixture-allowlist` and
`cross-repo-commit-needs-local-plan-staged`. Both public-safe project facts.
gitleaks clean; invariants hold (45 ↔ 45).

#### #0016 · note · 2026-06-13
Migrated task IDs T→FWK (PI v1→v2). Remap: T1=FWK1, T2=FWK2, T3=FWK3, T4=FWK4,
T5=FWK5, T6=FWK6, T7=FWK7, T8=FWK8, T9=FWK9, T10=FWK10. Historical log entries
above keep their T-form (append-only — never rewritten); the join holds via this
remap. New entries use FWK. (FWK10 = this migration; see
`docs/superpowers/plans/2026-06-13-pi-v2-migration.md`.)

#### #0017 · completed · FWK10 · 2026-06-13
PI v2 migration complete: vendored pi-convention.md (patterns main HEAD, @2c88543)
+ memory-convention.md (memory/v1) and re-pointed all references; adopted the FWK
prefix (T→FWK, numbers kept; remap #0016); relocated the PI pointer to AGENTS.md
with @AGENTS.md autoloaded by CLAUDE.md; registered v2/FWK by PR to
cdowell-swtr/patterns (PR #3). Runbook compliance self-check all-OK; gate green.

#### #0018 · note · 2026-06-13
Promoted the gh-only vendoring/registration learning into the committed store
(`framework-consumes-patterns-via-github-vendoring`, now 46) — public-safe +
project-useful, so the committed store is its proper home (travels to every
machine). gitleaks clean; invariants 46↔46. (Native duplicates pruned separately.)
