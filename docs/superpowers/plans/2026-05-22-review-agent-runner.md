# Layer-3 Review Agent Runner (Plan 7a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `framework review <agent>` — a CLI subcommand that reviews the PR diff with an Anthropic-backed agent, emits structured findings, and posts a GitHub Check Run — proven end-to-end with `review-security` and wired into the generated `ci.yml`.

**Architecture:** The runner lives in the installed CLI (`src/framework_cli/review/`), like `framework integrity` — framework-owned, normally tested, prompts versioned with the framework. Deterministic plumbing (parse → conclusion → annotations) is unit-tested with a **mocked** Anthropic client; real review *quality* is the eval harness's job (Plan 7d). Infra failure (no key, API error, bad output) → a `neutral` Check Run, never a CI hard-fail. The generated project gains only a thin `ci.yml` `review` job that installs the framework (the Plan 6b pattern) and runs `framework review security`.

**Tech Stack:** Python 3.12, Typer, the `anthropic` SDK (lazy import, prompt caching), the GitHub Checks API via `gh`, pytest. Design: `docs/superpowers/specs/2026-05-22-review-agent-runner-design.md`.

---

## Scope

**In scope:** the `src/framework_cli/review/` package (findings contract, agent registry + `review-security` prompt, runner, Check Run mapping/posting, diff), the `framework review` CLI command, `anthropic` as a CLI dep, and the generated `ci.yml` review-job activation.

**Out of scope (later sub-plans):** the other 14 agents + triggering matrix (7b), cross-agent interactions + aggregator (7c), the eval harness (7d). No real Anthropic API call in the framework's tests (mocked); real quality is 7d.

## Repo working agreement for EVERY commit

A `PreToolUse` hook **blocks `git commit` unless `CLAUDE.md` has a staged change.** Each "Commit" step: (1) bump `CLAUDE.md` Current State → Last updated (datetime + `PDT`); (2) `git add <files> CLAUDE.md` as ONE call; (3) `git commit` as a SEPARATE call. End the body with:
```
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

## File Structure

**New (framework source):**
- `src/framework_cli/review/__init__.py`
- `src/framework_cli/review/findings.py` — `Severity`, `Finding`, `severity_rank`, `parse_findings`, `FindingsParseError`.
- `src/framework_cli/review/registry.py` — `AgentSpec`, `get_agent`, `agent_names`.
- `src/framework_cli/review/agents/security.md` — the `review-security` prompt (package data).
- `src/framework_cli/review/checks.py` — `CheckRunPayload`, `to_check_run`, `neutral_payload`, `post_check_run`, `post_or_skip`.
- `src/framework_cli/review/runner.py` — `run_agent`, `default_client`.
- `src/framework_cli/review/diff.py` — `pr_diff`.

**Modified (framework source):** `src/framework_cli/cli.py` (add `review` command); `pyproject.toml` (add `anthropic`).

**Modified (template payload):** `src/framework_cli/template/.github/workflows/ci.yml.jinja` (activate the `review` job).

**New tests:** `tests/review/__init__.py`, `tests/review/test_findings.py`, `test_registry.py`, `test_checks.py`, `test_runner.py`, `test_diff.py`; extend `tests/test_cli.py` + `tests/test_copier_runner.py`.

---

### Task 1: The findings contract (`findings.py`)

**Files:** Create `src/framework_cli/review/__init__.py` (empty + docstring), `src/framework_cli/review/findings.py`, `tests/review/__init__.py` (empty), `tests/review/test_findings.py`.

- [ ] **Step 1: Write the failing test** — `tests/review/test_findings.py`:

```python
import pytest

from framework_cli.review.findings import (
    Finding,
    FindingsParseError,
    parse_findings,
    severity_rank,
)

_JSON = '[{"path": "a.py", "line": 3, "severity": "high", "message": "SQL injection", "suggestion": "use params"}]'


def test_parse_plain_json():
    findings = parse_findings(_JSON)
    assert findings == [Finding("a.py", 3, "high", "SQL injection", "use params")]


