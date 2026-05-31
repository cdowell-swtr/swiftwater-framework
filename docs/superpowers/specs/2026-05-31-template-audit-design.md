# template audit pass — design

**Date:** 2026-05-31
**Status:** approved (brainstorm), ready for plan
**Context:** the framework audit baseline (`docs/superpowers/eval-scorecards/audit-2026-05-30-2446de8/`) covered the framework's own source with the 6-agent `FRAMEWORK_AGENTS` roster. This is the natural next pass: audit the **template payload** — the app-domain code that roster deliberately excludes.

## Problem

The framework audit (`--target framework`) runs only `FRAMEWORK_AGENTS` =
`application-logic, architecture, dependency, documentation, security, test-quality`.
The app-domain reviewers — `observability(+db/-infra)`, `api-design`, `contracts`,
`accessibility`, `usability`, `data-integrity`, `data-lineage`, `privacy`, `compliance`,
`performance` — are excluded because they don't apply to CLI/tooling source
(`src/framework_cli/review/context.py:63-77`). But those reviewers are exactly the ones
built to review the **rendered application code** that the template payload
(`src/framework_cli/template/`) produces. That payload is currently unaudited by the agents
meant for it.

Two facts make this cheap to address:

1. **A freshly rendered project is naturally a pure-snapshot audit.** `snapshot_seed`
   (`review/diff.py:84-98`) returns `""`; bundle agents get the whole file set via
   `context_globs`, agentic agents explore via `root_dir` tools — neither needs a diff.
   A rendered project has `.copier-answers.yml`, so `audit-prepare` auto-detects
   `--target project` and uses the battery-aware roster.
2. **Preserve already supports an arbitrary destination.** `audit-finalize --preserve-as <dir>`
   copies `findings/ + audit-report.md + meta.json` to any path — including an absolute path
   back in the framework repo.

So the template audit is largely an **orchestration recipe over existing audit machinery**,
plus two small CLI helpers and one slash command.

## Decisions (from the brainstorm)

- **Coverage:** a single **all-batteries** render (all 11 batteries on) — maximizes agent
  activation in one pass (every battery-gated agent sees its payload at once). Not a
  multi-combo matrix.
- **Path mapping:** a **lightweight, non-authoritative triage aid** — annotate each finding's
  rendered path with a best-guess template-source path; no Jinja evaluation; line numbers
  stay as-rendered with a caveat.
- **Form:** a new **`/reviewers:template-audit` slash command** + two small CLI helpers
  (`template-render`, `template-map`). Consistent with `audit`/`gate`/`tune`.

## The 11 batteries

From `src/framework_cli/batteries.py`: `webhooks, websockets, workers, graphql, pgvector,
mongodb, timescaledb, age, redis, react, consumers`. These are additive/independent (the db
extensions ride the shared custom multi-extension Postgres image; mongodb/redis are separate
services; the rest are app-level). The all-on combo is the kitchen sink; acceptance tests
already render large multi-battery combos. If an all-on render fails, that failure is itself a
template finding.

## Components

### Component 1 — `framework template-render` (CLI)

```
framework template-render --out DIR [--batteries all|<csv>]
```

Wraps `render_project` (`copier_runner.py`) with the canonical fixture answers
(`project_name=Demo, project_slug=demo, package_name=demo, python_version=3.12`) plus the
battery list (default: all 11), then `git init && git add -A && git commit` (mirrors
`realize_fixture` in `review/evals.py`; gives agentic review tools a clean repo).
Deterministic and hermetic → unit-testable. Chosen over driving `framework new` because the
integrity-lock + portable-source-rewrite that `new` adds are not payload code the agents
review, and the wizard introduces non-determinism; `render_project` is the same faithful
render path the eval harness uses.

### Component 2 — `framework template-map` (CLI, the triage aid)

```
framework template-map --findings DIR --template-root PATH --render-root PATH [--out FILE]
```

For each finding's rendered path (e.g. `src/demo/graphql/schema.py`), performs a
**basename-anchored search** of the template payload: collect template files named
`<basename>` or `<basename>.jinja`; rank candidates by path-tail overlap after substituting
the rendered `package_name` back to `{{package_name}}`. Emits a `path-map.md` table mapping
each finding → `template_source`, one of:
- a single confident match (e.g. `src/framework_cli/template/src/{{package_name}}/.../schema.py.jinja`),
- multiple candidates (listed for the triager to pick), or
- `UNRESOLVED`.

