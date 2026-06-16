# FWK30 — Agentic coverage-gap reviewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `coverage-gap`, a framework-native, advisory, agentic review agent that watches the broad operational surface on template/registry PRs and flags only what FWK29's closed-world registry can't account for.

**Architecture:** A new `AgentSpec` (agentic, Opus, advisory, file-trigger, framework-only) registered in `_SPECS` and `FRAMEWORK_AGENTS`. It reads `tests/runtime_coverage/registry.py` + `enumerate.py` directly through the existing agentic tools to "defer to the registry," and is fed a template-inclusive full diff (resolving the target-scope wrinkle) while the other five framework agents keep `framework_diff()`. Two small `AgentSpec` flags (`framework_only`, `reviews_template`) drive (a) exclusion from the generated-project review set and (b) the template-inclusive diff. Calibrated by a framework-shaped eval fixture pair (a new realize path, since FWK30 reviews framework *source*, not rendered output).

**Tech Stack:** Python 3.12, `uv`, pytest, the in-repo review engine (`src/framework_cli/review/`), Copier template payload, the LiteLLM-backed agentic loop (`review/agentic.py`).

**Spec:** `docs/superpowers/specs/2026-06-16-fwk30-coverage-gap-reviewer-design.md`

**Execution model note (per CLAUDE.md review-model policy):** implementers → Sonnet (Haiku for trivial); spec-compliance review → Sonnet; **code-quality review → Opus**; final whole-branch review → Opus. Pass `model` explicitly per role. This is framework review-infra work — use the lighter per-task review + controller skip-marker commits + one branch-end full Opus review (see [[gate-cadence-framework-slices]] / [[controller-skip-marker-recipe]]), not the 18-app-agent per-commit gate.

**Branch:** `fwk30-coverage-gap-reviewer` (already created; the design spec is committed there as `bb54e1a`).

---

## File Structure

**Modify:**
- `src/framework_cli/review/registry.py` — add `framework_only` + `reviews_template` fields to `AgentSpec`; exclude `framework_only` agents in `active_agents()`; register the `coverage-gap` spec.
- `src/framework_cli/review/context.py` — add `"coverage-gap"` to `FRAMEWORK_AGENTS`; extend the explanatory comment.
- `src/framework_cli/cli.py` — in the live `review` command, source the template-inclusive `pr_diff()` for a `reviews_template` agent on the framework target (else `framework_diff()` unchanged).
- `src/framework_cli/review/evals.py` — add a framework-shaped realize branch in `realize_cached` for framework-scoped agents.
- `tests/eval/fixtures/thresholds.yaml` — add a `coverage-gap` threshold entry.
- `tests/review/test_framework_target.py` — update the expected `FRAMEWORK_AGENTS` tuple (6 → 7).
- `tests/review/test_context_policy.py` — add `coverage-gap` to the `agentic` set.

**Create:**
- `src/framework_cli/review/agents/coverage-gap.md` — the agent prompt (the heart of the deliverable).
- `tests/review/test_coverage_gap.py` — spec + wiring + framework_only + diff-scope + realize tests.
- `tests/eval/fixtures/coverage-gap/bad/unexercised-cache-overlay/{fixture.yaml,change.patch,expect.json}` — positive fixture (surface added, unexercised → must flag).
- `tests/eval/fixtures/coverage-gap/good/classified-cache-overlay/{fixture.yaml,change.patch}` — negative fixture (surface added + classified → must stay silent).

---

## Task 1: `AgentSpec` gains `framework_only` + `reviews_template`; `active_agents` excludes framework-only

**Why:** `coverage-gap` is a `file-trigger` agent, so without a guard it would leak into `active_agents("pull_request")` (the generated-project review set) and break `test_full_active_sets`. It must be framework-self-review-only. Separately, it needs the template-inclusive diff flag.

**Files:**
- Modify: `src/framework_cli/review/registry.py:37-46` (the `AgentSpec` dataclass) and `:321-342` (`active_agents`)
- Test: `tests/review/test_coverage_gap.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_coverage_gap.py
from framework_cli.review.registry import AgentSpec, DEFAULT_MODEL, active_agents


def test_agentspec_has_framework_only_and_reviews_template_defaults_false():
    spec = AgentSpec("review-x", "p", None, "always", DEFAULT_MODEL)
    assert spec.framework_only is False
    assert spec.reviews_template is False


def test_active_agents_excludes_framework_only_agents(monkeypatch):
    from framework_cli.review import registry

    registry._SPECS["_fwonly"] = AgentSpec(
        "review-fwonly", "p", None, "file-trigger", DEFAULT_MODEL,
        trigger_globs=("src/framework_cli/template/**",), framework_only=True,
    )
    try:
        # Present in the registry, but never in the generated-project PR set.
        assert "_fwonly" not in active_agents("pull_request")
        assert "_fwonly" not in active_agents("push")
    finally:
        del registry._SPECS["_fwonly"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_coverage_gap.py -q`