def test_parse_json_in_code_fence_and_prose():
    wrapped = f"Here are my findings:\n```json\n{_JSON}\n```\nDone."
    assert parse_findings(wrapped)[0].path == "a.py"


def test_parse_empty_array():
    assert parse_findings("[]") == []


def test_parse_optional_suggestion_absent():
    findings = parse_findings('[{"path": "x", "line": 1, "severity": "low", "message": "m"}]')
    assert findings[0].suggestion is None


def test_invalid_severity_raises():
    with pytest.raises(FindingsParseError):
        parse_findings('[{"path": "x", "line": 1, "severity": "nope", "message": "m"}]')


def test_no_array_raises():
    with pytest.raises(FindingsParseError):
        parse_findings("I could not produce JSON.")


def test_severity_rank_orders_critical_above_info():
    assert severity_rank("critical") > severity_rank("high") > severity_rank("info")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/review/test_findings.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.review`.

- [ ] **Step 3: Implement** — `src/framework_cli/review/__init__.py`:

```python
"""Layer-3 AI review agents — runner, contract, and agent registry (spec §7).

Lives in the installed CLI (like `framework integrity`) so it is framework-owned and the
agent prompts are versioned with the framework.
"""
```

`src/framework_cli/review/findings.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

Severity = Literal["critical", "high", "medium", "low", "info"]
_RANK: dict[str, int] = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class FindingsParseError(Exception):
    """The agent response could not be parsed as a findings JSON array."""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    severity: Severity
    message: str
    suggestion: str | None = None


def severity_rank(severity: str) -> int:
    return _RANK[severity]


def _extract_array(text: str) -> str:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise FindingsParseError("no JSON array found in agent response")
    return text[start : end + 1]


def parse_findings(text: str) -> list[Finding]:
    try:
        data = json.loads(_extract_array(text))
    except json.JSONDecodeError as exc:
        raise FindingsParseError(str(exc)) from exc
    if not isinstance(data, list):
        raise FindingsParseError("findings payload is not a list")
    findings: list[Finding] = []
    for item in data:
        if not isinstance(item, dict) or item.get("severity") not in _RANK:
            raise FindingsParseError(f"invalid finding: {item!r}")
        findings.append(
            Finding(
                path=str(item["path"]),
                line=int(item["line"]),
                severity=item["severity"],
                message=str(item["message"]),
                suggestion=str(item["suggestion"]) if item.get("suggestion") else None,
            )
        )
    return findings
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/review/test_findings.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/__init__.py src/framework_cli/review/findings.py \
        tests/review/__init__.py tests/review/test_findings.py CLAUDE.md
```
```bash
git commit -m "feat(review): structured findings contract + tolerant JSON parse"
```

---

### Task 2: Agent registry + the `review-security` prompt

**Files:** Create `src/framework_cli/review/registry.py`, `src/framework_cli/review/agents/security.md`; Test `tests/review/test_registry.py`.

- [ ] **Step 1: Write the failing test** — `tests/review/test_registry.py`:

```python
import pytest

from framework_cli.review.registry import AgentSpec, agent_names, get_agent


def test_security_agent_spec():
    spec = get_agent("security")
    assert isinstance(spec, AgentSpec)
    assert spec.name == "review-security"
    assert spec.block_threshold == "high"
    assert spec.active_when == "always"
    assert spec.model  # a model id is set
    assert "OWASP" in spec.prompt or "injection" in spec.prompt
    assert "JSON" in spec.prompt  # instructs JSON-only output


def test_unknown_agent_raises():
    with pytest.raises(KeyError):
        get_agent("nope")


def test_agent_names_lists_security():
    assert "security" in agent_names()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/review/test_registry.py -q`
Expected: FAIL — `ModuleNotFoundError` on `registry`.

- [ ] **Step 3: Implement** — `src/framework_cli/review/agents/security.md`:

```markdown
You are `review-security`, a precise application-security reviewer. You are given a unified
diff and must review ONLY the changes in it (added/modified lines), not the whole codebase.

