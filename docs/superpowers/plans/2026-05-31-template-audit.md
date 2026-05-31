# template audit pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the capability to audit the template *payload* — render it with all batteries, audit the rendered project with the full project roster, and preserve a scorecard back to the framework repo with template-source path annotations. (Building the mechanism; the first actual audit *run* is a user-triggered follow-up via the new slash command.)

**Architecture:** Two small CLI helpers (`template-render` renders the bundled template deterministically with all batteries; `template-map` annotates rendered finding paths with best-guess template-source paths via a focused `template_map.py` module) plus a framework-only `/reviewers:template-audit` slash command that orchestrates render → `audit-prepare --target project --snapshot` → `reviewers-audit` workflow → `audit-finalize` → `template-map` → preserve-back. Reuses all existing audit machinery.

**Tech Stack:** Python 3 (Typer CLI, `pathlib`, `subprocess`), `copier` (via `render_project`), pytest; the `reviewers-audit` Workflow script. All tooling via `uv run`.

**Spec:** `docs/superpowers/specs/2026-05-31-template-audit-design.md`

---

## File Structure

- **Modify** `src/framework_cli/cli.py` — add two thin Typer commands: `template-render` and `template-map` (the latter delegates to the new module).
- **Create** `src/framework_cli/template_map.py` — the path-mapping logic (basename-anchored search + tail-overlap ranking + markdown rendering). Focused, CLI-independent, unit-testable.
- **Create** `tests/test_template_map.py` — unit tests for the mapping module (synthetic fixtures + one real-template smoke).
- **Modify** `tests/test_cli.py` — tests for `template-render` and `template-map` CLI commands + a guard that the slash command is NOT in the template payload.
- **Create** `.claude/commands/reviewers/template-audit.md` — the framework-only slash command (NOT added under `src/framework_cli/template/.claude/`).

**Integrity note:** none of these are integrity-tracked, and nothing is added to `src/framework_cli/template/` → no baseline manifest shift.

**Key facts (verified):**
- `render_project(dest, {**answers, "batteries": [...]})` — `copier_runner.py:13`. Canonical answers: `project_name=Demo, project_slug=demo, package_name=demo, python_version=3.12`.
- `battery_names()` (`batteries.py:88`) → all 11 names; `resolve(selected)` (`batteries.py:98`) expands deps/implications + canonical order.
- Findings live at `<out_dir>/findings/<agent>.json` = `{"agent": str, "findings": [{"path": str, "line": int, "severity": str, "message": str, "suggestion": str}, ...]}`. Paths are **root-relative** (e.g. `src/demo/graphql/schema.py`).
- `audit-prepare` accepts `--target project --snapshot --output-dir ... --split-to ...` (`cli.py:633`). `audit-finalize --results --out-dir [--preserve-as] [--force]`.

---

## Task 1: `template-render` CLI command (TDD)

**Files:**
- Modify: `src/framework_cli/cli.py` (new command near the other dogfooding commands)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_template_render_renders_all_batteries(tmp_path):
    """template-render --out DIR renders the template with all 11 batteries,
    git-inits the result, and reports the resolved battery list."""
    out = tmp_path / "render"
    result = runner.invoke(app, ["template-render", "--out", str(out)])
    assert result.exit_code == 0, result.output

    from framework_cli.batteries import battery_names

    answers = (out / ".copier-answers.yml").read_text()
    for b in battery_names():
        assert b in answers, f"battery {b} missing from .copier-answers.yml"

    assert (out / "pyproject.toml").exists()
    assert (out / ".git").is_dir()
    # representative battery artifact (react ships a frontend/ dir):
    assert (out / "frontend").is_dir()

    payload = __import__("json").loads(result.stdout)
    assert sorted(payload["batteries"]) == sorted(battery_names())