Expected: FAIL — `AgentSpec` has no `framework_only`/`reviews_template` (TypeError or AttributeError).

- [ ] **Step 3: Write minimal implementation**

In `src/framework_cli/review/registry.py`, add two fields to `AgentSpec` (after `context`):

```python
@dataclass(frozen=True)
class AgentSpec:
    name: str
    prompt: str
    block_threshold: Severity | None  # None = advisory (never blocks)
    active_when: ActiveWhen
    model: str
    on_push: bool = False
    trigger_globs: tuple[str, ...] | None = None
    context: ContextPolicy = ContextPolicy("diff")
    # framework_only: a self-review-only agent (e.g. coverage-gap reviews the framework's
    # own template/registry). Excluded from active_agents() — the generated-project set.
    framework_only: bool = False
    # reviews_template: on the framework target, receive the template-INCLUSIVE diff
    # (pr_diff) instead of framework_diff()'s template-excluding one.
    reviews_template: bool = False
```

In `active_agents`, exclude `framework_only` from both the push and PR base sets:

```python
    if event == "push":
        base = {
            k for k, s in _SPECS.items()
            if s.on_push and s.active_when != "battery" and not s.framework_only
        }
        ...
    else:
        base = {
            k for k, s in _SPECS.items()
            if s.active_when in ("always", "file-trigger") and not s.framework_only
        }
```

(`battery_extra` sets are unaffected — `coverage-gap` is `file-trigger`, not `battery`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_coverage_gap.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the existing registry suite to confirm no regression**

Run: `uv run pytest tests/review/test_registry.py -q`
Expected: PASS — `_EXPECTED_PR`/`_EXPECTED_PUSH` unchanged (no `framework_only` agent registered yet).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/registry.py tests/review/test_coverage_gap.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk30): AgentSpec framework_only + reviews_template; active_agents excludes framework-only"
```

(Update `PLAN.md`/`ACTION_LOG.md` first — the commit-gate hook requires one staged. See [[commit-gate-hook-timing]]: separate `git add` then `git commit`.)

---

## Task 2: Author the `coverage-gap` prompt

**Why:** The prompt is the deliverable's heart — it encodes the coverage lens, the hard boundary against `architecture`/`observability`, the defer-to-registry rule, the two diff-anchored halves, and JSON-only output. Modeled on `agents/env-parity.md` (the closest agentic analog).

**Files:**
- Create: `src/framework_cli/review/agents/coverage-gap.md`
- Test: `tests/review/test_coverage_gap.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/review/test_coverage_gap.py
from framework_cli.review.registry import _prompt


def test_coverage_gap_prompt_loads_and_demands_json():
    p = _prompt("coverage-gap")
    assert p.strip()
    assert "JSON" in p


def test_coverage_gap_prompt_states_its_boundaries_and_registry_defer():
    p = _prompt("coverage-gap")
    # Hard boundary against neighbouring reviewers.
    assert "review-architecture" in p and "review-observability" in p
    # Defers to the FWK29 registry, by name, read through tools.
    assert "registry.py" in p and "enumerate.py" in p
    # The two halves and the diff-anchored discipline.
    assert "new kind" in p.lower()
    assert "exercised" in p.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_coverage_gap.py -q -k coverage_gap_prompt`
Expected: FAIL — `FileNotFoundError` (no `coverage-gap.md`).

- [ ] **Step 3: Write the prompt**

Create `src/framework_cli/review/agents/coverage-gap.md` with exactly this content:

```markdown
You are `review-coverage-gap`. You review a change to the swiftwater **framework's own
repository** for one thing only: **runtime-coverage completeness** — has a newly
provisioned operational surface been left unexercised by any test? You are the open-world
half of a two-part mechanism. The closed-world half is FWK29: `tests/runtime_coverage/
enumerate.py` mechanically enumerates six surface KINDS (compose overlays, compose
services, Dockerfile stages, scripts, workflow jobs, hooks) from an all-batteries render,
and `tests/runtime_coverage/registry.py` forces every instance to be classified
(EXERCISED / EXEMPT / KNOWN_GAP). Your job is everything that mechanism structurally
cannot see.

BOUNDARIES — you own COVERAGE, nothing else. Do NOT do these other reviewers' jobs:
- `review-architecture` owns whether the DESIGN is sound (coupling, boundaries, layering).
  A poorly-factored-but-tested surface is not your finding.
- `review-observability` / `review-observability-infra` / `review-observability-db` own
  whether a surface is INSTRUMENTED (spans / metrics / logs / dashboards / alerts). A
  surface that is exercised but uninstrumented is theirs, not yours.
- `review-env-parity` owns whether a service/var REACHES every environment. A surface that
  reaches prod but is untested is yours; one that is tested but dev-only is theirs.