Look for: authentication/authorization flaws; injection (SQL, command, template, path); secrets
or credentials committed in code/config; use of dependencies with known CVEs; and the OWASP Top
10 (broken access control, cryptographic failures, insecure design, security misconfiguration,
SSRF, etc.). Prefer precision over volume — report only issues you can point to on a specific
changed line.

Return JSON ONLY — a single JSON array, no prose, no code fences. Each element:
{"path": "<file path from the diff>", "line": <integer line number>, "severity":
"critical|high|medium|low|info", "message": "<what is wrong and why it matters>", "suggestion":
"<concrete fix, optional>"}

If you find nothing, return []. Severity guidance: critical/high = exploitable or
secret-exposing; medium = risky pattern; low/info = hardening or advisory.
```

`src/framework_cli/review/registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from typing import Literal

from framework_cli.review.findings import Severity

ActiveWhen = Literal["always", "battery", "file-trigger"]

# Latest Sonnet (good cost/quality default; per-agent overridable).
DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    prompt: str
    block_threshold: Severity
    active_when: ActiveWhen
    model: str


def _prompt(name: str) -> str:
    return (files("framework_cli.review") / "agents" / f"{name}.md").read_text()


_SPECS: dict[str, AgentSpec] = {
    "security": AgentSpec(
        name="review-security",
        prompt=_prompt("security"),
        block_threshold="high",
        active_when="always",
        model=DEFAULT_MODEL,
    ),
}


def get_agent(name: str) -> AgentSpec:
    if name not in _SPECS:
        raise KeyError(f"unknown review agent: {name}")
    return _SPECS[name]


def agent_names() -> list[str]:
    return sorted(_SPECS)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/review/test_registry.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean. (Hatchling includes non-`.py` files under the package, so `agents/security.md` ships in the wheel; `importlib.resources.files` reads it.)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/registry.py src/framework_cli/review/agents/security.md \
        tests/review/test_registry.py CLAUDE.md
```
```bash
git commit -m "feat(review): agent registry + review-security prompt"
```

---

### Task 3: Findings → Check Run mapping (`checks.py`)

**Files:** Create `src/framework_cli/review/checks.py`; Test `tests/review/test_checks.py`.

- [ ] **Step 1: Write the failing test** — `tests/review/test_checks.py`:

```python
from framework_cli.review.checks import neutral_payload, to_check_run
from framework_cli.review.findings import Finding
from framework_cli.review.registry import get_agent

_SPEC = get_agent("security")  # block_threshold = high


def test_no_findings_is_success():
    payload = to_check_run(_SPEC, [])
    assert payload.conclusion == "success"
    assert payload.annotations == []


def test_blocking_finding_is_failure():
    payload = to_check_run(_SPEC, [Finding("a.py", 1, "high", "m")])
    assert payload.conclusion == "failure"
    assert payload.annotations[0]["path"] == "a.py"
    assert payload.annotations[0]["start_line"] == 1


def test_below_threshold_is_neutral():
    payload = to_check_run(_SPEC, [Finding("a.py", 1, "low", "m"), Finding("b.py", 2, "medium", "m")])
    assert payload.conclusion == "neutral"
    assert len(payload.annotations) == 2


def test_annotation_includes_suggestion_and_level():
    payload = to_check_run(_SPEC, [Finding("a.py", 1, "critical", "boom", "fix it")])
    ann = payload.annotations[0]
    assert ann["annotation_level"] == "failure"
    assert "fix it" in ann["message"]


def test_neutral_payload():
    payload = neutral_payload("review-security", "skipped")
    assert payload.conclusion == "neutral" and payload.annotations == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/review/test_checks.py -q`
Expected: FAIL — `ModuleNotFoundError` on `checks`.

- [ ] **Step 3: Implement** — `src/framework_cli/review/checks.py`:

```python
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

from framework_cli.review.findings import Finding, severity_rank
from framework_cli.review.registry import AgentSpec

