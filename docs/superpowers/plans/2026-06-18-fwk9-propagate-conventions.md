# FWK9 — Propagate the patterns convention roster into generated projects — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every project produced by `framework new` born adopting all five `cdowell-swtr/patterns` conventions (PI, MEMORY, docs-layout, git, superpowers-model-routing) — pointer blocks + seeded stateful files + public/vendored validators, citing patterns as authority, with zero runtime dependency on the private patterns repo.

**Architecture:** Pure **template payload** work under `src/framework_cli/template/`. Managed (framework-owned) pieces — the pointer blocks (`AGENTS.md`, `CLAUDE.md`), the pre-commit wiring, and the vendored docs-layout validator — go in `FRAMEWORK:BEGIN/END` managed regions or `LOCKED_TRACKED`, so `framework upgrade`/`restore` keeps them current. Stateful PI/MEMORY files (`PLAN.md`, `ACTION_LOG.md`, `MEMORY.md`, `_memory/`, `_archive/`) are seeded once via copier `_skip_if_exists` + `INTENTIONALLY_UNLOCKED`, so upgrades never clobber a consumer's plan. The PI task-ID prefix is a new `pi_prefix` copier question.

**Tech Stack:** Copier (Jinja templates + `_skip_if_exists`), pre-commit (gitleaks + conventional-pre-commit public hooks + a vendored zero-dep bash validator), pytest (render-level in `tests/test_copier_runner.py`; acceptance in `tests/acceptance/`).

**Spec:** `docs/superpowers/specs/2026-06-18-fwk9-propagate-conventions-design.md`

**Conventions reference (published "copy this block" sources, adapted with a citation line):**
- PI / docs-layout / git → `AGENTS.md` (portable). MEMORY / model-routing → `CLAUDE.md` (CC-specific).
- gitleaks pin `v8.21.2` (already in template); conventional-pre-commit pin `v3.6.0`.
- docs-layout validator vendored from `cdowell-swtr/patterns` `hooks/docs-layout-check.sh` @ `docs-layout/v1`.

---

## File map

| Path (under `src/framework_cli/template/` unless noted) | Action | Class |
|---|---|---|
| `copier.yml` | add `pi_prefix` question + `_skip_if_exists` | — |
| `AGENTS.md.jinja` | **create** — PI + docs-layout + git pointer blocks (managed region) | HYBRID_TRACKED |
| `CLAUDE.md.jinja` | add `@AGENTS.md`/`@MEMORY.md` imports + MEMORY + model-routing blocks (managed region) | HYBRID_TRACKED (already) |
| `.pre-commit-config.yaml` | add conventional-pre-commit (commit-msg) + `default_install_hook_types` + docs-layout local hook (managed region) | HYBRID_TRACKED (already) |
| `scripts/docs_layout_check.sh` | **create** — vendored validator | LOCKED_TRACKED |
| `Taskfile.yml` | `task hooks` installs the `commit-msg` stage | HYBRID_TRACKED (already) |
| `PLAN.md.jinja` | **create** — seed (headers, empty Next/Done) → `PLAN.md` | INTENTIONALLY_UNLOCKED |
| `ACTION_LOG.md.jinja` | **create** — seed `#0001 · note` → `ACTION_LOG.md` | INTENTIONALLY_UNLOCKED |
| `MEMORY.md` | **create** — empty index + boundary note | INTENTIONALLY_UNLOCKED |
| `_memory/.gitkeep` | **create** | (keeper; unmanaged) |
| `_archive/ARCHIVED_PLAN.md` | **create** — stub | INTENTIONALLY_UNLOCKED |
| `_archive/ARCHIVED_ACTION_LOG.md` | **create** — stub | INTENTIONALLY_UNLOCKED |
| `README.md.jinja` | add optional-registration note | — |
| `src/framework_cli/copier_runner.py` (framework) | inject `render_date` for the seed log | — |
| `src/framework_cli/integrity/classes.py` (framework) | register new paths | — |
| `tests/runtime_coverage/registry.py` (framework) | classify new hook/script surfaces | — |

