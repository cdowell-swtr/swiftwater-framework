# Migration Backward-Compatibility (Plan 5c-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generated projects gate the container's auto-migration behind `APP_RUN_MIGRATIONS` (so a future multi-host deploy migrates once, not N racing times) and **block backward-incompatible (contract) migrations** — extending the Plan 5b reversibility guard with a contract-direction detector + an explicit opt-in marker — so a rolling/no-downtime deploy never silently breaks the old code still running during the roll.

**Architecture:** Two small, independent, no-Docker-host changes to **template payload**: (1) `scripts/entrypoint.sh` wraps its `alembic upgrade head` + seed in an `APP_RUN_MIGRATIONS` (default `true`) gate; (2) `scripts/check_migrations.py` (the 5b guard, already wired into pre-commit + the CI lint job) gains a second AST check that fails any migration whose `upgrade()` makes a destructive change (`drop_*`/`rename_table`/column rename) unless the file carries a `# deploy: contract` marker. Plus docs explaining *reversible ≠ backward-compatible* and the expand/contract-across-releases workflow. Validated by render assertions + a no-Docker acceptance test that exercises the detector, with the existing Docker live-stack tests confirming the default (`true`) migrate-on-start path is unchanged.

**Tech Stack:** Python `ast` (the guard), POSIX `sh` (the entrypoint), `pytest` (framework render + acceptance tests). No new dependencies, no Docker-host harness.

**Source spec:** `docs/superpowers/specs/2026-05-22-deploy-reference-strategy-design.md` §4 (migrate-once + entrypoint gating) and §5 (migration safety: reversible + backward-compatible, contract-direction detector + marker). This is **Plan 5c-1**, the migration-safety slice of Plan 5c; the multi-host rolling reference strategy + its e2e are **Plan 5c-2** (separate plan). Roadmap row: Plan 5c in `docs/superpowers/plans/2026-05-20-meta-plan.md`.

---

## Scope & Non-Goals

**In scope:**
1. `APP_RUN_MIGRATIONS` gate in `scripts/entrypoint.sh` (default `true` — dev / single-host / `test` unchanged; a multi-host deploy will set it `false` on the app hosts in 5c-2).
2. A **contract-direction (backward-compatibility) detector** added to `scripts/check_migrations.py`: fail any migration whose `upgrade()` does a destructive op, unless a `# deploy: contract` marker is present. Reuses the existing `migrations-reversible` pre-commit hook + CI lint step (no new wiring).
3. Docs: the *reversible ≠ backward-compatible* distinction + the expand/contract-across-releases workflow + the marker, in the generated `CLAUDE.md` convention, `infra/deploy/README.md`, and `DEPLOY.md`.

**Non-goals (deferred to Plan 5c-2):** the compose-over-SSH multi-host rolling `strategy.sh`, the app-only host compose, the deploy-workflow SSH/host-list wiring, and the local multi-container no-downtime e2e. None of those are touched here.

**Critical conventions (repo CLAUDE.md):** files under `src/framework_cli/template/` are template *payload* — the framework's own `ruff`/`mypy` exclude them; they're validated by rendering + running the generated project. `scripts/entrypoint.sh` and `scripts/check_migrations.py` have no Copier variables → plain files. `entrypoint.sh` must stay `shellcheck`-clean (the generated `shellcheck` pre-commit hook lints it); `check_migrations.py` must stay `ruff` + `ruff-format` clean (the generated project's pre-commit checks it — note ruff's default rule set does **not** include line-length E501, and `ruff format` does not rewrap string contents, so long message strings are fine; only over-long *expressions* get wrapped). The `migrations/versions/0001_initial.py` scaffold migration must keep passing both guards.

---

## File Structure

Modified template-payload files:

