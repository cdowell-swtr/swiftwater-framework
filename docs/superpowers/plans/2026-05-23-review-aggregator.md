# Cross-Agent Interactions + Review Aggregator (Plan 7c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect every review agent's findings as per-agent JSON artifacts, then consolidate them into one sticky PR comment that surfaces deterministic cross-agent relationships.

**Architecture:** `framework review <agent> --findings-out <path>` writes a lossless `{agent, conclusion, findings}` JSON at every terminal path. A pure `aggregate(results)` computes overall pass/fail, per-severity counts, and relationships (same file flagged by ≥2 agents + known related-domain pairs), and renders markdown. `framework review-aggregate <dir>` reads the per-agent files and posts/updates a single sticky PR comment via `gh` (prints on push). The generated `ci.yml` uploads per-agent findings (`if: always()`) and adds a `review-aggregate` job.

**Tech Stack:** Python 3.12, Typer CLI, `dataclasses`, `gh` CLI (subprocess), pytest + `typer.testing.CliRunner`, Copier/Jinja template, GitHub Actions.

**Source spec:** `docs/superpowers/specs/2026-05-22-review-aggregator-design.md`

---

## Standing rules for every task

- **TDD:** write the failing test, run it red, write the minimum to pass, run it green, commit.
- **Commit-gate hook:** a `PreToolUse` hook blocks `git commit` unless a **change to `CLAUDE.md` is staged**. So in every commit step: edit the `**Last updated:**` line near the top of `CLAUDE.md` to the current datetime + timezone (e.g. `2026-05-23 09:40 PDT`) with a one-clause note of what the commit did, then `git add CLAUDE.md` alongside the task's files. `git add` of an *unmodified* `CLAUDE.md` does **not** satisfy the hook — there must be a real staged diff. Do **not** rewrite the longer "Where we are / Next" narrative per task; the controller finalizes that at merge.
- **`git add` then `git commit` must be two separate Bash calls** (the hook inspects the staged index *before* the commit command runs; a combined `git add ... && git commit` is evaluated before the add takes effect and is blocked).
- Run only targeted tests during a task (e.g. `uv run pytest tests/review/test_aggregate.py -q`). Do **not** run the full Docker-gated acceptance suite mid-task — it has exhausted `/tmp` here before. The final whole-branch review runs the complete gate.
- Quality gate per task before commit: `uv run pytest -q <touched test files>`, `uv run ruff check .`, `uv run mypy src`.

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/framework_cli/review/aggregate.py` (create) | The findings JSON contract (write half) + the pure aggregator + the reader. `write_findings`, `SUMMARY_MARKER`, `_RELATED_PAIRS`, `AggregateResult`, `aggregate`, `_render_markdown`, `load_results`. | 1, 2, 3 |
| `src/framework_cli/review/comment.py` (create) | Sticky PR-comment find-or-create via `gh` (the only new I/O). `find_sticky_comment` (pure), `_gh_api` (seam), `post_sticky_comment` (non-fatal). | 3 |
| `src/framework_cli/cli.py` (modify) | Add `--findings-out` to `review`; add the `review-aggregate` command. | 1, 3 |
| `src/framework_cli/template/.github/workflows/ci.yml.jinja` (modify) | `review` job: `--findings-out` + `if: always()` artifact upload; new `review-aggregate` job. | 4 |
| `tests/review/test_aggregate.py` (create) | `write_findings`, `aggregate`, `load_results`. | 1, 2, 3 |
| `tests/review/test_comment.py` (create) | `find_sticky_comment` + `post_sticky_comment` find-or-create. | 3 |
| `tests/test_cli.py` (modify) | `review --findings-out` + `review-aggregate` command. | 1, 3 |
| `tests/test_copier_runner.py` (modify) | Rendered `ci.yml` aggregation wiring. | 4 |

---

## Task 1: Findings emission (`write_findings` + `review --findings-out`)

**Files:**
- Create: `src/framework_cli/review/aggregate.py` (the `write_findings` half only)
- Modify: `src/framework_cli/cli.py` (import + `review` command)
- Test: `tests/review/test_aggregate.py`, `tests/test_cli.py`

- [ ] **Step 1: Write the failing test for `write_findings`**

Create `tests/review/test_aggregate.py`:

```python
import json

from framework_cli.review.findings import Finding


