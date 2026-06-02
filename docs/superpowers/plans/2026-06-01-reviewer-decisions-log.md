# Reviewer Decisions Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the framework's review agents a machine-consumable log of accepted design decisions so they stop re-raising known/decided concerns, while still auto-blocking when a decision's explicit premise goes stale.

**Architecture:** A new `review/decisions.py` loads markdown decision records from `docs/superpowers/decisions/` (active-allowlist, fail-closed). Relevant decisions are rendered into a per-agent context block on both review paths — the local-subagent path (`_build_audit_work_item`, used by gate/audit) and the API path (`assemble`→`run_agent`/`run_agent_agentic`, used by `framework review`). Findings gain `acknowledged`/`stale` tags; `_finalize_gate` treats `acknowledged`-against-an-active-decision as non-blocking but keeps it in the report. The feature is inert (byte-identical context) until a decision is authored, and is never loaded during eval/tune.

**Tech Stack:** Python 3.12, `dataclasses`, PyYAML (already available via copier), Typer CLI, pytest. All changes are **framework source** (`src/framework_cli/…`) — normal `uv run pytest` loop, NOT the template render loop.

**Spec:** `docs/superpowers/specs/2026-06-01-reviewer-decisions-log-design.md`

---

## File Structure

- **Create** `src/framework_cli/review/decisions.py` — `Decision` model, `load_decisions`, `relevant_decisions`, `active_decision_ids`, `render_decisions_block`. One responsibility: read + filter + render decision records.
- **Modify** `src/framework_cli/review/context.py` — add `Bundle.decisions`; `assemble(..., agent=None)` populates it.
- **Modify** `src/framework_cli/review/runner.py` — `run_agent` renders `bundle.decisions` as a system block before the prompt.
- **Modify** `src/framework_cli/review/agentic.py` — `run_agent_agentic` does the same.
- **Modify** `src/framework_cli/review/findings.py` — `Finding` gains `acknowledged`/`stale`; `parse_findings` reads them.
- **Modify** `src/framework_cli/cli.py` — `_build_audit_work_item` injects the block (both branches); `review`/`review-agents` pass `agent=` to `assemble`; `_finalize_gate` excludes acknowledged-active findings from the blocking computation.
- **Modify** `src/framework_cli/review/analyze.py` — render acknowledged findings in their own report section.
- **Create** `docs/superpowers/decisions/DEC-0001-dlq-prune-internal-commit.md`, `DEC-0002-dlq-args-json-opt-in-redaction.md` — seed decisions.
- **Create** `tests/review/test_decisions.py`; **modify** `tests/test_cli.py` (verdict integration).

Naming note: decision `agents` use **short** names (`data-integrity`), matching `spec.name.removeprefix("review-")` and the gate's `agents_set`.

---

### Task 1: Decision model + loader (active-allowlist, fail-closed)