| File | Suffix | Change |
|---|---|---|
| `scripts/entrypoint.sh` | `.sh` (no vars) | Wrap `alembic upgrade head` + `python scripts/seed.py` in an `APP_RUN_MIGRATIONS` (default `true`) gate. |
| `scripts/check_migrations.py` | `.py` (no vars) | Add the contract-direction detector (`_contract_problem`) + the `# deploy: contract` marker; run it alongside the existing reversibility check. |
| `.pre-commit-config.yaml` | — | Update the `migrations-reversible` hook's human-readable `name` (the `id` is unchanged). |
| `CLAUDE.md.jinja` | `.jinja` | Extend the migration convention with backward-compatibility + the marker. |
| `infra/deploy/README.md` | `.md` (no vars) | Extend the migration-discipline section: expand-only-per-rolling-deploy, the contract detector + marker, `APP_RUN_MIGRATIONS`. |
| `DEPLOY.md.jinja` | `.jinja` | Extend the "Migrations are reversible (enforced)" section with the contract guard + marker. |

Modified framework-source tests:

| File | Change |
|---|---|
| `tests/test_copier_runner.py` | Extend `test_render_migration_guard` (detector present) + add `test_render_entrypoint_gates_migrations`. |
| `tests/acceptance/test_rendered_project.py` | Add `test_rendered_project_blocks_contract_migration` (no Docker — runs the detector over crafted migrations). |

---

## How to render & run during execution

```bash
uv run python -c "from framework_cli.copier_runner import render_project; from pathlib import Path; render_project(Path('/tmp/demo'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12'})"
cd "/tmp/demo" && uv sync
```

Re-render after every template edit. **No Docker is required for this plan's own checks** (the detector + render assertions). The existing Docker-gated live-stack tests still rely on the entrypoint's default-`true` migrate-on-start; they are run in Task 4's verification to confirm no regression.

### Committing in this repo (a hook will block you otherwise)
A `PreToolUse` hook blocks `git commit` unless `CLAUDE.md` has a **staged change**. Per commit: (1) bump the `**Last updated:**` line in `CLAUDE.md`; (2) `git add <files> CLAUDE.md` in ONE call; (3) `git commit` in a SEPARATE call (the hook checks staged state *before* the command runs — never combine add+commit). Avoid the word "commit" in other shell commands.

---

## Task 1: Gate the entrypoint's auto-migration behind `APP_RUN_MIGRATIONS`

