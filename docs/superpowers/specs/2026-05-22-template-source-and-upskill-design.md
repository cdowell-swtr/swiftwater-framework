# Portable Template Source + Upskill/Version (Plan 6b) — Design Spec

**Date:** 2026-05-22
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 6a (framework integrity) `docs/superpowers/plans/2026-05-22-framework-integrity.md`. Realizes spec §16 (upskill/check), the §18 commands `check`/`upskill`, and activates 6a's deferred CI step-0. Resolves the long-standing carried-forward note: *".copier-answers.yml records a machine-specific `_src_path`; the upskill/`copier update` flow needs a portable, versioned template source."*

---

## 1. Purpose

A generated project records where it came from in `.copier-answers.yml`. Today that is a machine-specific absolute path (`_src_path: /home/.../src/framework_cli/template`) with no version ref, so `copier update` — and therefore `framework upskill` — cannot work, and CI step-0 (`framework integrity --ci`) cannot install the framework. Plan 6b makes the template source **portable and versioned** (a git-tagged source), records it at `framework new`, and ships the `framework check` / `framework upskill` commands plus the now-activatable CI step-0.

## 2. Decisions (settled in brainstorm)

- **Source model:** the template stays a **subdirectory of the framework repo** (`src/framework_cli/template/`), addressable as a Copier source by git URL + tag via a repo-root `copier.yml` declaring `_subdirectory`. (Approach chosen over a separate template repo and over a bundled-only custom updater.)
- **Versioning:** a release is a git tag `vX.Y.Z` on the framework repo, equal to the `framework-cli` package version. **Invariant (by construction):** the template bundled in CLI `X.Y.Z` is the template at tag `vX.Y.Z`, because the release procedure tags the same commit the version is cut from. This makes `new` (bundled render) and `upskill` (git diff from the recorded tag) consistent with no sync step.
- **Distribution:** git tags only — install via `uv tool install git+<repo>@vX.Y.Z` (teammates and CI). No PyPI (can be added later without changing the model).
- **`upskill` is version-update only** in 6b; `--with <battery>` is deferred to Plan 8 (batteries do not exist yet).

## 3. Versioned template source

- Add a **repo-root `copier.yml`** declaring `_subdirectory: src/framework_cli/template` so `git+https://github.com/cdowell-swtr/swiftwater-framework@<tag>` is a valid Copier source resolving to the existing template.
- **Plan-time spike (the one unverified mechanic):** Copier's `_subdirectory` resolution and how it coexists with the *bundled local-path render* `framework new` already uses (source = `src/framework_cli/template`, reading that dir's `copier.yml`). The plan's first task is a short spike confirming the exact copier.yml placement (root vs. subdir vs. both) and the question-source so that BOTH paths work: (a) local bundled render for `new`, (b) git-URL render/update for `upskill`. The acceptance criterion: a project rendered locally and a project rendered from the git source at the same tag are identical, and `copier update` runs against the git source. No implementation tasks are written until the spike resolves this.

## 4. `framework new` records a portable source

After the bundled render (unchanged), `framework new` rewrites the generated `.copier-answers.yml`:
- `_src_path` → `gh:cdowell-swtr/swiftwater-framework` (the portable git source Copier understands),
- `_commit` → `v{installed_framework_version()}`,
- the real answers (project_name/slug/package/python_version) untouched.

If the installed CLI is a dev/pre-release build with no matching tag, `new` still records `v{version}`; `upskill` later surfaces a clear "tag not found" error. The normal path is a released CLI scaffolding an update-able project.

## 5. `framework check` and `framework upskill`

- **`framework check`** (read-only): query the framework repo's remote tags (`git ls-remote --tags <repo>`), pick the highest semver `vX.Y.Z`, compare to the installed CLI version. If behind, print the gap and the tag-to-tag changelog (commit subjects between the installed version's tag and the latest). Answers "is there a newer framework?".
- **`framework upskill <name>`** (spec §16): run Copier's `run_update` on the project directory to move it from its recorded `_commit` to the target version (latest tag by default, or `--vcs-ref <tag>`), then run `task test`; report success **only if the project is green**. On a Copier merge conflict or a failing test, stop and report — Copier leaves `.rej`/conflict markers for manual resolution (the project is not left silently broken). `--with <battery>` is out of scope (Plan 8).

## 6. CI step-0 activation

The generated `.github/workflows/ci.yml` integrity job (an echo placeholder since 6a) becomes real: a step reads `_commit` from the project's `.copier-answers.yml`, runs `uv tool install git+<repo>@<_commit>` to install the matching framework version, then runs `framework integrity --ci`. This activates the 6a integrity check as the authoritative CI step 0 — possible only now that an installable, versioned source exists.

## 7. Testing

- **Upskill / update path (no published tags required):** a test builds a **temporary local git repo** with the template at two tags (`v1`, then `v2` carrying a framework-file change), scaffolds a project at `v1`, runs `upskill` / `copier update` to `v2`, and asserts the merge is **non-destructive** (builder edits survive; framework change applied) and the upgraded project **stays green**. This is the spec §20 "upskill path" obligation.
- **`check`:** point at the local two-tag repo; assert it reports the newer tag + the version gap.
- **`new` records a portable source:** render assertion — the generated `.copier-answers.yml` has `_src_path` = the git source and `_commit` = `v{version}`.
- **CI activation:** render-assert `ci.yml` installs the framework (from `_commit`) and runs `framework integrity --ci`; `actionlint` validates the workflow. (GitHub Actions can't run locally — the same validation approach as Plans 5a/5b.)

## 8. Release discipline

A short `RELEASING.md` (framework repo) documents the procedure: bump the `framework-cli` version → commit → tag `vX.Y.Z` on that commit → push the tag. The "bundled == tag" invariant (§2) holds by construction. Cutting the first real tags is an operational step, not a code deliverable of 6b.

## 9. Scope & slicing

6b is cohesive (all about versioned updates) but sizeable; it is decomposed into plans at writing-plans time:
- **6b-1:** versioned template source (the `_subdirectory` spike + root `copier.yml`) + `framework new` records the portable source + `framework check` + `RELEASING.md`.
- **6b-2:** `framework upskill` + the local-git-repo two-tag upskill/update test.
- **6b-3:** CI step-0 activation (may fold into 6b-2).

Final slicing is decided when writing the plan(s).

**Out of scope:** PyPI publishing; `upskill --with <battery>` (Plan 8); a GitHub release-automation workflow (the framework's own release CI may land with Plan 9 dogfooding); multi-source/forked-template support.

## 10. Self-review

- **Placeholders:** none — every decision (source model, versioning, distribution, `new`-records, `check`, `upskill` semantics, CI activation, testing) is settled. The one genuinely-unverified mechanic (the `_subdirectory`/copier.yml wiring) is explicitly a **plan-time spike** with a stated acceptance criterion, not a hand-wave.
- **Internal consistency:** the "bundled == tag by construction" invariant is what lets `new` render from the bundled copy yet record a git tag that `upskill` can diff against — consistent across §3/§4/§5. Distribution (git tags) matches `check` (remote tags) and CI install (`git+@tag`).
- **Scope:** focused on the versioned-update theme; batteries, PyPI, and release-automation explicitly deferred.
- **Ambiguity:** the dev-build-no-tag edge (§4) and the conflict/failure behavior of `upskill` (§5) are stated explicitly.

---

*End of design. Next step (when ready): `superpowers:writing-plans` to produce the Plan 6b implementation plan(s), starting with the `_subdirectory` spike.*