**Files:**
- Create: `src/framework_cli/review/decisions.py`
- Test: `tests/review/test_decisions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_decisions.py
from pathlib import Path

import pytest

from framework_cli.review.decisions import (
    Decision,
    active_decision_ids,
    load_decisions,
    relevant_decisions,
)

def _write(d: Path, name: str, *, id: str, status: str, agents: str, premise: str = "p") -> None:
    (d / name).write_text(
        f"---\nid: {id}\nstatus: {status}\nagents: [{agents}]\n"
        f"concern: c\npremise: {premise!r}\ndate: 2026-06-01\n---\n\nrationale\n"
    )

def test_relevant_decisions_filters_by_agent_and_active_status(tmp_path):
    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True)
    _write(dec, "a.md", id="DEC-0001", status="accepted", agents="data-integrity")
    _write(dec, "b.md", id="DEC-0002", status="deferred", agents="data-integrity")
    _write(dec, "c.md", id="DEC-0003", status="retired", agents="data-integrity")
    _write(dec, "d.md", id="DEC-0004", status="whatever-typo", agents="data-integrity")
    _write(dec, "e.md", id="DEC-0005", status="accepted", agents="security")

    got = {d.id for d in relevant_decisions("data-integrity", tmp_path)}
    assert got == {"DEC-0001", "DEC-0002"}  # accepted + deferred; retired/typo/other-agent excluded

def test_relevant_decisions_empty_when_dir_missing(tmp_path):
    assert relevant_decisions("data-integrity", tmp_path) == []

def test_missing_premise_is_rejected(tmp_path):
    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True)
    (dec / "bad.md").write_text(
        "---\nid: DEC-0009\nstatus: accepted\nagents: [security]\nconcern: c\ndate: 2026-06-01\n---\n"
    )
    with pytest.raises(ValueError, match="premise"):
        load_decisions(dec)

def test_active_decision_ids(tmp_path):
    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True)
    _write(dec, "a.md", id="DEC-0001", status="accepted", agents="security")
    _write(dec, "b.md", id="DEC-0003", status="invalidated", agents="security")
    assert active_decision_ids(tmp_path) == {"DEC-0001"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_decisions.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.review.decisions`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/framework_cli/review/decisions.py
