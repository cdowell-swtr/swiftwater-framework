# FWK4 — Reviewer Self-Audit Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the Plan 21 audit→synthesis→adversarial reviewer-tuning method as a repeatable, in-process `framework reviewer-audit` command, and single-source the shared reviewer rubric via runtime prompt assembly so consistency for the centralized blocks cannot drift.

**Architecture:** Phase 0 extracts the duplicated-and-drifted shared rubric + output/findings-schema contract into one canonical source composed with each agent's domain block at prompt-build time (the existing `request.py` seam). Phases 1–3 build a deterministic, checkpoint-resumable Python orchestrator on the existing LiteLLM backend seam (`backend.messages.create`) that runs audit → cross-agent reconciliation → adversarial-refutation stages over 1..N reviewers and emits a vetted changelist + a dry-run git-applyable apply-preview patch. No Claude Code Workflow dependency; no auto-apply.

**Tech Stack:** Python 3.12, Typer CLI, `uv` tooling, pytest, LiteLLM-backed `ApiBackend`/`SubagentBackend`, the review engine's `checkpoint.py` primitives.

**Spec:** `docs/superpowers/specs/2026-06-19-fwk4-reviewer-self-audit-design.md`

**Execution policy (this repo):**
- Review-model policy ([[subagent-review-model-pattern]]): implementers → Sonnet (Haiku for trivial); spec-compliance review → Sonnet; code-quality + branch-end whole-branch review → **Opus**. Audit/reconcile/adversarial agents (the *tool's* runtime agents) run on **Opus** (`AGENTIC_MODEL`).
- Commit cadence ([[gate-cadence-framework-slices]]): these are review-infra files; the per-commit gate over-fires ~18 app-agents on them. Use the controller skip-marker recipe ([[controller-skip-marker-recipe]]) per task, **separate `git add` then `git commit` calls** ([[commit-gate-hook-timing]]), and one branch-end Opus whole-branch review.
- Before each commit, tick the task in `PLAN.md` and append an `ACTION_LOG.md` entry (the commit-gate hook requires one staged).
- Test/maintainer-tooling only → **no release, no template payload**. Reviewers are framework-internal (`src/framework_cli/review/`), absent from generated projects, so Phase 0 cannot change the rendered payload.
- Run the gate locally with `TMPDIR=/var/tmp` for any full run ([[full-suite-exhausts-tmp-tmpfs-use-var-tmp]]); the LLM-bearing pipeline tests in this plan use a **stubbed backend** and need no key or quota.

---

## File Structure

**Phase 0 — rubric/prompt centralization (runtime assembly):**
- Create: `src/framework_cli/review/rubric.md` — the canonical shared rubric body (5 sections).
- Create: `src/framework_cli/review/preamble.py` — `build_preamble(spec)` composing rubric body + derived advisory note + output/findings-schema contract.
- Modify: `src/framework_cli/review/registry.py` — add optional `severity_enum` field to `AgentSpec`; add `composed_prompt(spec)` accessor.
- Modify: `src/framework_cli/review/request.py` — compose `preamble + domain` at the system-prompt seam.
- Modify: `src/framework_cli/review/agents/*.md` (×21) — trim to domain-block-only.
- Create: `tests/review/test_preamble.py`, `tests/review/test_prompt_assembly.py`.

**Phase 1 — audit pipeline core:**
- Create: `src/framework_cli/review/audit/__init__.py`
- Create: `src/framework_cli/review/audit/changelist.py` — typed changelist dataclasses + JSON (de)serialization.
- Create: `src/framework_cli/review/audit/brief.py` — `build_audit_brief(...)`.
- Create: `src/framework_cli/review/audit/orchestrator.py` — deterministic checkpointed work-queue driver.
- Create: `src/framework_cli/review/audit/stages.py` — `audit_agent(...)` (Stage 1) — reconcile/refute added in Phase 2.
- Create: `tests/review/audit/test_changelist.py`, `test_brief.py`, `test_orchestrator.py`, `test_stages.py`.

**Phase 2 — reconciliation + adversarial spine:**
- Modify: `src/framework_cli/review/audit/stages.py` — add `reconcile(...)` (Stage 2) + `refute(...)` (Stage 3).
- Create: `src/framework_cli/review/audit/pipeline.py` — `run_audit(...)` wiring all stages via the orchestrator.
- Create: `tests/review/audit/test_pipeline.py`.

**Phase 3 — CLI + apply-preview + runbook:**
- Create: `src/framework_cli/review/audit/preview.py` — `render_patch(changelist, root)`.
- Modify: `src/framework_cli/cli.py` — `reviewer-audit` command.
- Create: `documentation/runbooks/reviewer-audit.md` (+ mkdocs nav entry).
- Create: `tests/review/audit/test_preview.py`, `tests/test_cli_reviewer_audit.py`.

**Shared test helper:**
- Create: `tests/review/audit/conftest.py` — `StubBackend` (a `.messages.create`-shaped fake returning scripted `Message`s) so pipeline tests need no key/quota.

---

# Phase 0 — Rubric/prompt centralization

**Outcome:** one canonical rubric source, composed at runtime; 21 domain-only prompt files; eval suite green (the behavior-preservation oracle). Independently mergeable.

### Task 0.1: Canonical rubric source file

**Files:**
- Create: `src/framework_cli/review/rubric.md`

- [ ] **Step 1: Create the canonical rubric body**

Copy the five canonical sections **verbatim** from `docs/superpowers/specs/plan21-rubric-final.md` (lines 9–82): `## Severity (one scale, consistent across all agents)`, `## Codebase-bar principle (the dominant false-positive guard)`, `## Internal consistency within one review`, `## Scope discipline (one owner per class)`, `## Grounding & diff-awareness`.

**Two deliberate changes from the spec doc when copying:**
1. **Drop the hardcoded advisory paragraph** under Severity (the "**Advisory agents** … currently `dependency`, `documentation`, `usability`" sentence — it is already stale, missing `observability-db`/`coverage-gap`). The advisory note is injected per-agent by `preamble.py` (Task 0.2), derived from `block_threshold`.
2. **Do not include the `## Output` section.** The output/findings-schema contract is parameterized per-agent (severity enum) and appended by `preamble.py`.

The file is plain Markdown (no front-matter, no template braces). It is framework source, not template payload.

- [ ] **Step 2: Verify it loads as a package resource**

Run: `uv run python -c "from importlib.resources import files; print(len((files('framework_cli.review') / 'rubric.md').read_text()))"`
Expected: a positive integer (the file is on the package path).

- [ ] **Step 3: Commit**

```bash
git add src/framework_cli/review/rubric.md PLAN.md ACTION_LOG.md
```
Then a separate commit call (per [[commit-gate-hook-timing]]):
```bash
git commit -m "FWK4 P0: canonical shared reviewer rubric source"
```

---

### Task 0.2: Preamble builder

**Files:**
- Create: `src/framework_cli/review/preamble.py`
- Test: `tests/review/test_preamble.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_preamble.py
from framework_cli.review.preamble import build_preamble, severity_enum_for
from framework_cli.review.registry import get_agent


def test_severity_enum_full_ladder_for_blocking_agent():
    assert severity_enum_for(get_agent("security")) == "high|medium|low|info"


def test_severity_enum_capped_for_advisory_agent():
    # usability is advisory (block_threshold is None) with no override
    assert severity_enum_for(get_agent("usability")) == "low|info"


def test_severity_enum_respects_override():
    # dependency is advisory but historically allows high|low|info (no medium)
    assert severity_enum_for(get_agent("dependency")) == "high|low|info"


def test_preamble_contains_rubric_core_and_output_contract():
    text = build_preamble(get_agent("security"))
    assert "## Severity (one scale, consistent across all agents)" in text
    assert "## Codebase-bar principle" in text
    assert "## Grounding & diff-awareness" in text
    assert "Return **JSON ONLY**" in text
    assert '"severity": "high|medium|low|info"' in text


def test_preamble_advisory_note_only_for_advisory_agents():
    blocking = build_preamble(get_agent("security"))
    advisory = build_preamble(get_agent("usability"))
    assert "ADVISORY agent" not in blocking
    assert "ADVISORY agent" in advisory
    assert "NEVER emit high/medium" in advisory
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/review/test_preamble.py -v`
Expected: FAIL — `ModuleNotFoundError: framework_cli.review.preamble`.

- [ ] **Step 3: Implement `preamble.py`**

```python
# src/framework_cli/review/preamble.py
"""Compose the shared reviewer preamble (rubric + output contract) per agent.

The rubric body is single-sourced in `rubric.md`; the only per-agent variation in
the shared blocks is the allowed severity enum, derived from `block_threshold`
(advisory → low|info) with an optional `AgentSpec.severity_enum` override. Composed
with the agent's domain block at prompt-build time (see `request.py`)."""

from __future__ import annotations

from importlib.resources import files

from framework_cli.review.registry import AgentSpec

_RUBRIC = (files("framework_cli.review") / "rubric.md").read_text()

_ADVISORY_NOTE = (
    "\n**You are an ADVISORY agent** (registry `block_threshold` is `None`): cap every "
    "finding at the severities in your output contract and NEVER emit high/medium unless "
    "your contract lists them. You surface observations by design; an info/low finding on "
    "otherwise-clean code is not a false positive for you.\n"
)

_OUTPUT_CONTRACT = (
    "\n## Output\n"
    "Return **JSON ONLY** — a single JSON array, no prose, no code fences. Each element:\n"
    '`{{"path": "<file path from the diff>", "line": <integer>, '
    '"severity": "{enum}", "message": "<what is wrong and why it matters>", '
    '"suggestion": "<concrete fix, optional>"}}`. '
    "Every element MUST include a `severity` field. Output exactly `[]` when there are no findings.\n"
)


def severity_enum_for(spec: AgentSpec) -> str:
    if spec.severity_enum is not None:
        return "|".join(spec.severity_enum)
    if spec.block_threshold is None:
        return "low|info"
    return "high|medium|low|info"


def build_preamble(spec: AgentSpec) -> str:
    parts = [_RUBRIC.rstrip()]
    if spec.block_threshold is None:
        parts.append(_ADVISORY_NOTE)
    parts.append(_OUTPUT_CONTRACT.format(enum=severity_enum_for(spec)))
    return "\n".join(parts)
```

Note: this imports `AgentSpec` from `registry`; `registry` must NOT import `preamble` (avoid a cycle — composition lives in `request.py`/an accessor, Task 0.3/0.4). The `severity_enum` field is added in Task 0.3; if running tests before then, expect an `AttributeError` until 0.3 lands — implement 0.3 first if your runner needs green between every task. (Order 0.3 → 0.2 if preferred; the test references `severity_enum`.)

- [ ] **Step 4: Run the test to verify it passes** (after Task 0.3's field exists)

Run: `uv run pytest tests/review/test_preamble.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/preamble.py tests/review/test_preamble.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P0: per-agent preamble builder (rubric + derived output contract)"
```

---

### Task 0.3: `severity_enum` field + composed-prompt accessor

**Files:**
- Modify: `src/framework_cli/review/registry.py`
- Test: `tests/review/test_prompt_assembly.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_prompt_assembly.py
from framework_cli.review.registry import agent_names, composed_prompt, get_agent

_CENTRALIZED_HEADERS = (
    "## Severity (one scale",
    "## Codebase-bar principle",
    "## Internal consistency within one review",
    "## Grounding & diff-awareness",
    "## Output",
)


def test_composed_prompt_has_rubric_then_domain():
    text = composed_prompt(get_agent("security"))
    assert "## Severity (one scale, consistent across all agents)" in text
    assert "## Your domain: `review-security`" in text
    # rubric precedes the domain block
    assert text.index("## Severity") < text.index("## Your domain")


def test_domain_files_do_not_redefine_centralized_sections():
    # After the trim (Tasks 0.5/0.6), each on-disk domain file must NOT re-introduce
    # a centralized section — consistency for those blocks is structural.
    for name in agent_names():
        domain = get_agent(name).prompt  # the raw on-disk domain file
        for header in _CENTRALIZED_HEADERS:
            assert header not in domain, f"{name}.md re-defines a centralized section: {header}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_prompt_assembly.py -v`
Expected: FAIL — `ImportError: cannot import name 'composed_prompt'` (and the second test would fail until the trim).

- [ ] **Step 3: Add the field + accessor in `registry.py`**

Add to the `AgentSpec` dataclass (after `reviews_template`):
```python
    # Override the output-contract severity enum (default derives from block_threshold:
    # advisory → low|info, blocking → high|medium|low|info). Set only for the bespoke
    # cases (e.g. dependency's high|low|info — advisory but allows high).
    severity_enum: tuple[str, ...] | None = None
```

Add `severity_enum=("high", "low", "info")` to the `dependency` spec (preserving its current contract).

Add the accessor at the bottom of `registry.py`:
```python
def composed_prompt(spec: AgentSpec) -> str:
    """The full system prompt: shared preamble (rubric + output contract) + the agent's
    domain block (`spec.prompt`, loaded from agents/<name>.md)."""
    from framework_cli.review.preamble import build_preamble  # local: avoid import cycle

    return f"{build_preamble(spec)}\n\n{spec.prompt}"
```

- [ ] **Step 4: Run the first assembly test (domain-trim test still red until 0.5/0.6)**

Run: `uv run pytest tests/review/test_prompt_assembly.py::test_composed_prompt_has_rubric_then_domain -v`
Expected: PASS (the second test stays RED until the trim lands — that is its purpose).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/registry.py tests/review/test_prompt_assembly.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P0: AgentSpec.severity_enum + composed_prompt accessor"
```

---

### Task 0.4: Compose at the prompt-build seam

**Files:**
- Modify: `src/framework_cli/review/request.py:54` and `:125`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_prompt_assembly.py
from framework_cli.review.context import Bundle
from framework_cli.review.registry import composed_prompt, get_agent
from framework_cli.review.request import build_agentic_request, build_review_request


def test_review_request_system_carries_composed_prompt(tmp_path):
    spec = get_agent("security")
    bundle = Bundle(diff="--- a\n+++ b\n", context_files=[], truncated=False, decisions=())
    req = build_review_request(bundle, spec, root=tmp_path)
    system_text = req.system[-1]["text"]
    assert system_text == composed_prompt(spec)


def test_agentic_request_system_carries_composed_prompt(tmp_path):
    spec = get_agent("architecture")
    req = build_agentic_request("--- a\n+++ b\n", spec, root=tmp_path, max_turns=8)
    assert req.system[-1]["text"] == composed_prompt(spec)
```

(Check `Bundle`'s exact constructor in `src/framework_cli/review/context.py` and adjust the kwargs if they differ; the test only needs a minimal valid bundle.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_prompt_assembly.py -k composed_prompt_via_request -v` (use the two new test names)
Expected: FAIL — `req.system[-1]["text"]` equals the bare `spec.prompt`, not the composed prompt.

- [ ] **Step 3: Implement — compose at both seams**

In `request.py`, add an import:
```python
from framework_cli.review.registry import AgentSpec, composed_prompt
```
Replace `system.append({"type": "text", "text": spec.prompt})` in `build_review_request` (line ~54) **and** in `build_agentic_request` (line ~125) with:
```python
        system.append({"type": "text", "text": composed_prompt(spec)})
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_prompt_assembly.py -v`
Expected: the two new tests PASS (the domain-trim test still RED until 0.5/0.6).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/request.py tests/review/test_prompt_assembly.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P0: compose preamble + domain at the prompt-build seam"
```

---

### Task 0.5: Trim the reference agent (worked example: `security.md`)

**Files:**
- Modify: `src/framework_cli/review/agents/security.md`

- [ ] **Step 1: Apply the trim transformation**

The transformation rule for **every** agent file: delete the centralized sections now supplied by the preamble — `## Severity …`, `## Codebase-bar principle …`, `## Internal consistency …`, `## Scope discipline …`, `## Grounding …`, and `## Output`. **Keep** the opening identity line and everything from `## Your domain: …` onward, and fold any *genuinely agent-specific* note from the deleted sections (one not already covered by the canonical rubric in `rubric.md`) into the `## Your domain` block.

For `security.md`, the trimmed result is:
```markdown
You are `review-security`, a precise application-security reviewer. The shared reviewer rubric
(severity, the codebase-bar, internal consistency, scope, grounding) is supplied above; your
security-specific domain follows.

## Your domain: `review-security`
Review ONLY the added/modified lines in the given unified diff; do not reach into unchanged code
outside the diff (`lru_cache`, `env_file`, `model_dump`, etc.). Flag, on a specific changed line:

- authentication / authorization flaws (broken access control)
- injection (SQL, command, template, path)
- a committed/leaked **secret VALUE** — a hardcoded default, a key in code/config, or a secret
  written into a logged field. A **high** "secret-exposing" finding requires an ACTUAL secret value
  present on a changed line, **not** the mere presence or handling of a secret-typed field (an
  env-sourced `api_secret_key: str` with no default is the sanctioned, clean idiom — do NOT flag it).
- dependencies with a known, **verified** CVE (cite only a CVE you have grounded, never from memory)
- OWASP Top 10: cryptographic failures, insecure design, security misconfiguration, SSRF.

Domain severity notes (the shared scale above governs): **never** raise hardening to high/medium —
`SecretStr`, `min_length`, secret rotation, and `.env` handling are **info at most**, because the
template itself omits them.
```

- [ ] **Step 2: Confirm the structural guard passes for security**

Run: `uv run pytest "tests/review/test_prompt_assembly.py::test_domain_files_do_not_redefine_centralized_sections" -v`
Expected: still FAILs overall (other 20 not yet trimmed) but the failure message must NOT name `security`.

- [ ] **Step 3: Confirm security's composed prompt is well-formed**

Run: `uv run python -c "from framework_cli.review.registry import composed_prompt, get_agent; t=composed_prompt(get_agent('security')); assert '## Severity' in t and '## Your domain' in t and t.count('## Output')==1; print('ok')"`
Expected: `ok` (exactly one Output section — from the preamble, none left in the domain file).

- [ ] **Step 4: Re-confirm security's eval is unaffected** (behavior-preservation oracle; needs a backend — skip-neutral without a key)

Run: `FRAMEWORK_REVIEW_BACKEND=subagent uv run framework eval security --repeat 1`
Expected: security recall/fp unchanged vs. baseline (PASS). If no backend is available, defer to the Task 0.7 batch re-confirm and note it.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/agents/security.md PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P0: trim security.md to domain-only (worked example)"
```

---

### Task 0.6: Trim the remaining 20 agent files

**Files (Modify, one trim each, same transformation rule as Task 0.5):**
`application-logic`, `accessibility`, `api-design`, `architecture`, `compliance`, `contracts`, `coverage-gap`, `data-integrity`, `data-lineage`, `dependency`, `documentation`, `env-parity`, `observability`, `observability-db`, `observability-fe`, `observability-infra`, `performance`, `privacy`, `test-quality`, `usability`.

- [ ] **Step 1: Apply the trim rule to each file**

For each `agents/<name>.md`: delete the six centralized sections (`## Severity`, `## Codebase-bar principle`, `## Internal consistency`, `## Scope discipline`, `## Grounding`, `## Output` — match on the actual header text in each file, which varies, e.g. `## Severity (advisory agent — capped)`, `## Scope & grounding`, `## Grounding & no fabrication`), keep the identity line + `## Your domain` onward, and fold any genuinely-unique deleted note into `## Your domain`. **Do not delete the per-agent domain content.** When a section is a hybrid (e.g. `## Scope & grounding` mixing a domain-specific scope note with the generic grounding text), keep the domain-specific clause in the domain block and drop the generic half.

- [ ] **Step 2: Run the structural guard across all 21**

Run: `uv run pytest "tests/review/test_prompt_assembly.py::test_domain_files_do_not_redefine_centralized_sections" -v`
Expected: PASS — no domain file re-introduces a centralized header.

- [ ] **Step 3: Confirm every composed prompt is well-formed**

Run:
```bash
uv run python -c "
from framework_cli.review.registry import agent_names, composed_prompt, get_agent
for n in agent_names():
    t = composed_prompt(get_agent(n))
    assert t.count('## Output') == 1, (n, 'output count', t.count('## Output'))
    assert '## Severity' in t and '## Your domain' in t, (n, 'missing section')
print('all', len(agent_names()), 'composed prompts well-formed')
"
```
Expected: `all 21 composed prompts well-formed`.

- [ ] **Step 4: Run the full review test suite (no LLM calls — structure/registry only)**

Run: `uv run pytest tests/review/test_registry.py tests/review/test_context_policy.py tests/review/test_prompt_assembly.py tests/review/test_preamble.py tests/test_reviewer_reference.py -q`
Expected: PASS. (`test_reviewer_reference.py` is registry-driven; if it reads `spec.prompt`, confirm it still passes or update `gen_reviewer_reference.py` to read `composed_prompt` — see Task 0.8.)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/agents PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P0: trim remaining 20 agent prompts to domain-only"
```

---

### Task 0.7: Eval re-confirmation sweep (behavior preservation)

**Files:** none (verification task; needs a backend — skip-neutral without a key).

- [ ] **Step 1: Run the full eval suite on the free backend**

Run: `TMPDIR=/var/tmp FRAMEWORK_REVIEW_BACKEND=subagent uv run framework eval --repeat 1`
Expected: every agent's recall/fp within its `thresholds.yaml` band (PASS), i.e. the composed prompts are behavior-equivalent to the pre-trim concatenation. Investigate any agent whose recall dropped or fp rose — that signals a domain note was lost in the trim (restore it into the domain block) **or** the agent now inherits a fuller rubric than before and genuinely shifted (acceptable only if the new behavior is correct; record the decision in `ACTION_LOG.md`).

- [ ] **Step 2: Spot-confirm one agent on the paid backend** (optional, cheap)

Run: `uv run framework eval security --repeat 1 --backend api` (requires `ANTHROPIC_EVAL_API_KEY`).
Expected: PASS. Skip-neutral if no key.

- [ ] **Step 3: Record the sweep result**

Append an `ACTION_LOG.md` entry with the per-agent recall/fp deltas (or "no deltas"). No commit of code; this is the oracle gate before Phase 1.

---

### Task 0.8: Reviewer-reference doc + integrity reconciliation

**Files:**
- Modify (if needed): `scripts/gen_reviewer_reference.py`, `src/framework_cli/review/reference_doc.py`
- Possibly Modify: `tests/integrity/` classification (new `rubric.md` is framework source, not template payload — confirm it is not picked up by any template/integrity scrape).

- [ ] **Step 1: Regenerate the reviewer reference and check sync**

Run: `uv run python scripts/gen_reviewer_reference.py && uv run pytest tests/test_reviewer_reference.py -q`
Expected: PASS. If the generator or its test reads each agent's prompt for trigger/scope facts, confirm it still resolves (it reads the registry + `_BLURBS`, not the rubric body, so it should be unaffected — verify).

- [ ] **Step 2: Confirm no integrity/coverage surface regression**

Run: `uv run pytest tests/integrity -q tests/runtime_coverage -q`
Expected: PASS. `rubric.md`/`preamble.py` live under `src/framework_cli/review/` (framework source), not `template/` or `infra/`/`scripts/`/`.github/workflows`, so neither the FWK7 reverse-integrity check nor the FWK29 runtime-coverage registry should require a new classification. If either fails, classify per its existing rules.

- [ ] **Step 3: Full local gate (Phase 0 done)**

Run: `TMPDIR=/var/tmp uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all green.

- [ ] **Step 4: Commit + branch checkpoint**

```bash
git add -A
```
```bash
git commit -m "FWK4 P0: regenerate reviewer reference; integrity reconciled"
```

**Phase 0 is a mergeable checkpoint.** Run a branch-end Sonnet spec review + Opus code-quality review of the centralization before layering Phase 1 on top (or merge it as its own PR first if you want to de-risk).

---

# Phase 1 — Audit pipeline core

**Outcome:** the brief assembler + checkpointed orchestrator + Stage-1 audit agent + the changelist schema, producing a per-agent audit (no reconciliation/adversarial yet), testable on a stubbed backend.

### Task 1.1: Stub backend test fixture

**Files:**
- Create: `tests/review/audit/__init__.py` (empty)
- Create: `tests/review/audit/conftest.py`

- [ ] **Step 1: Create the stub backend**

```python
# tests/review/audit/conftest.py
"""A `.messages.create`-shaped stub so audit-pipeline tests need no key/quota."""
from __future__ import annotations

import pytest

from framework_cli.review.backend import Message, TextBlock


class _StubMessages:
    def __init__(self, scripted):  # scripted: list[str] OR callable(system, messages)->str
        self._scripted = scripted
        self._i = 0
        self.calls = []

    def create(self, *, model, max_tokens, system, messages, tools=None):
        self.calls.append({"model": model, "system": system, "messages": messages})
        if callable(self._scripted):
            text = self._scripted(system, messages)
        else:
            text = self._scripted[min(self._i, len(self._scripted) - 1)]
            self._i += 1
        return Message(content=[TextBlock(text=text)], stop_reason="end_turn")


class StubBackend:
    def __init__(self, scripted):
        self.messages = _StubMessages(scripted)


@pytest.fixture
def stub_backend():
    return StubBackend
```

- [ ] **Step 2: Sanity-check the stub**

Run: `uv run python -c "import json; from tests.review.audit.conftest import StubBackend; b=StubBackend(['[]']); print(b.messages.create(model='m', max_tokens=1, system=[], messages=[]).content[0].text)"`
Expected: `[]`

- [ ] **Step 3: Commit**

```bash
git add tests/review/audit/__init__.py tests/review/audit/conftest.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P1: StubBackend test fixture for the audit pipeline"
```

---

### Task 1.2: Changelist schema

**Files:**
- Create: `src/framework_cli/review/audit/__init__.py` (empty)
- Create: `src/framework_cli/review/audit/changelist.py`
- Test: `tests/review/audit/test_changelist.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/audit/test_changelist.py
from framework_cli.review.audit.changelist import (
    AgentChange,
    Changelist,
    ProposedEdit,
    Verdict,
)


def test_changelist_roundtrips_json():
    cl = Changelist(
        agents=[
            AgentChange(
                agent="security",
                proposed_block_threshold="high",
                edits=[
                    ProposedEdit(
                        target="domain_prompt",
                        rationale="tighten secret-value rule",
                        before="old",
                        after="new",
                    )
                ],
                fixture_verdicts={"good/clean": "clean", "bad/leak": "unambiguous"},
            )
        ],
        preamble_edits=[ProposedEdit(target="rubric", rationale="x", before="a", after="b")],
    )
    again = Changelist.from_dict(cl.to_dict())
    assert again == cl
    assert again.agents[0].edits[0].target == "domain_prompt"


def test_vetted_filters_refuted_changes():
    e_keep = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="b",
                          verdict=Verdict(refuted=False, votes=3, refutation=""))
    e_drop = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="c",
                          verdict=Verdict(refuted=True, votes=1, refutation="lets bad/Y slip"))
    ac = AgentChange(agent="security", proposed_block_threshold=None,
                     edits=[e_keep, e_drop], fixture_verdicts={})
    cl = Changelist(agents=[ac], preamble_edits=[])
    vetted = cl.vetted()
    assert len(vetted.agents[0].edits) == 1
    assert vetted.agents[0].edits[0] is e_keep
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/audit/test_changelist.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `changelist.py`**

```python
# src/framework_cli/review/audit/changelist.py
"""Typed changelist: the contract every audit stage reads and writes.

`ProposedEdit.target` ∈ {"domain_prompt","fixture","block_threshold","rubric"}.
A Verdict comes from the Phase-2 adversarial spine; `vetted()` keeps only the
changes the majority of skeptics FAILED to refute."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EditTarget = Literal["domain_prompt", "fixture", "block_threshold", "rubric"]


@dataclass(frozen=True)
class Verdict:
    refuted: bool
    votes: int  # skeptics who FAILED to refute (i.e. the change survives if majority)
    refutation: str = ""


@dataclass(frozen=True)
class ProposedEdit:
    target: EditTarget
    rationale: str
    before: str
    after: str
    path: str | None = None  # fixture path / agent file, when applicable
    verdict: Verdict | None = None


@dataclass(frozen=True)
class AgentChange:
    agent: str
    proposed_block_threshold: str | None
    edits: list[ProposedEdit] = field(default_factory=list)
    fixture_verdicts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Changelist:
    agents: list[AgentChange] = field(default_factory=list)
    preamble_edits: list[ProposedEdit] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Changelist:
        def _edit(e: dict[str, Any]) -> ProposedEdit:
            v = e.get("verdict")
            return ProposedEdit(
                target=e["target"], rationale=e["rationale"], before=e["before"],
                after=e["after"], path=e.get("path"),
                verdict=Verdict(**v) if v else None,
            )
        agents = [
            AgentChange(
                agent=a["agent"],
                proposed_block_threshold=a["proposed_block_threshold"],
                edits=[_edit(e) for e in a.get("edits", [])],
                fixture_verdicts=dict(a.get("fixture_verdicts", {})),
            )
            for a in d.get("agents", [])
        ]
        return cls(agents=agents, preamble_edits=[_edit(e) for e in d.get("preamble_edits", [])])

    def vetted(self) -> Changelist:
        """Drop edits a verdict marked refuted (unverified edits are kept — they
        simply have not been through the spine yet)."""
        def _keep(e: ProposedEdit) -> bool:
            return not (e.verdict and e.verdict.refuted)
        agents = [
            AgentChange(a.agent, a.proposed_block_threshold,
                        [e for e in a.edits if _keep(e)], dict(a.fixture_verdicts))
            for a in self.agents
        ]
        return Changelist(agents=agents,
                          preamble_edits=[e for e in self.preamble_edits if _keep(e)])
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/audit/test_changelist.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/audit/__init__.py src/framework_cli/review/audit/changelist.py tests/review/audit/test_changelist.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P1: typed audit changelist schema (+ vetted filter)"
```

---

### Task 1.3: Brief assembler

**Files:**
- Create: `src/framework_cli/review/audit/brief.py`
- Test: `tests/review/audit/test_brief.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/audit/test_brief.py
import json
from pathlib import Path

from framework_cli.review.audit.brief import AuditBrief, build_audit_brief


def _write_baseline(d: Path):
    # mimic `framework eval --findings-out`: per-(agent,fixture,repeat) JSON
    d.mkdir(parents=True, exist_ok=True)
    (d / "security__good__clean__0.json").write_text(json.dumps({"agent": "security", "findings": []}))
    (d / "security__bad__leak__0.json").write_text(
        json.dumps({"agent": "security", "findings": [{"path": "a.py", "line": 1, "severity": "high", "message": "secret"}]})
    )


def test_brief_collects_target_prompt_fixtures_and_baseline(tmp_path):
    base = tmp_path / "findings"
    _write_baseline(base)
    brief = build_audit_brief("security", root=Path.cwd(), baseline_dir=base)
    assert isinstance(brief, AuditBrief)
    assert brief.target == "security"
    assert "## Your domain: `review-security`" in brief.composed_prompt
    assert "## Severity" in brief.composed_prompt  # the preamble is included
    # baseline findings grouped for this agent
    assert len(brief.baseline_findings) == 2
    # the consistency oracle: the full roster's bars are present
    assert brief.roster_bars["security"] == "high"
    assert "usability" in brief.roster_bars and brief.roster_bars["usability"] is None


def test_brief_tolerates_absent_baseline(tmp_path):
    brief = build_audit_brief("security", root=Path.cwd(), baseline_dir=None)
    assert brief.baseline_findings == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/audit/test_brief.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `brief.py`**

```python
# src/framework_cli/review/audit/brief.py
"""Assemble a per-target audit brief: the composed prompt under review, its fixtures
+ expectations, the baseline eval findings (the evidence), the canonical preamble, and
the FULL roster's block_thresholds (the cross-agent consistency oracle). Script-authored
and persisted by the orchestrator for auditability."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from framework_cli.review.preamble import build_preamble
from framework_cli.review.registry import agent_names, composed_prompt, get_agent


@dataclass(frozen=True)
class FixtureRef:
    kind: str   # "good" | "bad"
    case: str
    patch: str
    expect: dict[str, Any] | None


@dataclass(frozen=True)
class AuditBrief:
    target: str
    composed_prompt: str
    preamble: str
    fixtures: list[FixtureRef] = field(default_factory=list)
    baseline_findings: list[dict[str, Any]] = field(default_factory=list)
    roster_bars: dict[str, str | None] = field(default_factory=dict)


def _load_fixtures(target: str, fixtures_root: Path) -> list[FixtureRef]:
    out: list[FixtureRef] = []
    base = fixtures_root / target
    for kind in ("good", "bad"):
        kdir = base / kind
        if not kdir.is_dir():
            continue
        for case in sorted(p for p in kdir.iterdir() if p.is_dir()):
            patch_f = case / "change.patch"
            if not patch_f.exists():
                continue
            exp = case / "expect.json"
            out.append(FixtureRef(
                kind=kind, case=case.name, patch=patch_f.read_text(),
                expect=json.loads(exp.read_text()) if exp.exists() else None,
            ))
    return out


def _load_baseline(target: str, baseline_dir: Path | None) -> list[dict[str, Any]]:
    if baseline_dir is None or not baseline_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for f in sorted(baseline_dir.glob(f"{target}__*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def build_audit_brief(
    target: str, *, root: Path, baseline_dir: Path | None,
    fixtures_root: Path | None = None,
) -> AuditBrief:
    spec = get_agent(target)
    froot = fixtures_root or (root / "tests" / "eval" / "fixtures")
    roster = {n: get_agent(n).block_threshold for n in agent_names()}
    return AuditBrief(
        target=target,
        composed_prompt=composed_prompt(spec),
        preamble=build_preamble(spec),
        fixtures=_load_fixtures(target, froot),
        baseline_findings=_load_baseline(target, baseline_dir),
        roster_bars=roster,
    )
```

(The baseline glob `f"{target}__*.json"` assumes the eval `--findings-out` naming. Verify the real filename pattern in `cli.py`'s eval `--findings-out` writer and adjust the separator if it differs; the test seeds the same pattern so it stays self-consistent — reconcile both to the real writer in Step 4.)

- [ ] **Step 4: Reconcile baseline filename with the real `--findings-out` writer**

Run: `grep -n "findings_out\|findings-out" src/framework_cli/cli.py` and read the writer; adjust `_load_baseline`'s glob and the test's seed filenames to match the real `<agent>`/`<fixture>`/`<repeat>` naming. Re-run the test.

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/review/audit/test_brief.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/audit/brief.py tests/review/audit/test_brief.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P1: per-target audit brief assembler (with roster consistency oracle)"
```

---

### Task 1.4: Checkpointed orchestrator

**Files:**
- Create: `src/framework_cli/review/audit/orchestrator.py`
- Test: `tests/review/audit/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/audit/test_orchestrator.py
from pathlib import Path

from framework_cli.review.audit.orchestrator import run_stage


def test_run_stage_persists_each_item_and_resumes(tmp_path: Path):
    calls = []

    def work(item):
        calls.append(item)
        return {"item": item, "out": item.upper()}

    run_dir = tmp_path / "audit" / "stage1"
    results = run_stage(["a", "b", "c"], work, run_dir=run_dir, item_id=lambda x: x)
    assert {r["out"] for r in results} == {"A", "B", "C"}
    # each item persisted
    assert (run_dir / "findings" / "a.json").exists()

    # resume: a second call re-uses persisted outputs, does NOT re-run work
    calls.clear()
    results2 = run_stage(["a", "b", "c"], work, run_dir=run_dir, item_id=lambda x: x, resume=True)
    assert calls == []  # nothing re-run
    assert {r["out"] for r in results2} == {"A", "B", "C"}


def test_run_stage_records_failure_and_continues(tmp_path: Path):
    def work(item):
        if item == "b":
            raise ValueError("boom")
        return {"item": item, "out": item}

    run_dir = tmp_path / "audit" / "stage1"
    results = run_stage(["a", "b", "c"], work, run_dir=run_dir, item_id=lambda x: x)
    by = {r["item"]: r for r in results}
    assert by["a"]["out"] == "a" and by["c"]["out"] == "c"
    assert "error" in by["b"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/audit/test_orchestrator.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `orchestrator.py`** (reuse `checkpoint.py` primitives)

```python
# src/framework_cli/review/audit/orchestrator.py
"""Deterministic, checkpoint-resumable work-queue for the audit stages. Each item's
output persists to <run_dir>/findings/<id>.json; a resume re-reads completed ids and
skips re-running them. Mirrors review/engine.run_engine, reusing checkpoint.py. ALL
orchestration is script-authored — no LLM 'manager' agent spawns sub-agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from framework_cli.review.backend import BackendExhausted
from framework_cli.review.checkpoint import (
    append_record,
    init_run,
    load_state,
    pending_items,
)


def _persisted(run_dir: Path, item_id: str) -> dict[str, Any]:
    return json.loads((run_dir / "findings" / f"{item_id}.json").read_text())


def run_stage(
    items: list[Any],
    work: Callable[[Any], dict[str, Any]],
    *,
    run_dir: Path,
    item_id: Callable[[Any], str],
    resume: bool = False,
) -> list[dict[str, Any]]:
    ids = [item_id(it) for it in items]
    if not resume or not (run_dir / "run-state.json").exists():
        init_run(run_dir, planned=ids, git_sha="", dirty_hash="", backend="audit")
    todo = set(pending_items(run_dir))
    by_id = dict(zip(ids, items))
    for iid in list(todo):
        item = by_id[iid]
        try:
            record = work(item)
        except BackendExhausted:
            raise  # stop scheduling; a later resume continues
        except Exception as exc:  # noqa: BLE001 — record the one-off failure, keep going
            record = {"item": iid, "error": f"{type(exc).__name__}: {exc}"}
        append_record(run_dir, iid, record)
    done = load_state(run_dir)["done"]
    return [_persisted(run_dir, iid) for iid in ids if iid in done]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/audit/test_orchestrator.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/audit/orchestrator.py tests/review/audit/test_orchestrator.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P1: checkpointed audit work-queue (reuses checkpoint.py)"
```

---

### Task 1.5: Stage 1 — audit agent

**Files:**
- Create: `src/framework_cli/review/audit/stages.py`
- Test: `tests/review/audit/test_stages.py`

- [ ] **Step 1: Write the failing test** (stubbed backend — no quota)

```python
# tests/review/audit/test_stages.py
import json
from pathlib import Path

from framework_cli.review.audit.brief import build_audit_brief
from framework_cli.review.audit.stages import audit_agent
from tests.review.audit.conftest import StubBackend


def test_audit_agent_parses_structured_report(tmp_path: Path):
    report_json = json.dumps({
        "agent": "security",
        "severity_issues": ["over-flags hardening as high"],
        "scope_creep": [],
        "fixture_verdicts": {"good/clean": "clean"},
        "proposed_block_threshold": "high",
        "edits": [
            {"target": "domain_prompt", "rationale": "tighten", "before": "x", "after": "y"}
        ],
    })
    backend = StubBackend([report_json])
    brief = build_audit_brief("security", root=Path.cwd(), baseline_dir=None)
    report = audit_agent(brief, backend, root=Path.cwd())
    assert report["agent"] == "security"
    assert report["proposed_block_threshold"] == "high"
    assert report["edits"][0]["target"] == "domain_prompt"
    # the audit system prompt embedded the target's composed prompt + the roster bars
    sent = backend.messages.calls[0]["system"]
    sent_text = " ".join(b.get("text", "") for b in sent)
    assert "## Your domain: `review-security`" in sent_text
    assert "consistency" in sent_text.lower()


def test_audit_agent_tolerates_fenced_json(tmp_path: Path):
    backend = StubBackend(["```json\n{\"agent\":\"security\",\"edits\":[]}\n```"])
    brief = build_audit_brief("security", root=Path.cwd(), baseline_dir=None)
    report = audit_agent(brief, backend, root=Path.cwd())
    assert report["agent"] == "security"
    assert report["edits"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/audit/test_stages.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement Stage 1 in `stages.py`**

```python
# src/framework_cli/review/audit/stages.py
"""The LLM audit stages. Each builds a system prompt from a script-authored brief and
dispatches ONE structured call through the backend seam (backend.messages.create).
Stage 1 (audit) here; Stage 2 (reconcile) + Stage 3 (refute) added in Phase 2.

All stages run on Opus (AGENTIC_MODEL) — these are agentic judgments."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from framework_cli.review.audit.brief import AuditBrief
from framework_cli.review.registry import AGENTIC_MODEL

_AUDIT_SYSTEM = """You are a reviewer-prompt AUDITOR. You audit ONE framework review agent's
prompt for severity-bar calibration, scope discipline, hallucination resistance,
stricter-than-codebase and internal-consistency violations, and fixture validity.

The agent under audit, its composed prompt (shared rubric + its domain block):
<<<PROMPT
{prompt}
PROMPT>>>

The FULL reviewer roster's block_thresholds — your CONSISTENCY baseline (this agent's bar
must be consistent with how the rest of the roster grades the same severity class):
{roster}

Its golden fixtures (good = must stay clean; bad = must be caught) and expectations:
{fixtures}

Its baseline eval findings (evidence — reason FROM these AND beyond them; --repeat variance
exposes flakiness, not ground truth):
{baseline}

Return JSON ONLY — an object:
{{"agent": "<name>", "severity_issues": [..], "scope_creep": [..],
  "fixture_verdicts": {{"<kind>/<case>": "clean|unambiguous|dirty|ambiguous"}},
  "proposed_block_threshold": "<high|medium|low|info|null>",
  "edits": [{{"target": "domain_prompt|fixture|block_threshold|rubric",
             "rationale": "..", "before": "..", "after": "..", "path": "<optional>"}}]}}
No prose, no code fences."""


def _extract_json(text: str) -> Any:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t).rstrip("`").rstrip()
    return json.loads(t)


def _fmt_fixtures(brief: AuditBrief) -> str:
    return "\n".join(
        f"[{f.kind}/{f.case}] expect={f.expect}\n{f.patch}" for f in brief.fixtures
    ) or "(no fixtures)"


def audit_agent(brief: AuditBrief, backend: Any, *, root: Path) -> dict[str, Any]:
    system = _AUDIT_SYSTEM.format(
        prompt=brief.composed_prompt,
        roster=json.dumps(brief.roster_bars, indent=2, sort_keys=True),
        fixtures=_fmt_fixtures(brief),
        baseline=json.dumps(brief.baseline_findings, indent=2)[:20000] or "(none)",
    )
    msg = backend.messages.create(
        model=AGENTIC_MODEL,
        max_tokens=8000,
        system=[{"type": "text", "text": system}],
        messages=[{"role": "user", "content": "Audit this agent. Return the JSON object."}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    report = _extract_json(text)
    report.setdefault("agent", brief.target)
    report.setdefault("edits", [])
    return report
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/audit/test_stages.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/audit/stages.py tests/review/audit/test_stages.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P1: Stage 1 audit agent (structured, roster-aware)"
```

---

# Phase 2 — Reconciliation + adversarial spine

### Task 2.1: Stage 2 — cross-agent reconciliation

**Files:**
- Modify: `src/framework_cli/review/audit/stages.py`
- Test: `tests/review/audit/test_stages.py` (add)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/audit/test_stages.py
import json
from framework_cli.review.audit.changelist import Changelist
from framework_cli.review.audit.stages import reconcile
from tests.review.audit.conftest import StubBackend


def test_reconcile_merges_reports_into_changelist():
    cl_json = json.dumps({
        "agents": [
            {"agent": "security", "proposed_block_threshold": "high",
             "edits": [{"target": "domain_prompt", "rationale": "r", "before": "a", "after": "b"}],
             "fixture_verdicts": {}}
        ],
        "preamble_edits": [],
    })
    backend = StubBackend([cl_json])
    reports = [
        {"agent": "security", "edits": [], "proposed_block_threshold": "high"},
        {"agent": "usability", "edits": [], "proposed_block_threshold": None},
    ]
    roster = {"security": "high", "usability": None}
    cl = reconcile(reports, roster, backend)
    assert isinstance(cl, Changelist)
    assert cl.agents[0].agent == "security"
    # the reconciliation prompt saw ALL reports + the roster (cross-agent visibility)
    sent = " ".join(b.get("text", "") for b in backend.messages.calls[0]["system"])
    assert "usability" in sent and "security" in sent
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/audit/test_stages.py::test_reconcile_merges_reports_into_changelist -v`
Expected: FAIL — `reconcile` undefined.

- [ ] **Step 3: Implement `reconcile`** (append to `stages.py`)

```python
from framework_cli.review.audit.changelist import Changelist

_RECONCILE_SYSTEM = """You are the reviewer-roster RECONCILER. You receive every per-agent
audit report and the full roster's block_thresholds. Produce ONE consolidated changelist
that (a) reconciles the severity bar ACROSS agents — the same defect class must not be HIGH
for one agent and LOW for another; (b) enforces one-owner-per-class scope boundaries;
(c) proposes refinements to the SHARED rubric (preamble_edits) when a fix belongs in the
common block rather than one agent.

All per-agent audit reports:
{reports}

Full roster block_thresholds:
{roster}

Return JSON ONLY in the Changelist shape:
{{"agents": [{{"agent": "..", "proposed_block_threshold": "..|null",
   "edits": [{{"target": "domain_prompt|fixture|block_threshold", "rationale": "..",
              "before": "..", "after": "..", "path": "<optional>"}}],
   "fixture_verdicts": {{}}}}],
 "preamble_edits": [{{"target": "rubric", "rationale": "..", "before": "..", "after": ".."}}]}}
No prose, no code fences."""


def reconcile(reports: list[dict[str, Any]], roster: dict[str, Any], backend: Any) -> Changelist:
    system = _RECONCILE_SYSTEM.format(
        reports=json.dumps(reports, indent=2)[:60000],
        roster=json.dumps(roster, indent=2, sort_keys=True),
    )
    msg = backend.messages.create(
        model=AGENTIC_MODEL, max_tokens=16000,
        system=[{"type": "text", "text": system}],
        messages=[{"role": "user", "content": "Reconcile into one changelist."}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return Changelist.from_dict(_extract_json(text))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/audit/test_stages.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/audit/stages.py tests/review/audit/test_stages.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P2: Stage 2 cross-agent reconciliation"
```

---

### Task 2.2: Stage 3 — adversarial refutation

**Files:**
- Modify: `src/framework_cli/review/audit/stages.py`
- Test: `tests/review/audit/test_stages.py` (add)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/audit/test_stages.py
from framework_cli.review.audit.changelist import ProposedEdit, Verdict
from framework_cli.review.audit.stages import refute


def test_refute_returns_verdict_majority_survives():
    # 3 skeptics: 2 fail-to-refute (survives), 1 refutes
    backend = StubBackend([
        json.dumps({"refuted": False, "reason": "edit is sound"}),
        json.dumps({"refuted": False, "reason": "still catches bad case"}),
        json.dumps({"refuted": True, "reason": "loosens bar for bad/Y"}),
    ])
    edit = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="b")
    v = refute(edit, "security", backend, skeptics=3)
    assert isinstance(v, Verdict)
    assert v.refuted is False  # majority failed to refute → survives
    assert v.votes == 2


def test_refute_majority_refutes_kills_change():
    backend = StubBackend([
        json.dumps({"refuted": True, "reason": "x"}),
        json.dumps({"refuted": True, "reason": "y"}),
        json.dumps({"refuted": False, "reason": "z"}),
    ])
    edit = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="b")
    v = refute(edit, "security", backend, skeptics=3)
    assert v.refuted is True
    assert "x" in v.refutation or "y" in v.refutation
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/audit/test_stages.py -k refute -v`
Expected: FAIL — `refute` undefined.

- [ ] **Step 3: Implement `refute`** (append to `stages.py`)

```python
from framework_cli.review.audit.changelist import ProposedEdit, Verdict

_REFUTE_SYSTEM = """You are an adversarial SKEPTIC. Your job is to REFUTE the proposed change
to a reviewer prompt/fixture. Default to refuted=true if uncertain. Refute if the change
under-flags a defect class, loosens a bar so a `bad` fixture would slip, was tuned against a
dirty `good` fixture, or makes a bad case ambiguous.

Agent: {agent}
Proposed change ({target}): {rationale}
--- before ---
{before}
--- after ---
{after}

Return JSON ONLY: {{"refuted": true|false, "reason": "<one sentence>"}}. No prose, no fences."""


def refute(edit: ProposedEdit, agent: str, backend: Any, *, skeptics: int = 3) -> Verdict:
    system = _REFUTE_SYSTEM.format(
        agent=agent, target=edit.target, rationale=edit.rationale,
        before=edit.before, after=edit.after,
    )
    refutals, survived = [], 0
    for _ in range(skeptics):
        msg = backend.messages.create(
            model=AGENTIC_MODEL, max_tokens=600,
            system=[{"type": "text", "text": system}],
            messages=[{"role": "user", "content": "Refute or fail to refute. JSON only."}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            verdict = _extract_json(text)
        except Exception:  # noqa: BLE001 — an unparseable skeptic counts as a refutation (default-to-refuted)
            refutals.append("unparseable skeptic response")
            continue
        if verdict.get("refuted", True):
            refutals.append(str(verdict.get("reason", "")))
        else:
            survived += 1
    refuted = survived < (skeptics // 2 + 1)  # survives only on a strict majority fail-to-refute
    return Verdict(refuted=refuted, votes=survived, refutation=" | ".join(refutals))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/audit/test_stages.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/audit/stages.py tests/review/audit/test_stages.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P2: Stage 3 adversarial refutation (default-to-refuted, majority survives)"
```

---

### Task 2.3: Pipeline wiring

**Files:**
- Create: `src/framework_cli/review/audit/pipeline.py`
- Test: `tests/review/audit/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/audit/test_pipeline.py
import json
from pathlib import Path

from framework_cli.review.audit.pipeline import run_audit
from tests.review.audit.conftest import StubBackend


def _scripted(system, messages):
    text = " ".join(b.get("text", "") for b in system)
    if "reviewer-prompt AUDITOR" in text:
        return json.dumps({"agent": "security", "edits": [
            {"target": "domain_prompt", "rationale": "r", "before": "a", "after": "b"}
        ], "proposed_block_threshold": "high", "fixture_verdicts": {}})
    if "roster RECONCILER" in text:
        return json.dumps({"agents": [{"agent": "security", "proposed_block_threshold": "high",
            "edits": [
                {"target": "domain_prompt", "rationale": "keep", "before": "a", "after": "b"},
                {"target": "domain_prompt", "rationale": "drop", "before": "c", "after": "d"},
            ], "fixture_verdicts": {}}], "preamble_edits": []})
    if "adversarial SKEPTIC" in text:
        # refute only the "drop" change (after == "d")
        refuted = "--- after ---\nd" in text
        return json.dumps({"refuted": refuted, "reason": "x"})
    return "{}"


def test_run_audit_produces_vetted_changelist(tmp_path: Path):
    backend = StubBackend(_scripted)
    cl = run_audit(["security"], backend=backend, root=Path.cwd(),
                   baseline_dir=None, out_dir=tmp_path / "out", skeptics=3)
    edits = cl.agents[0].edits
    # the refuted "drop" edit (after == "d") is excluded; the "keep" edit survives
    assert [e.after for e in edits] == ["b"]
    assert edits[0].verdict is not None and edits[0].verdict.refuted is False
    # the changelist + each stage's records were persisted under out_dir
    assert (tmp_path / "out" / "changelist.json").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/audit/test_pipeline.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `pipeline.py`**

```python
# src/framework_cli/review/audit/pipeline.py
"""Wire the audit stages through the checkpointed orchestrator and emit a vetted
changelist. Sequence: brief→audit (Stage 1, per target) → reconcile (Stage 2, one call) →
refute (Stage 3, per proposed edit) → vetted changelist persisted to out_dir."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from framework_cli.review.audit.brief import build_audit_brief
from framework_cli.review.audit.changelist import AgentChange, Changelist, ProposedEdit
from framework_cli.review.audit.orchestrator import run_stage
from framework_cli.review.audit.stages import audit_agent, reconcile, refute
from framework_cli.review.registry import agent_names, get_agent


def run_audit(
    targets: list[str], *, backend: Any, root: Path, baseline_dir: Path | None,
    out_dir: Path, skeptics: int = 3, resume: bool = False,
) -> Changelist:
    out_dir.mkdir(parents=True, exist_ok=True)
    roster = {n: get_agent(n).block_threshold for n in agent_names()}

    # Stage 1 — audit fan-out (per target), checkpointed.
    def _audit(target: str) -> dict[str, Any]:
        brief = build_audit_brief(target, root=root, baseline_dir=baseline_dir)
        return audit_agent(brief, backend, root=root)

    reports = run_stage(
        targets, _audit, run_dir=out_dir / "stage1-audit",
        item_id=lambda t: t, resume=resume,
    )

    # Stage 2 — cross-agent reconciliation (single call; full roster as oracle).
    cl = reconcile(reports, roster, backend)

    # Stage 3 — adversarial refutation per proposed edit, checkpointed.
    flat = [(a.agent, i, e) for a in cl.agents for i, e in enumerate(a.edits)]
    flat += [("__preamble__", i, e) for i, e in enumerate(cl.preamble_edits)]

    def _refute(item: tuple[str, int, ProposedEdit]) -> dict[str, Any]:
        agent, idx, edit = item
        v = refute(edit, agent, backend, skeptics=skeptics)
        return {"agent": agent, "idx": idx, "verdict": {"refuted": v.refuted,
                "votes": v.votes, "refutation": v.refutation}}

    verdicts = run_stage(
        flat, _refute, run_dir=out_dir / "stage3-refute",
        item_id=lambda it: f"{it[0]}__{it[1]}", resume=resume,
    )
    vmap = {(r["agent"], r["idx"]): r["verdict"] for r in verdicts}

    def _attach(agent: str, edits: list[ProposedEdit]) -> list[ProposedEdit]:
        from framework_cli.review.audit.changelist import Verdict
        out = []
        for i, e in enumerate(edits):
            v = vmap.get((agent, i))
            out.append(ProposedEdit(e.target, e.rationale, e.before, e.after, e.path,
                                    Verdict(**v) if v else None))
        return out

    decided = Changelist(
        agents=[AgentChange(a.agent, a.proposed_block_threshold,
                            _attach(a.agent, a.edits), dict(a.fixture_verdicts))
                for a in cl.agents],
        preamble_edits=_attach("__preamble__", cl.preamble_edits),
    )
    vetted = decided.vetted()
    (out_dir / "changelist.json").write_text(json.dumps(vetted.to_dict(), indent=2))
    (out_dir / "changelist-full.json").write_text(json.dumps(decided.to_dict(), indent=2))
    return vetted
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/audit/test_pipeline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/audit/pipeline.py tests/review/audit/test_pipeline.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P2: pipeline wiring (audit→reconcile→refute→vetted changelist)"
```

---

# Phase 3 — Apply-preview + CLI + runbook

### Task 3.1: Apply-preview patch renderer

**Files:**
- Create: `src/framework_cli/review/audit/preview.py`
- Test: `tests/review/audit/test_preview.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/audit/test_preview.py
from framework_cli.review.audit.changelist import AgentChange, Changelist, ProposedEdit
from framework_cli.review.audit.preview import render_patch


def test_render_patch_emits_unified_diff_for_domain_edit():
    cl = Changelist(agents=[AgentChange("security", "high", edits=[
        ProposedEdit(target="domain_prompt", rationale="r",
                     before="old line\n", after="new line\n",
                     path="src/framework_cli/review/agents/security.md")
    ], fixture_verdicts={})], preamble_edits=[])
    patch = render_patch(cl)
    assert "--- a/src/framework_cli/review/agents/security.md" in patch
    assert "+new line" in patch and "-old line" in patch


def test_render_patch_skips_non_textual_targets():
    cl = Changelist(agents=[AgentChange("security", "high", edits=[
        ProposedEdit(target="block_threshold", rationale="r", before="info", after="high")
    ], fixture_verdicts={})], preamble_edits=[])
    patch = render_patch(cl)
    # block_threshold change is surfaced as a comment, not a code diff
    assert "block_threshold" in patch
    assert "security" in patch
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/audit/test_preview.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `preview.py`** (use stdlib `difflib`)

```python
# src/framework_cli/review/audit/preview.py
"""Render a vetted changelist as an inspectable, git-applyable patch (textual edits)
plus a human-readable summary for non-textual edits (block_threshold). No mutation —
the maintainer inspects and `git apply`s themselves."""

from __future__ import annotations

import difflib

from framework_cli.review.audit.changelist import Changelist, ProposedEdit

_TEXTUAL = {"domain_prompt", "fixture", "rubric"}


def _diff(edit: ProposedEdit) -> str:
    path = edit.path or "<unknown-path>"
    before = edit.before.splitlines(keepends=True)
    after = edit.after.splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        before, after, fromfile=f"a/{path}", tofile=f"b/{path}"
    ))


def render_patch(changelist: Changelist) -> str:
    out: list[str] = []
    notes: list[str] = []
    for ac in changelist.agents:
        for e in ac.edits:
            if e.target in _TEXTUAL and e.path:
                out.append(f"# {ac.agent}: {e.rationale}\n{_diff(e)}")
            elif e.target == "block_threshold":
                notes.append(f"# {ac.agent}: set block_threshold {e.before} -> {e.after} "
                             f"({e.rationale}) — edit registry.py by hand")
    for e in changelist.preamble_edits:
        if e.path or e.target == "rubric":
            e2 = ProposedEdit(e.target, e.rationale, e.before, e.after,
                              e.path or "src/framework_cli/review/rubric.md", e.verdict)
            out.append(f"# rubric: {e.rationale}\n{_diff(e2)}")
    header = "\n".join(notes)
    return (header + "\n\n" if header else "") + "\n".join(out)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/audit/test_preview.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/audit/preview.py tests/review/audit/test_preview.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P3: dry-run apply-preview patch renderer"
```

---

### Task 3.2: `framework reviewer-audit` CLI command

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli_reviewer_audit.py`

- [ ] **Step 1: Write the failing test** (uses Typer's `CliRunner` + a monkeypatched backend resolver so no key is needed)

```python
# tests/test_cli_reviewer_audit.py
import json
from pathlib import Path

from typer.testing import CliRunner

from framework_cli.cli import app

runner = CliRunner()


def test_reviewer_audit_writes_changelist_and_preview(tmp_path, monkeypatch):
    import framework_cli.cli as climod
    from tests.review.audit.conftest import StubBackend

    def _scripted(system, messages):
        text = " ".join(b.get("text", "") for b in system)
        if "AUDITOR" in text:
            return json.dumps({"agent": "security", "edits": [], "proposed_block_threshold": "high",
                               "fixture_verdicts": {}})
        if "RECONCILER" in text:
            return json.dumps({"agents": [{"agent": "security", "proposed_block_threshold": "high",
                               "edits": [], "fixture_verdicts": {}}], "preamble_edits": []})
        return "{}"

    # Force a stub backend regardless of keys/config.
    monkeypatch.setattr(climod, "_make_backend", lambda *a, **k: StubBackend(_scripted))
    monkeypatch.setattr(
        climod, "_resolve_review_backend",
        lambda **k: type("R", (), {"backend": "subagent", "reason": ""})(),
    )

    out = tmp_path / "audit-out"
    result = runner.invoke(app, ["reviewer-audit", "security", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "changelist.json").exists()
    assert (out / "apply-preview.patch").exists()


def test_reviewer_audit_skip_neutral_without_backend(tmp_path, monkeypatch):
    import framework_cli.cli as climod
    monkeypatch.setattr(
        climod, "_resolve_review_backend",
        lambda **k: type("R", (), {"backend": None, "reason": "no key"})(),
    )
    result = runner.invoke(app, ["reviewer-audit", "security", "--out", str(tmp_path / "o")])
    assert result.exit_code == 0
    assert "skipped" in result.output.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli_reviewer_audit.py -v`
Expected: FAIL — no `reviewer-audit` command.

- [ ] **Step 3: Implement the command in `cli.py`** (mirror the `eval` command's backend-resolution pattern at `cli.py:1029+`)

```python
@app.command(name="reviewer-audit")
def reviewer_audit(
    agents: list[str] = typer.Argument(
        None, help="Reviewers to audit (default: all registered)."
    ),
    baseline: str = typer.Option(
        "", "--baseline", help="Dir of a prior `framework eval --findings-out` run (evidence)."
    ),
    out: str = typer.Option(
        ".framework/reviewer-audit", "--out", help="Output dir for the changelist + preview."
    ),
    backend: str | None = typer.Option(
        None, "--backend", help="'api' (paid) or 'subagent' (free claude -p)."
    ),
    skeptics: int = typer.Option(3, "--skeptics", help="Adversarial skeptics per change."),
    resume: bool = typer.Option(False, "--resume", help="Resume a prior run from --out."),
) -> None:
    """Audit reviewer prompts (rubric consistency, severity bar, scope, fixtures) and emit a
    vetted changelist + a dry-run apply-preview patch. No edits are applied (FWK4)."""
    from framework_cli.review.audit.pipeline import run_audit
    from framework_cli.review.audit.preview import render_patch

    res = _resolve_review_backend(flag=backend or None, key_env=EVAL_KEY_ENV)
    if res.backend is None:  # type: ignore[attr-defined]
        typer.echo(f"reviewer-audit: skipped ({_no_backend_message(getattr(res, 'reason', ''), key_env=EVAL_KEY_ENV)})")
        raise typer.Exit(0)

    _backend = _make_backend(res.backend, EVAL_KEY_ENV)  # type: ignore[attr-defined]
    targets = list(agents) if agents else agent_names()
    out_dir = Path(out)
    cl = run_audit(
        targets, backend=_backend, root=Path.cwd(),
        baseline_dir=Path(baseline) if baseline else None,
        out_dir=out_dir, skeptics=skeptics, resume=resume,
    )
    patch = render_patch(cl)
    (out_dir / "apply-preview.patch").write_text(patch)
    n = sum(len(a.edits) for a in cl.agents) + len(cl.preamble_edits)
    typer.echo(f"reviewer-audit: {n} vetted change(s) across {len(targets)} agent(s) → {out_dir}/")
```

Confirm `agent_names`, `_resolve_review_backend`, `_make_backend`, `_no_backend_message`, `EVAL_KEY_ENV`, and `Path` are already imported in `cli.py` (the `eval` command uses all of them).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cli_reviewer_audit.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli_reviewer_audit.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P3: framework reviewer-audit command"
```

---

### Task 3.3: Runbook + mkdocs nav

**Files:**
- Create: `documentation/runbooks/reviewer-audit.md`
- Modify: `mkdocs.yml` (add the runbook to nav)
- Test: existing docs-build / nav tests (if any) stay green.

- [ ] **Step 1: Write the runbook**

Author `documentation/runbooks/reviewer-audit.md` covering the end-to-end flow, with these exact sections and commands:
```markdown
# Runbook: auditing the review agents

When to run: after adding or retuning a reviewer, or periodically to catch rubric drift.

## 1. Baseline (evidence)
    framework eval --repeat 3 --findings-out .framework/eval-baseline --backend subagent

## 2. Audit
    framework reviewer-audit --baseline .framework/eval-baseline --out .framework/reviewer-audit
    # or a subset: framework reviewer-audit coverage-gap security --baseline ...

## 3. Inspect
- `.framework/reviewer-audit/changelist.json` — vetted changes (refuted ones excluded; see `changelist-full.json` for the kicked-back set + refutations).
- `.framework/reviewer-audit/apply-preview.patch` — `git apply --check` it, then `git apply` if sound.

## 4. Apply + re-confirm (the gate)
    git apply .framework/reviewer-audit/apply-preview.patch
    framework eval <agent> --repeat 3 --backend subagent   # good stays clean, bad stays caught
    # block_threshold changes are applied by hand in registry.py (called out in the patch header)

## 5. Re-derive thresholds + scorecard (whole-set retune only)
    framework eval --repeat 3 --findings-out .framework/eval-after --backend subagent
    framework eval-analyze .framework/eval-after   # re-derive thresholds.yaml with margin
    # commit a dated scorecard under docs/superpowers/eval-scorecards/

Notes: resumable across quota resets via `--resume` (agent-granularity checkpoints under `--out`).
Audit/reconcile/skeptic agents run on Opus. No edits are applied automatically.
```

- [ ] **Step 2: Add to mkdocs nav**

Add `- Runbooks: { Reviewer audit: runbooks/reviewer-audit.md }` (or match the existing nav structure) to `mkdocs.yml`.

- [ ] **Step 3: Build the docs strict**

Run: `uv run mkdocs build --strict` (or the repo's docs task)
Expected: builds with no warnings (nav resolves).

- [ ] **Step 4: Commit**

```bash
git add documentation/runbooks/reviewer-audit.md mkdocs.yml PLAN.md ACTION_LOG.md
```
```bash
git commit -m "FWK4 P3: reviewer-audit runbook + mkdocs nav"
```

---

### Task 3.4: Full gate + branch-end review

**Files:** none (verification).

- [ ] **Step 1: Full local gate**

Run: `TMPDIR=/var/tmp uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all green. The audit-pipeline tests run on the StubBackend (no key/quota).

- [ ] **Step 2: Optional live smoke** (cheap; confirms real backend wiring end-to-end)

Run: `FRAMEWORK_REVIEW_BACKEND=subagent uv run framework reviewer-audit coverage-gap --out /tmp/ra-smoke`
Expected: a `changelist.json` + `apply-preview.patch` written; exit 0. (Quota-gated; skip-neutral without a backend.)

- [ ] **Step 3: Update PLAN.md / ACTION_LOG.md**

Mark FWK4 done in `PLAN.md` (move to Done with a summary); append the closing `ACTION_LOG.md` entry.

- [ ] **Step 4: Branch-end reviews**

Run a Sonnet spec-compliance review + an Opus code-quality whole-branch review ([[subagent-review-model-pattern]]). Address findings, then open the PR (master is protected — PR required; required checks `gate`+`build`+`render-complete`).

---

## Self-Review (completed against the spec)

**Spec coverage:**
- In-process `reviewer-audit` on the LiteLLM seam → Tasks 1.4/1.5/2.1/2.2/2.3/3.2 (no Workflow; uses `backend.messages.create`). ✓
- Unified 1..N + full roster as consistency baseline → `brief.roster_bars` (1.3), `reconcile(...)` (2.1), CLI default-all (3.2). ✓
- Vetted changelist + dry-run apply-preview, no auto-apply → `changelist.vetted()` (1.2), `render_patch` (3.1), CLI writes both (3.2); apply stays manual (runbook 3.3). ✓
- Runtime assembly / single-sourced rubric + output contract → Tasks 0.1–0.6; structural drift guard (0.3 test). ✓
- Per-agent severity enum derived from `block_threshold` + override → `severity_enum_for` / `AgentSpec.severity_enum` (0.2/0.3). ✓
- "Rubric can move" → canonical `rubric.md` edited once + recomposed; audit emits `preamble_edits` (single rubric edit), not N prompt diffs (1.2/2.1/3.1). ✓
- Checkpoint-resumable across quota resets → `orchestrator.run_stage` reuses `checkpoint.py`; `--resume` (1.4/2.3/3.2). ✓
- Testable without quota → `StubBackend` (1.1) drives every LLM-stage test. ✓
- Adversarial spine, default-to-refuted, majority survives, refuted logged + kicked back not dropped → `refute` (2.2) + `changelist-full.json` retains refuted set (2.3). ✓
- Advisory invariant preserved → `severity_enum`/derivation keeps advisory caps (0.2); eval re-confirm (0.7). ✓
- Opus for audit/reconcile/skeptic agents → `AGENTIC_MODEL` in every stage (1.5/2.1/2.2). ✓
- No release / no template payload → stated in the execution policy; Phase 0 integrity check (0.8). ✓

**Placeholder scan:** no TBD/TODO; every code step shows complete code; the one mechanical 21-file repetition (0.6) gives the explicit transformation rule + a worked example (0.5) + a structural guard that test-verifies all 21. The two "verify the real filename/Bundle constructor" notes (1.3 Step 4, 0.4 Step 1) are explicit reconciliation steps with commands, not deferred work.

**Type consistency:** `Changelist`/`AgentChange`/`ProposedEdit`/`Verdict` field names are consistent across 1.2 → 2.1 → 2.3 → 3.1 → 3.2. `run_stage(items, work, *, run_dir, item_id, resume)` signature matches every call site (1.4, 2.3). `audit_agent(brief, backend, *, root)` / `reconcile(reports, roster, backend)` / `refute(edit, agent, backend, *, skeptics)` signatures match the pipeline (2.3) and tests. `build_audit_brief(target, *, root, baseline_dir, fixtures_root=None)` matches its caller (2.3) and tests.