# GitHub annotation_level per severity.
_LEVEL = {
    "critical": "failure",
    "high": "failure",
    "medium": "warning",
    "low": "notice",
    "info": "notice",
}
_MAX_ANNOTATIONS = 50  # GitHub Checks API limit per request


@dataclass(frozen=True)
class CheckRunPayload:
    name: str
    conclusion: str  # "success" | "neutral" | "failure"
    title: str
    summary: str
    annotations: list[dict] = field(default_factory=list)


def to_check_run(spec: AgentSpec, findings: list[Finding]) -> CheckRunPayload:
    threshold = severity_rank(spec.block_threshold)
    blocking = [f for f in findings if severity_rank(f.severity) >= threshold]
    conclusion = "success" if not findings else ("failure" if blocking else "neutral")
    annotations = [
        {
            "path": f.path,
            "start_line": f.line,
            "end_line": f.line,
            "annotation_level": _LEVEL[f.severity],
            "title": f"{spec.name}: {f.severity}",
            "message": f.message + (f"\n\nSuggestion: {f.suggestion}" if f.suggestion else ""),
        }
        for f in findings[:_MAX_ANNOTATIONS]
    ]
    summary = "No findings." if not findings else f"{len(findings)} finding(s); {len(blocking)} blocking."
    return CheckRunPayload(spec.name, conclusion, f"{spec.name}: {conclusion}", summary, annotations)


def neutral_payload(name: str, reason: str) -> CheckRunPayload:
    return CheckRunPayload(name, "neutral", f"{name}: skipped", reason, [])


def post_check_run(payload: CheckRunPayload, *, token: str, repo: str, sha: str) -> None:
    """Post the Check Run via the `gh` CLI (available on GitHub runners)."""
    body = json.dumps(
        {
            "name": payload.name,
            "head_sha": sha,
            "status": "completed",
            "conclusion": payload.conclusion,
            "output": {"title": payload.title, "summary": payload.summary, "annotations": payload.annotations},
        }
    )
    subprocess.run(
        ["gh", "api", f"repos/{repo}/check-runs", "--method", "POST", "--input", "-"],
        input=body,
        text=True,
        check=True,
        capture_output=True,
        env={**os.environ, "GH_TOKEN": token},
    )


def post_or_skip(payload: CheckRunPayload, *, token: str, repo: str, sha: str) -> None:
    """Post if we have GitHub context; never raise (posting failure must not block CI)."""
    if not (token and repo and sha):
        return
    try:
        post_check_run(payload, token=token, repo=repo, sha=sha)
    except Exception:  # noqa: BLE001 - posting failure is non-fatal by design
        pass
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/review/test_checks.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/checks.py tests/review/test_checks.py CLAUDE.md
```
```bash
git commit -m "feat(review): findings -> Check Run mapping + non-fatal posting"
```

---

### Task 4: The runner (`runner.py`) + the `anthropic` dependency

**Files:** Modify `pyproject.toml`; Create `src/framework_cli/review/runner.py`; Test `tests/review/test_runner.py`.

- [ ] **Step 1: Add the dependency** — in `pyproject.toml`, add `"anthropic>=0.40"` to `[project] dependencies` (keep the list alphabetical-ish; place after `anthropic`'s neighbors):

```toml
dependencies = [
    "anthropic>=0.40",
    "copier>=9.4",
    "pathspec>=0.12",
    "pyyaml>=6.0",
    "typer>=0.15",
]
```

Run: `uv sync`  (installs `anthropic`).

- [ ] **Step 2: Write the failing test** — `tests/review/test_runner.py`:

```python
from framework_cli.review.findings import Finding
from framework_cli.review.registry import get_agent
from framework_cli.review.runner import run_agent


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Message:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, text):
        self._text = text
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _Message(self._text)


class _FakeClient:
    def __init__(self, text):
        self.messages = _FakeMessages(text)


def test_run_agent_parses_findings_from_client():
    client = _FakeClient('[{"path": "a.py", "line": 2, "severity": "high", "message": "bad"}]')
    findings = run_agent("--- a/a.py\n+++ b/a.py\n", get_agent("security"), client)
    assert findings == [Finding("a.py", 2, "high", "bad")]