def test_write_findings_round_trips(tmp_path):
    from framework_cli.review.aggregate import write_findings

    out = tmp_path / "sub" / "review-x.json"  # parent dir does not exist yet
    write_findings(out, "review-x", "failure", [Finding("a.py", 1, "high", "boom", "fix")])

    assert json.loads(out.read_text()) == {
        "agent": "review-x",
        "conclusion": "failure",
        "findings": [
            {"path": "a.py", "line": 1, "severity": "high", "message": "boom", "suggestion": "fix"}
        ],
    }


def test_write_findings_empty_list(tmp_path):
    from framework_cli.review.aggregate import write_findings

    out = tmp_path / "review-y.json"
    write_findings(out, "review-y", "neutral", [])
    assert json.loads(out.read_text()) == {"agent": "review-y", "conclusion": "neutral", "findings": []}
```

- [ ] **Step 2: Run it red**

Run: `uv run pytest tests/review/test_aggregate.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.review.aggregate`.

- [ ] **Step 3: Create `aggregate.py` with `write_findings`**

Create `src/framework_cli/review/aggregate.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from framework_cli.review.findings import Finding


def write_findings(path: Path, agent: str, conclusion: str, findings: list[Finding]) -> None:
    """Write this agent's result as the lossless JSON the aggregator consumes.

    Called at every terminal path of `framework review` so a skipped/neutral agent still
    produces a file (conclusion set, empty findings) and the aggregator sees the full set.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent": agent,
        "conclusion": conclusion,
        "findings": [asdict(f) for f in findings],
    }
    path.write_text(json.dumps(payload, indent=2))
```

- [ ] **Step 4: Run it green**

Run: `uv run pytest tests/review/test_aggregate.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing CLI tests for `--findings-out`**

Add to `tests/test_cli.py` (note `runner` and `app` are already imported at the top of the file; `import json as _json` is already present):

```python
def test_review_findings_out_writes_on_normal_path(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "diff")
    monkeypatch.setattr(cli_mod, "_review_run", lambda diff, spec: [Finding("a.py", 3, "low", "m")])

    out = tmp_path / "findings" / "security.json"
    result = runner.invoke(app, ["review", "security", "--findings-out", str(out)])
    assert result.exit_code == 0, result.output
    data = _json.loads(out.read_text())
    assert data["agent"] == "review-security"
    assert data["conclusion"] == "neutral"  # low finding → below "high" threshold → neutral
    assert data["findings"] == [
        {"path": "a.py", "line": 3, "severity": "low", "message": "m", "suggestion": None}
    ]


def test_review_findings_out_on_skip_path(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    out = tmp_path / "findings" / "security.json"
    result = runner.invoke(app, ["review", "security", "--findings-out", str(out)])
    assert result.exit_code == 0, result.output
    data = _json.loads(out.read_text())
    assert data["conclusion"] == "neutral" and data["findings"] == []
```

- [ ] **Step 6: Run them red**

Run: `uv run pytest tests/test_cli.py -k findings_out -q`
Expected: FAIL — `review` has no `--findings-out` option (Typer reports "No such option").

- [ ] **Step 7: Wire `--findings-out` into the `review` command**

In `src/framework_cli/cli.py`, add the import near the other `framework_cli.review` imports (around line 12-15):

```python
from framework_cli.review.aggregate import write_findings
```

Replace the entire `review` command (currently `src/framework_cli/cli.py:166-206`) with:

```python
@app.command()
def review(
    agent: str = typer.Argument(..., help="Review agent name, e.g. 'security'."),
    findings_out: str = typer.Option(
        "",
        "--findings-out",
        help="Write this agent's findings JSON to this path (for aggregation).",
    ),
) -> None:
    """Run a Layer-3 review agent over the PR diff and post a GitHub Check Run."""
    try:
        spec = get_agent(agent)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")

    def _emit(conclusion: str, found: list) -> None:
        if findings_out:
            write_findings(Path(findings_out), spec.name, conclusion, found)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        payload = neutral_payload(spec.name, "review skipped — set ANTHROPIC_API_KEY to enable.")
        post_or_skip(payload, token=token, repo=repo, sha=sha)
        _emit("neutral", [])
        typer.echo(f"{spec.name}: skipped (no ANTHROPIC_API_KEY)")
        raise typer.Exit(0)

    try:
        diff = _review_diff()
        if spec.trigger_globs and not matches_globs(changed_files(diff), spec.trigger_globs):
            payload = neutral_payload(
                spec.name, f"not triggered (no {', '.join(spec.trigger_globs)} change)"
            )
            post_or_skip(payload, token=token, repo=repo, sha=sha)
            _emit("neutral", [])
            typer.echo(f"{spec.name}: skipped (not triggered)")
            raise typer.Exit(0)
        findings = _review_run(diff, spec)
        payload = to_check_run(spec, findings)
    except typer.Exit:
        raise  # the not-triggered skip (and any Exit) must propagate, not become neutral
    except Exception as exc:  # noqa: BLE001 - infra failure must not block CI
        payload = neutral_payload(spec.name, f"review could not run: {exc}")
        post_or_skip(payload, token=token, repo=repo, sha=sha)
        _emit("neutral", [])
        typer.echo(f"{spec.name}: neutral (could not run: {exc})", err=True)
        raise typer.Exit(0) from exc

    post_or_skip(payload, token=token, repo=repo, sha=sha)
    _emit(payload.conclusion, findings)
    typer.echo(f"{spec.name}: {payload.conclusion} ({len(payload.annotations)} finding(s))")
    raise typer.Exit(1 if payload.conclusion == "failure" else 0)
```

(The only changes vs. the current command: the new `findings_out` option, the `_emit` helper, and an `_emit(...)` call on the no-key, not-triggered, infra-error, and normal paths — each *before* its `raise`. The unknown-agent path exits 1 with no agent identity and writes nothing; CI never passes an unknown agent since the matrix comes from the registry.)

- [ ] **Step 8: Run the CLI tests green + confirm nothing regressed**

Run: `uv run pytest tests/test_cli.py tests/review/test_aggregate.py -q`
Expected: PASS (the new tests + all existing `review` tests still green).

- [ ] **Step 9: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** line (datetime + tz) — note: "7c Task 1: review --findings-out"
git add src/framework_cli/review/aggregate.py src/framework_cli/cli.py tests/review/test_aggregate.py tests/test_cli.py CLAUDE.md
```

```bash
git commit -m "feat(review): write per-agent findings JSON via review --findings-out

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: The pure aggregator (`aggregate` + relationships + markdown)

**Files:**
- Modify: `src/framework_cli/review/aggregate.py`
- Test: `tests/review/test_aggregate.py`

- [ ] **Step 1: Write the failing tests for `aggregate`**

Add to `tests/review/test_aggregate.py`:

```python
def _result(agent, conclusion, findings):
    return {"agent": agent, "conclusion": conclusion, "findings": findings}


def _f(path, line, sev, msg):
    return {"path": path, "line": line, "severity": sev, "message": msg}


def test_overall_fails_if_any_agent_failed():
    from framework_cli.review.aggregate import aggregate

    r = aggregate(
        [
            _result("review-security", "failure", [_f("a.py", 1, "high", "x")]),
            _result("review-test-quality", "success", []),
        ]
    )
    assert r.overall == "fail"


def test_overall_passes_when_no_failure():
    from framework_cli.review.aggregate import aggregate

    r = aggregate([_result("review-security", "neutral", [_f("a.py", 1, "low", "x")])])
    assert r.overall == "pass"


def test_severity_counts_across_agents():
    from framework_cli.review.aggregate import aggregate

    r = aggregate(
        [
            _result("review-a", "neutral", [_f("a.py", 1, "low", "x"), _f("b.py", 2, "high", "y")]),
            _result("review-b", "neutral", [_f("c.py", 3, "low", "z")]),
        ]
    )
    assert r.severity_counts == {"low": 2, "high": 1}


def test_same_file_flagged_by_two_agents_is_a_relationship():
    from framework_cli.review.aggregate import aggregate

    r = aggregate(
        [
            _result("review-security", "neutral", [_f("a.py", 1, "low", "x")]),
            _result("review-architecture", "neutral", [_f("a.py", 9, "low", "y")]),
        ]
    )
    assert any("Multiple agents flagged `a.py`" in s for s in r.relationships)


def test_related_domain_pair_is_a_relationship():
    from framework_cli.review.aggregate import aggregate

    r = aggregate(
        [
            _result("review-data-lineage", "neutral", [_f("p.py", 1, "low", "x")]),
            _result("review-privacy", "neutral", [_f("p.py", 2, "low", "y")]),
        ]
    )
    assert any("related concern" in s for s in r.relationships)


def test_no_relationships_when_files_disjoint():
    from framework_cli.review.aggregate import aggregate

    r = aggregate(
        [
            _result("review-security", "neutral", [_f("a.py", 1, "low", "x")]),
            _result("review-privacy", "neutral", [_f("b.py", 2, "low", "y")]),
        ]
    )
    assert r.relationships == []


def test_markdown_has_header_groups_relationships_files_and_marker():
    from framework_cli.review.aggregate import SUMMARY_MARKER, aggregate

    md = aggregate([_result("review-security", "failure", [_f("a.py", 1, "high", "danger")])]).markdown
    assert SUMMARY_MARKER in md
    assert "Review summary" in md and "FAIL" in md
    assert "high" in md and "danger" in md and "review-security" in md
    assert "Cross-agent relationships" in md
    assert "Affected files" in md and "a.py" in md
```

- [ ] **Step 2: Run them red**

Run: `uv run pytest tests/review/test_aggregate.py -q`
Expected: FAIL — `cannot import name 'aggregate'` / `'SUMMARY_MARKER'`.

- [ ] **Step 3: Implement the aggregator in `aggregate.py`**

Append to `src/framework_cli/review/aggregate.py` (and add `from dataclasses import dataclass` to the existing `from dataclasses import asdict` line → `from dataclasses import asdict, dataclass`):

```python
SUMMARY_MARKER = "<!-- framework-review-summary -->"

# Severity ordering for grouping + counts display (highest first).
_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

# Known related-domain agent pairs: when both flag an overlapping file, that co-occurrence is
# itself worth surfacing. Uses the registry's full agent names.
_RELATED_PAIRS: set[frozenset[str]] = {
    frozenset({"review-data-lineage", "review-privacy"}),
    frozenset({"review-data-lineage", "review-compliance"}),
    frozenset({"review-performance", "review-data-integrity"}),
}


@dataclass(frozen=True)
class AggregateResult:
    overall: str  # "pass" | "fail"
    severity_counts: dict[str, int]
    relationships: list[str]
    markdown: str


def aggregate(results: list[dict]) -> AggregateResult:
    """Combine per-agent results (parsed findings JSONs) into one summary. Pure, no I/O."""
    overall = "fail" if any(r.get("conclusion") == "failure" for r in results) else "pass"

    severity_counts: dict[str, int] = {}
    by_path: dict[str, set[str]] = {}
    all_findings: list[tuple[str, dict]] = []  # (agent, finding) in input order
    for r in results:
        agent = r.get("agent", "?")
        for f in r.get("findings", []):
            sev = f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            by_path.setdefault(f["path"], set()).add(agent)
            all_findings.append((agent, f))

    relationships: list[str] = []
    for path in sorted(by_path):  # (a) same file flagged by >= 2 distinct agents
        agents = by_path[path]
        if len(agents) >= 2:
            relationships.append(
                f"Multiple agents flagged `{path}`: {', '.join(sorted(agents))}"
            )
    for path in sorted(by_path):  # (b) known related-domain pairs co-occurring on a file
        agents = by_path[path]
        for pair in _RELATED_PAIRS:
            if pair <= agents:
                a, b = sorted(pair)
                relationships.append(f"`{a}` + `{b}` both flagged `{path}` — related concern.")

    markdown = _render_markdown(overall, severity_counts, relationships, all_findings, sorted(by_path))
    return AggregateResult(overall, severity_counts, relationships, markdown)


def _render_markdown(
    overall: str,
    severity_counts: dict[str, int],
    relationships: list[str],
    all_findings: list[tuple[str, dict]],
    files: list[str],
) -> str:
    icon = "✅" if overall == "pass" else "❌"
    total = sum(severity_counts.values())
    counts = ", ".join(
        f"{severity_counts[s]} {s}" for s in _SEVERITY_ORDER if severity_counts.get(s)
    )
    lines = [
        SUMMARY_MARKER,
        f"## {icon} Review summary — {overall.upper()}",
        "",
        f"{total} finding(s)" + (f" ({counts})" if counts else "") + ".",
        "",
    ]
    for sev in _SEVERITY_ORDER:
        group = [(a, f) for (a, f) in all_findings if f.get("severity") == sev]
        if not group:
            continue
        lines.append(f"### {sev}")
        lines.extend(f"- {agent} · `{f['path']}:{f['line']}` · {f['message']}" for agent, f in group)
        lines.append("")
    lines.append("### Cross-agent relationships")
    lines.extend([f"- {r}" for r in relationships] or ["- none"])
    lines.append("")
    lines.append("### Affected files")
    lines.extend([f"- `{p}`" for p in files] or ["- none"])
    return "\n".join(lines)
```

- [ ] **Step 4: Run them green**

Run: `uv run pytest tests/review/test_aggregate.py -q`
Expected: PASS (all Task 1 + Task 2 aggregate tests).

- [ ] **Step 5: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** line — note: "7c Task 2: pure aggregate() + relationships"
git add src/framework_cli/review/aggregate.py tests/review/test_aggregate.py CLAUDE.md
```

```bash
git commit -m "feat(review): pure aggregate() with severity counts + cross-agent relationships

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Reader + sticky comment + `review-aggregate` command

**Files:**
- Modify: `src/framework_cli/review/aggregate.py` (add `load_results`)
- Create: `src/framework_cli/review/comment.py`
- Modify: `src/framework_cli/cli.py` (add `review-aggregate` command)
- Test: `tests/review/test_aggregate.py`, `tests/review/test_comment.py`, `tests/test_cli.py`

- [ ] **Step 1: Write the failing test for `load_results`**

Add to `tests/review/test_aggregate.py`:

```python
def test_load_results_reads_json_and_skips_malformed(tmp_path):
    from framework_cli.review.aggregate import load_results

    (tmp_path / "review-a.json").write_text(
        '{"agent": "review-a", "conclusion": "success", "findings": []}'
    )
    (tmp_path / "review-b.json").write_text("{ not valid json")
    (tmp_path / "ignore.txt").write_text("not json at all")

    results = load_results(tmp_path)
    assert len(results) == 1 and results[0]["agent"] == "review-a"
```

- [ ] **Step 2: Run it red**

Run: `uv run pytest tests/review/test_aggregate.py -k load_results -q`
Expected: FAIL — `cannot import name 'load_results'`.

- [ ] **Step 3: Implement `load_results`**

Append to `src/framework_cli/review/aggregate.py`:

```python
def load_results(directory: Path) -> list[dict]:
    """Read every `*.json` in `directory`, tolerating a missing/malformed file (skip it)."""
    results: list[dict] = []
    for p in sorted(directory.glob("*.json")):
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            results.append(data)
    return results
```

- [ ] **Step 4: Run it green**

Run: `uv run pytest tests/review/test_aggregate.py -k load_results -q`
Expected: PASS.

- [ ] **Step 5: Write the failing tests for `comment.py`**

Create `tests/review/test_comment.py`:

```python
import json

from framework_cli.review import comment
from framework_cli.review.aggregate import SUMMARY_MARKER


def test_find_sticky_comment_matches_marker():
    comments = [{"id": 1, "body": "hello"}, {"id": 9, "body": f"x {SUMMARY_MARKER} y"}]
    assert comment.find_sticky_comment(comments) == 9


def test_find_sticky_comment_returns_none_when_absent():
    assert comment.find_sticky_comment([{"id": 1, "body": "nope"}]) is None


def test_post_sticky_updates_existing(monkeypatch):
    calls = []

    def fake_gh(args, *, token, stdin=None):
        calls.append(args)
        if "--method" not in args:  # the list call
            return json.dumps([{"id": 7, "body": SUMMARY_MARKER}])
        return ""

    monkeypatch.setattr(comment, "_gh_api", fake_gh)
    comment.post_sticky_comment("md", repo="o/r", pr="3", token="t")
    assert any("--method" in a and "PATCH" in a and "comments/7" in a[0] for a in calls)


def test_post_sticky_creates_when_absent(monkeypatch):
    calls = []

    def fake_gh(args, *, token, stdin=None):
        calls.append(args)
        if "--method" not in args:
            return json.dumps([])
        return ""

    monkeypatch.setattr(comment, "_gh_api", fake_gh)
    comment.post_sticky_comment("md", repo="o/r", pr="3", token="t")
    assert any("--method" in a and "POST" in a and a[0] == "repos/o/r/issues/3/comments" for a in calls)


def test_post_sticky_never_raises(monkeypatch):
    def boom(args, *, token, stdin=None):
        raise RuntimeError("gh down")

    monkeypatch.setattr(comment, "_gh_api", boom)
    comment.post_sticky_comment("md", repo="o/r", pr="3", token="t")  # must not raise
```

- [ ] **Step 6: Run them red**

Run: `uv run pytest tests/review/test_comment.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.review.comment`.

- [ ] **Step 7: Implement `comment.py`**

Create `src/framework_cli/review/comment.py`:

```python
from __future__ import annotations

import json
import os
import subprocess

from framework_cli.review.aggregate import SUMMARY_MARKER


def find_sticky_comment(comments: list[dict]) -> int | None:
    """The id of the existing review-summary comment (carrying the marker), if any."""
    for c in comments:
        if SUMMARY_MARKER in c.get("body", ""):
            return int(c["id"])
    return None


def _gh_api(args: list[str], *, token: str, stdin: str | None = None) -> str:
    """Run `gh api <args>`; return stdout. Raises on non-zero (callers swallow)."""
    result = subprocess.run(
        ["gh", "api", *args],
        input=stdin,
        text=True,
        check=True,
        capture_output=True,
        env={**os.environ, "GH_TOKEN": token},
    )
    return result.stdout


def post_sticky_comment(markdown: str, *, repo: str, pr: str, token: str) -> None:
    """Create or update the single review-summary comment on the PR. Never raises."""
    try:
        listed = _gh_api([f"repos/{repo}/issues/{pr}/comments"], token=token)
        comments = json.loads(listed) if listed.strip() else []
        existing = find_sticky_comment(comments)
        body = json.dumps({"body": markdown})
        if existing is not None:
            _gh_api(
                [f"repos/{repo}/issues/comments/{existing}", "--method", "PATCH", "--input", "-"],
                token=token,
                stdin=body,
            )
        else:
            _gh_api(
                [f"repos/{repo}/issues/{pr}/comments", "--method", "POST", "--input", "-"],
                token=token,
                stdin=body,
            )
    except Exception:  # noqa: BLE001 - posting failure must not fail the CI job
        pass
```

- [ ] **Step 8: Run them green**

Run: `uv run pytest tests/review/test_comment.py -q`
Expected: PASS (5 tests).

- [ ] **Step 9: Write the failing tests for the `review-aggregate` command**

Add to `tests/test_cli.py`:

```python
def test_review_aggregate_prints_when_no_pr(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_PR_NUMBER", raising=False)
    (tmp_path / "review-security.json").write_text(
        '{"agent": "review-security", "conclusion": "failure", '
        '"findings": [{"path": "a.py", "line": 1, "severity": "high", "message": "danger"}]}'
    )
    result = runner.invoke(app, ["review-aggregate", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Review summary" in result.output and "FAIL" in result.output


def test_review_aggregate_posts_when_pr_present(tmp_path, monkeypatch):
    import framework_cli.review.comment as comment_mod

    posted = {}
    monkeypatch.setattr(
        comment_mod,
        "post_sticky_comment",
        lambda md, *, repo, pr, token: posted.update(pr=pr, repo=repo, token=token),
    )
    monkeypatch.setenv("GITHUB_PR_NUMBER", "12")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    (tmp_path / "review-a.json").write_text(
        '{"agent": "review-a", "conclusion": "success", "findings": []}'
    )
    result = runner.invoke(app, ["review-aggregate", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert posted == {"pr": "12", "repo": "o/r", "token": "t"}
```

- [ ] **Step 10: Run them red**

Run: `uv run pytest tests/test_cli.py -k review_aggregate -q`
Expected: FAIL — no such command `review-aggregate`.

- [ ] **Step 11: Add the `review-aggregate` command to `cli.py`**

In `src/framework_cli/cli.py`, add after the `review` command:

```python
@app.command(name="review-aggregate")
def review_aggregate(
    directory: str = typer.Argument(..., help="Directory of per-agent findings JSON files."),
    pr: str = typer.Option("", "--pr", help="PR number (default: $GITHUB_PR_NUMBER)."),
) -> None:
    """Aggregate per-agent review findings into one sticky PR comment (prints on a push)."""
    from framework_cli.review import comment
    from framework_cli.review.aggregate import aggregate, load_results

    result = aggregate(load_results(Path(directory)))
    pr_number = pr or os.environ.get("GITHUB_PR_NUMBER", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if pr_number and repo and token:
        comment.post_sticky_comment(result.markdown, repo=repo, pr=pr_number, token=token)
        typer.echo(f"review-aggregate: posted summary to PR #{pr_number} ({result.overall})")
    else:
        typer.echo(result.markdown)
```

- [ ] **Step 12: Run the CLI tests green + the whole review suite**

Run: `uv run pytest tests/test_cli.py tests/review -q`
Expected: PASS (new command tests + all existing review tests).

- [ ] **Step 13: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** line — note: "7c Task 3: review-aggregate command + sticky comment"
git add src/framework_cli/review/aggregate.py src/framework_cli/review/comment.py src/framework_cli/cli.py tests/review/test_aggregate.py tests/review/test_comment.py tests/test_cli.py CLAUDE.md
```

```bash
git commit -m "feat(review): review-aggregate command posts a sticky PR summary comment

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: CI wiring (per-agent artifacts + `review-aggregate` job)

**Files:**
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja`
- Test: `tests/test_copier_runner.py`

> Reminder: `ci.yml.jinja` is template *payload*, not framework source — it is validated only by rendering it. `{% raw %}{% endraw %}` brackets are required around every `${{ ... }}` GitHub expression so Jinja does not try to interpret them.

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py` (the module already imports `yaml`, `Path`, `render_project`, and defines `DATA`):

```python
def test_render_ci_review_aggregation(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ci = yaml.safe_load((dest / ".github" / "workflows" / "ci.yml").read_text())
    jobs = ci["jobs"]

    # the review matrix job writes per-agent findings and uploads them even on a blocking failure
    review_steps = jobs["review"]["steps"]
    runs = " ".join(str(s.get("run", "")) for s in review_steps)
    assert "--findings-out" in runs
    upload = next(s for s in review_steps if "upload-artifact" in str(s.get("uses", "")))
    assert upload["if"] == "always()"
    assert "review-findings-" in upload["with"]["name"]

    # a review-aggregate job consolidates them into the single PR comment
    assert "review-aggregate" in jobs
    agg = jobs["review-aggregate"]
    assert agg["needs"] == "review"
    assert agg["if"] == "always()"
    assert " ".join(str(s.get("run", "")) for s in agg["steps"]).find("framework review-aggregate") != -1
    download = next(s for s in agg["steps"] if "download-artifact" in str(s.get("uses", "")))
    assert download["with"]["pattern"] == "review-findings-*"
```

- [ ] **Step 2: Run it red**

Run: `uv run pytest tests/test_copier_runner.py -k review_aggregation -q`
Expected: FAIL — no `--findings-out`, no upload step, no `review-aggregate` job.

- [ ] **Step 3: Update the `review` job step + add the upload step**

In `src/framework_cli/template/.github/workflows/ci.yml.jinja`, replace the final step of the `review` job (currently `src/framework_cli/template/.github/workflows/ci.yml.jinja:160-164`):

```yaml
      - name: review {% raw %}${{ matrix.agent }}{% endraw %}
        env:
          ANTHROPIC_API_KEY: {% raw %}${{ secrets.ANTHROPIC_API_KEY }}{% endraw %}
          GITHUB_TOKEN: {% raw %}${{ github.token }}{% endraw %}
        run: framework review {% raw %}${{ matrix.agent }}{% endraw %} --findings-out findings/{% raw %}${{ matrix.agent }}{% endraw %}.json
      - name: upload findings
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: review-findings-{% raw %}${{ matrix.agent }}{% endraw %}
          path: findings/
          if-no-files-found: ignore
```

- [ ] **Step 4: Add the `review-aggregate` job**

Append to the end of `src/framework_cli/template/.github/workflows/ci.yml.jinja`:

```yaml

  # Aggregator (spec §7): consolidate every agent's findings into one sticky PR comment, surfacing
  # cross-agent relationships. Runs even when an agent blocked (`if: always()`), downloading the
  # per-agent findings artifacts. On a push (no PR) the summary is printed to the job log instead.
  review-aggregate:
    needs: review
    if: always()
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: install the framework CLI at the recorded version
        run: |
          ref="$(awk '/^_commit:/ {print $2}' .copier-answers.yml)"
          uv tool install "git+https://github.com/cdowell-swtr/swiftwater-framework@${ref}"
      - uses: actions/download-artifact@v4
        with:
          pattern: review-findings-*
          merge-multiple: true
          path: all-findings
      - name: aggregate review findings
        env:
          GITHUB_TOKEN: {% raw %}${{ github.token }}{% endraw %}
          GITHUB_REPOSITORY: {% raw %}${{ github.repository }}{% endraw %}
          GITHUB_PR_NUMBER: {% raw %}${{ github.event.pull_request.number }}{% endraw %}
        run: framework review-aggregate all-findings
```

- [ ] **Step 5: Run the render test green + the broader render suite**

Run: `uv run pytest tests/test_copier_runner.py -k "review_aggregation or ci_pipeline" -q`
Expected: PASS (the new test + the existing `test_render_includes_ci_pipeline`, which still finds the `review` job intact).

- [ ] **Step 6: Lint the rendered workflow with actionlint (catches YAML/Actions errors the parser misses)**

```bash
uv run python -c "from framework_cli.copier_runner import render_project; from pathlib import Path; import tempfile,os; d=Path(tempfile.mkdtemp())/'demo'; render_project(d, {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12'}); print(d/'.github/workflows/ci.yml')"
```

Then run `actionlint` on the printed path if it is installed locally (`uv run pre-commit run actionlint --files <path>` inside a generated project is the authoritative check; the final whole-branch review will run it). Expected: no errors.

- [ ] **Step 7: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# edit CLAUDE.md **Last updated:** line — note: "7c Task 4: ci.yml findings artifacts + review-aggregate job"
git add src/framework_cli/template/.github/workflows/ci.yml.jinja tests/test_copier_runner.py CLAUDE.md
```

```bash
git commit -m "feat(review): generated ci.yml uploads findings + runs review-aggregate

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Final whole-branch review (controller, after all tasks)

Dispatch a final code reviewer over the whole branch that **runs the tooling**, not just reads diffs (the lesson from Plan 7a):

- [ ] `uv run pytest -q` — the full suite (incl. the Docker-gated acceptance suite), expected all green.
- [ ] `uv run ruff check .` and `uv run mypy src` — clean.
- [ ] `uv lock --check` — clean (no new runtime deps were added in 7c, so this should pass unchanged; confirm).
- [ ] Render a project and run `actionlint` on the generated `ci.yml` (validates the new `review-aggregate` job + the matrix expressions).
- [ ] Build a wheel and confirm it still ships the 12 agent prompts (no packaging regression from the new modules).
- [ ] Confirm `framework review-aggregate --help` and `framework review --help` show the new option/command.

Then use **superpowers:finishing-a-development-branch**: the controller finalizes the CLAUDE.md "Where we are / Next" narrative + the meta-plan 7c row (→ ✅ merged), fast-forward merges to `master`, and pushes.

---

## Self-review (against the spec)

**Spec coverage:**
- §3 findings collection — `write_findings` (Task 1) called at every terminal path of `review`; `--findings-out` flag (Task 1); CI `--findings-out` + `if: always()` upload (Task 4). ✔
- §4 aggregator — `AggregateResult`, pure `aggregate` with overall/severity_counts/relationships (same-file + `_RELATED_PAIRS`)/markdown (Task 2); `load_results` (Task 3); `review-aggregate` command with find-or-create sticky comment + print-on-push (Task 3, `comment.py`). ✔
- §5 CI wiring — `review` job `--findings-out` + artifact upload, `review-aggregate` job with `needs: review`, `if: always()`, `download-artifact` pattern, `GITHUB_PR_NUMBER` (Task 4). ✔
- §6 testing — `aggregate` pure tests, `--findings-out` normal + skip, `review-aggregate` print + post + malformed-skip, sticky find-or-create with stubbed `gh`, ci.yml render parses (Tasks 1-4). ✔

**Placeholder scan:** none — every step has concrete code/commands/expected output.

**Type consistency:** `write_findings(path, agent, conclusion, findings)`, `aggregate(results) -> AggregateResult`, `load_results(directory) -> list[dict]`, `find_sticky_comment(comments) -> int | None`, `post_sticky_comment(markdown, *, repo, pr, token)`, `_gh_api(args, *, token, stdin=None)` — names and signatures match across tasks and tests. `SUMMARY_MARKER` is defined once in `aggregate.py` (Task 2) and imported by `comment.py` (Task 3), avoiding a duplicate-constant drift bug. Findings flow as plain dicts end-to-end (`asdict` on write, dict access on aggregate), so the aggregator never depends on the `Finding` type.