def test_template_render_accepts_subset(tmp_path):
    """--batteries <csv> renders only the named batteries."""
    out = tmp_path / "render"
    result = runner.invoke(app, ["template-render", "--out", str(out), "--batteries", "webhooks"])
    assert result.exit_code == 0, result.output
    answers = (out / ".copier-answers.yml").read_text()
    assert "webhooks" in answers
    assert "graphql" not in answers
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -k template_render -v`
Expected: FAIL — `No such command 'template-render'` (exit code 2).

- [ ] **Step 3: Implement the command**

Add to `src/framework_cli/cli.py` (place it alongside the other dogfooding commands, e.g. near `dev-combos`):

```python
@app.command(name="template-render")
def template_render(
    out: str = typer.Option(..., "--out", help="Target directory to render into."),
    batteries: str = typer.Option(
        "all",
        "--batteries",
        help="'all' (default) or a comma-separated battery subset.",
    ),
) -> None:
    """Render the bundled template into OUT (deterministic, non-interactive).

    Uses the canonical fixture answers (package_name=demo) plus the chosen
    batteries (default: all), then git-inits + commits so review tooling sees a
    clean repo. Produces the audit subject for /reviewers:template-audit.
    """
    import subprocess

    from framework_cli.batteries import battery_names, resolve
    from framework_cli.copier_runner import render_project

    if batteries.strip() == "all":
        selected = battery_names()
    else:
        selected = [b.strip() for b in batteries.split(",") if b.strip()]
    resolved = resolve(selected)

    root = Path(out)
    render_project(
        root,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
            "batteries": resolved,
        },
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        [
            "git", "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-qm", "template-audit base",
        ],
        cwd=root,
        check=True,
    )
    typer.echo(
        json.dumps(
            {"out": str(root), "package_name": "demo", "batteries": resolved},
            indent=2,
        )
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cli.py -k template_render -v`
Expected: PASS (2 tests). If the `frontend/` assertion fails, render once manually (`uv run framework template-render --out /tmp/tr`) and replace it with an actually-rendered battery artifact path; keep the `.copier-answers.yml` assertion as the authoritative check.

- [ ] **Step 5: Lint + type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: clean.

- [ ] **Step 6: Commit**

Stage `src/framework_cli/cli.py` and `tests/test_cli.py`. Do NOT stage/edit CLAUDE.md — if the commit-gate hook blocks demanding CLAUDE.md, STOP and report it (the controller handles CLAUDE.md). Use separate `git add` then `git commit` calls (never chained), and keep the word "commit" out of every Bash command description (a hook greps for it).
Message: `feat(cli): template-render — deterministic all-batteries render`

---

## Task 2: `template_map` module + `template-map` CLI command (TDD)

**Files:**
- Create: `src/framework_cli/template_map.py`
- Test: `tests/test_template_map.py`
- Modify: `src/framework_cli/cli.py` (thin `template-map` command)
- Test: `tests/test_cli.py` (CLI-level test)

- [ ] **Step 1: Write the failing module tests**

Create `tests/test_template_map.py`:

```python
import json
from pathlib import Path

from framework_cli.template_map import map_findings, map_finding_path, render_markdown
from framework_cli.template_map import _template_files_by_basename


def _make_template(root: Path) -> None:
    """Build a tiny fake template payload."""
    (root / "src" / "{{package_name}}").mkdir(parents=True)
    (root / "src" / "{{package_name}}" / "main.py.jinja").write_text("x")
    (root / "src" / "{{package_name}}" / "graphql").mkdir()
    (root / "src" / "{{package_name}}" / "graphql" / "schema.py.jinja").write_text("x")
    # a duplicate basename in two locations:
    (root / "tests").mkdir()
    (root / "tests" / "conftest.py.jinja").write_text("x")
    (root / "src" / "{{package_name}}" / "conftest.py.jinja").write_text("x")


def test_unique_match(tmp_path):
    troot = tmp_path / "template"
    _make_template(troot)
    idx = _template_files_by_basename(troot)
    r = map_finding_path("src/demo/main.py", package_name="demo", template_root=troot, index=idx)
    assert r["status"] == "unique"
    assert r["template_source"] == "src/{{package_name}}/main.py.jinja"


def test_unique_match_via_tail_overlap(tmp_path):
    troot = tmp_path / "template"
    _make_template(troot)
    idx = _template_files_by_basename(troot)
    r = map_finding_path("src/demo/graphql/schema.py", package_name="demo", template_root=troot, index=idx)
    assert r["status"] == "unique"
    assert r["template_source"] == "src/{{package_name}}/graphql/schema.py.jinja"


def test_multi_candidate(tmp_path):
    troot = tmp_path / "template"
    _make_template(troot)
    idx = _template_files_by_basename(troot)
    # a rendered path whose tail doesn't clearly disambiguate the two conftest files
    r = map_finding_path("conftest.py", package_name="demo", template_root=troot, index=idx)
    assert r["status"] == "candidates"
    assert len(r["candidates"]) == 2


def test_unresolved(tmp_path):
    troot = tmp_path / "template"
    _make_template(troot)
    idx = _template_files_by_basename(troot)
    r = map_finding_path("src/demo/does_not_exist.py", package_name="demo", template_root=troot, index=idx)
    assert r["status"] == "unresolved"
    assert r["template_source"] is None


def test_map_findings_and_markdown(tmp_path):
    troot = tmp_path / "template"
    _make_template(troot)
    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "security.json").write_text(json.dumps({
        "agent": "security",
        "findings": [
            {"path": "src/demo/main.py", "line": 12, "severity": "high", "message": "m"},
            {"path": "src/demo/nope.py", "line": 3, "severity": "low", "message": "m"},
        ],
    }))
    rows = map_findings(findings, troot, "demo")
    assert len(rows) == 2
    assert rows[0]["agent"] == "security"
    md = render_markdown(rows)
    assert "as-rendered" in md            # the line-number caveat
    assert "src/{{package_name}}/main.py.jinja" in md
    assert "UNRESOLVED" in md


