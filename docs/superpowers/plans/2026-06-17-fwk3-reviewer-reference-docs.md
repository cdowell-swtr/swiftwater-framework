# FWK3 — Per-agent reviewer reference docs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans` (or subagent-driven for Task 2). Steps use `- [ ]`.

**Goal:** Publish the long-promised per-agent reviewer reference — one page documenting all 21 review agents (concern, scope, blocks-vs-advisory, context tier, review scope) — and retire the two promissory notes in `documentation/working/review-system.md`.

**Architecture:** Registry-driven + guarded (Fork A). The *mechanical* facts come live from `src/framework_cli/review/registry.py` (`agent_names()` / `get_agent()`); the *prose* (a 2-3 sentence "what it flags / what it won't" per agent) is hand-authored in a `_BLURBS` map. A `render_reference()` function in `src/framework_cli/review/reference_doc.py` emits the markdown; a thin `scripts/gen_reviewer_reference.py` writes the committed page; a guard test asserts the committed page equals a fresh render (mirrors the `gen_observability.py` codegen+guard pattern). Adding/retuning an agent regenerates or fails CI — the page can't silently rot.

**Tech Stack:** Python, the existing review registry, mkdocs docs site, pytest.

---

## File Structure

- **Create** `src/framework_cli/review/reference_doc.py` — `render_reference() -> str` + `_BLURBS: dict[str,str]` (framework source → mypy-checked, importable by the test).
- **Create** `scripts/gen_reviewer_reference.py` — thin CLI that writes `documentation/reference/review-agents.md`.
- **Create** `documentation/reference/review-agents.md` — the generated, committed page.
- **Create** `tests/test_reviewer_reference.py` — the "is current" + blurb-coverage guards.
- **Modify** `mkdocs.yml` — add the nav entry under `Reference`.
- **Modify** `documentation/working/review-system.md` — replace the two promissory sentences with a pointer.
- **Modify** `PLAN.md` + `ACTION_LOG.md`.

No template payload, no FWK29 surface, no release.

---

## Task 1: The generator (mechanical render + empty blurbs)

**Files:** Create `src/framework_cli/review/reference_doc.py`, `scripts/gen_reviewer_reference.py`.

- [ ] **Step 1: Write `reference_doc.py`** (the `_BLURBS` map starts empty — filled in Task 2)

```python
"""Generates documentation/reference/review-agents.md — mechanical facts live from the
registry, prose from _BLURBS. Regenerate via scripts/gen_reviewer_reference.py; a test guards it."""

from __future__ import annotations

from framework_cli.review.registry import agent_names, get_agent

# 2-3 sentence operator-facing blurb per agent: the lens, what it flags, and what it deliberately
# will NOT flag (its scope boundary / codebase-bar). Keyed by agent_names() (short keys). The
# mechanical facts (scope/threshold/tier) are read live from the registry — do NOT repeat them here.
_BLURBS: dict[str, str] = {}  # filled in Task 2

_HEADER = """# Review agents — reference

> Generated from `src/framework_cli/review/registry.py` by
> `scripts/gen_reviewer_reference.py`. Do not edit by hand — change the registry (mechanical
> facts) or `reference_doc._BLURBS` (prose) and regenerate
> (`uv run python scripts/gen_reviewer_reference.py`); a test keeps this page in sync.

The review system runs a panel of single-concern AI agents over a change — see
[The review system](../working/review-system.md) for the architecture and why. Each agent below
owns one lens. **Blocks** is the severity at/above which a finding fails the gate (*advisory*
agents surface findings but never block). **Context** is how the agent sees the change (`diff` /
`bundle` / `agentic` tool-loop) and its model tier."""


def _tier(model: str) -> str:
    # "claude-sonnet-4-6" -> "sonnet", "claude-opus-4-8" -> "opus"
    parts = model.split("-")
    return parts[1] if len(parts) > 1 else model


def _row(key: str) -> str:
    a = get_agent(key)
    blocks = a.block_threshold or "advisory"
    triggers = (
        ", ".join(f"`{g}`" for g in a.trigger_globs)
        if a.trigger_globs
        else "all changed files"
    )
    context = f"{a.context.strategy} · {_tier(a.model)}"
    if a.framework_only:
        scope = "framework self-review"
    elif a.reviews_template:
        scope = "project + framework (template-incl.)"
    else:
        scope = "project + framework"
    return f"| `{a.name}` | {blocks} | {triggers} | {context} | {scope} |"


def render_reference() -> str:
    names = sorted(agent_names())
    missing = [n for n in names if n not in _BLURBS]
    if missing:
        raise ValueError(f"reference_doc._BLURBS is missing blurbs for: {missing}")
    orphans = [k for k in _BLURBS if k not in names]
    if orphans:
        raise ValueError(f"reference_doc._BLURBS has entries not in the registry: {orphans}")
    out = [_HEADER, "", "## At a glance", ""]
    out += ["| Agent | Blocks | Triggers on | Context | Review scope |"]
    out += ["| --- | --- | --- | --- | --- |"]
    out += [_row(n) for n in names]
    out += ["", "## Agents", ""]
    for n in names:
        out += [f"### `{get_agent(n).name}`", "", _BLURBS[n], ""]
    return "\n".join(out).rstrip() + "\n"
```