Your single question is: **is this provisioned surface exercised by a test that DRIVES it
on its real runtime path?**

WHAT "EXERCISED" MEANS (be strict). A surface is exercised only when a test actually drives
it on the path that gives it value. These do NOT count as exercised when the surface's value
is its live path:
- render-text-checked only (a test asserts the file RENDERS, never that it RUNS);
- a `docker build` that asserts `returncode == 0` but never RUNS the built artifact;
- in-process unit coverage (FastAPI `TestClient`, eager-Celery, a mocked beacon) when the
  point of the surface is the LIVE ASGI / Traefik / broker / worker path.

THE TWO GAPS YOU FLAG (both DIFF-ANCHORED — reason only about surface this change introduces
or touches; do NOT audit the whole pre-existing tree):
1. NEW-KIND surface. Operational surface added under `src/framework_cli/template/` that
   matches NONE of `enumerate.py`'s six rules — so the completeness test stays green while
   the surface ships unexercised. Read `tests/runtime_coverage/enumerate.py` with your tools
   to learn exactly which kinds are already enumerated; flag provisioned surface outside all
   of them (e.g. a systemd unit, a k8s manifest, a Makefile/Taskfile-external target, a new
   `infra/` shape) that no test drives.
2. IN-APP code-path surface. A bootstrap / lifecycle / live-route / worker path the change
   introduces in the template app — `create_app` / lifespan wiring, DB engine/pool lifecycle
   (`dispose_engine`, pre-ping), a new battery route served through Traefik, worker/beat
   tracing — that no test drives on its real runtime path (per the strictness above).

DEFER TO THE REGISTRY. Before flagging any surface of an ENUMERABLE kind, read
`tests/runtime_coverage/registry.py` with your tools. If the surface already has an entry
there — ANY status, including `KNOWN_GAP` with its `FWK<N>` id — it is HANDLED; stay silent.
You only flag a genuinely NEW kind (no enumeration rule) or an unclassified in-app path
(the registry excludes in-app paths by design, so judge those from the change itself). Your
diff is the FULL repository diff: if this same change ALSO adds the matching `registry.py`
entry (or `enumerate.py` rule), the surface is classified — do NOT flag it.

GRADUATION (context, not an action): when the same new KIND recurs across changes, a
maintainer promotes it into a seventh `enumerate.py` rule plus registry entries, moving it
from your open-world judgment to the closed-world ratchet. You do not do this; you just
surface the gap.

Tool & answer discipline: you have read-only tools (`read_file`, `grep`, `glob`) over the
framework repo. Read `enumerate.py`, `registry.py`, the changed template files, and the
relevant tests to decide whether a surface is driven — then STOP and answer. Cite only
files you have ACTUALLY read this run; never assert a test exists or a surface is
classified from memory. If a file is genuinely unreadable, judge from the diff alone rather
than speculating. Your FINAL response is the findings array itself — never emit a
`{"tool_calls": …}` object, a narration, or a claim that tools are unavailable.

Each finding names the surface and which gap it is. `suggestion` should be concrete: either
the test that would exercise the surface on its real path, or — for an enumerable new kind —
the `registry.py` / `enumerate.py` classification it needs.

Return JSON ONLY — your final response is one JSON array parseable by `json.loads`, with no
prose, no preamble, no code fences, and no commentary before or after it; put any rationale
inside a finding's `message`. Output exactly `[]` when there are no findings. Every element
MUST carry all of `path`, `line`, `severity`, `message` (optional `suggestion`); `severity`
is REQUIRED and MUST be exactly one of `high|medium|low|info` — an object missing it
invalidates the entire response. Element shape:
{"path","line","severity","message","suggestion"}. An unexercised newly-provisioned surface
is "medium" (advisory — you never block the gate); use "high" only for a surface whose
unexercised failure would be silent in production (a live route or worker path).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_coverage_gap.py -q -k coverage_gap_prompt`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/agents/coverage-gap.md tests/review/test_coverage_gap.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk30): coverage-gap agent prompt (coverage lens, registry defer, boundaries)"
```

---

## Task 3: Register `coverage-gap` in `_SPECS` + `FRAMEWORK_AGENTS`

**Why:** Make the agent real: a registered spec (agentic, Opus, advisory, file-trigger, framework-only, reviews-template) and a member of the framework self-review set.

