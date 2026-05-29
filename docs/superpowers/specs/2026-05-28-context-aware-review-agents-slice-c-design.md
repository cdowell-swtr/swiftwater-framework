# Context-aware review agents — Slice C (framework-repo target + dogfooding CI) design

**Date:** 2026-05-28
**Status:** Approved (brainstorm).
**Parent design:** `docs/superpowers/specs/2026-05-28-context-aware-review-agents-design.md` (§5b/§7 Slice C).
**Builds on:** Slice A (the target-agnostic spine — `ReviewTarget`/`assemble`/`run_agent`, FF `1c051cd`) and Slice B (the agentic loop `run_agent_agentic` + tools, FF `9687016`).

## 1. Problem

The review agents run against generated projects (Slice A/B). To **dogfood**, the framework should review its **own** changes with the same machinery. The spine is already target-agnostic (the only target-specific artifact is `ReviewTarget`), so Slice C adds a *second* target — the framework repo — and wires it into the framework's own CI.

Two facts shape the design:
- The bundle agents' `context_globs` are **app-shaped** (`src/*/routes/*.py`, `src/*/observability/*.py`, …) and don't fit the framework's CLI layout (`src/framework_cli/…`). So the framework target can't reuse them.
- The framework repo contains both **CLI/tooling source** (`src/framework_cli/**` minus the template) and **template payload** (`src/framework_cli/template/**`, the generated-app code).

## 2. Decisions (locked in brainstorm)

1. **Agentic for all applicable agents.** On the framework target, every applicable agent runs through the Slice B **agentic loop** (explore the repo via `read_file`/`grep`/`glob`), regardless of its generated-project strategy. No per-target glob table to maintain; reuses Slice B verbatim; suits the framework's small, cross-referencing CLI. Agent prompts are generic, so running e.g. `security` agentically on the framework is sound.
2. **Template payload is out of scope.** The framework target reviews only the framework's own CLI/tooling source. Template-payload quality is the **product's** concern — reviewed when a generated project runs its shipped review CI (the generated-project target), fully realized once **Plan 12** runs a rendered project's `ci.yml` on GitHub Actions. **This revises the parent spec's "render-then-review" intent** (dropped as redundant + mechanically heavy).
3. **Applicable subset (6):** `architecture`, `security`, `dependency`, `test-quality`, `documentation`, `application-logic`. Excluded (non-applicable to a Python Copier-wrapper CLI): `observability`/`observability-infra`/`observability-db`, `api-design`, `contracts`, `accessibility`, `usability`, `data-integrity`, `privacy`, `compliance`, `performance`.
4. **Full subset on both PR and push-to-master** (no `on_push` narrowing): the subset is small, framework changes are infrequent, and the actual dev flow is FF-merge-to-master without a PR — so push is the trigger that fires.

## 3. Architecture

The spine stays **target-blind**. `--target framework` is the only place behavior differs; it lives at the CLI layer, which constructs the right inputs (diff, root, agentic dispatch) for the target-agnostic spine.