"""Accepted design-decision records the review agents read (spec 2026-06-01).

A decision lives as one markdown file with YAML frontmatter under
docs/superpowers/decisions/. The code keys ONLY on an active allowlist; every other
status (the open "no longer stands" family + typos) is inactive, fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ACTIVE_STATUSES = frozenset({"accepted", "deferred"})


@dataclass(frozen=True)
class Decision:
    id: str
    status: str
    agents: tuple[str, ...]
    concern: str
    premise: str
    body: str
    source: str  # filename, for reporting


def _decisions_dir(root: Path) -> Path:
    return Path(root) / "docs" / "superpowers" / "decisions"


def _parse(path: Path) -> Decision:
    text = path.read_text()
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing YAML frontmatter")
    _, fm, body = text.split("---", 2)
    meta = yaml.safe_load(fm) or {}
    premise = str(meta.get("premise", "")).strip()
    if not premise:
        raise ValueError(f"{path.name}: decision is missing a non-empty `premise`")
    agents = meta.get("agents") or []
    return Decision(
        id=str(meta["id"]),
        status=str(meta.get("status", "")),
        agents=tuple(str(a) for a in agents),
        concern=str(meta.get("concern", "")),
        premise=premise,
        body=body.strip(),
        source=path.name,
    )


def load_decisions(decisions_dir: Path) -> list[Decision]:
    """Parse every *.md decision in `decisions_dir` (any status). Raises on a bad record."""
    d = Path(decisions_dir)
    if not d.is_dir():
        return []
    return [_parse(p) for p in sorted(d.glob("*.md"))]


def relevant_decisions(agent: str, root: Path) -> list[Decision]:
    """Active (accepted/deferred) decisions whose `agents` includes `agent` (short name)."""
    return [
        dec
        for dec in load_decisions(_decisions_dir(root))
        if dec.status in ACTIVE_STATUSES and agent in dec.agents
    ]


def active_decision_ids(root: Path) -> set[str]:
    """Ids of all active decisions (for the verdict integrity guard)."""
    return {
        dec.id for dec in load_decisions(_decisions_dir(root)) if dec.status in ACTIVE_STATUSES
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_decisions.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/decisions.py tests/review/test_decisions.py CLAUDE.md
git commit -m "feat(review): decision-record model + loader (active-allowlist, fail-closed)"
```
(Update CLAUDE.md Current State first — a PreToolUse hook blocks the commit until CLAUDE.md is staged.)

---

### Task 2: Render the decisions context block

**Files:**
- Modify: `src/framework_cli/review/decisions.py`
- Test: `tests/review/test_decisions.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_decisions.py
from framework_cli.review.decisions import render_decisions_block

def test_render_decisions_block_none_when_empty():
    assert render_decisions_block([]) is None

def test_render_decisions_block_contains_records_and_protocol():
    d = Decision(
        id="DEC-0001", status="accepted", agents=("data-integrity",),
        concern="prune commits internally", premise="only caller is the beat task",
        body="rationale", source="DEC-0001.md",
    )
    block = render_decisions_block([d])
    assert block is not None
    assert "DEC-0001" in block and "only caller is the beat task" in block
    assert "acknowledged:" in block and "stale:" in block  # the protocol preamble
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_decisions.py -k render -q`
Expected: FAIL — `ImportError: cannot import name 'render_decisions_block'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/framework_cli/review/decisions.py
_PROTOCOL = (
    "Accepted Decisions (design choices already made and accepted for THIS repo).\n"
    "For each finding you would raise, consult these:\n"
    "- If it matches a decision's concern AND the decision's `premise` still holds given the "
    "code → still emit the finding, but add `\"acknowledged\": \"<id>\"`.\n"
    "- If it matches but the premise NO LONGER holds → emit a normal finding with "
    "`\"stale\": \"<id>\"` and say which premise clause broke.\n"
    "- Otherwise emit the finding normally.\n"
)


def render_decisions_block(decisions: list[Decision]) -> str | None:
    """Render the protocol preamble + records as one text block, or None if no decisions."""
    if not decisions:
        return None
    records = "\n\n".join(
        f"[{d.id}] (agents: {', '.join(d.agents)})\n"
        f"  concern: {d.concern}\n"
        f"  premise (must hold, else STALE): {d.premise}\n"
        f"  rationale: {d.body}"
        for d in decisions
    )
    return f"{_PROTOCOL}\n{records}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_decisions.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/decisions.py tests/review/test_decisions.py CLAUDE.md
git commit -m "feat(review): render decisions context block (protocol + records)"
```

---

### Task 3: `Bundle.decisions` + `assemble(agent=)` population

**Files:**
- Modify: `src/framework_cli/review/context.py`
- Test: `tests/review/test_context.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_context.py
from pathlib import Path

from framework_cli.review.context import assemble
from framework_cli.review.registry import ContextPolicy

def _decision(tmp_path: Path) -> None:
    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True, exist_ok=True)
    (dec / "x.md").write_text(
        "---\nid: DEC-0001\nstatus: accepted\nagents: [security]\nconcern: c\n"
        "premise: 'must hold'\ndate: 2026-06-01\n---\n\nbody\n"
    )

def test_assemble_without_agent_has_no_decisions(tmp_path):
    _decision(tmp_path)
    b = assemble("diff", tmp_path, ContextPolicy(strategy="diff"), model="claude-opus-4-8")
    assert b.decisions == ()

def test_assemble_with_agent_populates_relevant_decisions(tmp_path):
    _decision(tmp_path)
    b = assemble(
        "diff", tmp_path, ContextPolicy(strategy="diff"), model="claude-opus-4-8", agent="security"
    )
    assert tuple(d.id for d in b.decisions) == ("DEC-0001",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_context.py -k decision -q`
Expected: FAIL — `assemble() got an unexpected keyword argument 'agent'` (and/or `Bundle` has no `decisions`).

- [ ] **Step 3: Write minimal implementation**

In `src/framework_cli/review/context.py`, add the import and field, and the `agent` parameter:

```python
# near the top imports
from framework_cli.review.decisions import Decision, relevant_decisions

# in the Bundle dataclass (add field; keep existing fields):
    decisions: tuple[Decision, ...] = ()

# change the assemble signature + populate decisions (keep all existing body logic):
def assemble(
    diff: str, root: Path, policy: ContextPolicy, *, model: str, agent: str | None = None
) -> Bundle:
    decisions = tuple(relevant_decisions(agent, root)) if agent else ()
    # ... existing body unchanged, EXCEPT every `return Bundle(...)` now also passes
    #     decisions=decisions. There are two returns (diff-only early return + final).
```

Concretely, the early `diff`-strategy return becomes `return Bundle(diff=diff, decisions=decisions)` and the final return becomes `return Bundle(diff=diff, context_files=tuple(files), truncated=truncated, decisions=decisions)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_context.py -q`
Expected: PASS (including the pre-existing context tests — `decisions` defaults to `()`).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/context.py tests/review/test_context.py CLAUDE.md
git commit -m "feat(review): Bundle.decisions + assemble(agent=) population"
```

---

### Task 4: Render decisions in `run_agent` and `run_agent_agentic` (API path)

**Files:**
- Modify: `src/framework_cli/review/runner.py`
- Modify: `src/framework_cli/review/agentic.py`
- Test: `tests/review/test_runner.py` (or the existing runner test module)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_runner.py
from framework_cli.review.context import Bundle
from framework_cli.review.decisions import Decision
from framework_cli.review.registry import get_agent
from framework_cli.review.runner import run_agent

class _FakeMsg:
    def __init__(self): self.content = [type("B", (), {"text": "[]"})()]
    stop_reason = "end_turn"
    usage = type("U", (), {"input_tokens": 0, "output_tokens": 0})()

class _FakeClient:
    def __init__(self): self.captured = None
    class messages:  # noqa
        pass
    def __init_subclass__(cls): ...

class _Recorder:
    def __init__(self): self.system = None
    def create(self, **kwargs):
        self.system = kwargs["system"]
        return _FakeMsg()

def _client(rec):
    c = type("C", (), {})()
    c.messages = rec
    return c

def test_run_agent_injects_decisions_block_when_present():
    rec = _Recorder()
    spec = get_agent("security")
    dec = Decision("DEC-1", "accepted", ("security",), "c", "premise", "body", "DEC-1.md")
    bundle = Bundle(diff="d", decisions=(dec,))
    run_agent(bundle, spec, _client(rec))
    texts = [b["text"] for b in rec.system]
    assert any("DEC-1" in t and "acknowledged:" in t for t in texts)

def test_run_agent_no_decisions_is_byte_identical():
    rec = _Recorder()
    spec = get_agent("security")
    run_agent(Bundle(diff="d"), spec, _client(rec))
    texts = [b["text"] for b in rec.system]
    # exactly: diff block + prompt block (no decisions block)
    assert len(texts) == 2 and "DEC-" not in "".join(texts)
```

(Match the existing fake-client pattern in `tests/review/test_runner.py` if it differs; the assertion is what matters — a decisions block appears iff `bundle.decisions` is non-empty, inserted before `spec.prompt`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_runner.py -k decisions -q`
Expected: FAIL — no decisions block in `system`.

- [ ] **Step 3: Write minimal implementation**

In `run_agent` (`runner.py`), after the optional `context_files` block and **before** appending `spec.prompt`:

```python
from framework_cli.review.decisions import render_decisions_block

block = render_decisions_block(list(bundle.decisions))
if block is not None:
    system.append({"type": "text", "text": block, "cache_control": {"type": "ephemeral"}})
system.append({"type": "text", "text": spec.prompt})
```

Make the identical insertion in `run_agent_agentic` (`agentic.py`), before its prompt block.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_runner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/runner.py src/framework_cli/review/agentic.py tests/review/test_runner.py CLAUDE.md
git commit -m "feat(review): render decisions block in run_agent + run_agent_agentic"
```

---

### Task 5: Inject decisions into work items + wire `review` (and exclude eval/tune)

**Files:**
- Modify: `src/framework_cli/cli.py` (`_build_audit_work_item`; the `review`/`review-agents` `assemble` calls)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cli.py
def test_build_audit_work_item_injects_decisions(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.registry import get_agent

    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True)
    (dec / "x.md").write_text(
        "---\nid: DEC-0001\nstatus: accepted\nagents: [security]\nconcern: c\n"
        "premise: 'must hold'\ndate: 2026-06-01\n---\n\nbody\n"
    )
    wi = cli_mod._build_audit_work_item(get_agent("security"), "diff", tmp_path)
    texts = [b["text"] for b in wi["system_blocks"]]
    assert any("DEC-0001" in t for t in texts)

def test_build_audit_work_item_byte_identical_without_decisions(tmp_path):
    import framework_cli.cli as cli_mod
    from framework_cli.review.registry import get_agent

    wi = cli_mod._build_audit_work_item(get_agent("security"), "diff", tmp_path)
    texts = "".join(b["text"] for b in wi["system_blocks"])
    assert "DEC-" not in texts and "Accepted Decisions" not in texts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -k "work_item_injects_decisions" -q`
Expected: FAIL — no `DEC-0001` in system blocks.

- [ ] **Step 3: Write minimal implementation**

In `_build_audit_work_item`, compute the block once from the short name and insert it before the prompt block in **both** branches:

```python
from framework_cli.review.decisions import relevant_decisions, render_decisions_block

short = spec.name.removeprefix("review-")
dec_block = render_decisions_block(relevant_decisions(short, root))
```

- Agentic branch: build `system_blocks` as `[{diff}] + ([{dec_block}] if dec_block else []) + [{prompt}]`.
- Bundle branch: after the `context_files` append and **before** `system_blocks.append({"text": spec.prompt})`, add `if dec_block: system_blocks.append({"text": dec_block})`.

Wire the API review path (so `framework review --target framework` honors decisions): in the `review`/`review-agents` command bodies, change `assemble(diff, ..., model=spec.model)` to `assemble(diff, ..., model=spec.model, agent=spec.name.removeprefix("review-"))`. **Do NOT** change the `framework eval` assemble call (it must stay `agent=None`) and do NOT touch `_emit_tune_prep` — that keeps eval/tune decision-free.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -k "work_item" -q`
Expected: PASS (both new tests).

- [ ] **Step 5: Verify eval/tune still decision-free**

Run: `grep -n "assemble(" src/framework_cli/cli.py`
Expected: the eval-path `assemble(` call has **no** `agent=` argument; only `review`/`review-agents` and `_build_audit_work_item`'s bundle branch pass an agent.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git commit -m "feat(review): inject decisions into gate/audit work items + review path"
```

---

### Task 6: `Finding` gains `acknowledged`/`stale`

**Files:**
- Modify: `src/framework_cli/review/findings.py`
- Test: `tests/review/test_findings.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_findings.py
from framework_cli.review.findings import parse_findings

def test_parse_findings_reads_acknowledged_and_stale():
    text = (
        '[{"path":"a.py","line":1,"severity":"high","message":"m","acknowledged":"DEC-0001"},'
        '{"path":"b.py","line":2,"severity":"high","message":"m","stale":"DEC-0002"}]'
    )
    fs = parse_findings(text)
    assert fs[0].acknowledged == "DEC-0001" and fs[0].stale is None
    assert fs[1].stale == "DEC-0002" and fs[1].acknowledged is None

def test_parse_findings_defaults_tags_none():
    fs = parse_findings('[{"path":"a.py","line":1,"severity":"low","message":"m"}]')
    assert fs[0].acknowledged is None and fs[0].stale is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_findings.py -k acknowledged -q`
Expected: FAIL — `Finding` has no `acknowledged`.

- [ ] **Step 3: Write minimal implementation**

In `findings.py`, add fields to `Finding` and read them in `parse_findings`:

```python
@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    severity: Severity
    message: str
    suggestion: str | None = None
    acknowledged: str | None = None
    stale: str | None = None
```

In `parse_findings`, in the `Finding(...)` construction add:

```python
        acknowledged=str(item["acknowledged"]) if item.get("acknowledged") else None,
        stale=str(item["stale"]) if item.get("stale") else None,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_findings.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/findings.py tests/review/test_findings.py CLAUDE.md
git commit -m "feat(review): Finding gains acknowledged/stale tags"
```

---

### Task 7: Gate verdict honors `acknowledged` (with integrity guard)

**Files:**
- Modify: `src/framework_cli/cli.py` (`_finalize_gate`)
- Modify: `src/framework_cli/review/analyze.py` (acknowledged report section)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cli.py — exercise gate-finalize end to end
import json as _json
from pathlib import Path

def _run_gate_finalize(tmp_path, finding: dict, decisions: list[dict]) -> str:
    # seed a decisions dir
    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True)
    for d in decisions:
        (dec / f"{d['id']}.md").write_text(
            f"---\nid: {d['id']}\nstatus: {d['status']}\nagents: [security]\n"
            f"concern: c\npremise: 'p'\ndate: 2026-06-01\n---\n\nbody\n"
        )
    results = tmp_path / "results.json"
    results.write_text(_json.dumps({
        "results": [{"agent": "security", "findings": [finding]}],
        "meta": {"mode": "gate", "staged_hash": "sha256:x", "agents_set": ["security"]},
    }))
    out = tmp_path / ".framework" / "audit" / "latest"
    out.mkdir(parents=True)
    import subprocess, sys
    subprocess.run(
        [sys.executable, "-m", "framework_cli", "gate-finalize",
         "--results", str(results), "--out-dir", str(out)],
        cwd=tmp_path, check=True,
    )
    return _json.loads((out.parent / "marker.json").read_text())["verdict"]

def test_acknowledged_finding_against_active_decision_passes(tmp_path):
    f = {"path": "a.py", "line": 1, "severity": "high", "message": "m", "acknowledged": "DEC-0001"}
    v = _run_gate_finalize(tmp_path, f, [{"id": "DEC-0001", "status": "accepted"}])
    assert v == "PASS"

def test_acknowledged_against_inactive_id_still_blocks(tmp_path):
    f = {"path": "a.py", "line": 1, "severity": "high", "message": "m", "acknowledged": "DEC-0001"}
    v = _run_gate_finalize(tmp_path, f, [{"id": "DEC-0001", "status": "retired"}])
    assert v == "FAIL"

def test_stale_finding_blocks(tmp_path):
    f = {"path": "a.py", "line": 1, "severity": "high", "message": "m", "stale": "DEC-0001"}
    v = _run_gate_finalize(tmp_path, f, [{"id": "DEC-0001", "status": "accepted"}])
    assert v == "FAIL"
```

(`security` has `block_threshold="high"`, so an un-acknowledged high finding blocks. Adjust the module-invocation line to however the suite invokes the CLI if `python -m framework_cli` differs.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -k "acknowledged_finding_against_active" -q`
Expected: FAIL — verdict is `FAIL` (acknowledged not yet honored).

- [ ] **Step 3: Write minimal implementation**

In `_finalize_gate`, before computing `failing`, resolve the active ids once, and exclude acknowledged-active findings from the per-agent blocking list:

```python
from framework_cli.review.decisions import active_decision_ids

active_ids = active_decision_ids(Path.cwd())
```

When building `findings_objs` for the blocking check, split:

```python
        blocking = [
            f for f in findings_objs
            if not (f.acknowledged and f.acknowledged in active_ids)
        ]
        if spec.block_threshold is None:
            continue
        if flags(blocking, spec):
            failing = True
            summary_parts.append(f"{r.agent}:{len(blocking)}")
```

(The full `findings_objs` — including acknowledged — are still written to the per-agent records in `findings_dir`, so they remain in the report. Construct `Finding(...)` with the new `acknowledged`/`stale` kwargs read from `f`.)

In `analyze.render_markdown` (report), add a section listing findings that carry an `acknowledged` tag resolving to an active decision, under a heading like `## Acknowledged (covered by decisions)`, separate from the blocking findings.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -k "acknowledged or stale_finding" -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py src/framework_cli/review/analyze.py tests/test_cli.py CLAUDE.md
git commit -m "feat(review): gate verdict honors acknowledged decisions (active-id guard)"
```

---

### Task 8: Seed decisions + full-suite verification

**Files:**
- Create: `docs/superpowers/decisions/DEC-0001-dlq-prune-internal-commit.md`
- Create: `docs/superpowers/decisions/DEC-0002-dlq-args-json-opt-in-redaction.md`

- [ ] **Step 1: Write DEC-0001**

```markdown
---
id: DEC-0001
status: accepted
agents: [data-integrity]
concern: "prune_expired commits its own DB session internally"
premise: >
  The only caller is the prune_expired_records beat task, which scopes a dedicated
  session for the prune. If prune_expired is ever called inside a caller's outer
  transaction (a shared session), this decision is STALE.
date: 2026-06-01
---

A standalone maintenance prune is intentionally self-committing — see
src/framework_cli/template/.../tasks/dead_letter.py and the v0.1.0 release-fix
(commit 935588f). Re-raise if the caller set changes.
```

- [ ] **Step 2: Write DEC-0002**

```markdown
---
id: DEC-0002
status: deferred
agents: [compliance]
concern: "DLQ args_json default stores task args unredacted (opt-in redaction seam)"
premise: >
  The BaseTask.dlq_args_json override seam exists and is documented. This is tracked
  debt pending the DLQ-PII compliance-posture follow-up; the default-redact question
  is decided there, not here.
date: 2026-06-01
---

Deferred (not accepted-forever): the redaction default is intentionally opt-in for now.
Tracked by the DLQ-PII compliance-posture slice. Re-raise if that slice closes without
a decision, or if the seam is removed.
```

- [ ] **Step 3: Verify the seed decisions load**

Run: `uv run python -c "from pathlib import Path; from framework_cli.review.decisions import relevant_decisions; print([d.id for d in relevant_decisions('data-integrity', Path('.'))], [d.id for d in relevant_decisions('compliance', Path('.'))])"`
Expected: `['DEC-0001'] ['DEC-0002']`

- [ ] **Step 4: Full gate (lint + types + suite)**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q --ignore=tests/acceptance`
Expected: all green; the new tests pass; no regression.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/decisions/ CLAUDE.md
git commit -m "feat(review): seed DEC-0001 (prune commit) + DEC-0002 (opt-in redaction)"
```

---

## Self-Review

**Spec coverage:**
- §3 record format → Task 1 (model/loader), Task 8 (seed files). `premise` required → Task 1.
- §3 active-allowlist / fail-closed → Task 1 (`ACTIVE_STATUSES`, status-not-in-set excluded incl. typos).
- §4 injection + protocol + inert-until-used → Tasks 2 (render), 4 (API path), 5 (subagent path); byte-identity tests in Tasks 4 & 5.
- §5 schema + verdict + integrity guard + report section → Tasks 6 (fields) + 7 (verdict filter, active-id guard, report).
- §6 consumers (gate/audit/review) → Task 5; eval/tune exclusion → Task 5 Step 5 (no `agent=` on eval; tune untouched).
- §7 tests → every task is TDD; fail-closed + byte-identity + integrity-guard all covered.
- §8 seed decisions → Task 8.

**Placeholder scan:** none — every code step shows the code; every run step shows the command + expected output.

**Type consistency:** `Decision` fields (id/status/agents/concern/premise/body/source) are consistent across Tasks 1/2/3. `relevant_decisions(agent, root)`, `active_decision_ids(root)`, `render_decisions_block(list[Decision])` signatures match all call sites (context.py, cli.py, _finalize_gate). `Finding` gains `acknowledged`/`stale` (Task 6) and they're read in `_finalize_gate` (Task 7) and rendered in the protocol (Task 2). Agent matching uses the short name (`removeprefix("review-")`) everywhere.

**Note for the implementer:** confirm the exact fake-client shape used by `tests/review/test_runner.py` and the CLI invocation style in `tests/test_cli.py`; adapt the test scaffolding in Tasks 4 & 7 to match the existing pattern (the assertions are the contract). All work is framework source — run `uv run pytest`, not the template render loop.
