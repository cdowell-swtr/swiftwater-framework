# FWK108 — Worktree instance identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute a worktree's `STACK_INSTANCE` (`<slug>-<inst>`) from its git branch — sanitized to a single `^[a-z0-9-]+$` DNS label, with a loud guard against stream B's reserved tier-3 namespace.

**Architecture:** A new plain (non-Jinja) template script `src/framework_cli/template/scripts/worktree.py` holds the pure identity functions plus thin runtime resolvers (slug from `infra/compose/base.yml`, branch from git). The pure functions take their inputs as parameters so a framework-level test (`tests/test_worktree.py`) can `importlib`-load the script and exercise it in the framework venv with no project render — the exact pattern `tests/test_check_migrations.py` uses for `check_migrations.py`.

**Tech Stack:** Python 3 stdlib only (`re`, `subprocess`, `pathlib`); pytest; the framework's `uv` toolchain.

## Global Constraints

- **Instance-string contract (FROZEN seam, FWK88):** `<inst>` and the full `STACK_INSTANCE` MUST match `^[a-z0-9-]+$` — a single DNS label, lowercase, no dots/uppercase — so the box's static `*.localhost` wildcard cert covers it.
- **Default parity (FROZEN):** for the standalone/single-stack case `STACK_INSTANCE` defaults to `<slug>` (today's labels byte-for-byte). FWK92 computes the worktree (`<slug>-<inst>`) form; the bare-`<slug>` default is the no-instance path and must not be broken.
- **Tier-2 ↔ tier-3 disjointness (FROZEN):** A2's `COMPOSE_PROJECT_NAME` (= `STACK_INSTANCE`) generator must **never** emit a name in stream B's reserved transient namespace `<slug>-t-<uuid>`. Conservatively, A2 reserves any instance whose first dash-segment is exactly `t`. *(Exact token pending confirmation with stream B / FWK76 — keep the reserved marker a single named constant.)*
- **`src/framework_cli/template/` is template payload, not framework source** — it renders into generated projects. `worktree.py` must be valid, ruff/mypy-clean Python (the generated project lints it), but the framework's own `mypy src` excludes it.
- **Seam is frozen, not renegotiable** — a wrong cut against FWK88 is a loud finding (record + surface), not a quiet adaptation.

---

### Task 1: Pure instance sanitization + STACK_INSTANCE assembly + tier-3 guard

**Files:**
- Create: `src/framework_cli/template/scripts/worktree.py`
- Test: `tests/test_worktree.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces (later sub-PLANs FWK93/FWK94 rely on these exact names/types):
  - `RESERVED_TIER3_MARKER: str` — the single reserved first-segment token (`"t"`).
  - `class Tier3NamespaceError(ValueError)` — raised when a derived instance enters B's reserved namespace.
  - `sanitize_instance(raw: str) -> str` — lowercases, maps every run of chars outside `[a-z0-9]` to a single `-`, strips leading/trailing `-`; raises `ValueError` if nothing valid remains.
  - `build_stack_instance(slug: str, branch: str) -> str` — returns `f"{slug}-{sanitize_instance(branch)}"`; raises `Tier3NamespaceError` if the sanitized instance's first dash-segment equals `RESERVED_TIER3_MARKER`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_worktree.py`:

```python
"""FWK92 — worktree instance identity. Framework-level: loads the plain template
script via importlib and exercises the pure functions in the framework venv (no
render), mirroring tests/test_check_migrations.py."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src/framework_cli/template/scripts/worktree.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("worktree", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- sanitize_instance ---------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("fwk92-instance-identity", "fwk92-instance-identity"),  # already clean
        ("Feature/Foo_Bar", "feature-foo-bar"),                  # slash, underscore, case
        ("---edge---", "edge"),                                  # trim leading/trailing dashes
        ("a__b//c", "a-b-c"),                                    # collapse runs to one dash
        ("CAPS", "caps"),                                        # lowercase
    ],
)
def test_sanitize_instance(raw, expected):
    mod = _load()
    assert mod.sanitize_instance(raw) == expected


def test_sanitize_instance_empty_raises():
    mod = _load()
    with pytest.raises(ValueError):
        mod.sanitize_instance("___")


def test_sanitize_instance_output_is_a_single_dns_label():
    import re

    mod = _load()
    for raw in ("Feature/Foo", "x..y", "9-Lives", "a/b/c"):
        out = mod.sanitize_instance(raw)
        assert re.fullmatch(r"[a-z0-9-]+", out), out
        assert not out.startswith("-") and not out.endswith("-")


# --- build_stack_instance ------------------------------------------------

def test_build_stack_instance_happy():
    mod = _load()
    assert mod.build_stack_instance("acme", "feature/foo") == "acme-feature-foo"


def test_build_stack_instance_tier3_reserved_raises():
    mod = _load()
    # A branch sanitizing to a first-segment "t" would enter B's <slug>-t-<uuid>
    # namespace — A2 must never emit it.
    with pytest.raises(mod.Tier3NamespaceError):
        mod.build_stack_instance("acme", "t-1234")


def test_build_stack_instance_tier3_only_guards_exact_t_segment():
    mod = _load()
    # "test" / "tango" start with the letter t but the first SEGMENT is not "t".
    assert mod.build_stack_instance("acme", "test-branch") == "acme-test-branch"
    assert mod.build_stack_instance("acme", "tango") == "acme-tango"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_worktree.py -v`
Expected: FAIL — collection/exec error because `src/framework_cli/template/scripts/worktree.py` does not exist.

- [ ] **Step 3: Write the minimal implementation**

Create `src/framework_cli/template/scripts/worktree.py`:

```python
"""Worktree-aware dev-stack provisioning (FWK74 / stream A2).

Computes this worktree's box-agnostic instance identity STACK_INSTANCE=<slug>-<inst>
from the git branch, sanitized to a single ^[a-z0-9-]+$ DNS label so the box's static
*.localhost cert covers it. Later sub-PLANs add the durable .env writer (FWK93),
provision via `task dev:edge` (FWK94), and symmetric deprovision (FWK95).

Plain (non-Jinja) template payload: the pure functions take slug/branch as arguments
so they are unit-testable in the framework venv; main() resolves them at runtime.
"""

from __future__ import annotations

import re

# Stream B reserves the transient COMPOSE_PROJECT_NAME namespace <slug>-t-<uuid>
# (carving spec, FWK88). A2 must never emit an instance whose first dash-segment is
# this marker. Exact token pending confirmation with stream B / FWK76.
RESERVED_TIER3_MARKER = "t"

_NON_LABEL = re.compile(r"[^a-z0-9]+")


class Tier3NamespaceError(ValueError):
    """Raised when a branch-derived instance falls in stream B's reserved tier-3 namespace."""


def sanitize_instance(raw: str) -> str:
    """Reduce an arbitrary branch/worktree name to a single ^[a-z0-9-]+$ DNS label."""
    label = _NON_LABEL.sub("-", raw.lower()).strip("-")
    if not label:
        raise ValueError(
            f"cannot derive a valid instance label from {raw!r} "
            "(empty after sanitization); pass an explicit instance name"
        )
    return label


def build_stack_instance(slug: str, branch: str) -> str:
    """Return STACK_INSTANCE=<slug>-<sanitized-branch>, guarding B's reserved namespace."""
    inst = sanitize_instance(branch)
    if inst.split("-", 1)[0] == RESERVED_TIER3_MARKER:
        raise Tier3NamespaceError(
            f"instance {inst!r} is in the reserved tier-3 namespace "
            f"({RESERVED_TIER3_MARKER!r}-*); rename the branch or pass an explicit "
            "instance name (--instance, FWK94)"
        )
    return f"{slug}-{inst}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_worktree.py -v`
Expected: PASS (all parametrized cases + the two tier-3 cases).

- [ ] **Step 5: Lint + format the new files**

Run: `uv run ruff check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py && uv run ruff format --check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py`
Expected: no errors (per [[ruff-format-check-after-inline-edits]], `format --check` catches long-line reflow `check` alone misses).

- [ ] **Step 6: Commit**

Stage `PLAN.md`/`ACTION_LOG.md` (tick FWK92 progress; append a log entry) FIRST per the commit-gate, then:

```bash
git add tests/test_worktree.py src/framework_cli/template/scripts/worktree.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk92): worktree instance identity — sanitize + STACK_INSTANCE + tier-3 guard"
```

---

### Task 2: Runtime resolvers — slug from compose, branch from git, and the public `resolve_stack_instance()`

**Files:**
- Modify: `src/framework_cli/template/scripts/worktree.py`
- Test: `tests/test_worktree.py`

**Interfaces:**
- Consumes: `sanitize_instance`, `build_stack_instance` (Task 1).
- Produces (FWK93/FWK94 rely on these):
  - `read_slug(base_yml: Path) -> str` — returns the compose project name from the `name:` key of `infra/compose/base.yml` (the slug == today's `COMPOSE_PROJECT_NAME` default). Raises `ValueError` if absent.
  - `current_branch(cwd: Path | None = None) -> str` — returns the branch name via `git symbolic-ref --short HEAD` (precise branch name; works on an unborn branch with no commits, unlike `rev-parse --abbrev-ref`; correctly errors on a detached HEAD, which a parallel-dev worktree is never on).
  - `resolve_stack_instance(base_yml: Path, cwd: Path | None = None) -> str` — composes the two resolvers through `build_stack_instance`; the one call FWK93/FWK94 use.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_worktree.py`:

```python
import subprocess


def test_read_slug_parses_compose_name(tmp_path):
    mod = _load()
    base = tmp_path / "base.yml"
    base.write_text("# header\nname: acme-store\nservices:\n  app: {}\n")
    assert mod.read_slug(base) == "acme-store"


def test_read_slug_missing_name_raises(tmp_path):
    mod = _load()
    base = tmp_path / "base.yml"
    base.write_text("services:\n  app: {}\n")
    with pytest.raises(ValueError):
        mod.read_slug(base)


def test_current_branch_reads_git(tmp_path):
    mod = _load()
    subprocess.run(["git", "init", "-q", "-b", "feature/foo"], cwd=tmp_path, check=True)
    assert mod.current_branch(tmp_path) == "feature/foo"


def test_resolve_stack_instance_end_to_end(tmp_path):
    mod = _load()
    base = tmp_path / "infra" / "compose" / "base.yml"
    base.parent.mkdir(parents=True)
    base.write_text("name: acme-store\n")
    subprocess.run(["git", "init", "-q", "-b", "wt/blue", "."], cwd=tmp_path, check=True)
    assert mod.resolve_stack_instance(base, tmp_path) == "acme-store-wt-blue"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_worktree.py -k "read_slug or current_branch or resolve_stack_instance" -v`
Expected: FAIL — `read_slug`/`current_branch`/`resolve_stack_instance` not defined.

- [ ] **Step 3: Write the minimal implementation**

Add to `src/framework_cli/template/scripts/worktree.py` (after `build_stack_instance`; add the imports to the top block):

```python
import subprocess
from pathlib import Path

_NAME_KEY = re.compile(r"^name:\s*(?P<name>[A-Za-z0-9._-]+)\s*$", re.MULTILINE)

# Path to the rendered project's compose base, relative to the project root.
COMPOSE_BASE = Path("infra/compose/base.yml")


def read_slug(base_yml: Path = COMPOSE_BASE) -> str:
    """Return the compose project name (== the slug / COMPOSE_PROJECT_NAME default)."""
    m = _NAME_KEY.search(base_yml.read_text())
    if not m:
        raise ValueError(f"no top-level `name:` key found in {base_yml}")
    return m.group("name")


def current_branch(cwd: Path | None = None) -> str:
    """Return the current git branch name.

    `symbolic-ref --short HEAD` resolves the branch even on an unborn branch (no
    commits yet) and errors loudly on a detached HEAD — a parallel-dev worktree is
    always on a named branch, so a detached HEAD is a real misuse worth failing on.
    """
    out = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def resolve_stack_instance(base_yml: Path = COMPOSE_BASE, cwd: Path | None = None) -> str:
    """Compute this worktree's STACK_INSTANCE from the compose slug + the git branch."""
    return build_stack_instance(read_slug(base_yml), current_branch(cwd))
```

(Consolidate the `from __future__ import annotations`, `import re`, `import subprocess`, and `from pathlib import Path` into the single top-of-file import block — don't leave a mid-file import; ruff will flag it.)

- [ ] **Step 4: Run the full test file to verify it passes**

Run: `uv run pytest tests/test_worktree.py -v`
Expected: PASS (Task 1 + Task 2 tests).

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py && uv run ruff format --check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py`
Expected: no errors.

- [ ] **Step 6: Commit**

Stage `PLAN.md`/`ACTION_LOG.md` first (tick FWK92 done; log entry), then:

```bash
git add tests/test_worktree.py src/framework_cli/template/scripts/worktree.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk92): runtime resolvers (slug from compose, branch from git) + resolve_stack_instance"
```

---

## Verification (whole sub-PLAN)

- [ ] `uv run pytest tests/test_worktree.py -v` — all green.
- [ ] `uv run ruff check src/framework_cli/template/scripts/worktree.py tests/test_worktree.py` — clean.
- [ ] `uv run ruff format --check src/framework_cli/template/scripts/worktree.py tests/test_worktree.py` — clean.
- [ ] Confirm `worktree.py` has **no** Jinja markers (`grep -cE '\{\{|\{%' src/framework_cli/template/scripts/worktree.py` → `0`), so the importlib load works and it renders verbatim.
- [ ] `STACK_INSTANCE` values produced are valid single DNS labels (asserted by `test_sanitize_instance_output_is_a_single_dns_label` + the end-to-end test).

## Notes for the next sub-PLAN (FWK93)

- FWK93 consumes `resolve_stack_instance()` to write the durable per-worktree `.env`
  (`STACK_INSTANCE`, `COMPOSE_PROJECT_NAME=$STACK_INSTANCE`, exported `PORT_OFFSET` when `--ports`),
  with idempotent reconcile, plus offset selection via live `docker compose ls` introspection.
- The `--instance` override escape hatch (for a branch that legitimately sanitizes into the reserved
  `t-*` namespace, or any manual override) lands in FWK93/FWK94's CLI surface — `build_stack_instance`
  already accepts an explicit instance via `sanitize_instance`, so the override wires a user string in
  ahead of `current_branch()`.
- Before `/clear`-ing after FWK92: no stack is ever brought up here (pure logic), so no teardown is
  needed — just confirm the commits landed.
```
