# Context-aware review agents — design

**Date:** 2026-05-28
**Status:** Approved (brainstorm) — Slice A detailed; Slices B/C/D scoped as follow-on cycles.
**Supersedes the framing of:** the original "Plan 11 — post-harness validations" (real-key eval scoring). That scoring survives intact as **Slice D**; this redesign is its prerequisite.

## 1. Problem

The Layer-3 review agents (Plan 7) are **diff-scoped**: `run_agent(diff, spec, client)` sends the LLM exactly the PR's unified diff (changed hunks + ~3 lines of surrounding context, hard-capped at `_MAX_DIFF_CHARS = 200_000`) plus the agent prompt. The whole repo never enters context.

That is structurally insufficient for the holistic concerns most of the ~18 agents are nominally responsible for:

- a one-line change whose defect only shows in the full method/file;
- accessibility/usability, which depend on the whole component/ARIA tree across files;
- architecture, data-lineage, privacy/compliance, api-design, contracts, observability — all of which reason about relationships that span files;
- the obs-infra-scaling "should this graduate off a single host?" judgment, which needs the whole topology.

We considered, and **rejected**, the reading that "holistic checks live in another layer." They largely do not: `axe`/Playwright cover a slice of accessibility but nothing of usability/architecture/lineage/privacy/api-design/test-quality; the obs-completeness `tests/` invariant covers one narrow thing. For most agents the holistic concern is checked by *no* layer — and a diff can't check it either.

**Consequence for validation:** the eval fixtures are themselves small diffs authored to be diff-detectable. So a green real-key scorecard could only certify "agents catch defects visible in a diff" — it would *over-claim*. Calibrating thresholds against diff-blind agents on diff-shaped fixtures is premature. **Therefore the agents must become context-aware first, and eval scoring becomes the tail of that work.**

## 2. Goals / non-goals

**Goals**
- Give each review agent the context it needs to do holistic review, via a **per-agent context policy in the registry**.
- Keep the review machinery **target-agnostic**: one runner, one assembler, one registry schema. The *only* target-specific artifact is a thin `ReviewTarget` profile.
- Support **two review targets** sharing that identical machinery: (a) generated projects (shipped use), and (b) the framework's own repo (dogfooding).
- Run the **same context machinery in eval and production**, via rendered-project fixtures.
- Then produce the first real-key scorecard and calibrate thresholds (the original Plan 11).