> **Note on copier markers:** the managed-region delimiters are the literal `FRAMEWORK:BEGIN`/`FRAMEWORK:END` tokens inside HTML comments, exactly as in the existing `CLAUDE.md.jinja`. Per the repo's hybrid-marker rule, never write that token in surrounding prose — only as the actual delimiter.

---

## Task 1: `pi_prefix` question + `AGENTS.md.jinja` (PI + docs-layout + git blocks)

**Files:**
- Modify: `src/framework_cli/template/copier.yml`
- Create: `src/framework_cli/template/AGENTS.md.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_copier_runner.py`:

```python
def test_render_seeds_agents_md_with_portable_convention_blocks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    agents = (dest / "AGENTS.md").read_text()
    # all three PORTABLE convention markers present
    assert "PI-convention: v2" in agents
    assert "DOCS-convention: v1" in agents
    assert "GIT-convention: v1" in agents
    # patterns is cited as authority, not vendored
    assert "cdowell-swtr/patterns" in agents
    # a managed region exists (hybrid file)
    from framework_cli.integrity.sections import section_content
    assert section_content(agents) is not None
    # consumer area exists below the closing marker
    assert "FRAMEWORK:END" in agents


def test_render_pi_prefix_defaults_from_slug(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)  # slug "demo"
    agents = (dest / "AGENTS.md").read_text()
    assert "`DEMO`" in agents  # derived default, uppercased slug truncated to 4


def test_render_pi_prefix_override(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(dest, {**DATA, "pi_prefix": "MRDN"})
    agents = (dest / "AGENTS.md").read_text()
    assert "`MRDN`" in agents
    assert "MRDN1, MRDN2" in agents
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_copier_runner.py -k "agents_md or pi_prefix" -v`
Expected: FAIL (AGENTS.md not rendered / KeyError on pi_prefix).

- [ ] **Step 3: Add the `pi_prefix` question to `copier.yml`**

Insert after the `package_name` block in `src/framework_cli/template/copier.yml`:

```yaml
pi_prefix:
  type: str
  help: PI task-ID prefix (short uppercase tag, e.g. FWK, MDN)
  default: "{{ (project_slug | upper | replace('-', '') | replace('_', ''))[:4] }}"
```

- [ ] **Step 4: Create `src/framework_cli/template/AGENTS.md.jinja`**

```jinja
# {{ project_name }} — Agent Working Agreement

<!-- FRAMEWORK:BEGIN -->
<!-- This section is managed by the framework. Edit outside the markers; framework upgrades may rewrite this block. -->

<!-- PI-convention: v2 -->
## Planning Instrument
Read `PLAN.md` first. Maintain `PLAN.md` + `ACTION_LOG.md` at task grain as you work
(tick tasks; append a log entry on every completion and every deviation). Task IDs use this
repo's prefix **`{{ pi_prefix }}`** (`{{ pi_prefix }}1, {{ pi_prefix }}2, …`).
Full convention: `cdowell-swtr/patterns` `pi-convention.md` @ `pi/v2`.

<!-- DOCS-convention: v1 -->
## Documentation layout
Internal docs in `_docs/`, external in `documentation/`. Namespace internal docs per concern
(`_docs/<namespace>/`). A planning tool's specs/plans go in `_docs/<namespace>/<tool>/{specs,plans}/`
(dated `YYYY-MM-DD-<name>.md`) — NOT the tool's default (e.g. superpowers' `docs/superpowers/...`);
drop a `.tool` file naming the tool in each tool dir. Validated by the `docs-layout` pre-commit hook.
Full convention: `cdowell-swtr/patterns` `docs-layout-convention.md` @ `docs-layout/v1`.

<!-- GIT-convention: v1 -->
## Git
Branches: `<task-id>-<slug>` (1:1 to a PLAN item) or `<type>/<slug>` fallback; direct-to-main OK for solo/small repos.
Commits: Conventional Commits `type(scope): subject` (+ `Co-Authored-By` for agents). Tags: `<thing>/vN`.
Write to other repos via a clone/PR, never their live working copy; never run two sessions in one working copy.
Enforced by the `conventional-pre-commit` (commit-msg) + `gitleaks` hooks.
Full convention: `cdowell-swtr/patterns` `git-convention.md` @ `git/v1`.

<!-- FRAMEWORK:END -->

## Project notes

_Add project-specific agent guidance here. This area is yours; the framework will not overwrite it._
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k "agents_md or pi_prefix" -v`
Expected: PASS.