**Files:**
- Modify: `src/framework_cli/review/registry.py` (add to `_SPECS`, after the `usability` entry, before the closing `}`)
- Modify: `src/framework_cli/review/context.py:73-80` (`FRAMEWORK_AGENTS`) + the comment above it
- Modify: `tests/review/test_framework_target.py` (6-tuple → 7-tuple)
- Modify: `tests/review/test_context_policy.py` (add to the `agentic` set)
- Test: `tests/review/test_coverage_gap.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/review/test_coverage_gap.py
from framework_cli.review.context import FRAMEWORK_AGENTS
from framework_cli.review.diff import matches_globs
from framework_cli.review.registry import AGENTIC_MODEL, get_agent


def test_coverage_gap_spec_is_advisory_agentic_filetrigger_framework_only():
    spec = get_agent("coverage-gap")
    assert spec.name == "review-coverage-gap"
    assert spec.block_threshold is None          # advisory — never blocks
    assert spec.active_when == "file-trigger"
    assert spec.model == AGENTIC_MODEL
    assert spec.on_push is False
    assert spec.context.strategy == "agentic"
    assert spec.framework_only is True
    assert spec.reviews_template is True
    assert spec.trigger_globs is not None
    assert set(spec.trigger_globs) == {
        "src/framework_cli/template/**",
        "tests/runtime_coverage/**",
    }


def test_coverage_gap_trigger_globs_match_template_and_registry_changes():
    spec = get_agent("coverage-gap")
    assert matches_globs(
        ["src/framework_cli/template/infra/compose/cache.yml.jinja"], spec.trigger_globs
    )
    assert matches_globs(["tests/runtime_coverage/registry.py"], spec.trigger_globs)
    # framework CLI source is NOT a trigger (that's the other five agents' job)
    assert not matches_globs(["src/framework_cli/cli.py"], spec.trigger_globs)


def test_coverage_gap_is_in_framework_agents_only():
    from framework_cli.review.registry import active_agents

    assert "coverage-gap" in FRAMEWORK_AGENTS
    assert "coverage-gap" not in active_agents("pull_request")  # not a project agent
```

NOTE on the glob form: `matches_globs` (review/diff.py) uses `fnmatch`, where `*` already spans `/`. Confirm `"src/framework_cli/template/**"` matches the nested path above when you run the test; if `**`-vs-`*` behaves differently under `fnmatch` on this path, use `"src/framework_cli/template/*"` instead (the existing `observability-infra` agent uses single-`*` globs like `infra/*` for exactly this reason — see `test_observability_split_infra`). The test is the oracle: make the glob value match what passes.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_coverage_gap.py -q -k "spec_is_advisory or trigger_globs_match or framework_agents_only"`
Expected: FAIL — `get_agent("coverage-gap")` raises `KeyError`.

- [ ] **Step 3: Register the spec**

In `src/framework_cli/review/registry.py`, add to `_SPECS` (after the `"usability"` entry):

```python
    # FWK30 — open-world coverage-gap reviewer. Framework-self-review only (reviews the
    # template payload + the FWK29 registry, neither of which exists in a generated
    # project). Advisory + agentic; reads registry.py/enumerate.py via its tools to defer
    # to the closed-world ratchet. Gated to template/registry changes; fed the
    # template-inclusive diff (reviews_template).
    "coverage-gap": AgentSpec(
        "review-coverage-gap",
        _prompt("coverage-gap"),
        None,  # advisory — surfaces, never blocks
        "file-trigger",
        AGENTIC_MODEL,
        trigger_globs=(
            "src/framework_cli/template/**",
            "tests/runtime_coverage/**",
        ),
        context=ContextPolicy("agentic"),
        framework_only=True,
        reviews_template=True,
    ),
```

In `src/framework_cli/review/context.py`, add `"coverage-gap"` to `FRAMEWORK_AGENTS` (keep alphabetical) and extend the comment block to note the exception:

```python
# ... (existing comment) ...
# FWK30 adds the one deliberate exception: `coverage-gap` IS a framework agent that reviews
# the template payload — but only through the runtime-coverage-completeness lens, never for
# general quality (which stays the product's concern). It is `framework_only` so it never
# joins the generated-project review set, and `reviews_template` so it gets the
# template-inclusive diff.
FRAMEWORK_AGENTS: tuple[str, ...] = (
    "application-logic",
    "architecture",
    "coverage-gap",
    "dependency",
    "documentation",
    "security",
    "test-quality",
)
```

In `tests/review/test_framework_target.py`, update the expected tuple in `test_framework_agents_are_the_expected_subset_and_registered`:

```python
    assert FRAMEWORK_AGENTS == (
        "application-logic",
        "architecture",
        "coverage-gap",
        "dependency",
        "documentation",
        "security",
        "test-quality",
    )