### 3.1 The framework target profile
`framework_target()` (in `review/context.py`, alongside `generated_project_target`) → `ReviewTarget(root=Path.cwd(), active=<the 6-agent subset, filtered to registered agents>)`. The subset is a module-level constant `FRAMEWORK_AGENTS`. (No glob/strategy fields on `ReviewTarget` — "force agentic" and "exclude template" are applied by the CLI's `--target framework` path, keeping `ReviewTarget` a pure `(root, active)` value.)

### 3.2 Diff scoping
The framework review diff is the framework's git diff **with `src/framework_cli/template/**` excluded** (template payload is out of scope). A `framework_diff()` helper (in `review/diff.py`, beside `pr_diff()`) runs `git diff <range> -- . ':(exclude)src/framework_cli/template'` (the existing PR/push range logic from `pr_diff`). A template-only change ⇒ empty diff ⇒ the review no-ops gracefully (no findings; neutral check).

### 3.3 CLI
- `review-agents --target {project,framework}` (default `project`): `framework` returns `sorted(FRAMEWORK_AGENTS)` (the dogfooding CI doesn't event-narrow — it always runs the full subset; the `--event` arg is still accepted/ignored for the framework target, or simply not passed).
- `review --target {project,framework} <agent>` (default `project`): for `framework`, source the diff via `framework_diff()`, and dispatch through `run_agent_agentic(diff, Path.cwd(), spec, default_client(), max_turns=spec.context.max_agentic_turns or DEFAULT_MAX_TURNS)` — i.e. force agentic regardless of `spec.context.strategy`. The existing no-key → neutral and infra-failure → neutral handling is unchanged.
- `--target project` paths are **byte-unchanged** from Slice A/B.

### 3.4 CI wiring
Extend the repo-root `.github/workflows/ci.yml` (or a sibling `review.yml`) with a review matrix mirroring the generated project's `ci.yml.jinja` flow, but with `--target framework`:
- a `review-agents` step: `framework review-agents --target framework` → `GITHUB_OUTPUT` → a `fromJSON` `strategy.matrix`;
- a matrixed `framework review --target framework <agent> --findings-out …` job;
- a `review-aggregate` job over the collected findings.

Gated like the generated project: the `review` command **skips neutral when `ANTHROPIC_FRAMEWORK_CI_EVAL` (→ `ANTHROPIC_API_KEY`) is unset**, so the framework's CI never goes red merely for a missing key (distinct from `agent-evals.yml`'s `--require-key`). Runs on the framework's `pull_request` and `push` (to `master`).

## 4. Components / files

- `src/framework_cli/review/context.py` (modify) — `FRAMEWORK_AGENTS` constant; `framework_target()`.
- `src/framework_cli/review/diff.py` (modify) — `framework_diff()` (template-excluded git diff, reusing the PR/push range logic).
- `src/framework_cli/cli.py` (modify) — `--target` option on `review-agents` and `review`; the framework path (framework subset; `framework_diff`; forced agentic).
- `.github/workflows/ci.yml` (modify) or `.github/workflows/review.yml` (create) — the framework review matrix + aggregate, secret-gated skip-neutral.
- `tests/review/test_framework_target.py` (create) — subset, diff exclusion, forced-agentic dispatch, default-project regression.

## 5. Testing (hermetic — no API key)

- `framework_target()` returns exactly the 6 `FRAMEWORK_AGENTS`, all registered; `review-agents --target framework` prints them as JSON.
- `framework_diff()` excludes `src/framework_cli/template/**` (construct a fake diff/range or assert the `git diff` pathspec); a template-only change yields an empty review diff → neutral.
- The `--target framework` review path forces agentic: monkeypatch `run_agent_agentic`, run `review --target framework security` (a *bundle*-tier agent), assert the agentic loop was invoked (not `assemble`/`run_agent`).
- `--target project` (default) `review-agents`/`review` behavior unchanged (regression).
- The CI workflow is statically valid (an `actionlint`/parse check if available; otherwise asserted by a YAML-load test mirroring existing workflow tests).
- Full gate green; no template-payload, spine, prompt, or generated-project-review changes.

## 6. Risks

- **Cost:** agentic-for-all × 6 on each framework push — bounded by the per-agent turn cap; framework changes are infrequent; skip-neutral without the key means it's off until the secret is set.
- **No-PR flow:** push-to-master review is post-merge (detective, not blocking). Accepted — it's the trigger that actually fires given the FF-merge habit; adopting PRs later yields pre-merge blocking for free.
- **Applicable subset is a judgment call** — it's data (`FRAMEWORK_AGENTS`), trivially widened later.
- **Real agentic behavior on the framework repo is unverified without a key** — same posture as Slice B; the first real run happens once the secret is set (Slice D plumbs it). Slice C ships the wiring + hermetic tests.
