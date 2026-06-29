# FWK110 — Provision orchestration (`worktree:up` → export + `task dev:edge`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the CLI/orchestration layer to `scripts/worktree.py` — an `up` subcommand that resolves the worktree's `STACK_INSTANCE`, optionally selects a `PORT_OFFSET`, writes/merges the durable `.env`, **exports** the vars itself, and execs `task dev:edge`. Plus the `worktree:up` Taskfile target, and the two FWK93 whole-sub-PLAN-review carry-forwards (the ports-less→`--ports` reconcile-to-0 foot-gun; the `BASE_HOST_PORTS`↔`compose.sh` sync-guard test).

**Architecture:** Extend `src/framework_cli/template/scripts/worktree.py` (FWK92 identity + FWK93 `.env`/offset/planner shipped) with: a `PORT_OFFSET_FOR` selection marker (the foot-gun fix, modifies `plan_provision`), `parse_obs_selection` (frozen routable-set validation), a pure-ish `provision(...)` (introspect → plan → write → export → exec), and `main(argv)` (argparse `up`, instance resolution, Tier-3 catch). The `down` subcommand body is **FWK95** — not pulled forward. Add the `worktree:up` task target to `Taskfile.yml.jinja`'s managed `FRAMEWORK:BEGIN/END` block.

**Tech Stack:** Python 3 stdlib only (`argparse`, `os`, `re`, `subprocess`, `pathlib`); pytest; the framework's `uv` toolchain.

## Decisions settled (the two FWK94-open forks — closed via advisor, full session context)

- **F1 — stub-vs-wait → WAIT, no stub.** A1 (`fwk75-behind-edge`) has **not** landed `task dev:edge` (its tip is only the fwk92 `STACK_INSTANCE` compose plumbing). A no-op `dev:edge` stub validates nothing an injected subprocess runner doesn't, and a *real* `worktree:up` needs both A1's `dev:edge` **and** A1's compose `STACK_INSTANCE` plumbing — both A1-side and absent. So the **live edge integration test is inherently a Milestone-M item** (post-rebase onto real A1). FWK94-now scopes to: orchestration logic via an **injected runner** (mirroring how `running_host_ports` already injects `run`) + the carry-forwards + the Taskfile target. No fenced stub is written.
- **F2 — reconcile-to-0 foot-gun → extra recorded state (`PORT_OFFSET_FOR`), inside `plan_provision`.** The `.env` value alone can't tell "defaulted 0" from "selected 0" (carry-forward's own note), so CLI-on-the-value is out. Gate verbatim reuse on a marker written **only when `--ports` actually selects**: `PORT_OFFSET_FOR=<instance>`. Reconcile iff `recorded.get("PORT_OFFSET_FOR") == instance`. This **modifies shipped FWK93 behavior** (not pure-additive) → the already-committed `test_plan_provision_reconciles_recorded_offset_verbatim` must be updated to carry the marker, and the full `test_worktree.py` (not a `-k` slice) is the gate.

## Global Constraints