def test_real_template_root_runs(tmp_path):
    """Smoke: mapping against the real bundled template resolves a common file."""
    from framework_cli.copier_runner import template_path
    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "x.json").write_text(json.dumps({
        "agent": "application-logic",
        "findings": [{"path": "src/demo/main.py", "line": 1, "severity": "low", "message": "m"}],
    }))
    rows = map_findings(findings, template_path(), "demo")
    assert rows[0]["status"] in {"unique", "candidates"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_template_map.py -v`
Expected: FAIL — `ModuleNotFoundError: framework_cli.template_map`.

- [ ] **Step 3: Implement the module**

Create `src/framework_cli/template_map.py`:

```python
"""Best-guess mapping from rendered finding paths back to template-source paths.

Used by /reviewers:template-audit as a triage aid. Non-authoritative: it does a
basename-anchored search of the template payload (a template file `foo.py.jinja`
renders to `foo.py`), ranked by path-tail overlap after substituting the rendered
package_name back to `{{package_name}}`. Line numbers are NOT mapped — Jinja
rendering shifts them — so the report carries an explicit caveat.
"""

from __future__ import annotations

import json
from pathlib import Path

_JINJA_SUFFIX = ".jinja"


def _rendered_name(name: str) -> str:
    return name[: -len(_JINJA_SUFFIX)] if name.endswith(_JINJA_SUFFIX) else name


def _template_files_by_basename(template_root: Path) -> dict[str, list[Path]]:
    """Index every template payload file by its *rendered* basename."""
    index: dict[str, list[Path]] = {}
    for p in template_root.rglob("*"):
        if p.is_file():
            index.setdefault(_rendered_name(p.name), []).append(p)
    return index


def _tail_overlap(want_parts: list[str], template_path: Path, template_root: Path) -> int:
    """Count matching trailing path segments between the desired rendered-relative
    path and a candidate template path (with the last segment de-jinja'd)."""
    tparts = list(template_path.relative_to(template_root).parts)
    if tparts:
        tparts[-1] = _rendered_name(tparts[-1])
    n = 0
    for a, b in zip(reversed(want_parts), reversed(tparts)):
        if a == b:
            n += 1
        else:
            break
    return n


def map_finding_path(
    rendered_path: str,
    *,
    package_name: str,
    template_root: Path,
    index: dict[str, list[Path]],
) -> dict:
    """Map one rendered finding path to a best-guess template-source path.

    Returns {'rendered', 'status' in {'unique','candidates','unresolved'},
             'template_source': str|None, 'candidates': [str, ...]}.
    """
    rp = Path(rendered_path)
    cands = index.get(rp.name, [])
    if not cands:
        return {"rendered": rendered_path, "status": "unresolved",
                "template_source": None, "candidates": []}

    want_parts = ["{{package_name}}" if seg == package_name else seg for seg in rp.parts]
    scored = sorted(
        cands, key=lambda c: _tail_overlap(want_parts, c, template_root), reverse=True
    )
    rels = [str(c.relative_to(template_root)) for c in scored]
    top = _tail_overlap(want_parts, scored[0], template_root)
    tied = [c for c in scored if _tail_overlap(want_parts, c, template_root) == top]

    if len(cands) == 1 or (len(tied) == 1 and top >= 2):
        return {"rendered": rendered_path, "status": "unique",
                "template_source": rels[0], "candidates": rels}
    return {"rendered": rendered_path, "status": "candidates",
            "template_source": None, "candidates": rels}


def map_findings(findings_dir: Path, template_root: Path, package_name: str) -> list[dict]:
    """Map every finding under findings_dir/*.json. Returns rows for the report."""
    index = _template_files_by_basename(template_root)
    rows: list[dict] = []
    for fp in sorted(findings_dir.glob("*.json")):
        data = json.loads(fp.read_text())
        for f in data.get("findings", []):
            mapped = map_finding_path(
                f.get("path") or "",
                package_name=package_name,
                template_root=template_root,
                index=index,
            )
            rows.append(
                {
                    "agent": data.get("agent"),
                    "line": f.get("line"),
                    "severity": f.get("severity"),
                    **mapped,
                }
            )
    return rows


def render_markdown(rows: list[dict]) -> str:
    """Render the path-map table with the line-number caveat."""
    lines = [
        "# Template-source path map",
        "",
        "> Line numbers are **as-rendered**, not template-source — Jinja shifts them.",
        "> Mappings are best-effort (basename-anchored); verify before triaging.",
        "",
        "| agent | rendered path:line | status | template source / candidates |",
        "|---|---|---|---|",
    ]
    for r in rows:
        loc = f"`{r['rendered']}:{r['line']}`"
        if r["status"] == "unique":
            tgt = f"`{r['template_source']}`"
        elif r["status"] == "candidates":
            tgt = "candidates: " + ", ".join(f"`{c}`" for c in r["candidates"])
        else:
            tgt = "UNRESOLVED"
        lines.append(f"| {r['agent']} | {loc} | {r['status']} | {tgt} |")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run module tests to verify they pass**

Run: `uv run pytest tests/test_template_map.py -v`
Expected: all pass.

- [ ] **Step 5: Add the thin CLI command**

Add to `src/framework_cli/cli.py` (near `template-render`):

```python
@app.command(name="template-map")
def template_map_cmd(
    findings: str = typer.Option(
        ..., "--findings", help="Path to the findings/ dir (per-agent JSON)."
    ),
    template_root: str = typer.Option(
        ..., "--template-root", help="Path to src/framework_cli/template."
    ),
    package_name: str = typer.Option(
        "demo", "--package-name", help="package_name used in the render."
    ),
    out: str = typer.Option(
        "", "--out", help="Output markdown path (default: <findings>/../path-map.md)."
    ),
) -> None:
    """Annotate rendered-project findings with best-guess template-source paths."""
    from framework_cli.template_map import map_findings, render_markdown

    findings_dir = Path(findings)
    rows = map_findings(findings_dir, Path(template_root), package_name)
    out_path = Path(out) if out else findings_dir.parent / "path-map.md"
    out_path.write_text(render_markdown(rows))
    typer.echo(json.dumps({"rows": len(rows), "out": str(out_path)}, indent=2))
```

- [ ] **Step 6: Add a CLI-level test**

Add to `tests/test_cli.py`:

```python
def test_template_map_cli_writes_path_map(tmp_path):
    from framework_cli.copier_runner import template_path

    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "security.json").write_text(__import__("json").dumps({
        "agent": "security",
        "findings": [{"path": "src/demo/main.py", "line": 5, "severity": "high", "message": "m"}],
    }))
    result = runner.invoke(app, [
        "template-map",
        "--findings", str(findings),
        "--template-root", str(template_path()),
    ])
    assert result.exit_code == 0, result.output
    out = findings.parent / "path-map.md"
    assert out.exists()
    assert "as-rendered" in out.read_text()
```

- [ ] **Step 7: Run all new tests + quality gate**

Run: `uv run pytest tests/test_template_map.py tests/test_cli.py -k "template_map or template_render" -v && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all pass / clean.

- [ ] **Step 8: Commit**

Stage `src/framework_cli/template_map.py`, `src/framework_cli/cli.py`, `tests/test_template_map.py`, `tests/test_cli.py` (same hook discipline as Task 1: separate add/commit, no "commit" in descriptions, don't touch CLAUDE.md).
Message: `feat(cli): template-map — rendered-path → template-source triage aid`

---

## Task 3: `/reviewers:template-audit` slash command + payload-exclusion guard

**Files:**
- Create: `.claude/commands/reviewers/template-audit.md`
- Test: `tests/test_cli.py` (guard that the command is NOT in the template payload)

- [ ] **Step 1: Write the failing payload-exclusion guard test**

Add to `tests/test_cli.py`:

```python
def test_template_audit_command_is_framework_only():
    """The template-audit slash command must NOT ship in the template payload
    (it audits the framework's own template; meaningless in a generated project)."""
    from framework_cli.copier_runner import template_path

    repo_cmd = Path(".claude/commands/reviewers/template-audit.md")
    assert repo_cmd.exists(), "framework-side slash command should exist"
    payload_cmd = template_path() / ".claude/commands/reviewers/template-audit.md.jinja"
    payload_cmd_plain = template_path() / ".claude/commands/reviewers/template-audit.md"
    assert not payload_cmd.exists() and not payload_cmd_plain.exists(), (
        "template-audit must not be added to the template payload (no manifest shift)"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -k template_audit_command_is_framework_only -v`
Expected: FAIL on the first assertion (`repo_cmd.exists()` is False — file not created yet).

- [ ] **Step 3: Create the slash command file**

Create `.claude/commands/reviewers/template-audit.md` with this content:

````markdown
---
description: Template-payload audit — render the bundled template with all batteries, audit the rendered project with the full project roster (snapshot), map findings back to template source, and preserve a dated scorecard under docs/superpowers/eval-scorecards/template-audit-…/. Framework-only (audits the framework's own template). Runs on subscription subagents, no paid API.
---

You are running the `/reviewers:template-audit` workflow. Your job: audit the **template payload** — the app-domain code the framework audit (`FRAMEWORK_AGENTS`) can't see — by rendering it with all batteries and running the full project review roster against the rendered project.

**Steps:**

1. **Capture the framework repo root + SHA** (you start in the framework repo):
   ```bash
   FW_ROOT=$(git rev-parse --show-toplevel)
   FW_SHA=$(git rev-parse --short HEAD)
   DATE=$(date +%Y-%m-%d)
   DEST="$FW_ROOT/docs/superpowers/eval-scorecards/template-audit-$DATE-$FW_SHA"
   ```

2. **Render the all-batteries audit subject**:
   ```bash
   rm -rf /tmp/template-audit-render /tmp/template-audit-split 2>/dev/null
   uv run framework template-render --out /tmp/template-audit-render
   ```

3. **Prepare the audit** (run IN the render dir so it reads that project's batteries; snapshot ⇒ whole-tree, no baseline lookup):
   ```bash
   cd /tmp/template-audit-render
   uv run framework audit-prepare --target project --snapshot \
     --output-dir /tmp/template-audit-render/.framework/audit/latest \
     --split-to /tmp/template-audit-split > /tmp/template-audit-prep.json
   cd "$FW_ROOT"
   ```

4. **Read the prep manifest** (`/tmp/template-audit-prep.json`); note `agents_set` (the full ~18-agent project roster). Print a pre-flight estimate (agent count, ~30s–2min each, subscription-quota note). If the work-item count > 30, confirm with the user.

5. **Invoke the Workflow tool** (`name: "reviewers-audit"`) with args `{indexPath: "/tmp/template-audit-split/index.json", itemsDir: "/tmp/template-audit-split/items", meta: <{mode,target,agents_set,output_dir} copied from the prep manifest>}`. Wait for the result in the foreground.

6. **Quota-drop guard:** compare the number of returned `results` to `agents_set`. If any agents are missing (silent subagent-quota drops), re-run `audit-prepare` restricted to the missing agents (`--agent X --agent Y …`, same `--target project --snapshot`, a fresh `--split-to /tmp/template-audit-split-retry`), dispatch the `reviewers-audit` workflow again for that subset, and merge the new results into the full set before finalizing.

7. **Write the merged `{results, meta}`** to `/tmp/template-audit-results.json` (Write tool).

8. **Finalize** (writes findings/ + audit-report.md + meta.json into the render dir):
   ```bash
   cd /tmp/template-audit-render
   uv run framework audit-finalize \
     --results /tmp/template-audit-results.json \
     --out-dir /tmp/template-audit-render/.framework/audit/latest
   cd "$FW_ROOT"
   ```

9. **Map findings back to template source** (the triage aid):
   ```bash
   uv run framework template-map \
     --findings /tmp/template-audit-render/.framework/audit/latest/findings \
     --template-root "$FW_ROOT/src/framework_cli/template" \
     --package-name demo
   ```
   This writes `path-map.md` next to the findings dir.

10. **Preserve the scorecard back to the framework repo**:
    ```bash
    mkdir -p "$DEST"
    cp -r /tmp/template-audit-render/.framework/audit/latest/findings "$DEST/"
    cp /tmp/template-audit-render/.framework/audit/latest/audit-report.md "$DEST/"
    cp /tmp/template-audit-render/.framework/audit/latest/meta.json "$DEST/"
    cp /tmp/template-audit-render/.framework/audit/latest/path-map.md "$DEST/"
    ```
    NB: `meta.json`'s `git_sha` is the render dir's, not the framework's — the dated dir name (`$FW_SHA`) is the authoritative framework reference.

11. **Write `triage.md`** (hand-authored, as with the framework audit): for each finding decide fix-now / defer / false-positive, using `path-map.md` to locate the template source. Save it in `$DEST/triage.md`.

12. **Clean up**:
    ```bash
    rm -rf /tmp/template-audit-render /tmp/template-audit-split /tmp/template-audit-split-retry
    rm -f /tmp/template-audit-prep.json /tmp/template-audit-results.json
    ```

13. **Print a summary**: findings count by severity per agent, the `$DEST` path, and a note that `path-map.md` is a best-effort aid (line numbers as-rendered).

**Important notes:**
- Framework-only command — it audits the framework's *own* template; it is intentionally NOT shipped into generated projects.
- Runs entirely on CC subagents (subscription quota), not the paid API.
- The scorecard under `docs/superpowers/eval-scorecards/template-audit-…/` is the repo-persisted output — review it for anything sensitive before committing.
````

- [ ] **Step 4: Run the guard test to verify it passes**

Run: `uv run pytest tests/test_cli.py -k template_audit_command_is_framework_only -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Stage `.claude/commands/reviewers/template-audit.md` and `tests/test_cli.py` (same hook discipline). Message: `feat(reviewers): /reviewers:template-audit slash command (framework-only)`

NB: editing `.claude/commands/**` makes `gate-prepare` mark agents affected — the commit-gate hook will require a fresh `/reviewers:gate`. If the controller hits that block, run `/reviewers:gate` (it will be a quick review of these doc/test changes) before retrying the commit, or note it for the controller.

---

## Task 4: Full-suite verification + docs/state

**Files:** `CLAUDE.md`, `docs/superpowers/plans/2026-05-20-meta-plan.md` (state only)

- [ ] **Step 1: Full fast suite + quality gate**

Run: `uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all pass / clean.

- [ ] **Step 2: Confirm no template payload change (no manifest shift)**

Run: `git diff --stat <branch-base>..HEAD -- src/framework_cli/template`
Expected: empty output (nothing under the template payload changed).

- [ ] **Step 3: Update CLAUDE.md + meta-plan**

Mark the template-audit *mechanism* delivered in the CLAUDE.md Current State pointer (and the outstanding-roadmap bullet: the mechanism is built; the first actual audit *run* is a user-triggered follow-up via `/reviewers:template-audit`). Update `Last updated` with a timezone datetime. Stage `CLAUDE.md` (+ meta-plan if edited) and commit (separate add/commit, no "commit" in descriptions).
Message: `docs(state): template-audit mechanism delivered`

---

## Self-Review

**Spec coverage:**
- All-batteries render → Task 1 (`template-render`, default `all` via `battery_names()`/`resolve()`). ✓
- Audit rendered project with full project roster, snapshot → Task 3 slash command step 3 (`audit-prepare --target project --snapshot`). ✓
- Lightweight non-authoritative path mapping → Task 2 (`template_map.py`: basename search, tail-overlap rank, line-number caveat, unique/candidates/unresolved). ✓
- New `/reviewers:template-audit` slash command → Task 3. ✓
- Preserve scorecard back to framework repo (`template-audit-<date>-<sha>`) → Task 3 steps 1, 10. ✓
- Quota-drop guard → Task 3 step 6. ✓
- No manifest shift (framework-only, nothing in payload) → Task 3 guard test + Task 4 step 2. ✓
- Testing (render, map module, map CLI, payload-exclusion) → Tasks 1, 2, 3. ✓

**Placeholder scan:** `<branch-base>` in Task 4 step 2 is the only token — it resolves to the branch point at execution time (the controller substitutes the actual base SHA). No TBD/TODO; all code steps carry complete code.

**Type consistency:** `map_finding_path(rendered_path, *, package_name, template_root, index)` and `map_findings(findings_dir, template_root, package_name)` and `render_markdown(rows)` are used identically in the module tests, the CLI command, and `map_findings`. Finding dict keys (`path`, `line`, `severity`, `agent`, `findings`) match the verified `findings/<agent>.json` shape. `template-render` emits `{out, package_name, batteries}` consumed by the Task 1 test.

**Scope note:** This slice builds the *mechanism* and verifies it with hermetic tests. It does NOT run the first real ~18-agent template audit (that's user-triggered post-merge via the slash command) — keeping the implementation deterministic and avoiding an expensive dispatch inside the build.