def test_run_agent_caches_the_diff_prefix():
    client = _FakeClient("[]")
    run_agent("THE DIFF", get_agent("security"), client)
    system = client.messages.last_kwargs["system"]
    # The diff is the first system block and is marked for prompt caching; the agent prompt follows.
    assert "THE DIFF" in system[0]["text"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert any("review-security" in b["text"] or "security" in b["text"].lower() for b in system[1:])
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/review/test_runner.py -q`
Expected: FAIL — `ModuleNotFoundError` on `runner`.

- [ ] **Step 4: Implement** — `src/framework_cli/review/runner.py`:

```python
from __future__ import annotations

from typing import Any

from framework_cli.review.findings import Finding, parse_findings
from framework_cli.review.registry import AgentSpec

_MAX_DIFF_CHARS = 200_000
_MAX_TOKENS = 4096


def run_agent(diff: str, spec: AgentSpec, client: Any) -> list[Finding]:
    """Call the LLM with `spec`'s prompt over `diff`; return parsed findings.

    The diff is the first system block (a cached prefix shared across agents); the agent
    prompt is the second. `client` is an Anthropic-style client (injected for tests).
    """
    message = client.messages.create(
        model=spec.model,
        max_tokens=_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": f"Review this unified diff:\n\n{diff[:_MAX_DIFF_CHARS]}",
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": spec.prompt},
        ],
        messages=[{"role": "user", "content": "Return your findings as a JSON array only."}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )
    return parse_findings(text)


def default_client() -> Any:  # pragma: no cover - thin SDK wrapper, exercised by the manual smoke
    import anthropic

    return anthropic.Anthropic()
```

- [ ] **Step 5: Run it to verify it passes**

Run: `uv run pytest tests/review/test_runner.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/framework_cli/review/runner.py tests/review/test_runner.py CLAUDE.md
```
```bash
git commit -m "feat(review): agent runner (Anthropic, diff-prefix prompt caching) + anthropic dep"
```

---

### Task 5: PR diff resolution (`diff.py`)

**Files:** Create `src/framework_cli/review/diff.py`; Test `tests/review/test_diff.py`.

- [ ] **Step 1: Write the failing test** — `tests/review/test_diff.py`:

```python
import subprocess
from pathlib import Path

from framework_cli.review.diff import pr_diff


def _git(repo: Path, *a):
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)