- [ ] **Step 2: Write `scripts/gen_reviewer_reference.py`**

```python
#!/usr/bin/env python
"""Regenerate documentation/reference/review-agents.md from the review registry + blurbs."""

from pathlib import Path

from framework_cli.review.reference_doc import render_reference

_DOC = (
    Path(__file__).resolve().parents[1] / "documentation" / "reference" / "review-agents.md"
)

if __name__ == "__main__":
    _DOC.write_text(render_reference())
    print(f"wrote {_DOC}")
```

- [ ] **Step 3: Verify it imports + raises on the empty map (proves the coverage guard works)**

Run: `uv run python -c "from framework_cli.review.reference_doc import render_reference; render_reference()"`
Expected: `ValueError: reference_doc._BLURBS is missing blurbs for: [...all 21...]` — confirms the missing-blurb guard fires. (Don't commit yet — Task 2 fills the map.)

---

## Task 2: Author the 21 blurbs (the content — fan out, then fact-check)

**Files:** Modify `src/framework_cli/review/reference_doc.py` (`_BLURBS`).

The 21 keys (from `agent_names()`): `accessibility, api-design, application-logic, architecture, compliance, contracts, coverage-gap, data-integrity, data-lineage, dependency, documentation, env-parity, observability, observability-db, observability-fe, observability-infra, performance, privacy, security, test-quality, usability`.

- [ ] **Step 1: Draft a blurb per agent.** For each key, read its prompt `src/framework_cli/review/agents/{key}.md` (the domain section after the shared rubric) AND its registry entry. Write **2-3 sentences**: (1) the lens / concern, (2) the kind of defect it flags, (3) what it deliberately will NOT flag (its scope boundary or the codebase-bar). This parallelizes — one pass per agent (or per small group). **Format example** (`security`):

```python
    "security": (
        "Application-security review: injection, authn/z gaps, secret handling, unsafe "
        "deserialization, and crypto misuse on changed lines. Flags concrete, demonstrable "
        "defects in the diff — not speculative hardening the surrounding codebase doesn't already "
        "adopt (defense-in-depth it doesn't itself follow is info at most)."
    ),
```

- [ ] **Step 2: Controller fact-check each blurb against the registry + prompt.** Per [[design-spec-stale-verify-docs-against-code]], doc-writing confidently fabricates specifics — verify every blurb: does its claimed scope match `trigger_globs`/`framework_only`/`reviews_template`? Does "blocks/advisory" framing match `block_threshold`? Is the concern actually the prompt's concern (not an adjacent agent's — e.g. `api-design` is GraphQL-schema, `contracts` is Pact, `performance` is web-SLO globs, per [[check-agent-prompt-fit-before-adding-to-target]])? Fix any drift.

- [ ] **Step 3: Paste all 21 into `_BLURBS`** and confirm render succeeds:

Run: `uv run python -c "from framework_cli.review.reference_doc import render_reference; print(len(render_reference()))"`
Expected: a positive length, no `ValueError`.

- [ ] **Step 4: Commit** (`reference_doc.py` + the generator).

---

## Task 3: Generate + commit the page

**Files:** Create `documentation/reference/review-agents.md`.

- [ ] **Step 1: Generate.** Run: `uv run python scripts/gen_reviewer_reference.py`
Expected: `wrote …/documentation/reference/review-agents.md`.

- [ ] **Step 2: Eyeball the output** — 21 rows in the table, 21 `### review-*` subsections, no missing/garbled cells. Run: `uv run python -c "import pathlib,re; t=pathlib.Path('documentation/reference/review-agents.md').read_text(); print('rows', t.count('| review-'), 'sections', len(re.findall(r'^### ', t, re.M)))"` — expect `rows 21 sections 21`.

