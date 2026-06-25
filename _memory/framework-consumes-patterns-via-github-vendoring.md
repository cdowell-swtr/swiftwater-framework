---
name: framework-consumes-patterns-via-github-vendoring
description: "The patterns repo (PI/MEMORY conventions) is gh-only for consumers. VENDOR the convention files locally from cdowell-swtr/patterns via the gh API (tag for released, main HEAD for un-tagged hotfixes) with a provenance comment; reference the bare local copy, NEVER `../../patterns/`. Update the implementer registry via a pure gh-API PR (create ref → PUT contents → gh pr create) — no local clone, no cross-repo commit-gate."
scope: project
metadata:
  type: project
---

As of 2026-06-13 (PI v2 migration, FWK10) the sibling `cdowell-swtr/patterns` repo
is **gh-only for consumers** — it is NOT a reliable local `../../patterns/` sibling
on every machine. The framework consumes its conventions by **vendoring**:

- **Vendor, don't sibling-path.** Pull the convention into the repo root from
  GitHub and reference the bare local name. The framework currently vendors
  `pi-convention.md` (from `main` HEAD, to capture an un-tagged access-pattern
  hotfix), `memory-convention.md` (from tag `memory/v1`), and
  `cross-repo-convention.md` (from tag `cross-repo/v4`, vendored 2026-06-25 /
  FWK64 — adopted as the **absorber** of the Meridian→Framework auth promote-up;
  the AGENTS.md rule block + the Promote-Up Record live in-repo). Each carries a
  provenance comment: `<!-- vendored from cdowell-swtr/patterns <file> @ <sha>
  (<ref>) on <date> -->`. **Re-vendor** when a later tag supersedes a hotfix.
  Pull command: `gh api "repos/cdowell-swtr/patterns/contents/<file>?ref=<tag|main>"
  -H "Accept: application/vnd.github.raw"`.
- **Tag vs HEAD:** released conventions come from a tag (`pi/vN`, `memory/vN`);
  pull from `main` HEAD only to get a fix that isn't tagged yet, and record the
  SHA so the exact version is reproducible despite a moving HEAD.

**Registering / updating the implementer registry is a pure gh-API PR** — no local
clone, so it never touches the framework's cross-repo commit-gate (a local-clone
commit is fiddly: the gate checks the session cwd's repo and fires before any
`cd` — see [[cross-repo-commit-needs-local-plan-staged]]). Recipe:
`gh api --method POST .../git/refs` (branch off main's sha) →
`gh api --method PUT .../contents/<file>` with `-f content="$(base64 -w0 file)"`
+ the file's `sha` + `branch` → `gh pr create --repo cdowell-swtr/patterns`. The
patterns CC reviews/merges its own registry (SwiftwaterLib + swiftwater-framework
both registered this way).

**PI v2 specifics for this repo:** task-ID prefix is **`FWK`** (`PLAN.md` IDs are
`FWK1, FWK2, …`); the PI pointer lives in **`AGENTS.md`** (`<!-- PI-convention:
v2 -->`) and CLAUDE.md autoloads it via `@AGENTS.md` (Claude Code autoloads
CLAUDE.md, not AGENTS.md). MEMORY stayed v1 — only its reference path changed.