**Files:**
- Modify: `src/framework_cli/template/scripts/entrypoint.sh`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_entrypoint_gates_migrations(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    entry = (dest / "scripts" / "entrypoint.sh").read_text()
    assert "APP_RUN_MIGRATIONS" in entry
    assert "alembic upgrade head" in entry
    assert 'exec "$@"' in entry
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_entrypoint_gates_migrations -q`
Expected: FAIL — `APP_RUN_MIGRATIONS` not in the entrypoint.

- [ ] **Step 3: Add the gate**

Replace the entire contents of `src/framework_cli/template/scripts/entrypoint.sh` with:

```sh
#!/bin/sh
set -e

# On container start: apply pending migrations + load seed data (both idempotent), then hand
# off to the server command (uvicorn, passed as CMD / compose `command`). Gated by
# APP_RUN_MIGRATIONS (default true) so dev / single-host / test self-migrate on start. A
# multi-host rolling deploy sets APP_RUN_MIGRATIONS=false on the app hosts and migrates ONCE
# before the roll (see infra/deploy/README.md), so N containers don't race the same migration.
if [ "${APP_RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
  python scripts/seed.py
fi
exec "$@"
```

- [ ] **Step 4: Run the render assertion + shellcheck**

Run: `uv run pytest tests/test_copier_runner.py::test_render_entrypoint_gates_migrations -q` → PASS.

Confirm the rendered entrypoint stays shellcheck-clean (it's linted by the generated `shellcheck` hook):
```bash
cd "/tmp/demo" && git init -q && git add -A && uv sync -q
uv run pre-commit run shellcheck --all-files
```
Expected: shellcheck Passed.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/scripts/entrypoint.sh tests/test_copier_runner.py
git commit -m "feat(template): gate entrypoint auto-migration behind APP_RUN_MIGRATIONS (default true)"
```
(Bump `CLAUDE.md`'s Last updated + `git add CLAUDE.md` in the same staging call, separate from the commit — see "Committing".)

---

## Task 2: Contract-direction (backward-compatibility) migration guard

**Files:**
- Modify: `src/framework_cli/template/scripts/check_migrations.py`
- Modify: `src/framework_cli/template/.pre-commit-config.yaml`
- Test: `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the failing acceptance test (no Docker)**

In `tests/acceptance/test_rendered_project.py`, add (it renders, `uv sync`s, then runs the detector over crafted migrations — no Docker needed):

```python
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_blocks_contract_migration(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    # The scaffold's own migration is safe (reversible + expand-only) -> exit 0.
    clean = subprocess.run(["uv", "run", "python", "scripts/check_migrations.py"], cwd=dest)
    assert clean.returncode == 0, "the scaffold's 0001 migration should pass both guards"

    versions = dest / "migrations" / "versions"

    # A destructive (contract) upgrade with NO marker -> blocked (exit 1).
    bad = versions / "9999_drop.py"
    bad.write_text(
        "def upgrade():\n    op.drop_column('items', 'name')\n\n"
        "def downgrade():\n    op.add_column('items', sa.Column('name', sa.String()))\n"
    )
    blocked = subprocess.run(
        ["uv", "run", "python", "scripts/check_migrations.py"], cwd=dest, capture_output=True, text=True
    )
    assert blocked.returncode == 1, "a contract migration without the marker must be blocked"
    assert "contract" in (blocked.stdout + blocked.stderr).lower()

    # Same migration WITH the acknowledgement marker -> allowed (exit 0).
    bad.write_text(
        "# deploy: contract\n"
        "def upgrade():\n    op.drop_column('items', 'name')\n\n"
        "def downgrade():\n    op.add_column('items', sa.Column('name', sa.String()))\n"
    )
    allowed = subprocess.run(["uv", "run", "python", "scripts/check_migrations.py"], cwd=dest)
    assert allowed.returncode == 0, "the '# deploy: contract' marker must exempt the migration"

    bad.unlink()
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_blocks_contract_migration -q`
Expected: FAIL — the unmarked `drop_column` migration is **not** blocked yet (the current guard only checks `downgrade()` reversibility, and this `downgrade()` is non-trivial), so `blocked.returncode` is 0, not 1.

- [ ] **Step 3: Extend the guard**

Replace the entire contents of `src/framework_cli/template/scripts/check_migrations.py` with:

```python
"""Block migrations that aren't safe for a rolling / no-downtime deploy.

Two structural guards, both run in pre-commit and CI over migrations/versions/*.py:

1. Reversible  — every migration's downgrade() must really reverse it (not missing / empty /
   pass / raise), so a rollback can always step back.
2. Backward-compatible — a rolling (or blue-green) deploy runs old and new code against ONE
   shared schema, so each deploy's migration must be expand-only (additive). A destructive
   "contract" change in upgrade() (drop_column / drop_table / drop_constraint / drop_index /
   rename_table, or a column rename via alter_column(new_column_name=...)) breaks the old code
   still running during the roll. Ship such a change as its OWN post-rollout release; add a
   `# deploy: contract` comment to the file to acknowledge that and exempt it from this guard.

Structural, not semantic: these don't decide whether a drop is *actually* safe given current
code — Plan 7's data-integrity review agent adds that judgement. See infra/deploy/README.md
for the expand/contract-across-releases workflow.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

VERSIONS = Path("migrations/versions")

_DESTRUCTIVE_OPS = {
    "drop_column",
    "drop_table",
    "drop_constraint",
    "drop_index",
    "rename_table",
}
_CONTRACT_MARKER = "deploy: contract"


def _top_level_func(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    return next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name),
        None,
    )


def _is_trivial(func: ast.FunctionDef) -> bool:
    # Drop docstrings / bare literal statements (runtime no-ops); what remains is the real body.
    body = [
        node
        for node in func.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    ]
    if not body:
        return True
    if all(isinstance(node, ast.Pass) for node in body):
        return True
    return len(body) == 1 and isinstance(body[0], ast.Raise)


def _destructive_op(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    name = node.func.attr
    if name in _DESTRUCTIVE_OPS:
        return name
    if name == "alter_column" and any(
        kw.arg == "new_column_name" for kw in node.keywords
    ):
        return "alter_column (rename)"
    return None


def _downgrade_problem(path: Path, tree: ast.Module) -> str | None:
    downgrade = _top_level_func(tree, "downgrade")
    if downgrade is None:
        return f"{path}: no downgrade() function"
    if _is_trivial(downgrade):
        return f"{path}: downgrade() is empty / pass / raise — write a real reversal (expand/contract)"
    return None


def _contract_problem(path: Path, tree: ast.Module, source: str) -> str | None:
    if _CONTRACT_MARKER in source:
        return None  # explicitly acknowledged as a standalone, post-rollout contract release
    upgrade = _top_level_func(tree, "upgrade")
    if upgrade is None:
        return None
    for node in ast.walk(upgrade):
        op = _destructive_op(node)
        if op is not None:
            return (
                f"{path}: upgrade() makes a destructive (contract) change ({op}) — it breaks "
                f"old code during a rolling deploy. Ship it as its own post-rollout release, "
                f"or add a '# {_CONTRACT_MARKER}' comment to acknowledge it."
            )
    return None


def _problems(path: Path) -> list[str]:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    found = [_downgrade_problem(path, tree), _contract_problem(path, tree, source)]
    return [msg for msg in found if msg is not None]


def main() -> int:
    if not VERSIONS.is_dir():
        return 0
    failures = [msg for path in sorted(VERSIONS.glob("*.py")) for msg in _problems(path)]
    for msg in failures:
        print(f"::error::{msg}", file=sys.stderr)
    if failures:
        print(
            f"\n{len(failures)} unsafe migration(s). Migrations must be reversible AND "
            "backward-compatible (expand-only); never destroy unreconstructable data. "
            "See infra/deploy/README.md.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

> **Why scan `upgrade()` (not `downgrade()`):** a *contract* change is destructive in the forward direction — you drop in `upgrade()`. The scaffold's `0001_initial.py` `upgrade()` calls `op.create_table(...)` (not destructive) and its `downgrade()` drops the table (the legitimate reversal we do *not* flag), so it stays clean. The marker is matched as a source substring (it's a comment, not in the AST).

- [ ] **Step 4: Update the pre-commit hook's name (the `id` stays `migrations-reversible`)**

In `src/framework_cli/template/.pre-commit-config.yaml`, change the `migrations-reversible` hook's `name` line from:

```yaml
        name: migrations are reversible (no irreversible downgrade)
```

to:

```yaml
        name: migrations are reversible + backward-compatible (rolling-safe)
```

(Leave `id: migrations-reversible`, `entry`, `files`, etc. unchanged — the hook already runs `scripts/check_migrations.py` in pre-commit, and the CI lint job already runs it too, so the new check is picked up with no wiring change.)

- [ ] **Step 5: Run the acceptance test + the reversibility regression**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_blocks_contract_migration -q` → PASS.

Confirm the existing reversibility behavior still holds and the scaffold stays clean (no Docker):
```bash
cd "/tmp/demo" && uv sync -q && uv run python scripts/check_migrations.py && echo "guard: clean"   # exit 0
uv run ruff check scripts/check_migrations.py && uv run ruff format --check scripts/check_migrations.py
```
Expected: "guard: clean" (the scaffold passes both checks); ruff + format clean.

- [ ] **Step 6: Add/extend the render assertion**

In `tests/test_copier_runner.py`, find the existing `test_render_migration_guard` and add these assertions to it (after its current body):

```python
    # the backward-compatibility (contract-direction) guard + the opt-in marker
    assert "_contract_problem" in guard.read_text()
    assert "deploy: contract" in guard.read_text()
```

(`guard` is the `scripts/check_migrations.py` Path already defined in that test.)

Run: `uv run pytest tests/test_copier_runner.py::test_render_migration_guard -q` → PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/scripts/check_migrations.py src/framework_cli/template/.pre-commit-config.yaml tests/test_copier_runner.py tests/acceptance/test_rendered_project.py
git commit -m "feat(template): block backward-incompatible (contract) migrations + # deploy: contract opt-in"
```
(Bump + stage `CLAUDE.md` separately, as in Task 1.)

---

## Task 3: Document reversible ≠ backward-compatible (the expand/contract workflow)

**Files:**
- Modify: `src/framework_cli/template/CLAUDE.md.jinja`
- Modify: `src/framework_cli/template/infra/deploy/README.md`
- Modify: `src/framework_cli/template/DEPLOY.md.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_migration_docs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    claude = (dest / "CLAUDE.md").read_text()
    assert "backward-compatible" in claude.lower()

    deploy_readme = (dest / "infra" / "deploy" / "README.md").read_text()
    assert "deploy: contract" in deploy_readme
    assert "APP_RUN_MIGRATIONS" in deploy_readme
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_migration_docs -q`
Expected: FAIL — `backward-compatible` not yet in CLAUDE.md / `deploy: contract` not in the deploy README.

- [ ] **Step 3: Extend the CLAUDE.md migration convention**

In `src/framework_cli/template/CLAUDE.md.jinja`, inside the `<!-- FRAMEWORK:BEGIN/END -->` block's `## Conventions` list, **replace** the current migration line:

```markdown
- Schema changes require a new migration; never edit an applied one. Every migration MUST be reversible — its `downgrade()` must really reverse the `upgrade()` (the migration guard blocks empty/`pass`/`raise` downgrades, in pre-commit and CI, so rollback can always step back). Prefer expand/contract; **never destroy data that cannot be reconstructed.** This applies to every database paradigm, not just the relational one.
```

with:

```markdown
- Schema changes require a new migration; never edit an applied one. Every migration must be both **reversible** (a real `downgrade()`) **and backward-compatible** (expand-only / additive) — a rolling deploy runs old and new code against one schema, so a destructive change breaks the still-running old code. The migration guard (pre-commit + CI) blocks empty/`pass`/`raise` downgrades AND destructive `upgrade()` ops (`drop_*`, `rename_table`, column renames); a genuinely destructive change must be its **own** post-rollout release, marked `# deploy: contract`. Prefer expand/contract; **never destroy data that cannot be reconstructed.** Applies to every database paradigm.
```

- [ ] **Step 4: Extend the deploy README's migration section**

In `src/framework_cli/template/infra/deploy/README.md`, in the "## Migrations: reversible by discipline, across every paradigm" section, **replace** the first two bullets:

```markdown
- **Write expand/contract migrations.** Add columns/tables (expand) and ship code that works
  with and without them; only remove the old shape (contract) in a later release once nothing
  uses it. A rollback's downgrade is then non-destructive.
- **Irreversible migrations are blocked, not just discouraged.** The migration guard
  (`scripts/check_migrations.py`, run in pre-commit + CI) fails any migration whose `downgrade`
  is empty/`pass`/`raise` — you cannot ship a one-way migration by accident. **Never destroy
  data that cannot be reconstructed**; if a destructive change is truly intended, make it a
  separate, explicitly-reviewed migration and accept that releases across it cannot be rolled
  back through it.
```

with:

```markdown
- **Write expand/contract migrations.** A rolling deploy runs old and new code against ONE
  shared schema, so each deploy's migration must be **backward-compatible (expand-only)**: add
  columns/tables/indexes (additive) and ship code that works with and without them; a
  destructive **contract** change (drop/rename) breaks the old code still running during the
  roll. Migrations also run **once** before the roll — set `APP_RUN_MIGRATIONS=false` on the
  app hosts so the per-container entrypoint does not race them (it defaults `true` for
  dev/single-host). A rollback then rolls the **code** back first, **then** downgrades.
- **Unsafe migrations are blocked, not just discouraged.** The migration guard
  (`scripts/check_migrations.py`, pre-commit + CI) fails any migration whose `downgrade()` is
  empty/`pass`/`raise` (irreversible) **or** whose `upgrade()` does a destructive op
  (`drop_*`, `rename_table`, column rename) — the latter unless the file is marked
  `# deploy: contract`. **Contract changes are their own post-rollout release:** ship the
  expand release, let it fully roll out, remove the old code, then a later `# deploy: contract`
  migration removes the old shape. **Never destroy data that cannot be reconstructed.**
```

- [ ] **Step 5: Extend the DEPLOY.md migration note**

In `src/framework_cli/template/DEPLOY.md.jinja`, in the "## Migrations are reversible (enforced)" section, **replace** the paragraph:

```markdown
Rollback reverses migrations to the previous release, so every migration must be reversible —
the framework **blocks** irreversible ones (`scripts/check_migrations.py`, in pre-commit + CI):
a `downgrade()` may not be empty/`pass`/`raise`. Write **expand/contract** migrations; never
destroy unreconstructable data. The same discipline applies to every database paradigm you add
(Plan 8), not just PostgreSQL.
```

with:

```markdown
Rollback reverses migrations, and a rolling deploy runs old + new code against one schema, so
every migration must be both **reversible** and **backward-compatible (expand-only)**. The
framework **blocks** both failure modes (`scripts/check_migrations.py`, in pre-commit + CI): a
`downgrade()` may not be empty/`pass`/`raise`, and an `upgrade()` may not make a destructive
change (`drop_*`/`rename`) unless the file is marked `# deploy: contract` (a destructive change
must be its own post-rollout release). Write **expand/contract** migrations; never destroy
unreconstructable data. The same discipline applies to every database paradigm you add (Plan
8), not just PostgreSQL.
```

- [ ] **Step 6: Run the render assertion**

Run: `uv run pytest tests/test_copier_runner.py::test_render_migration_docs -q` → PASS.

Confirm the doc edits didn't break existing doc-assertion tests (these assert other strings in the same files):
Run: `uv run pytest tests/test_copier_runner.py -q` → all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/CLAUDE.md.jinja src/framework_cli/template/infra/deploy/README.md src/framework_cli/template/DEPLOY.md.jinja tests/test_copier_runner.py
git commit -m "docs(template): document reversible vs backward-compatible migrations + the contract marker"
```
(Bump + stage `CLAUDE.md` separately.)

---

## Task 4: Full verification + roadmap/state update

**Files:**
- Modify: `docs/superpowers/plans/2026-05-20-meta-plan.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Framework Layer-A gate (no Docker)**

Run from the repo root:
```bash
uv run ruff check .
uv run mypy src
uv run pytest tests/test_copier_runner.py tests/test_cli.py tests/test_naming.py tests/test_smoke.py -q
uv run pytest \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_blocks_contract_migration" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_precommit_runs_clean" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_exports_openapi" -q
```
Expected: all PASS. `precommit_runs_clean` runs `shellcheck` over the updated `entrypoint.sh` and the `migrations-reversible` hook over the scaffold's `0001_initial.py` — both must be clean. `blocks_contract_migration` proves the new detector.

> If `ruff format --check` would change `check_migrations.py` after rendering, fix it (`cd /tmp/demo && uv run ruff format --check scripts/check_migrations.py`). The plan's code is pre-wrapped; verify after rendering — this caught misses in Plans 3c/4/5b.

- [ ] **Step 2: Generated-project suite + the default-`true` migrate path (Docker)**

The `APP_RUN_MIGRATIONS` default (`true`) must keep the live stack migrating + seeding on start. Run:
```bash
uv run pytest \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_passes_its_own_tests" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_dev_stack_serves_seeded_items" -q
```
Expected: PASS — the dev/lite stack still runs migrations + serves the seeded `/items` (proving the default-`true` gate preserves the existing behavior). If Docker is unavailable these skip; note that in the final review.

- [ ] **Step 3: Update the meta-plan**

In `docs/superpowers/plans/2026-05-20-meta-plan.md`: the `5c` row currently covers the whole reference strategy. Split its tracking — mark **5c-1 (migration backward-compatibility)** `✅ Done` with this plan's filename + the merge commit (`TBD (FF pending)` — controller fills after merge), and keep **5c-2 (the multi-host rolling reference strategy + e2e)** as `⬜ Not started (design approved)` referencing the design spec. Update the "Done so far" prose to mention the `APP_RUN_MIGRATIONS` gate + the contract-direction guard.

- [ ] **Step 4: Update CLAUDE.md state**

In `CLAUDE.md`, update **Last updated** (datetime + tz), **Where we are** (5c-1 implemented & green on branch, pending review+merge — the `APP_RUN_MIGRATIONS` entrypoint gate + the backward-compatibility migration guard), and **Next** (Plan 5c-2 — the multi-host rolling reference strategy + e2e, after a short e2e-harness design pass; then Plan 6).

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-05-20-meta-plan.md CLAUDE.md
git commit -m "docs: mark Plan 5c-1 (migration backward-compatibility) complete"
```

---

## Self-Review

**Spec coverage (design spec §4–§5):**
- §4 entrypoint auto-migrate gating (`APP_RUN_MIGRATIONS`, default true) → Task 1. ✅ (migrate-once orchestration itself is 5c-2.)
- §5 reversible ≠ backward-compatible; contract-direction detector over `upgrade()` (`drop_*`/`rename_table`/column-rename) + `# deploy: contract` opt-in; reuses the existing pre-commit + CI wiring → Task 2. ✅
- §5 Plan 7 adds semantic judgement later → documented (the guard's docstring + Task 3 docs say it's structural, agent adds semantics). ✅
- §5 expand/contract-across-releases workflow documented (CLAUDE.md + deploy README + DEPLOY.md) → Task 3. ✅
- Multi-host strategy / app-only compose / workflow wiring / e2e → **explicitly 5c-2**, not here. ✅ (intentional slice)

**Placeholder scan:** No TBD/"add X"/"similar to Task N". Every code step shows full file content or an exact old→new replacement; every run step shows the command + expected result. ✅

**Type/name consistency:**
- `APP_RUN_MIGRATIONS` — entrypoint gate (Task 1), documented in the deploy README (Task 3), and the render assertions (Tasks 1, 3). Consistent. ✅
- `check_migrations.py` functions — `_top_level_func`, `_is_trivial`, `_destructive_op`, `_downgrade_problem`, `_contract_problem`, `_problems`, `main` — defined once in Task 2; the render assertion checks `_contract_problem` + the marker (Task 2 Step 6). ✅
- `_CONTRACT_MARKER = "deploy: contract"` ↔ the marker string asserted in the acceptance test (Task 2 Step 1), the render assertions (Task 2 Step 6, Task 3 Step 1), and the docs (Task 3). Consistent. ✅
- `_DESTRUCTIVE_OPS` set (`drop_column`/`drop_table`/`drop_constraint`/`drop_index`/`rename_table`) + the `alter_column(new_column_name=)` rename — the test uses `op.drop_column` (in the set) → blocked. ✅
- The pre-commit hook `id` stays `migrations-reversible` (only `name` changes), so the 5b render assertion (`"migrations-reversible" in precommit`) still passes. ✅

**Cleanliness:** `check_migrations.py` long message strings don't trip ruff (E501 not in the default rule set; `ruff format` doesn't rewrap strings); the one long boolean (`alter_column` rename check) is pre-wrapped. `entrypoint.sh` is POSIX `sh`, `set -e`-safe, shellcheck-clean. The scaffold `0001_initial.py` passes both guards (create_table upgrade, drop_table downgrade). ✅

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-22-migration-backward-compat.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, spec + code-quality review between tasks (this repo's flow: branch → implementer per task → spec review → code-quality review → final review → merge to `master`).

**2. Inline Execution** — execute in this session with checkpoints.

**Which approach?**