- [ ] **Step 3: Commit** the generated page.

---

## Task 4: The guard test

**Files:** Create `tests/test_reviewer_reference.py`.

- [ ] **Step 1: Write the test**

```python
"""FWK3 — keep the generated reviewer reference page in sync with the registry + blurbs."""

from pathlib import Path

from framework_cli.review.reference_doc import _BLURBS, render_reference
from framework_cli.review.registry import agent_names

_DOC = (
    Path(__file__).resolve().parents[1]
    / "documentation"
    / "reference"
    / "review-agents.md"
)


def test_reference_doc_is_current():
    assert _DOC.read_text() == render_reference(), (
        "documentation/reference/review-agents.md is stale — run "
        "`uv run python scripts/gen_reviewer_reference.py`"
    )


def test_every_agent_has_a_blurb():
    assert set(agent_names()) <= set(_BLURBS), (
        f"missing blurbs: {set(agent_names()) - set(_BLURBS)}"
    )


def test_no_orphan_blurbs():
    assert set(_BLURBS) <= set(agent_names()), (
        f"orphan blurbs (not in registry): {set(_BLURBS) - set(agent_names())}"
    )
```

- [ ] **Step 2: Run** `uv run pytest tests/test_reviewer_reference.py -q` → 3 passed. **Bite-proof:** delete a line from the committed `.md` → `test_reference_doc_is_current` RED; restore. **Commit.**

---

## Task 5: Wire the nav + retire the promissory notes

**Files:** Modify `mkdocs.yml`, `documentation/working/review-system.md`.

- [ ] **Step 1: Add the nav entry** under `Reference:` (mkdocs.yml:59-61):

```yaml
  - Reference:
      - CLI: reference/cli.md
      - Python API: reference/api.md
      - Review agents: reference/review-agents.md
```

- [ ] **Step 2: Retire promissory note #1** (`review-system.md:3`) — replace `… the detailed per-agent reference — which agents exist, what each one checks, and the thresholds they apply — will be published once the ongoing reviewer re-tuning lands.` with: `… the detailed per-agent reference — which agents exist, what each checks, and the thresholds they apply — is in [Review agents](../reference/review-agents.md).`

- [ ] **Step 3: Retire promissory note #2** (`review-system.md:35`) — replace `The full per-agent reference will follow once the reviewer re-tuning is complete.` with: `See [Review agents](../reference/review-agents.md) for the full per-agent reference.`

- [ ] **Step 4:** `uv run pytest tests/test_reviewer_reference.py -q` still green; `grep -c "will be published\|will follow" documentation/working/review-system.md` → `0`. **Commit.**

---

## Task 6: Close-out

- [ ] **Step 1: Gates** — `uv run ruff check . && uv run ruff format --check src/framework_cli/review/reference_doc.py scripts/gen_reviewer_reference.py tests/test_reviewer_reference.py && uv run mypy src` → clean.
- [ ] **Step 2:** Full quick suite sanity: `uv run pytest tests/test_reviewer_reference.py -q` (and the review test tier if quick). Update `PLAN.md` (move FWK3 to Done) + `ACTION_LOG.md`.
- [ ] **Step 3:** Branch-end Opus review of the diff (docs accuracy is the risk — confirm blurbs match prompts/registry). Address findings. Commit + PR. No release.

---

## Self-Review

- **Spec coverage:** generated page (Task 1/3), 21 blurbs fact-checked (Task 2), guard test (Task 4), nav + promissory-note retirement (Task 5). ✓
- **Placeholders:** `_BLURBS` is intentionally empty in Task 1 and filled in Task 2 (the content work) with a concrete format + example + fact-check rule — not a hand-wave. Every other code block is complete. ✓
- **Type/name consistency:** `render_reference`/`_BLURBS`/`_row`/`_tier` defined in Task 1 and used identically in Tasks 2/4; doc path identical across the generator + test; registry accessors (`agent_names`, `get_agent`, `.name/.block_threshold/.model/.context.strategy/.trigger_globs/.framework_only/.reviews_template`) all confirmed live. ✓
- **Durability:** the guard test fails if the registry changes (regenerate) or an agent lacks a blurb — closes the stale-doc risk the promissory notes were stalling on. ✓