**Non-goals**
- Rewriting agent *prompts* for quality (deferred to follow-ups unless the scorecard shows an agent is badly broken).
- A new aggregator/PR-comment design (Plan 7's aggregator is unchanged).
- Changing which severities block (unchanged from the current registry).

## 3. Architecture (target-agnostic spine)

The unifying invariant, to be enforced by a test:

> The only target-specific artifact is the `ReviewTarget` profile. The runner, assembler, and registry context schema are shared and target-blind — both targets drive the identical `assemble → run_agent` path.

### 3.1 Data model (registry)

```python
@dataclass(frozen=True)
class ContextPolicy:
    strategy: Literal["diff", "bundle", "agentic"]   # "agentic" lands in Slice B
    context_globs: tuple[str, ...] = ()              # domain subtree, resolved against the target root
    max_context_tokens: int | None = None            # optional per-agent override of the derived ceiling

# AgentSpec gains:
    context: ContextPolicy = ContextPolicy("diff")
```

- `strategy="diff"` is the **default** ⇒ every un-migrated agent behaves exactly as today; migration is incremental and safe.
- `strategy="bundle"` ⇒ *diff + full content of changed files + files matching `context_globs`*.
- `strategy="agentic"` ⇒ the agent is a tool-using loop (read/grep/glob) over the target root (designed in Slice B).
- `context_globs` use the same glob string style as the existing `trigger_globs`, resolved against whatever root the target hands in (target-agnostic patterns).

### 3.2 The seam: `ReviewTarget`

```python
@dataclass(frozen=True)
class ReviewTarget:
    root: Path                # the tree (CWD for the generated project; the repo root for the framework)
    active: tuple[str, ...]   # agent names applicable to this target
```

The only place the two targets differ. `pr_diff()` already runs `git diff` in the CWD, which *is* the checked-out tree — so for the generated-project target `root` is essentially already present; we now also read files/globs from it.

### 3.3 `ContextAssembler`

```python
def assemble(diff: str, root: Path, policy: ContextPolicy, *, model: str) -> Bundle
```

Builds, in **priority order** under a token budget: (1) the diff — always; (2) full content of `changed_files(diff)`; (3) files matching `context_globs`. When the running estimate would exceed the ceiling, stop adding and record a truncation marker. Diff wins, then changed files, then the wider subtree, so we degrade gracefully on pathological bundles rather than dropping the diff.

**Budget ceiling.** Derived from the agent's model context window minus reserved output (`max_tokens = 4096`) minus the prompt minus a safety margin, measured in *estimated* tokens (chars ÷ 4 — no count-tokens API call). `policy.max_context_tokens`, if set, overrides downward/upward. The `_MAX_DIFF_CHARS = 200_000` constant is **removed** — selection (globs + changed files) is the primary control; the ceiling is only a safety net.

### 3.4 Runner + cache layout

`run_agent(bundle, spec, client)` emits system blocks in this order:

1. **diff block** — `cache_control: ephemeral`. Identical across all agents on the same target ⇒ preserves today's cross-agent shared-prefix cache hit.
2. **context block** — `cache_control: ephemeral`. Per-agent (differs by globs/strategy); cache-hits across `--repeat` within the cache TTL.
3. **agent prompt.**

For `strategy="diff"` the context block is empty/omitted ⇒ the call is **byte-identical** to today's two-block message, so unmigrated agents are provably unchanged and the cross-agent diff cache is retained for everyone.

## 4. Fixtures (rendered-project + injected defect)

A fixture is a *render spec* + a *seeded change*, not a committed tree:

```
tests/eval/fixtures/<agent>/<bad|good>/<case>/
    fixture.yaml     # render spec: batteries (e.g. [react]), optional notes
    change.patch     # the seeded bad/good change, applied to the rendered tree
    expect.json      # (bad only) seeded_file + expected finding markers
```

**Loader flow:** render the base project from the framework's own template (`render_project`, `--with` the combo) → apply `change.patch` → compute the diff → `ReviewTarget(root=rendered_dir)` → `assemble` → `run_agent` → score. The same assembler/runner the production path uses.

**Realization — render at eval time, cached per battery-combo.** No committed snapshots: this matches the repo's ethos ("the template is the source of truth; validate by rendering and exercising the generated project") and the render-matrix/acceptance tiers already render projects in CI. The render cost is amortized by caching one base render per battery-combo within a run. Committed snapshots are rejected — they drift from the template and would test a stale app shape.

## 5. Review targets

Both targets are instances of the same `ReviewTarget` type and drive the identical spine.

- **(a) Generated-project target** (Slice A). `root = CWD` (the checked-out rendered project); `active = active_agents(event, batteries)` (existing logic). The full app-domain agent set applies.
- **(b) Framework-repo target** (Slice C). `root =` the framework repo; `active =` the subset whose domain generalizes to a Python CLI + Copier template (e.g. architecture, security, dependency, test-quality, documentation, application-logic). App-only agents (accessibility, usability, api-design, contracts, observability-db) **do not** apply to this target. Template-payload changes are reviewed **render-then-review** (render the affected template, review the rendered diff) because the agents understand app code, not Jinja — finalized in Slice C. Wired into the framework's own CI as dogfooding.

## 6. Tier assignment

Principle: **`bundle`** if a bounded domain subtree (globs) + changed files suffices; **`agentic`** if the agent must *follow references across the repo* — e.g. trace a concern from a changed file out to where it is consumed/produced, which a static subtree can't satisfy.

- **Static `bundle` tier** (migrated in Slice A) — 11: accessibility, application-logic, compliance, data-integrity, dependency, documentation, observability (app), performance, security, test-quality, usability.
- **Agentic tier** (stays `diff` until Slice B) — 7: architecture (module graph), data-lineage (cross-file data-flow), privacy (data-flow tracing), api-design (a contract can match while the *both-ends* usage is wrong → must see consumers), observability-infra (infra obs correctness depends on the app's instrumentation + topology, not just `infra/`), observability-db (db problems surface in *app* files, not only the data layer), contracts (Pact: consumer client + provider live in different files — the both-ends back-and-forth is the whole point).

The exact per-agent `context_globs` (bundle tier) are finalized during migration (Slice A) and recorded in the registry; the agentic tier's tool scope is designed in Slice B.

## 7. Decomposition (slices — each its own spec → plan → implement cycle)

- **Slice A — context-model spine + static tier (generated-project target).** `ContextPolicy` on `AgentSpec` (default `diff`), `ReviewTarget`, `ContextAssembler` (model-derived budget), runner refactor + cache layout, the generated-project profile, migration of the static-tier agents to `bundle` with rendered-project fixtures, and the target-agnostic invariant test. **This spec details Slice A.**
- **Slice B — agentic tier.** read/grep/glob tools, a token/tool-call budget, the seven agentic agents (architecture, data-lineage, privacy, api-design, observability-infra, observability-db, contracts), their fixtures, and the `strategy="agentic"` execution path.
- **Slice C — framework-repo target (dogfooding).** Add the second `ReviewTarget` profile (applicable agent subset + framework-repo glob roots + render-then-review for template payload) + CI wiring. Reuses the spine verbatim — the proof the pattern is genuinely identical.
- **Slice D — real-key eval scoring + threshold tuning (the original Plan 11).** Score the now-context-aware agents against the rendered fixtures with `--repeat`-averaging; calibrate `thresholds.yaml` per agent with a safety margin (`recall_min` below observed healthy recall, `fp_max` above observed false-positive rate); commit a dated scorecard under `docs/superpowers/eval-scorecards/`; confirm green on real GitHub Actions (local-key iteration first, then the `ANTHROPIC_FRAMEWORK_CI_EVAL` secret on a `workflow_dispatch`-enabled `agent-evals.yml`). Also enrich shallow good fixtures across all agents (single-good ⇒ coarse precision), act on the carried-over OBS-COMPLETE inputs (richer obs good fixtures with health-signal + correlation-id cases; tighten `observability-infra/bad/exporter-dev-only`; per-store `matches_globs` assertions). Cost is modest — diff-scoped, prompt-cached calls — but bundle/agentic strategies raise per-call input above the old diff-only baseline; budget accordingly.

## 8. Slice A — detailed plan inputs

### 8.1 Components
- `framework_cli/review/registry.py` — add `ContextPolicy`; add `context` field to `AgentSpec` (default `ContextPolicy("diff")`); set `bundle` policies + `context_globs` for the static-tier agents.
- `framework_cli/review/context.py` (new) — `ReviewTarget`, `Bundle`, `assemble(...)`, the model-derived budget helper. Reuses `changed_files` (diff.py) and the existing glob matcher.
- `framework_cli/review/runner.py` — `run_agent(bundle, spec, client)`; the 3-block cache layout; `diff`-strategy byte-identity.
- `framework_cli/cli.py` — `_review_run`/`_eval_run` assemble a `Bundle` from a `ReviewTarget` before calling the runner.
- `tests/eval/` loader — render-at-eval-time + patch + diff producing `(root, diff)`; per-combo render cache.

### 8.2 Testing (all hermetic — no LLM key; real scoring is Slice D)
- `assemble`: diff-strategy ⇒ diff-only bundle (byte-identical to today); bundle-strategy ⇒ full changed-file content + glob-matched subtree; budget ceiling trips truncation in priority order (diff retained, subtree dropped first); model-derived ceiling + per-agent override; globs resolve against root.
- `run_agent(bundle, …)` with a fake client: asserts the 3 cache-blocked system blocks; diff-strategy omits the context block ⇒ provably unchanged call.
- `ReviewTarget` generated-project profile: root + active set.
- Fixture loader: a migrated agent's fixture renders+patches+diffs and the assembled bundle contains the expected subtree files.
- Regression: unmigrated agents + the existing `review` command behavior preserved.
- Target-agnostic invariant: a test asserting the single `assemble → run_agent` path (fully exercised once Slice C adds the second profile).

### 8.3 Migration order
1. Land the spine with `ContextPolicy` defaulting to `diff` ⇒ everything green and byte-identical (safe foundation).
2. Migrate static-tier agents to `bundle` + author rendered-project fixtures incrementally, each with its hermetic assembly test.

## 9. Risks
- **Budget/cost.** Bundle and agentic strategies raise per-call input above the diff-only baseline; the model-derived ceiling + per-agent override + the retained shared-diff cache keep it bounded. Watch the agentic tier (Slice B) most.
- **Fixture authoring cost.** Injecting meaningful defects into a real rendered tree is more work than a 20-line diff; accepted as the price of fidelity.
- **Render-at-eval-time latency in CI.** Mitigated by per-combo render caching; acceptable given the render-matrix already renders in CI.
- **Glob drift.** Per-agent `context_globs` must track the template's package layout; covered by the rendered-fixture assembly tests (a stale glob ⇒ missing expected subtree file ⇒ test fails).
