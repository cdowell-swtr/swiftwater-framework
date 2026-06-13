---
name: scaffold-from-real-tag-not-default-branch
description: "Generated projects must scaffold from a released git tag, not master HEAD, or the upskill anchor lies"
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 2b6a934f-6acf-4185-8669-1a0fa4506849
---

`framework new` records an **upgrade anchor** into the project's `.copier-answers.yml`: `record_portable_source` (`source.py:127`) writes `_commit: v<version>` where `<version>` = `installed_framework_version()` (`manifest.py:14`) = the installed package's importlib-metadata version = whatever `pyproject.toml` said at install time. `version_tag()` just prepends `v`. That `_commit` MUST correspond to a real git tag, because `framework upskill` runs `copier update` from it (the three-way-merge baseline).

**The trap (now resolved — kept as the why):** the gap was that the only tag was `v0.1.9` while master ran ~69 commits ahead (docs battery 22b/site 22a) with `pyproject.toml` still at `0.1.9`. Pinning `@v0.1.9` → clean anchor but stale template; installing from master HEAD → current template but a `_commit: v0.1.9` that doesn't match what you rendered → first `upskill` merges from the wrong baseline → spurious conflicts.

**Rule:** before scaffolding a real project, cut a fresh release tag from master (bump pyproject + the version), then `uv tool install …@vX.Y.Z` and scaffold from that. Never start a real project off an un-bumped default branch. See [[release-cut-procedure]] and [[release-readiness-needs-render-not-local-gate]].

**RESOLVED 2026-06-11:** **v0.2.0 cut + published** (master is no longer ahead of an un-bumped pyproject) — the upskill anchor is now real, so scaffold the first real project against **`@v0.2.0`**. The GraphQL-introspection-in-prod template bug shipped fixed in v0.2.0 ([[app-environment-tokens-never-production]]). Re-apply this rule for every future release before scaffolding.