- **`src/framework_cli/template/` is template payload, not framework source** — `worktree.py` must be valid, ruff/mypy-clean Python (the generated project lints it), but the framework's own `mypy src` excludes it. Keep it **Jinja-marker-free except the one intentional `{{.Ports}}`** (the `docker ps --format` Go-template idiom — `grep -cE '\{\{|\{%'` → exactly `1`, safe per copier `_templates_suffix: .jinja` verbatim-copy; locked by FWK93 evidence log:#0327). The `importlib` load is unaffected.
- **The export IS the deliverable.** worktree.py exports the vars itself (vs leaning on A1's `dotenv:`) precisely so `compose.sh` only ever sees an **exported** `PORT_OFFSET`. The core new test asserts the `task dev:edge` exec environment carries the exported `STACK_INSTANCE`/`PORT_OFFSET` — do not let argparse plumbing crowd this out.
- **Seam is frozen, not renegotiable** — `STACK_INSTANCE`, the routable obs set `{grafana,prometheus,alertmanager}`, the network invariants are FWK88-frozen. A2 validates `--obs` against the frozen set; **how** the selection reaches the edge is A1's `dev:edge` contract (undefined until it lands) → validate input now, **defer propagation to Milestone M**.
- **Scope = provision (`up`) only.** FWK95 owns `down` + `worktree:down`. Define `up` fully; do not pull a `down` body forward. Catch `Tier3NamespaceError` in `main()` and point the user at `--instance`.
- **Tests are framework-venv `importlib` loads** (no render) for the `worktree.py` logic, exactly as FWK92/FWK93. The Taskfile target is a **template-payload change** → its check is a render assertion in `test_copier_runner.py`.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/framework_cli/template/scripts/worktree.py` | FWK92/93 (shipped) **+** `PORT_OFFSET_FOR` marker, `parse_obs_selection`, `provision`, `main`. | Modify (append + amend `plan_provision`) |
| `tests/test_worktree.py` | FWK92/93 tests (shipped; **amend** one) **+** foot-gun, sync-guard, obs, orchestration tests. | Modify |
| `src/framework_cli/template/Taskfile.yml.jinja` | Add `worktree:up` target to the managed block. | Modify |
| `tests/test_copier_runner.py` | Render assertion: rendered Taskfile exposes `worktree:up`. | Modify (append) |

---

### Task 1: Foot-gun fix — `PORT_OFFSET_FOR` selection marker in `plan_provision`

Closes carry-forward #1: after a ports-less `up` the `.env` carries `STACK_INSTANCE=<inst>` + the template default `PORT_OFFSET=0` but no selection marker, so the old gate (`STACK_INSTANCE==instance and "PORT_OFFSET" in recorded`) wrongly reconciled a later `--ports` up to `0`.

**Files:** Modify `worktree.py`, `tests/test_worktree.py`.

**Interfaces:**
- `plan_provision(...)` — gate verbatim reuse on `recorded.get("PORT_OFFSET_FOR") == instance` (NOT `"PORT_OFFSET" in recorded`). On any `--ports` provision, **also write `PORT_OFFSET_FOR=<instance>`** (idempotent on reconcile, fresh on select).

- [ ] **Step 1: Amend the shipped reconcile test + add the foot-gun + marker tests**

Edit the existing `test_plan_provision_reconciles_recorded_offset_verbatim` so its `env_text` carries the marker (the new precondition for verbatim reuse):

```python
def test_plan_provision_reconciles_recorded_offset_verbatim():
    # advisor #1 / FWK94 F2: the .env records THIS instance's SELECTED offset via the
    # PORT_OFFSET_FOR marker. A re-run (e.g. after /clear, stack still up) must reuse 3000
    # verbatim — NOT re-introspect — even though `occupied` would otherwise select 1000.
    mod = _load()
    env_text = (
        "STACK_INSTANCE=acme-store-wt-blue\n"
        "PORT_OFFSET_FOR=acme-store-wt-blue\n"
        "PORT_OFFSET=3000\n"
    )
    updates = mod.plan_provision(
        env_text, "acme-store-wt-blue", with_ports=True, occupied={8000}
    )
    assert updates["PORT_OFFSET"] == "3000"
```

Append the two new tests:

```python
def test_plan_provision_portless_then_ports_selects_fresh():
    # carry-forward #1: a prior ports-less up left STACK_INSTANCE=<inst> + the template
    # default PORT_OFFSET=0 but NO PORT_OFFSET_FOR marker. A later --ports up must select
    # fresh (1000 here), NOT silently reconcile to the defaulted 0 → main-stack collision.
    mod = _load()
    env_text = "STACK_INSTANCE=acme-store-wt-blue\nPORT_OFFSET=0\n"
    updates = mod.plan_provision(
        env_text, "acme-store-wt-blue", with_ports=True, occupied={8000}
    )
    assert updates["PORT_OFFSET"] == "1000"
    assert updates["PORT_OFFSET_FOR"] == "acme-store-wt-blue"


def test_plan_provision_writes_marker_on_fresh_select():
    # A fresh --ports provision records the selection marker so the NEXT run reconciles.
    mod = _load()
    updates = mod.plan_provision("", "acme-store-wt-blue", with_ports=True, occupied=set())
    assert updates["PORT_OFFSET"] == "0"  # nothing occupied → offset 0 is a real selection
    assert updates["PORT_OFFSET_FOR"] == "acme-store-wt-blue"
```

- [ ] **Step 2: Run — confirm the amended test fails first (red)**

Run: `uv run pytest tests/test_worktree.py -k plan_provision -v`
Expected: `test_plan_provision_reconciles_recorded_offset_verbatim` now **fails** (recorded `3000` re-selected to `1000` under the old gate); the two new tests fail (`PORT_OFFSET_FOR` absent).

- [ ] **Step 3: Implement — gate on the marker, write the marker**

Amend `plan_provision` in `worktree.py`:

```python
def plan_provision(
    env_text: str,
    instance: str,
    *,
    with_ports: bool,
    occupied: set[int] | None = None,
) -> dict[str, str]:
    """Compute the durable-.env updates for provisioning `instance`.

    STACK_INSTANCE / COMPOSE_PROJECT_NAME are always the resolved `instance` literal.
    With `--ports`, PORT_OFFSET is reused verbatim when the .env records a prior SELECTION
    for this instance (the PORT_OFFSET_FOR marker — the /clear reconcile, never re-introspect
    a live stack), else freshly selected. The marker distinguishes a deliberately-selected
    offset (incl. a legitimate 0) from the template default PORT_OFFSET=0 (carry-forward #1).
    """
    updates = {"STACK_INSTANCE": instance, "COMPOSE_PROJECT_NAME": instance}
    if with_ports:
        recorded = parse_env(env_text)
        if recorded.get("PORT_OFFSET_FOR") == instance and "PORT_OFFSET" in recorded:
            updates["PORT_OFFSET"] = recorded["PORT_OFFSET"]
        else:
            updates["PORT_OFFSET"] = str(select_port_offset(occupied or set()))
        updates["PORT_OFFSET_FOR"] = instance
    return updates
```

- [ ] **Step 4: Run — full file green**

Run: `uv run pytest tests/test_worktree.py -v`
Expected: PASS — all FWK92/93 (incl. amended reconcile) + the two new tests. Verify `test_plan_provision_recorded_other_instance_is_not_reconciled` + `test_plan_provision_fresh_selects_offset` + `test_plan_provision_sets_resolved_literals_no_ports` still pass unchanged (marker absent / different instance ⇒ select fresh; no-`--ports` ⇒ no marker).

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py && uv run ruff format --check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py`

- [ ] **Step 6: Commit** (stage `PLAN.md`/`ACTION_LOG.md` first per the commit-gate; `git add` sources+plan+log as one call, `git commit` separate — [[commit-gate-hook-timing]])

```
git commit -m "fix(fwk94): PORT_OFFSET_FOR marker — ports-less→--ports no longer reconciles to 0"
```

---

### Task 2: `BASE_HOST_PORTS` ↔ `compose.sh` sync-guard test

Closes carry-forward #2: the 16-port `BASE_HOST_PORTS` tuple is a hand-copied mirror of `compose.sh`'s `_p VAR DEFAULT` lines, checked only once manually. Add a framework-side test that parses the **template** `compose.sh` and asserts set-equality (obs-completeness-guard pattern, per [[obs-completeness-guard-already-exists]]).

**Files:** Modify `tests/test_worktree.py` (pure test; no source change unless drift is found).

- [ ] **Step 1: Write the test**

Append to `tests/test_worktree.py`:

```python
# --- BASE_HOST_PORTS ↔ compose.sh sync-guard (FWK94, carry-forward #2) ----


def test_base_host_ports_mirror_compose_sh():
    # BASE_HOST_PORTS is a hand-copied mirror of compose.sh's `_p VAR DEFAULT` host-port
    # defaults. Parse the template compose.sh and assert the DEFAULT set matches exactly,
    # so a future port added to compose.sh can't silently drift the offset window.
    import re as _re

    mod = _load()
    compose_sh = (
        Path(__file__).resolve().parents[1]
        / "src/framework_cli/template/scripts/compose.sh"
    )
    defaults = {
        int(m.group(1))
        for m in _re.finditer(
            r"^\s*_p\s+\w+\s+(\d+)\s*$", compose_sh.read_text(), _re.MULTILINE
        )
    }
    assert defaults == set(mod.BASE_HOST_PORTS), (
        f"compose.sh defaults {sorted(defaults)} != "
        f"BASE_HOST_PORTS {sorted(mod.BASE_HOST_PORTS)}"
    )
```

- [ ] **Step 2: Run — confirm it passes against current state (the mirror is correct today)**

Run: `uv run pytest tests/test_worktree.py -k base_host_ports -v`
Expected: PASS (FWK93 review verified the 16-port mirror). If it *fails*, the mirror has drifted — reconcile `BASE_HOST_PORTS` to `compose.sh` (the shell file is source-of-truth) before proceeding.

> Note: this is a guard test that is green on a correct mirror — there is no red-first step because no production behavior changes. The "test fails when the invariant breaks" is demonstrated by construction (the regex set-equality), and `compose.sh`'s 16 `_p` lines are the fixture.

- [ ] **Step 3 (optional, carry-forward #3): strengthen the self-collision test**

Only if cheap: extend `test_select_offset_handles_cross_window_self_collision` to force a window whose grafana (3000+offset) would land on a lower window's app (8000) — i.e. assert `select_port_offset({8000, ...})` skips offset 5000. Skip if it adds noise; the existing disjointness test already covers the mechanism.

- [ ] **Step 4: Lint + format + commit**

Run: `uv run ruff check tests/test_worktree.py && uv run ruff format --check tests/test_worktree.py`
Then commit (stage PLAN/LOG first):

```
git commit -m "test(fwk94): guard BASE_HOST_PORTS stays in sync with compose.sh _p defaults"
```

---

### Task 3: Provision orchestration — `parse_obs_selection`, `provision`, `main`

The CLI heart: `up` resolves the instance, introspects, plans, writes the durable `.env`, **exports** the vars, and execs `task dev:edge`. Split into a pure-ish `provision(...)` (testable with an injected runner + a tmp `.env`) and a thin `main(...)` glue (argparse + instance resolution + Tier-3 catch).

**Files:** Modify `worktree.py`, `tests/test_worktree.py`.

**Interfaces:**
- `ROUTABLE_OBS: tuple[str, ...] = ("grafana", "prometheus", "alertmanager")` — the FWK88-frozen edge-routable obs UIs.
- `parse_obs_selection(raw: str) -> tuple[str, ...]` — split a comma list, strip blanks, **raise `ValueError`** on any svc outside `ROUTABLE_OBS`; `""` → `()`.
- `provision(instance: str, *, with_ports: bool, run=subprocess.run, env_path: Path = ENV_PATH) -> int` — introspect occupied (only if `with_ports`), `plan_provision`, `write_env`, build `child_env = {**os.environ, **updates}`, exec `run(["task", "dev:edge"], check=True, env=child_env)`. **No `obs` param** — propagation to the edge is A1's `dev:edge` contract (Milestone M); threading an unused `obs` now is YAGNI. `main` validates `--obs` early (so a bad value fails loud) and discards the result until M.
- `main(argv: list[str] | None = None, *, run=subprocess.run) -> int` — argparse `up` (`--ports` flag, `--obs` str, `--instance` str override); resolve `instance = build_stack_instance(read_slug(), args.instance or current_branch())`; catch `Tier3NamespaceError` → `parser.error(... pass --instance ...)`; call `provision`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_worktree.py` (top-of-file already imports `subprocess`, `Path`, `pytest`):

```python
# --- provision orchestration (FWK94) -------------------------------------


def test_parse_obs_selection_accepts_frozen_set():
    mod = _load()
    assert mod.parse_obs_selection("grafana,prometheus") == ("grafana", "prometheus")
    assert mod.parse_obs_selection("") == ()
    assert mod.parse_obs_selection(" alertmanager ") == ("alertmanager",)


def test_parse_obs_selection_rejects_non_routable():
    mod = _load()
    # loki/tempo/exporters have no UI → not edge-routable (FWK88 frozen set).
    with pytest.raises(ValueError):
        mod.parse_obs_selection("grafana,loki")


def test_provision_exports_instance_and_offset_to_dev_edge(tmp_path):
    # The deliverable: worktree.py exports the vars itself so `task dev:edge` (and the
    # compose.sh under it) sees an EXPORTED PORT_OFFSET — never a bare .env value.
    mod = _load()
    env = tmp_path / ".env"
    env.write_text("PORT_OFFSET=0\n")
    seen = {}

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["task", "dev:edge"]:
            seen["cmd"] = cmd
            seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    rc = mod.provision(
        "acme-store-wt-blue", with_ports=True, run=fake_run, env_path=env
    )
    assert rc == 0
    assert seen["cmd"] == ["task", "dev:edge"]
    # Exported into the child env (nothing occupied → offset 0).
    assert seen["env"]["STACK_INSTANCE"] == "acme-store-wt-blue"
    assert seen["env"]["COMPOSE_PROJECT_NAME"] == "acme-store-wt-blue"
    assert seen["env"]["PORT_OFFSET"] == "0"
    # And persisted to the durable .env (idempotent merge), with the selection marker.
    written = mod.parse_env(env.read_text())
    assert written["STACK_INSTANCE"] == "acme-store-wt-blue"
    assert written["PORT_OFFSET_FOR"] == "acme-store-wt-blue"


def test_provision_no_ports_skips_docker_and_offset(tmp_path):
    # Without --ports: no docker ps introspection, no PORT_OFFSET written; dev:edge still runs.
    mod = _load()
    env = tmp_path / ".env"
    env.write_text("")
    seen = {}

    def fake_run(cmd, **kwargs):
        assert cmd[:2] != ["docker", "ps"], "must not introspect without --ports"
        if cmd[:2] == ["task", "dev:edge"]:
            seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    mod.provision("acme-store-wt-blue", with_ports=False, run=fake_run, env_path=env)
    assert "PORT_OFFSET" not in seen["env"] or "PORT_OFFSET" not in mod.parse_env(
        env.read_text()
    )
    assert seen["env"]["STACK_INSTANCE"] == "acme-store-wt-blue"


def test_main_up_resolves_branch_and_provisions(tmp_path, monkeypatch):
    # End-to-end glue: main('up') reads slug from infra/compose/base.yml + branch from git,
    # then provisions. Mirrors test_resolve_stack_instance_end_to_end's project setup.
    mod = _load()
    base = tmp_path / "infra" / "compose" / "base.yml"
    base.parent.mkdir(parents=True)
    base.write_text("name: acme-store\n")
    subprocess.run(["git", "init", "-q", "-b", "wt/blue", "."], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["task", "dev:edge"]:
            seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    rc = mod.main(["up"], run=fake_run)
    assert rc == 0
    assert seen["env"]["STACK_INSTANCE"] == "acme-store-wt-blue"


def test_main_up_instance_override(tmp_path, monkeypatch):
    # --instance overrides the branch (the escape hatch for a branch that sanitizes into t-*).
    mod = _load()
    base = tmp_path / "infra" / "compose" / "base.yml"
    base.parent.mkdir(parents=True)
    base.write_text("name: acme-store\n")
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["task", "dev:edge"]:
            seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    mod.main(["up", "--instance", "green"], run=fake_run)
    assert seen["env"]["STACK_INSTANCE"] == "acme-store-green"


def test_main_up_tier3_branch_errors_with_instance_hint(tmp_path, monkeypatch, capsys):
    # A branch sanitizing into B's reserved t-* namespace fails loud with a --instance hint.
    mod = _load()
    base = tmp_path / "infra" / "compose" / "base.yml"
    base.parent.mkdir(parents=True)
    base.write_text("name: acme-store\n")
    subprocess.run(["git", "init", "-q", "-b", "t/1234", "."], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        mod.main(["up"], run=lambda *a, **k: None)
    assert "--instance" in capsys.readouterr().err


def test_main_up_detached_head_errors_with_instance_hint(tmp_path, monkeypatch, capsys):
    # Detached HEAD: `git symbolic-ref` fails → friendly --instance hint, no raw traceback
    # (carried-forward FWK92 Minor). Set up a repo with a commit, then detach.
    mod = _load()
    base = tmp_path / "infra" / "compose" / "base.yml"
    base.parent.mkdir(parents=True)
    base.write_text("name: acme-store\n")
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(["git", "checkout", "-q", sha], cwd=tmp_path, check=True)  # detach
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        mod.main(["up"], run=lambda *a, **k: None)
    assert "--instance" in capsys.readouterr().err
```

- [ ] **Step 2: Run — confirm failure**

Run: `uv run pytest tests/test_worktree.py -k "obs_selection or provision_ or main_up" -v`
Expected: FAIL — `parse_obs_selection` / `provision` / `main` not defined.

- [ ] **Step 3: Implement**

Add `import argparse` and `import os` to the top import block of `worktree.py`. Append:

```python
# --- Provision orchestration: up → export → task dev:edge (FWK94) ---------

# FWK88-frozen edge-routable observability UIs (A1 adds the discovery labels). loki/tempo/
# exporters/otel-collector have no UI and are not edge-routable. A2 only selects from this set.
ROUTABLE_OBS: tuple[str, ...] = ("grafana", "prometheus", "alertmanager")


def parse_obs_selection(raw: str) -> tuple[str, ...]:
    """Parse/validate a comma-separated --obs list against the frozen routable set."""
    selected = tuple(part.strip() for part in raw.split(",") if part.strip())
    invalid = [svc for svc in selected if svc not in ROUTABLE_OBS]
    if invalid:
        raise ValueError(
            f"--obs: {invalid} not edge-routable; choose from {list(ROUTABLE_OBS)}"
        )
    return selected


def provision(
    instance: str,
    *,
    with_ports: bool,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    env_path: Path = ENV_PATH,
) -> int:
    """Provision this worktree's stack: plan → write durable .env → export → task dev:edge.

    Exports STACK_INSTANCE/COMPOSE_PROJECT_NAME (+ PORT_OFFSET when --ports) into the
    dev:edge child environment, so compose.sh sees an EXPORTED PORT_OFFSET — never a bare
    .env value (the whole reason this engine exports rather than leaning on `dotenv:`).
    """
    occupied = running_host_ports(run=run) if with_ports else set()
    env_text = env_path.read_text() if env_path.exists() else ""
    updates = plan_provision(
        env_text, instance, with_ports=with_ports, occupied=occupied
    )
    write_env(updates, path=env_path)
    child_env = {**os.environ, **updates}
    run(["task", "dev:edge"], check=True, env=child_env)
    return 0


def main(
    argv: list[str] | None = None,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    """CLI entrypoint. `up` provisions this worktree's stack; `down` is FWK95."""
    parser = argparse.ArgumentParser(prog="worktree", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    up = sub.add_parser("up", help="provision this worktree's stack behind the shared edge")
    up.add_argument(
        "--ports",
        action="store_true",
        help="also allocate a free PORT_OFFSET for direct host access",
    )
    up.add_argument(
        "--obs",
        default="",
        help=f"comma-separated obs UIs to expose ({', '.join(ROUTABLE_OBS)})",
    )
    up.add_argument(
        "--instance",
        default="",
        help="override the branch-derived instance (escape hatch for a reserved name)",
    )
    args = parser.parse_args(argv)

    if args.command == "up":
        try:
            parse_obs_selection(args.obs)  # validate now; edge propagation is Milestone M
        except ValueError as exc:
            parser.error(str(exc))
        if args.instance:
            source = args.instance
        else:
            try:
                source = current_branch()
            except subprocess.CalledProcessError:
                # detached HEAD or non-git cwd: git can't name a branch. Friendly hint
                # (carried-forward FWK92 Minor — don't surface a raw traceback at the CLI).
                parser.error(
                    "could not determine the git branch (detached HEAD?); "
                    "pass --instance to name the worktree explicitly"
                )
        try:
            instance = build_stack_instance(read_slug(), source)
        except Tier3NamespaceError as exc:
            parser.error(f"{exc} — pass --instance to override")
        return provision(instance, with_ports=args.ports, run=run)

    parser.error(f"unknown command {args.command!r}")  # unreachable (required=True)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 4: Run — green**

Run: `uv run pytest tests/test_worktree.py -v`
Expected: PASS (all FWK92/93/94).

- [ ] **Step 5: Lint + format + marker count**

Run: `uv run ruff check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py && uv run ruff format --check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py && grep -cE '\{\{|\{%' src/framework_cli/template/scripts/worktree.py`
Expected: clean; marker count still **1** (the `{{.Ports}}` idiom — no new markers introduced).

- [ ] **Step 6: Commit** (stage PLAN/LOG first)

```
git commit -m "feat(fwk94): worktree up orchestration — resolve/plan/export/exec task dev:edge"
```

---

### Task 4: `worktree:up` Taskfile target + render assertion

**Files:** Modify `src/framework_cli/template/Taskfile.yml.jinja`, `tests/test_copier_runner.py`.

**Interfaces:** a `worktree:up` task in the managed `FRAMEWORK:BEGIN/END` block → `uv run python scripts/worktree.py up` (precedent: `gen_observability.py`/`seed.py` targets at Taskfile.yml.jinja:153,163). Pass-through flags via `task` `{{.CLI_ARGS}}` so `task worktree:up -- --ports --obs grafana` reaches the script.

> **Jinja caveat:** the Taskfile is a `.jinja` file — `{{.CLI_ARGS}}` is go-task's own templating and **will be eaten by copier's Jinja** unless wrapped. Use copier's `{% raw %}{{.CLI_ARGS}}{% endraw %}` (grep the existing Taskfile for a `{% raw %}` precedent; if go-task pass-through isn't already used in the template, prefer the simpler form below and let FWK95 revisit args). **Simplest safe form (no CLI_ARGS):** the target runs `uv run python scripts/worktree.py up` and documents that flags are passed by editing/running the script directly — adequate for FWK94 (the orchestration + flags are script-level and unit-tested; the task target is the ergonomic entry). Confirm which form renders cleanly via the render assertion before committing.

- [ ] **Step 1: Add the target** (place it near `dev:`/`dev:down` inside the managed block):

```yaml
  worktree:up:
    desc: Provision THIS worktree's isolated dev stack behind the shared box edge (FWK74).
    preconditions:
      - sh: command -v docker
        msg: "Docker is required for `task worktree:up`. Run `task doctor` to check all host tools."
    cmds:
      - uv run python scripts/worktree.py up
```

(Flag pass-through deferred: run `uv run python scripts/worktree.py up --ports --obs grafana` directly for now; FWK95 + the M rebase onto A1's `dev:edge` revisit ergonomic args. Keep the target minimal so it renders without a `{{.CLI_ARGS}}`/`{% raw %}` hazard.)

- [ ] **Step 2: Add the render assertion** to `tests/test_copier_runner.py` — mirror `test_render_db_tasks` exactly (module helpers `render_project` + `DATA` already imported/defined):

```python
def test_render_worktree_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "worktree:up:" in taskfile
    assert "scripts/worktree.py up" in taskfile
    # The orchestration script renders verbatim into the project (non-.jinja payload).
    assert (dest / "scripts" / "worktree.py").is_file()
```

- [ ] **Step 3: Render + acceptance evidence** (template change → CLAUDE.md obligation; sandbox-disabled, `TMPDIR=/var/tmp`):

Run: `uv run pytest tests/test_copier_runner.py -k worktree -v`
Then a baseline render to confirm the Taskfile renders cleanly and the target survives verbatim:
`TMPDIR=/var/tmp uv run pytest tests/test_copier_runner.py -k "taskfile or render" -q` (or the module's standard render smoke).
Expected: PASS; rendered `Taskfile.yml` contains `worktree:up:` + `scripts/worktree.py up`, no stray `{{`/`{%`.

- [ ] **Step 4: Lint + commit** (stage PLAN/LOG first)

```
git commit -m "feat(fwk94): worktree:up Taskfile target + render assertion"
```

---

## Verification (whole sub-PLAN)

- [ ] `uv run pytest tests/test_worktree.py -v` — all green (FWK92 + FWK93 + FWK94).
- [ ] `uv run pytest tests/test_copier_runner.py -k worktree -v` — rendered Taskfile exposes `worktree:up`.
- [ ] `uv run ruff check` + `uv run ruff format --check` on the two changed source files + both test files — clean.
- [ ] `grep -cE '\{\{|\{%' src/framework_cli/template/scripts/worktree.py` → exactly `1` (the `{{.Ports}}` idiom; no new markers).
- [ ] Foot-gun closed: `test_plan_provision_portless_then_ports_selects_fresh` green; the amended `test_plan_provision_reconciles_recorded_offset_verbatim` reuses `3000` **only because** the marker is present.
- [ ] Export proven: `test_provision_exports_instance_and_offset_to_dev_edge` asserts the `task dev:edge` child env carries the exported vars.
- [ ] Sync-guard live: `test_base_host_ports_mirror_compose_sh` green (mirror intact).
- [ ] Optional: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py -k ...` if a generated-project lint of `worktree.py` is warranted (the rendered project's ruff/mypy lints the new orchestration code) — sandbox-disabled.

## Execution

Per CLAUDE.md's review-model policy ([[subagent-review-model-pattern]]), restated so the subagent-driven skill's generic "least powerful model" guidance does not collapse the reviewers:
- **Implementers → Sonnet** (`claude-sonnet-4-6`); small pure-Python + a Taskfile line.
- **Spec-compliance review → Sonnet.**
- **Code-quality review → Opus** (`claude-opus-4-8`); a passing test is not a code-quality review.
- **Final whole-sub-PLAN review → Opus.**

**No stack is ever brought up in FWK94** — the docker touch + `task dev:edge` are mocked via the injected runner (decision F1: wait, no stub). So no teardown is owed before `/clear` into FWK95.

## Milestone M carry-forwards (recorded — survive `/clear`)

1. **Live edge integration test** (F1 deferral): once rebased onto real A1 (`fwk75-behind-edge` with `task dev:edge` + the compose `STACK_INSTANCE` plumbing), add the guarded docker-tier test — `worktree:up` brings up a real stack behind the shared edge; assert routing + per-instance isolation. Sandbox-disabled, `TMPDIR=/var/tmp`.
2. **`--obs` propagation**: wire the validated obs selection to A1's `dev:edge` contract (the mechanism is undefined until A1 lands). FWK94 validates + holds it; M wires it.
3. **Flag ergonomics for `worktree:up`**: revisit go-task `{{.CLI_ARGS}}` pass-through (with the `{% raw %}` copier guard) once the args surface stabilizes against A1.
4. **RE-KEY FWK92–96** to the next free range read from the then-current `main` PLAN (carving learning #5; the shared-counter triplicate-ID collision) — rename rows, spec, plans, `_memory`/doc cross-refs; commit-message IDs stay historical. Gates the A2→main merge (A1 lands first).

## Notes for the next sub-PLAN (FWK95)

- FWK95 adds the `down` subcommand body + `worktree:down` target: `docker compose -p ${STACK_INSTANCE} down -v` (reclaim the named volumes `dev:down` keeps) + edge-disconnect (A1's `dev:edge:down`) + offset auto-release, **ordered before `git worktree remove`**; plus the 2-instance network-isolation conformance test (store `default` nets + the `postgres` alias disjoint). The argparse already has the `up` subparser; FWK95 adds a `down` subparser alongside.