Every row carries the caveat: **line numbers are as-rendered, not template-source** (Jinja
shifts them). Deliberately avoids reimplementing Jinja path/conditional evaluation — it is a
best-effort aid, not authoritative, matching the "lightweight aid" decision.

Inputs: `--findings` points at the finalized `findings/` dir (per-agent JSON, each finding
carrying a `file` path); `--template-root` is `<framework>/src/framework_cli/template`;
`--render-root` is the temp render dir (to strip the prefix from rendered paths); `--out`
defaults to `<findings-parent>/path-map.md`.

### Component 3 — `/reviewers:template-audit` (slash command)

Orchestrates the flow, using **absolute paths** to juggle two roots — the temp render (the
audit subject) and the framework repo (template source + preserve target):

1. `framework template-render --out /tmp/template-audit-render`
2. *(cd /tmp/template-audit-render)* `framework audit-prepare --target project --snapshot
   --split-to /tmp/template-audit-split > /tmp/template-audit-prep.json`
   (all batteries ⇒ full ~18-agent roster; `--snapshot` ⇒ whole-tree, no baseline lookup)
3. Read the prep manifest; invoke the Workflow tool `name: "reviewers-audit"` with
   `{indexPath: "/tmp/template-audit-split/index.json", itemsDir: "/tmp/template-audit-split/items",
   meta: {mode, target, staged_hash|agents_set, …}}` copied from the prep manifest.
4. Write `{results, meta}` to `/tmp/template-audit-results.json`; run
   `framework audit-finalize --results /tmp/template-audit-results.json
   --out-dir /tmp/template-audit-render/.framework/audit/latest`.
5. **Quota-drop guard:** compare `len(results)` to the dispatched roster; if agents are
   missing (the `[[reviewers-tune-quota-throttling]]` pattern), re-dispatch the missing subset
   and merge before finalize.
6. `framework template-map --findings /tmp/template-audit-render/.framework/audit/latest/findings
   --template-root <FW>/src/framework_cli/template --render-root /tmp/template-audit-render`
   → `path-map.md`.
7. Preserve `findings/ + audit-report.md + meta.json + path-map.md` to
   `<FW>/docs/superpowers/eval-scorecards/template-audit-<date>-<framework-HEAD-sha>/`
   (the dir name uses the **framework repo's** short HEAD sha — computed in the slash command,
   since `meta.json`'s `git_sha` will be the render dir's, which is meaningless here).
8. Human writes `triage.md` (hand-authored, as with the framework audit).
9. Cleanup `/tmp/template-audit-render`, `/tmp/template-audit-split`,
   `/tmp/template-audit-prep.json`, `/tmp/template-audit-results.json`.

## Testing

- **template-render:** renders all 11 batteries to a tmp dir; asserts `.copier-answers.yml`
  `batteries` == the 11; spot-checks representative battery files exist (graphql schema, react
  `frontend/`, workers tasks, mongodb repo). Hermetic (render only).
- **template-map:** unit tests against the real template root — a finding citing
  `src/demo/main.py` resolves to its template file; a multi-candidate basename returns the
  candidate list; a bogus path → `UNRESOLVED`; `demo`→`{{package_name}}` substitution verified.
- **Slash command:** not unit-tested (matches existing reviewers slash-command practice); the
  two CLI helpers carry the coverage.

## Integrity / manifest impact

**None.**
- The `/reviewers:template-audit` slash command lives only in the framework's
  `.claude/commands/reviewers/` — **not** added to the template payload
  (`src/framework_cli/template/.claude/`), because it audits the framework's own template and
  is meaningless inside a generated project.
- The two CLI commands are in `framework_cli` (installed CLI), not template payload.
- The preserved scorecard lives under `docs/` (not integrity-tracked).

Confirmed against `src/framework_cli/integrity/classes.py` (`LOCKED_TRACKED`/`HYBRID_TRACKED`/
`GITIGNORED_EXISTENCE`): nothing this slice touches is tracked.

## Non-goals

- No multi-combo matrix (single all-batteries render only).
- No authoritative path/line mapping back to template source (Jinja shifts lines;
  conditional-dir reversal is out of scope).
- No CI integration — this is a manual/periodic audit; the generated-project end-to-end CI is
  Plan 12.
- Nothing shipped into generated projects.

## Cost note

All-batteries ⇒ the full ~18-agent project roster over a larger tree — heavier than the
6-agent framework audit, one comprehensive pass. The quota-drop guard (step 5) handles silent
agent drops.