def test_pr_diff_returns_last_commit_changes_without_base(tmp_path: Path, monkeypatch):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@x")
    _git(repo, "config", "user.name", "t")
    (repo / "f.py").write_text("a = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "one")
    (repo / "f.py").write_text("a = 1\nb = 2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "two")

    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.chdir(repo)
    diff = pr_diff()
    assert "b = 2" in diff and "f.py" in diff
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/review/test_diff.py -q`
Expected: FAIL — `ModuleNotFoundError` on `diff`.

- [ ] **Step 3: Implement** — `src/framework_cli/review/diff.py`:

```python
from __future__ import annotations

import os
import subprocess


def pr_diff() -> str:
    """The unified diff to review, derived from the CI environment.

    On a PR, GITHUB_BASE_REF names the base branch (diff base...HEAD); otherwise diff the
    last commit (HEAD~1...HEAD).
    """
    base = os.environ.get("GITHUB_BASE_REF")
    if base:
        subprocess.run(
            ["git", "fetch", "--depth=1", "origin", base], check=False, capture_output=True
        )
        rng = f"origin/{base}...HEAD"
    else:
        rng = "HEAD~1...HEAD"
    result = subprocess.run(
        ["git", "diff", rng], capture_output=True, text=True, check=False
    )
    return result.stdout
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/review/test_diff.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/diff.py tests/review/test_diff.py CLAUDE.md
```
```bash
git commit -m "feat(review): PR diff resolution from the CI environment"
```

---

### Task 6: The `framework review` command

**Files:** Modify `src/framework_cli/cli.py`; Test `tests/test_cli.py`.

- [ ] **Step 1: Write the failing test** — add to `tests/test_cli.py`:

```python
def test_review_skips_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 0
    assert "skipped" in result.output


def test_review_unknown_agent_errors(monkeypatch):
    result = runner.invoke(app, ["review", "nope"])
    assert result.exit_code == 1
    assert "unknown review agent" in result.output


def test_review_blocking_finding_exits_1(monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # no posting in tests
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(cli_mod, "_review_run", lambda diff, spec: [Finding("a.py", 1, "high", "bad")])
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 1
    assert "failure" in result.output


def test_review_low_finding_exits_0(monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(cli_mod, "_review_run", lambda diff, spec: [Finding("a.py", 1, "low", "m")])
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 0
    assert "neutral" in result.output


def test_review_infra_error_is_neutral_exit_0(monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def _boom():
        raise RuntimeError("API down")

    monkeypatch.setattr(cli_mod, "_review_diff", _boom)
    result = runner.invoke(app, ["review", "security"])
    assert result.exit_code == 0
    assert "neutral" in result.output or "could not run" in result.output
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cli.py -k review -q`
Expected: FAIL — no `review` command.

- [ ] **Step 3: Implement** — In `src/framework_cli/cli.py`, add module-level seams + the command. Add these imports at the top (alphabetical within the `framework_cli` block):

```python
import os

from framework_cli.review.checks import neutral_payload, post_or_skip, to_check_run
from framework_cli.review.diff import pr_diff
from framework_cli.review.registry import get_agent
from framework_cli.review.runner import default_client, run_agent
```

Add two thin module-level seams (so tests can monkeypatch the I/O without touching the SDK):

```python
def _review_diff() -> str:
    return pr_diff()


def _review_run(diff, spec):
    return run_agent(diff, spec, default_client())
```

Add the command (after the existing commands):

```python
@app.command()
def review(agent: str = typer.Argument(..., help="Review agent name, e.g. 'security'.")) -> None:
    """Run a Layer-3 review agent over the PR diff and post a GitHub Check Run."""
    try:
        spec = get_agent(agent)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        payload = neutral_payload(spec.name, "review skipped — set ANTHROPIC_API_KEY to enable.")
        post_or_skip(payload, token=token, repo=repo, sha=sha)
        typer.echo(f"{spec.name}: skipped (no ANTHROPIC_API_KEY)")
        raise typer.Exit(0)

    try:
        findings = _review_run(_review_diff(), spec)
        payload = to_check_run(spec, findings)
    except Exception as exc:  # noqa: BLE001 - infra failure must not block CI
        payload = neutral_payload(spec.name, f"review could not run: {exc}")
        post_or_skip(payload, token=token, repo=repo, sha=sha)
        typer.echo(f"{spec.name}: neutral (could not run: {exc})", err=True)
        raise typer.Exit(0) from exc

    post_or_skip(payload, token=token, repo=repo, sha=sha)
    typer.echo(f"{spec.name}: {payload.conclusion} ({len(payload.annotations)} finding(s))")
    raise typer.Exit(1 if payload.conclusion == "failure" else 0)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_cli.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS (all CLI tests); mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(review): framework review command (skip/neutral/block; non-fatal posting)"
```

---

### Task 7: Activate the generated `ci.yml` review job

**Files:** Modify `src/framework_cli/template/.github/workflows/ci.yml.jinja`; Test `tests/test_copier_runner.py`.

- [ ] **Step 1: Write the failing test** — add to `tests/test_copier_runner.py`:

```python
def test_ci_review_job_runs_framework_review(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(
        dest,
        {"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"},
    )
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "framework review security" in ci
    assert "uv tool install" in ci and "_commit" in ci  # framework installed at the recorded version
    assert "ANTHROPIC_API_KEY" in ci
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_ci_review_job_runs_framework_review -q`
Expected: FAIL — the `review` job is still the echo placeholder.

- [ ] **Step 3: Implement** — In `src/framework_cli/template/.github/workflows/ci.yml.jinja`, replace the `review` job (the comment + `review:` job with its echo step) with:

```yaml
  # Steps 9-10: Layer-3 AI review agents (spec §7). Opt-in: set the ANTHROPIC_API_KEY secret to
  # enable. Each agent posts a `review-*` GitHub Check Run; require those checks in branch
  # protection to gate merges on findings. A missing key or API error → a neutral check (never a
  # spurious CI failure). The full agent set + aggregator arrive in later framework versions.
  review:
    needs: [test, contract]
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
      pull-requests: read
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
      - name: install the framework CLI at the recorded version
        run: |
          ref="$(awk '/^_commit:/ {print $2}' .copier-answers.yml)"
          uv tool install "git+https://github.com/cdowell-swtr/swiftwater-framework@${ref}"
      - name: review-security
        env:
          ANTHROPIC_API_KEY: {% raw %}${{ secrets.ANTHROPIC_API_KEY }}{% endraw %}
          GITHUB_TOKEN: {% raw %}${{ github.token }}{% endraw %}
        run: framework review security
```

- [ ] **Step 4: Run it to verify it passes + nothing else broke**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS. Then confirm the rendered workflow is valid YAML and the `review` job parses:
```bash
uv run python -c "
import tempfile, pathlib, yaml
from framework_cli.copier_runner import render_project
d = pathlib.Path(tempfile.mkdtemp())/'p'
render_project(d, {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12'})
doc = yaml.safe_load((d/'.github/workflows/ci.yml').read_text())
print('review steps:', len(doc['jobs']['review']['steps']), '| perms:', doc['jobs']['review']['permissions'])
"
```
Report the output (expect 4 steps + the `checks: write` permission).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/.github/workflows/ci.yml.jinja tests/test_copier_runner.py CLAUDE.md
```
```bash
git commit -m "feat(review): activate the generated ci.yml review job (framework review security)"
```

---

## Self-Review

**1. Spec coverage (`docs/superpowers/specs/2026-05-22-review-agent-runner-design.md`):**
- §3 framework-source layout → Tasks 1 (`findings`), 2 (`registry` + `agents/security.md`), 3 (`checks`), 4 (`runner` + `anthropic` dep), 5 (`diff`), 6 (the `review` command).
- §4 finding→Check Run contract (severity threshold; annotations; conclusion) → Task 3.
- §5 CI wiring (install framework + `framework review security`, `checks: write`, `ANTHROPIC_API_KEY`) → Task 7.
- §2/§6 testability split: mocked client in `test_runner`; `to_check_run`/`parse_findings` pure; the command's skip/neutral/block paths via monkeypatched seams; **no real API call** in tests. Infra-failure→neutral and opt-in-by-secret are both directly tested (Task 6).
- §6 generated-project cleanliness: only `ci.yml` changes ship into projects → `test_rendered_project_precommit_runs_clean` stays green by construction.
- "Blocks merge = branch protection" documented in the `ci.yml` job comment (Task 7).

**2. Placeholder scan:** none — every step has complete code + an exact command. `default_client` (the only real-SDK touchpoint) is `# pragma: no cover`, exercised by the documented manual smoke, consistent with "real quality is 7d."

**3. Type consistency:** `Finding(path, line, severity, message, suggestion)`, `Severity`, `severity_rank`, `parse_findings`, `FindingsParseError`; `AgentSpec(name, prompt, block_threshold, active_when, model)`, `get_agent`/`agent_names`; `CheckRunPayload(name, conclusion, title, summary, annotations)`, `to_check_run`/`neutral_payload`/`post_or_skip`; `run_agent(diff, spec, client)`/`default_client`; `pr_diff()` — all consistent across tasks and the `review` command. The command monkeypatch seams `_review_diff`/`_review_run` are defined in Task 6 and used by its tests.

**Architecture note:** runner lives in the CLI (`framework review`), matching the spec revision; the generated project gains only the `ci.yml` job (installed-framework pattern from Plan 6b).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-review-agent-runner.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks.

**2. Inline Execution** — execute here with checkpoints.

Which approach?