```

In `tests/review/test_context_policy.py`, add `"coverage-gap"` to the `agentic` set in `test_every_agent_has_an_explicit_context_strategy`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/review/test_coverage_gap.py tests/review/test_framework_target.py tests/review/test_context_policy.py tests/review/test_registry.py -q`
Expected: PASS. (`test_full_active_sets` still green — `coverage-gap` is `framework_only`, so `_EXPECTED_PR` is unchanged.)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/registry.py src/framework_cli/review/context.py tests/review/test_coverage_gap.py tests/review/test_framework_target.py tests/review/test_context_policy.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk30): register coverage-gap spec + FRAMEWORK_AGENTS membership"
```

---

## Task 4: Per-agent diff scope — feed `coverage-gap` the template-inclusive diff

**Why:** The live `review` command sources `framework_diff()` for the framework target (cli.py:1803), which EXCLUDES `src/framework_cli/template`. The existing per-agent trigger-gate (cli.py:1804) then matches `coverage-gap`'s template globs against that template-excluding diff and ALWAYS skips it. Resolution: a `reviews_template` agent gets the full `pr_diff()` (template + registry + everything), so both the gate and the review see the real change. The other five framework agents are untouched.

**Files:**
- Modify: `src/framework_cli/cli.py:1803` (inside the `review` command)
- Test: `tests/review/test_coverage_gap.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/review/test_coverage_gap.py
def test_reviews_template_agent_sources_full_diff_on_framework_target(monkeypatch):
    """coverage-gap (reviews_template) must be fed pr_diff (template-inclusive), not the
    template-excluding framework_diff — otherwise its template trigger-globs never match."""
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "x")
    template_diff = (
        "diff --git a/src/framework_cli/template/infra/compose/cache.yml.jinja "
        "b/src/framework_cli/template/infra/compose/cache.yml.jinja\n"
        "--- /dev/null\n"
        "+++ b/src/framework_cli/template/infra/compose/cache.yml.jinja\n"
        "@@ -0,0 +1,1 @@\n+services: {}\n"
    )
    seen = {}

    def fake_pr_diff():
        return template_diff

    def fake_framework_diff():
        return ""  # template excluded → empty

    def fake_review_run(diff, spec, force_agentic=False, backend=None):
        seen["diff"] = diff
        seen["agent"] = spec.name
        return []

    monkeypatch.setattr(cli_mod, "pr_diff", fake_pr_diff)
    monkeypatch.setattr(cli_mod, "framework_diff", fake_framework_diff)
    monkeypatch.setattr(cli_mod, "_review_run", fake_review_run)

    from typer.testing import CliRunner
    from framework_cli.cli import app

    result = CliRunner().invoke(
        app, ["review", "coverage-gap", "--target", "framework", "--backend", "api"]
    )
    assert result.exit_code == 0
    # It was NOT skipped as not-triggered, and it saw the template-inclusive diff.
    assert seen.get("agent") == "review-coverage-gap"
    assert "template/infra/compose/cache.yml.jinja" in seen["diff"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_coverage_gap.py -q -k sources_full_diff`
Expected: FAIL — with `framework_diff()` (empty) the trigger-gate skips the agent; `_review_run` is never called, so `seen` is empty.

- [ ] **Step 3: Write minimal implementation**

In `src/framework_cli/cli.py`, change the diff-selection line (currently `diff = framework_diff() if target == "framework" else _review_diff()`) to honor `reviews_template`:

```python
        if target == "framework":
            # The five general framework agents review CLI/tooling source only
            # (framework_diff excludes the template payload). A reviews_template agent
            # (FWK30 coverage-gap) is the deliberate exception — it gets the full,
            # template-inclusive diff so its template/registry trigger-globs match and it
            # can see any same-PR registry classification.
            diff = pr_diff() if spec.reviews_template else framework_diff()
        else:
            diff = _review_diff()
```

(`pr_diff` is already imported in cli.py. The subsequent `matches_globs(changed_files(diff), spec.trigger_globs)` gate and `force_agentic=(target == "framework")` are unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_coverage_gap.py -q -k sources_full_diff`
Expected: PASS.

- [ ] **Step 5: Run the framework-target suite (regression)**

Run: `uv run pytest tests/review/test_framework_target.py -q`
Expected: PASS — the existing agents still source `framework_diff()` (they have `reviews_template=False`).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/cli.py tests/review/test_coverage_gap.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk30): feed reviews_template agent the template-inclusive diff on framework target"
```

---

## Task 5: Framework-shaped eval realize

**Why:** Every existing fixture is generated-project-shaped (`realize_*` runs `render_project`). `coverage-gap` reviews framework SOURCE (`src/framework_cli/template/**.jinja` + `tests/runtime_coverage/registry.py`) — paths that do not exist in a render. Its fixtures need a base that copies those framework subtrees so the patch applies and the agent can read the real `registry.py`/`enumerate.py`. This is production-faithful: on a real PR the agent reviews the raw framework repo, never a render.

**Files:**
- Modify: `src/framework_cli/review/evals.py` (add `_FRAMEWORK_SHAPED_AGENTS`, a `_framework_base(...)` helper, and a branch in `realize_cached`)
- Test: `tests/review/test_coverage_gap.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/review/test_coverage_gap.py
def test_realize_cached_builds_framework_shaped_base_for_coverage_gap(tmp_path):
    """coverage-gap fixtures realize a framework-shaped tree (template + runtime_coverage),
    not a rendered project, so the patch applies and registry.py is readable."""
    from framework_cli.review.evals import Fixture, realize_cached

    patch = (
        "--- a/src/framework_cli/template/infra/compose/observability.yml\n"
        "+++ b/src/framework_cli/template/infra/compose/observability.yml\n"
        "@@ -1,1 +1,2 @@\n"
        " services:\n"
        "+  # seeded comment for the fixture\n"
    )
    fx = Fixture(
        agent="coverage-gap", kind="bad", name="seed", batteries=(),
        patch=patch, seeded_file="src/framework_cli/template/infra/compose/observability.yml",
    )
    root, diff = realize_cached(fx, {}, tmp_path)
    # The framework subtrees are present in the realized base.
    assert (root / "tests" / "runtime_coverage" / "registry.py").is_file()
    assert (root / "src" / "framework_cli" / "template").is_dir()
    # The seeded change is in the diff (proves the patch applied to this base).
    assert "seeded comment for the fixture" in diff
```

NOTE: the `patch` above is illustrative. When implementing, pick a REAL template file + a hunk whose `@@` counts are correct (see [[eval-fixture-patch-truncation]]); regenerate it by applying to the copied base and running `git diff` rather than hand-counting. If `observability.yml`'s first line is not `services:`, adjust the context line to the file's actual content.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_coverage_gap.py -q -k framework_shaped_base`
Expected: FAIL — `realize_cached` renders a generated project; `git apply` fails (path `src/framework_cli/template/...` absent) → `CalledProcessError`.

- [ ] **Step 3: Write the framework-shaped realize**

In `src/framework_cli/review/evals.py`, add near the top (after imports):

```python
# Agents whose review target is the framework SOURCE (template payload + the FWK29 registry),
# not a rendered project. Their fixtures realize a framework-shaped base, not a render.
_FRAMEWORK_SHAPED_AGENTS = frozenset({"coverage-gap"})

# Repo subtrees a framework-shaped fixture needs (relative to the framework repo root).
_FRAMEWORK_SUBTREES = ("src/framework_cli/template", "tests/runtime_coverage")


def _framework_repo_root() -> Path:
    # evals.py lives at <root>/src/framework_cli/review/evals.py
    return Path(__file__).resolve().parents[3]


def _framework_base(base: Path) -> None:
    """Populate `base` with a minimal framework-shaped tree and an initial git commit."""
    root = _framework_repo_root()
    for sub in _FRAMEWORK_SUBTREES:
        src = root / sub
        dst = base / sub
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
    subprocess.run(["git", "init", "-q"], cwd=base, check=True)
    subprocess.run(["git", "config", "gc.auto", "0"], cwd=base, check=True)  # GC race guard
    subprocess.run(["git", "add", "-A"], cwd=base, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"],
        cwd=base,
        check=True,
    )
```

Then branch at the top of `realize_cached`:

```python
def realize_cached(
    fx: Fixture, cache: dict[tuple[str, ...], Path], base_dir: Path
) -> tuple[Path, str]:
    """Realize `fx` reusing a per-combo rendered+committed base. `base_dir` is a
    caller-owned tempdir; `cache` maps battery-combo → committed base path.

    Framework-shaped agents (e.g. coverage-gap) realize a copy of the framework's own
    template + runtime_coverage subtrees instead of a render — they review framework
    source, not generated output."""
    if fx.agent in _FRAMEWORK_SHAPED_AGENTS:
        cache_key = ("__framework__",)
        if cache_key not in cache:
            base = base_dir / "framework-base"
            base.mkdir(parents=True, exist_ok=True)
            _framework_base(base)
            cache[cache_key] = base  # type: ignore[index]
        work = base_dir / f"fx-{fx.agent}-{fx.kind}-{fx.name}"
        shutil.copytree(cache[cache_key], work)
        subprocess.run(
            ["git", "apply", "-"], cwd=work, input=fx.patch, text=True, check=True
        )
        diff = subprocess.run(
            ["git", "diff"], cwd=work, capture_output=True, text=True, check=True
        ).stdout
        return work, diff
    # ... existing render-based body unchanged ...
```

(`cache` is typed `dict[tuple[str, ...], Path]`; the `("__framework__",)` key is a valid `tuple[str, ...]` and won't collide with a battery combo.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_coverage_gap.py -q -k framework_shaped_base`
Expected: PASS.

- [ ] **Step 5: Run the existing realize/eval-harness suite (regression)**

Run: `uv run pytest tests/review/test_fixture_realize.py tests/review/test_evals.py -q`
Expected: PASS — the render-based path is unchanged for all other agents.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/evals.py tests/review/test_coverage_gap.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk30): framework-shaped eval realize for coverage-gap fixtures"
```

---

## Task 6: Eval fixture pair (positive flag + negative defer) + thresholds

**Why:** Calibrate the defer-to-registry behavior: a positive (a template surface added with NO classification → must flag) and a negative (the same surface added AND classified in the same change → must stay silent because the full-diff seed carries the registry entry).

**Design of the pair (both anchored on a REAL enumerable surface):**
- **bad/unexercised-cache-overlay** — `change.patch` adds a new compose overlay file under `src/framework_cli/template/infra/compose/` (a NEW `*.yml.jinja` surface) and adds NO `registry.py` entry. The agent must flag the unclassified overlay. `expect.json` `{"file": "<the overlay path>"}`.
- **good/classified-cache-overlay** — `change.patch` adds the SAME overlay AND a matching `SurfaceClass(...)` entry in `tests/runtime_coverage/registry.py` (classified, e.g. EXEMPT or KNOWN_GAP with an FWK id). The agent must stay silent (defer to the same-PR classification).

**Files:**
- Create: `tests/eval/fixtures/coverage-gap/bad/unexercised-cache-overlay/fixture.yaml`
- Create: `tests/eval/fixtures/coverage-gap/bad/unexercised-cache-overlay/change.patch`
- Create: `tests/eval/fixtures/coverage-gap/bad/unexercised-cache-overlay/expect.json`
- Create: `tests/eval/fixtures/coverage-gap/good/classified-cache-overlay/fixture.yaml`
- Create: `tests/eval/fixtures/coverage-gap/good/classified-cache-overlay/change.patch`
- Modify: `tests/eval/fixtures/thresholds.yaml`

- [ ] **Step 1: Author `fixture.yaml` for both cases**

Both fixtures use no batteries (the framework-shaped base ignores batteries). Write to each `fixture.yaml`:

```yaml
batteries: []
```

- [ ] **Step 2: Author the `bad` patch by realizing the base and diffing (do NOT hand-count hunks)**

Build the base once and generate the patch from a real `git diff` so hunk headers are correct (see [[eval-fixture-patch-truncation]]). In a scratch dir:

```bash
# Reproduce the framework-shaped base, add a NEW overlay file, diff.
# (mirror evals._framework_base: copy src/framework_cli/template + tests/runtime_coverage)
```

The `bad` change adds ONE new file, e.g. `src/framework_cli/template/infra/compose/cache.yml.jinja`:

```yaml
services:
  cache:
    image: redis:7
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
```

Because a brand-new file produces an empty `git diff` until staged (see [[new-file-eval-fixtures-empty-diff]]), generate the patch with `git add -A` then `git diff --staged` so the new file appears, and save that as `change.patch`. coverage-gap is agentic, so it detects new-file additions (the empty-untracked-diff caveat only bites non-agentic agents — but the patch must still contain the file, so use `--staged`).

`expect.json`:

```json
{"file": "src/framework_cli/template/infra/compose/cache.yml.jinja"}
```

- [ ] **Step 3: Author the `good` patch (same overlay + a registry classification)**

The `good` change adds the SAME `cache.yml.jinja` AND a matching entry in `tests/runtime_coverage/registry.py` — e.g. inside `REGISTRY`:

```python
    SurfaceClass(
        "overlay:cache.yml.jinja",
        "infra/compose/cache.yml.jinja",
        _EM,
        "fixture: classified in the same change — coverage-gap must defer",
    ),
```

Generate `change.patch` the same way (`git add -A` → `git diff --staged`) so it carries both the new overlay file and the `registry.py` hunk. No `expect.json` (good fixtures have none).

- [ ] **Step 4: Validate the patches are well-formed**

Run:
```bash
uv run python -c "from framework_cli.review.evals import validate_patch_hunks, load_fixtures; from pathlib import Path; \
fx=load_fixtures(Path('tests/eval/fixtures')); cg=[f for f in fx if f.agent=='coverage-gap']; \
print('loaded', [(f.kind,f.name) for f in cg]); \
[print('HUNK ERRORS', f.name, validate_patch_hunks(f.patch)) for f in cg]"
```
Expected: both fixtures load (one `bad`, one `good`); `validate_patch_hunks` returns `[]` for each.

- [ ] **Step 5: Add the threshold entry**

In `tests/eval/fixtures/thresholds.yaml`, add (a single bad + single good fixture means a binary recall/fp; keep the defaults explicit):

```yaml
coverage-gap:
  recall_min: 0.67
  fp_max: 0.34
```

- [ ] **Step 6: Confirm the fixtures realize + diff cleanly (no model call)**

Run:
```bash
uv run python -c "import tempfile; from pathlib import Path; \
from framework_cli.review.evals import load_fixtures, realize_cached; \
fx=[f for f in load_fixtures(Path('tests/eval/fixtures')) if f.agent=='coverage-gap']; \
d=Path(tempfile.mkdtemp()); cache={}; \
[print(f.kind, f.name, 'cache.yml.jinja' in rdiff, '/registry.py' in rdiff) \
 for f in fx for (rroot,rdiff) in [realize_cached(f, cache, d)]]"
```
Expected: `bad` → overlay True, registry False; `good` → overlay True, registry True.

- [ ] **Step 7: Commit**

```bash
git add tests/eval/fixtures/coverage-gap tests/eval/fixtures/thresholds.yaml PLAN.md ACTION_LOG.md
git commit -m "test(fwk30): coverage-gap eval fixture pair (flag unclassified / defer to same-PR registry)"
```

---

## Task 7: Full review-suite gate, register-completeness, and live eval calibration

**Why:** A new review agent must pass ALL of `tests/review/` (not just the registry tests) and the quality gate — see [[registering-review-agent-gate-completeness]]. Then a live eval run calibrates the thresholds before the branch-end review.

**Files:** none new — verification + any fixups the gate surfaces.

- [ ] **Step 1: Run the whole review suite**

Run: `uv run pytest tests/review/ -q`
Expected: PASS. Watch specifically: `test_registry.py` (`_EXPECTED_PR` unchanged), `test_context_policy.py` (coverage-gap classified agentic), `test_framework_target.py` (7-tuple), `test_evals.py`, `test_fixtures_wellformed.py`, `test_cli_review_wiring.py`. Capture pytest's OWN exit code — do not pipe through `tail` (it masks failures; see [[registering-review-agent-gate-completeness]]).

- [ ] **Step 2: Run the quality gate**

Run:
```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green. (`ruff format --check` catches long-line reflows that `ruff check` misses — see [[ruff-format-check-after-inline-edits]].)

- [ ] **Step 3: Live eval calibration (requires the eval key)**

Confirm `ANTHROPIC_EVAL_API_KEY` is SET (presence only — never print it; see [[feedback_secrets-in-files]]). Then:

```bash
uv run framework eval coverage-gap --backend api --repeat 3 --require-fixtures --findings-out /var/tmp/cg-eval
```
Expected: `review-coverage-gap   recall <r>  fp <f>   PASS`. The `bad` overlay should be flagged (recall → 1.00) and the `good` classified overlay should be silent (fp → 0.00). If the agent over-flags the `good` case or misses the `bad` case, the lever is the PROMPT, not the threshold (see [[reviewer-tuning-is-prompts-not-thresholds]]): inspect `/var/tmp/cg-eval` and tighten `coverage-gap.md`, then re-run. Use `TMPDIR=/var/tmp` if running the full suite alongside (see [[full-suite-exhausts-tmp-tmpfs-use-var-tmp]]).

- [ ] **Step 4: Record the scorecard**

Write a dated scorecard note under `docs/superpowers/eval-scorecards/` capturing the coverage-gap recall/fp and the prompt version, per the repo convention.

- [ ] **Step 5: Spec-compliance review (Sonnet) + code-quality review (Opus)**

Dispatch per the review-model policy: a spec-compliance review (Sonnet) against the design spec, then a code-quality review (Opus) of the whole branch diff. Address findings. Controller verifies the implementers committed (they stop before the final commit — see [[subagent-implementers-stop-before-commit]]).

- [ ] **Step 6: Finish the branch**

Update `PLAN.md` (tick FWK30 → Done) + `ACTION_LOG.md`, then open the PR (no release — this is test/review-infra only, no template-runtime or version change). Required checks: `gate` + `build` + `render-complete`. After merge, grep master for a `coverage-gap` marker (see [[verify-master-content-after-pr-merge]]).

---

## Self-Review (completed during planning)

- **Spec coverage:** mandate both halves → Task 2 prompt (gaps 1+2, diff-anchored) ✓; coverage lens/boundaries → Task 2 ✓; defer-to-registry by reading source → Task 2 + agentic tools (no code change needed — `read_file` already exists) ✓; full-diff seed via per-agent scope → Task 4 ✓; glob-gated activation → Task 3 trigger_globs + the existing cli.py:1804 gate (already present) ✓; advisory → Task 3 (`block_threshold=None`) ✓; framework-only (not in project set) → Task 1 ✓; eval pair (E1 framework-shaped) → Tasks 5+6 ✓; registration-completeness → Task 7 ✓.
- **Placeholder scan:** the prompt is given in full (Task 2); fixture patches are generated-from-diff with explicit commands rather than hand-pasted (correct per the patch-truncation gotcha) — not a placeholder but a deliberate generation step.
- **Type consistency:** `framework_only` / `reviews_template` used identically in Tasks 1, 3, 4; `_FRAMEWORK_SHAPED_AGENTS` / `_framework_base` / `realize_cached` consistent across Tasks 5–6; agent key `coverage-gap` and spec name `review-coverage-gap` consistent throughout.
- **Open verification deferred to implementation (flagged inline):** the exact `**`-vs-`*` glob form (Task 3 note — the test is the oracle); the real template file + correct hunk counts for the fixtures (Task 6 — generate from `git diff`).