- [ ] **Step 6: Format check the rendered output + stage (do not commit — controller finalizes)**

Run: `uv run ruff format --check . && uv run ruff check .`
Then: `git add src/framework_cli/template/copier.yml src/framework_cli/template/AGENTS.md.jinja tests/test_copier_runner.py`

---

## Task 2: `CLAUDE.md.jinja` — imports + MEMORY + model-routing blocks

**Files:**
- Modify: `src/framework_cli/template/CLAUDE.md.jinja` (inside the managed region, before `<!-- FRAMEWORK:END -->`)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_claude_md_imports_agents_and_memory(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    claude = (dest / "CLAUDE.md").read_text()
    assert "@AGENTS.md" in claude
    assert "@MEMORY.md" in claude
    assert "MEMORY-convention: v1" in claude
    assert "SUPERPOWERS-MODEL-ROUTING-convention: v1" in claude
    # CC-specific blocks must sit INSIDE the managed region (before the closing marker)
    body = claude
    assert body.index("MEMORY-convention: v1") < body.index("FRAMEWORK:END")
    assert body.index("@AGENTS.md") < body.index("FRAMEWORK:END")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -k claude_md_imports -v`
Expected: FAIL.

- [ ] **Step 3: Add the blocks to the managed region**

In `src/framework_cli/template/CLAUDE.md.jinja`, immediately **before** the `<!-- FRAMEWORK:END -->` line (the existing managed region ends after "## Quality commands"), insert:

```jinja
## Project conventions

This project adopts the `cdowell-swtr/patterns` convention roster. Portable conventions
(Planning Instrument, docs layout, git) are in `@AGENTS.md`; the Claude-Code-specific ones
are below.

@AGENTS.md

<!-- MEMORY-convention: v1 -->
## Committed project memory
Project memory is autoloaded from `MEMORY.md` (imported below). Resolve `[[slug]]` to `_memory/<slug>.md`.
Commit a memory only when it is BOTH useful to anyone working this repo AND safe to publish; otherwise keep
it in the native store. When in doubt, native. Full convention: `cdowell-swtr/patterns` `memory-convention.md` @ `memory/v1`.

@MEMORY.md

<!-- SUPERPOWERS-MODEL-ROUTING-convention: v1 -->
## Superpowers model routing
When running superpowers subagent-driven-development, route subagents by per-role model *floors* (never below):
implementer ≥ latest Sonnet; spec/mechanistic review ≥ latest Sonnet; code-quality review = latest Opus;
final full-implementation review = latest Opus. Upgrades (incl. the BLOCKED escalation) are always fine; only
downgrade below a floor is forbidden. This overrides the skill's "Model Selection" heuristic.
Full convention: `cdowell-swtr/patterns` `superpowers-model-routing-convention.md` @ `superpowers-model-routing/v1`.
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py -k claude_md_imports -v`
Expected: PASS.

- [ ] **Step 5: Format check + stage**

Run: `uv run ruff format --check . && uv run ruff check .`
Then: `git add src/framework_cli/template/CLAUDE.md.jinja tests/test_copier_runner.py`

---

## Task 3: Seed-once stateful files + `render_date` injection + `_skip_if_exists`

**Files:**
- Modify: `src/framework_cli/copier_runner.py` (inject `render_date`)
- Create: `src/framework_cli/template/PLAN.md`, `ACTION_LOG.md`, `MEMORY.md`, `_memory/.gitkeep`, `_archive/ARCHIVED_PLAN.md`, `_archive/ARCHIVED_ACTION_LOG.md`
- Modify: `src/framework_cli/template/copier.yml` (add `_skip_if_exists`)
- Test: `tests/test_copier_runner.py`

> These are plain files (no `.jinja` suffix) except where they interpolate — copier strips the `.jinja` suffix on render. `ACTION_LOG.md` needs `{{ render_date }}` + `{{ pi_prefix }}` and `PLAN.md` needs `{{ project_name }}`, so their **sources are `ACTION_LOG.md.jinja` and `PLAN.md.jinja`** (rendered paths `ACTION_LOG.md` / `PLAN.md`). `MEMORY.md` and the two `_archive/*.md` stubs interpolate nothing → static files. `_skip_if_exists` entries below use the **rendered** paths regardless of source suffix.

- [ ] **Step 1: Write the failing tests**

```python
def test_render_seeds_pi_and_memory_state_files(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert (dest / "PLAN.md").is_file()
    assert (dest / "MEMORY.md").is_file()
    assert (dest / "_memory" / ".gitkeep").is_file()
    assert (dest / "_archive" / "ARCHIVED_PLAN.md").is_file()
    assert (dest / "_archive" / "ARCHIVED_ACTION_LOG.md").is_file()
    log = (dest / "ACTION_LOG.md").read_text()
    assert "#0001 · note" in log
    assert "adopted" in log.lower()
    memory = (dest / "MEMORY.md").read_text()
    assert "MEMORY-convention: v1" in memory


def test_render_date_is_injected_into_seed_log(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "render_date": "2026-01-02"})
    log = (dest / "ACTION_LOG.md").read_text()
    assert "2026-01-02" in log
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_copier_runner.py -k "state_files or render_date" -v`
Expected: FAIL.

- [ ] **Step 3: Inject `render_date` in `copier_runner.py`**

Edit `src/framework_cli/copier_runner.py` — add the import and a default so the seed log is dated without breaking existing callers:

```python
from collections.abc import Mapping
from datetime import date
from importlib.resources import files
from pathlib import Path

from copier import run_copy


def template_path() -> Path:
    """Absolute path to the bundled Copier template directory."""
    return Path(str(files("framework_cli"))) / "template"


def render_project(dest: Path, data: Mapping[str, object]) -> None:
    """Render the bundled template into `dest` using the provided answers."""
    from framework_cli.migrations import migration_context

    merged = dict(data)
    merged.setdefault("render_date", date.today().isoformat())
    batteries = merged.get("batteries", []) or []
    merged.update(migration_context(batteries if isinstance(batteries, list) else []))
    run_copy(
        str(template_path()),
        str(dest),
        data=merged,
        defaults=True,
        overwrite=True,
        quiet=True,
    )
```

- [ ] **Step 4: Create the seed files**

`src/framework_cli/template/PLAN.md.jinja`:
```jinja
# PLAN — {{ project_name }}

> Current state only (Next + recent Done). Full history: git + `_archive/`.
> Maintained per the Planning Instrument convention (`PI-convention: v2`).

## Next

## Done
- (none yet — this project was scaffolded by swiftwater-framework)
```

`src/framework_cli/template/ACTION_LOG.md.jinja`:
```jinja
# ACTION_LOG — {{ project_name }}

> Append-only event narrative (completions + deviations + operational reasons), task grain.
> Maintained per the Planning Instrument convention (`PI-convention: v2`).

#### #0001 · note · {{ render_date }}
Adopted the `cdowell-swtr/patterns` convention roster (PI / MEMORY / docs-layout / git /
superpowers-model-routing) via swiftwater-framework scaffolding. Task IDs use the prefix
`{{ pi_prefix }}`. First real task is `{{ pi_prefix }}1` in `PLAN.md` `Next`.
```

`src/framework_cli/template/MEMORY.md`:
```markdown
<!-- MEMORY-convention: v1 -->
# Committed project memory

Project-scoped memories, autoloaded every session via the `@MEMORY.md` import in `CLAUDE.md`.
One file per memory under `_memory/`; resolve `[[slug]]` to `_memory/<slug>.md`.

Commit a memory only when it is BOTH useful to anyone working this repo AND safe to publish.
Otherwise keep it in the native store. When in doubt, native. Full rule: `memory-convention.md`
in `cdowell-swtr/patterns` @ `memory/v1`.

## Index
```

`src/framework_cli/template/_memory/.gitkeep`:
```
```
(empty file)

`src/framework_cli/template/_archive/ARCHIVED_PLAN.md`:
```markdown
# Archived Plan

> Per PI ("relocation, not duplication"), the full content of items that leave `PLAN.md`
> is preserved here, never truncated. Stub until the first item rolls off.
```

`src/framework_cli/template/_archive/ARCHIVED_ACTION_LOG.md`:
```markdown
# Archived Action Log

> Overflow for old `ACTION_LOG.md` sections. Stub until needed.
```

- [ ] **Step 5: Add `_skip_if_exists` to `copier.yml`**

Add at the top of `src/framework_cli/template/copier.yml` (alongside `_templates_suffix`):

```yaml
_skip_if_exists:
  - PLAN.md
  - ACTION_LOG.md
  - MEMORY.md
  - _memory/.gitkeep
  - _archive/ARCHIVED_PLAN.md
  - _archive/ARCHIVED_ACTION_LOG.md
```

- [ ] **Step 6: Run to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k "state_files or render_date" -v`
Expected: PASS.

- [ ] **Step 7: Format check + stage**

Run: `uv run ruff format --check . && uv run ruff check . && uv run mypy src`
Then: `git add src/framework_cli/copier_runner.py src/framework_cli/template/PLAN.md.jinja src/framework_cli/template/ACTION_LOG.md.jinja src/framework_cli/template/MEMORY.md "src/framework_cli/template/_memory/.gitkeep" src/framework_cli/template/_archive/ARCHIVED_PLAN.md src/framework_cli/template/_archive/ARCHIVED_ACTION_LOG.md src/framework_cli/template/copier.yml tests/test_copier_runner.py`

---

## Task 4: Vendored docs-layout validator + git/docs-layout pre-commit wiring

**Files:**
- Create: `src/framework_cli/template/scripts/docs_layout_check.sh`
- Modify: `src/framework_cli/template/.pre-commit-config.yaml` (managed region)
- Modify: `src/framework_cli/template/Taskfile.yml` (`task hooks`)
- Modify: `src/framework_cli/template/README.md.jinja` (optional-registration note)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_render_precommit_adds_convention_hooks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    cfg = (dest / ".pre-commit-config.yaml").read_text()
    assert "conventional-pre-commit" in cfg
    assert "commit-msg" in cfg
    assert "default_install_hook_types" in cfg
    assert "docs-layout" in cfg
    assert (dest / "scripts" / "docs_layout_check.sh").is_file()


def test_render_docs_layout_validator_is_zero_dep_bash(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    script = (dest / "scripts" / "docs_layout_check.sh").read_text()
    assert script.startswith("#!/usr/bin/env bash")
    assert "vendored from cdowell-swtr/patterns" in script
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_copier_runner.py -k "convention_hooks or docs_layout_validator" -v`
Expected: FAIL.

- [ ] **Step 3: Create the vendored validator**

`src/framework_cli/template/scripts/docs_layout_check.sh` — copy the script body verbatim from `cdowell-swtr/patterns` `hooks/docs-layout-check.sh` @ `docs-layout/v1` (fetch with `gh api repos/cdowell-swtr/patterns/contents/hooks/docs-layout-check.sh?ref=docs-layout/v1 --jq .content | base64 -d`), prefixing a provenance line as the second line:

```bash
#!/usr/bin/env bash
# vendored from cdowell-swtr/patterns hooks/docs-layout-check.sh @ docs-layout/v1 (2026-06-18); re-vendor on a later docs-layout/v tag.
# docs-layout validator (DOCS-convention). Zero-dep; scans the doc tree only.
# ... (rest of the upstream script verbatim) ...
```

Make it executable: `chmod +x src/framework_cli/template/scripts/docs_layout_check.sh`.

- [ ] **Step 4: Wire both hooks in the pre-commit managed region**

In `src/framework_cli/template/.pre-commit-config.yaml`, add a top-level key just under the opening `FRAMEWORK:BEGIN` comment block (before `repos:`):

```yaml
default_install_hook_types: [pre-commit, commit-msg]
```

Add the conventional-pre-commit repo block inside the managed `repos:` list (after the `gitleaks` block):

```yaml
  - repo: https://github.com/compilerla/conventional-pre-commit
    rev: v3.6.0
    hooks:
      - id: conventional-pre-commit
        stages: [commit-msg]
```

Add the docs-layout local hook inside the existing `- repo: local` `hooks:` list (after `coverage-threshold`):

```yaml
      - id: docs-layout
        name: docs-layout (internal docs structure)
        entry: bash scripts/docs_layout_check.sh
        language: system
        pass_filenames: false
        always_run: true
```

- [ ] **Step 5: Ensure `task hooks` installs the commit-msg stage**

In `src/framework_cli/template/Taskfile.yml`, find the `hooks:` task. If it runs `pre-commit install`, change it to install both hook types (the `default_install_hook_types` key above makes a bare `pre-commit install` honor both, so confirm the task uses `pre-commit install --install-hooks` and add `pre-commit install --hook-type commit-msg` if the installed pre-commit version predates `default_install_hook_types` support):

```yaml
  hooks:
    desc: Install pre-commit hooks (pre-commit + commit-msg stages)
    cmds:
      - pre-commit install --install-hooks
      - pre-commit install --hook-type commit-msg
```

- [ ] **Step 6: Add the optional-registration note to the README**

In `src/framework_cli/template/README.md.jinja`, add a short subsection (near the bottom, outside any managed region):

```markdown
## Conventions

This project adopts the [`cdowell-swtr/patterns`](https://github.com/cdowell-swtr/patterns)
convention roster (Planning Instrument, Committed Memory, docs layout, git, superpowers model
routing) — see `AGENTS.md` and `CLAUDE.md`. Registering this repo in the patterns implementer
registries is **optional**; if you want it tracked there, append a row per each convention's
adoption runbook.
```

- [ ] **Step 7: Run to verify the render tests pass**

Run: `uv run pytest tests/test_copier_runner.py -k "convention_hooks or docs_layout_validator" -v`
Expected: PASS.

- [ ] **Step 8: Format check + stage**

Run: `uv run ruff format --check . && uv run ruff check .`
Then: `git add src/framework_cli/template/scripts/docs_layout_check.sh src/framework_cli/template/.pre-commit-config.yaml src/framework_cli/template/Taskfile.yml src/framework_cli/template/README.md.jinja tests/test_copier_runner.py`

---

## Task 5: Integrity classification + FWK29 runtime-coverage registry

**Files:**
- Modify: `src/framework_cli/integrity/classes.py`
- Modify: `tests/runtime_coverage/registry.py`
- Test: `tests/integrity/test_classes.py`, `tests/runtime_coverage/` (existing completeness test)

- [ ] **Step 1: Write the failing integrity asserts**

Add to `tests/integrity/test_classes.py`:

```python
def test_agents_md_is_hybrid():
    from framework_cli.integrity.classes import HYBRID_TRACKED

    assert "AGENTS.md" in HYBRID_TRACKED


def test_docs_layout_validator_is_locked():
    from framework_cli.integrity.classes import LOCKED_TRACKED

    assert "scripts/docs_layout_check.sh" in LOCKED_TRACKED


def test_pi_memory_state_files_are_intentionally_unlocked():
    from framework_cli.integrity.classes import (
        INTENTIONALLY_UNLOCKED,
        LOCKED_TRACKED,
    )

    for rel in (
        "PLAN.md",
        "ACTION_LOG.md",
        "MEMORY.md",
        "_archive/ARCHIVED_PLAN.md",
        "_archive/ARCHIVED_ACTION_LOG.md",
    ):
        assert rel not in LOCKED_TRACKED
        assert rel in INTENTIONALLY_UNLOCKED
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/integrity/test_classes.py -k "agents_md or docs_layout_validator or state_files" -v`
Expected: FAIL.

- [ ] **Step 3: Register the paths in `classes.py`**

In `src/framework_cli/integrity/classes.py`:
- Add `"scripts/docs_layout_check.sh",` to `LOCKED_TRACKED` (keep the tuple alphabetically grouped with the other `scripts/` entries).
- Add `"AGENTS.md",` to `HYBRID_TRACKED`.
- Add to `INTENTIONALLY_UNLOCKED` (with a one-line comment each):

```python
    "PLAN.md",  # FWK9: PI stateful file — seeded once, consumer-owned (upgrade never clobbers)
    "ACTION_LOG.md",  # FWK9: PI append-only log — seeded once, consumer-owned
    "MEMORY.md",  # FWK9: committed-memory index — seeded once, consumer-owned
    "_archive/ARCHIVED_PLAN.md",  # FWK9: PI archive stub — consumer-owned
    "_archive/ARCHIVED_ACTION_LOG.md",  # FWK9: PI archive stub — consumer-owned
```

- [ ] **Step 4: Run to verify the integrity asserts pass + the hybrid-marker test still passes**

Run: `uv run pytest tests/integrity/test_classes.py -v`
Expected: PASS (incl. `test_every_hybrid_path_renders_with_markers`, which now checks `AGENTS.md` renders with a managed region — Task 1 ensured it does).

- [ ] **Step 5: Run the FWK29 completeness test to see the new unclassified surfaces**

Run: `uv run pytest tests/runtime_coverage/ -v`
Expected: FAIL — `test_every_surface_is_classified` reports new surfaces: `hook:conventional-pre-commit`, `hook:docs-layout`, `script:scripts/docs_layout_check.sh`.

- [ ] **Step 6: Classify the new surfaces as EXERCISED**

Add to `REGISTRY` in `tests/runtime_coverage/registry.py` (evidence = the Task 6 acceptance test):

```python
    SurfaceClass(
        "hook:conventional-pre-commit",
        ".pre-commit-config.yaml",
        _EX,
        # FWK9: git convention — commit-msg hook. A conventional message passes, a malformed
        # one is rejected, exercised on a fresh render.
        "test_rendered_project_adopts_conventions",
    ),
    SurfaceClass(
        "hook:docs-layout",
        ".pre-commit-config.yaml",
        _EX,
        # FWK9: docs-layout convention — vendored local validator, green on the born layout.
        "test_rendered_project_adopts_conventions",
    ),
    SurfaceClass(
        "script:scripts/docs_layout_check.sh",
        "scripts/docs_layout_check.sh",
        _EX,
        # FWK9: the docs-layout validator script, driven by the docs-layout pre-commit hook.
        "test_rendered_project_adopts_conventions",
    ),
```

- [ ] **Step 7: Run to verify the completeness test passes**

Run: `uv run pytest tests/runtime_coverage/ -v`
Expected: PASS.

- [ ] **Step 8: Stage**

Run: `git add src/framework_cli/integrity/classes.py tests/integrity/test_classes.py tests/runtime_coverage/registry.py`

---

## Task 6: Acceptance — born-adopted pre-commit green, conventional msg, upgrade idempotence

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`
- Test: itself (docker/acceptance tier — network needed for pre-commit to clone public hook repos)

> Model this on the existing `test_rendered_project_precommit_runs_clean` in the same file (find it for the render + `git init` + `pre-commit` invocation pattern, `disk_tmp` fixture, and any acceptance marker). Run acceptance tests with `TMPDIR=/var/tmp` per the repo's tmpfs note.

- [ ] **Step 1: Write the failing acceptance test**

Add to `tests/acceptance/test_rendered_project.py` (adapt the helper calls to match the file's existing render/init helpers):

```python
def test_rendered_project_adopts_conventions(disk_tmp):
    """FWK9: a fresh render is born adopted — pre-commit (incl. the vendored docs-layout
    validator + conventional-pre-commit) is green, a conventional commit message passes and a
    malformed one is rejected."""
    import subprocess

    dest = disk_tmp / "demo"
    render_project(dest, {**DATA, "pi_prefix": "DEMO"})

    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)

    # All hooks (incl. docs-layout + conventional config load) pass on the born layout.
    r = subprocess.run(
        ["pre-commit", "run", "--all-files"], cwd=dest, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr

    # commit-msg gate: a malformed message is rejected.
    subprocess.run(["pre-commit", "install", "--hook-type", "commit-msg"], cwd=dest, check=True)
    bad = subprocess.run(
        ["git", "commit", "-m", "not a conventional message"],
        cwd=dest, capture_output=True, text=True,
    )
    assert bad.returncode != 0, "conventional-pre-commit should reject a malformed message"
```

- [ ] **Step 2: Write the failing upgrade-idempotence test**

```python
def test_upgrade_preserves_seeded_plan_and_prefix(disk_tmp):
    """FWK9: PLAN.md is seed-once — a consumer edit survives `framework upgrade`, and the
    pi_prefix is stable (persisted answer)."""
    from framework_cli.upgrade import upgrade_project  # adapt to the real upgrade entrypoint

    dest = disk_tmp / "demo"
    render_project(dest, {**DATA, "pi_prefix": "DEMO"})
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(["git", "commit", "-qm", "chore: scaffold"], cwd=dest, check=True)

    plan = dest / "PLAN.md"
    plan.write_text(plan.read_text() + "\n- [ ] DEMO1 — my first real task\n")
    subprocess.run(["git", "commit", "-aqm", "chore: add task"], cwd=dest, check=True)

    upgrade_project(dest)  # re-render from the recorded template version

    assert "DEMO1 — my first real task" in plan.read_text()  # seed-once held
    assert "`DEMO`" in (dest / "AGENTS.md").read_text()  # prefix stable
```

> If the project's recorded `_commit` is not a real tag in this test context, follow the upgrade tests' existing pattern (`tests/test_upgrade.py`) for pointing the update at a local template ref; reuse their fixture/helper rather than inventing one.

- [ ] **Step 3: Run to verify they fail**

Run: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py -k "adopts_conventions or preserves_seeded_plan" -v`
Expected: FAIL (test functions are new and the wiring may need adaptation; the *intent* is the assertions above).

- [ ] **Step 4: Make them pass**

Fix wiring only — these assertions should hold once Tasks 1–5 are in. Adapt helper names (render/init/upgrade) to the file's existing patterns; do not weaken the assertions.

- [ ] **Step 5: Run to verify they pass**

Run: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py -k "adopts_conventions or preserves_seeded_plan" -v`
Expected: PASS.

- [ ] **Step 6: Stage**

Run: `git add tests/acceptance/test_rendered_project.py`

---

## Task 7: Full local gate + branch-end review

- [ ] **Step 1: Run the full framework gate**

Run:
```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green. (Acceptance tier separately: `TMPDIR=/var/tmp uv run pytest tests/acceptance -q` where docker is available.)

- [ ] **Step 2: Render + eyeball a generated project**

Run: `TMPDIR=/var/tmp uv run framework new /var/tmp/fwk9-demo --name "Fwk9 Demo"` (adapt to the real CLI signature), then confirm `AGENTS.md`, `CLAUDE.md`, `PLAN.md`, `ACTION_LOG.md` (dated `#0001`), `MEMORY.md`, `_memory/.gitkeep`, `_archive/*`, `scripts/docs_layout_check.sh`, and the pre-commit config all look right and the prefix is `FWK9` (slug `fwk9-demo` → `FWK9`).

- [ ] **Step 3: Branch-end whole-branch review (Opus) + finalize**

Controller dispatches the branch-end review; address findings; controller completes the commits (implementers stage but do not commit — see Execution).

---

## Execution

**Review-model policy (repo standing rule — restate, do not let the generic "least-powerful model" guidance collapse it):**
- Implementers → **Sonnet** (`claude-sonnet-4-6`); Haiku only for the most trivial mechanical task.
- Spec-compliance / mechanistic review → **Sonnet**.
- Code-quality review → **Opus** (`claude-opus-4-8`).
- Final / branch-end whole-branch review → **Opus**.
Pass `model` explicitly per role.

**Gate cadence (framework slice — the 18 app-agents over-fire on template/infra files):** use light per-task review + **controller skip-marker commits**, and one **branch-end full review**, rather than a full reviewers-gate per commit. Implementers stage + pass the commit-gate but **do not run `git commit`** — the controller verifies (`git log`/`status`) and finalizes each commit (writing the `.framework/audit/marker.json` skip-marker as needed). Keep the word "commit" out of Bash command *descriptions* (the PreToolUse gate false-matches the `git`+`commit` substring); stage with a separate call from any commit.

**Template-payload note:** these tests are render-level (they render and grep text — they run in the framework venv, no generated-project deps) except Task 6, which is acceptance-tier (docker/network; `TMPDIR=/var/tmp`). After any hand edit to a `.jinja`, re-run `ruff format --check` on the rendered output.

**No release:** template payload changes ship to consumers on the next release cut; FWK9 itself is not a release task. After merge, move FWK9 → PLAN `Done` and log the completion.
