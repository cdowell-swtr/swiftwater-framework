# FWK95 — Deprovision (`worktree:down`) + network-isolation conformance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the symmetric teardown to `scripts/worktree.py` — a `down` subcommand that reads this worktree's `STACK_INSTANCE` from the durable `.env` (never re-derived from the branch), tears the stack down **with volume reclaim** (`docker compose -p ${STACK_INSTANCE} down -v` — the normal `dev:down` keeps volumes by design), **releases the port offset** (clears the `.env` selection markers so a later `up --ports` re-introspects + picks fresh), prints the `git worktree remove` next-step hint, and is ordered **before** worktree removal (the tool never removes the worktree itself). Plus the `worktree:down` Taskfile target and the **network-isolation conformance guard** (frozen FWK88 invariant: a data store is never attached to the shared edge net `swiftwater-shared-edge`).

**Architecture:** Extend `src/framework_cli/template/scripts/worktree.py` (FWK92 identity + FWK93 `.env`/offset/planner + FWK94 `up` orchestration shipped) with: a `remove_env_vars` `.env` key-deletion helper (the symmetric counterpart to FWK93's `merge_env_vars`), a `resolve_provisioned_instance` reader (STACK_INSTANCE-from-`.env`, friendly error if absent), a `deprovision(...)` orchestrator (injected `run`, like `provision`), and a `down` subparser in `main`. Add the `worktree:down` task target to `Taskfile.yml.jinja`'s managed `FRAMEWORK:BEGIN/END` block. The conformance guard is a render-then-parse-YAML test (in-gate, no docker).

**Tech Stack:** Python 3 stdlib only (`argparse`, `os`, `re`, `subprocess`, `pathlib`); pytest; PyYAML (already a test dep, imported in `test_copier_runner.py`); the framework's `uv` toolchain.

## Decisions settled (the two FWK95-open forks — closed via advisor, full session context)

- **F1 — stub-vs-wait → WAIT, no stub (same call as FWK94 F1).** A1 (`fwk75-behind-edge`) has progressed (fwk92/fwk93 instance-parameterized Traefik labels) but **still has not landed** `task dev:edge`, `dev:edge:down`, or the shared edge net `swiftwater-shared-edge`. The teardown's load-bearing, A2-owned half — `docker compose -p ${STACK_INSTANCE} down -v` (volume reclaim) + offset release — is **real and fully testable now** via an injected runner (mirroring `provision`/`running_host_ports`). The **edge-disconnect** half (A1's `dev:edge:down`) is **deferred to Milestone M**, not stubbed: pre-A1 there is no shared edge net to disconnect *from*, so an edge-disconnect call would be both impossible (target undefined) **and semantically vacuous** — and, unlike `up` (whose whole bring-up needs A1), `down`'s stack teardown succeeds without A1, so calling an undefined `dev:edge:down` with `check=True` would fail a real `worktree down` **after the stack already came down** (a confusing partial). So `deprovision` issues the real `down -v` directly (mirrors `dev:down`/`dev:reset`, which call `docker compose` directly, not a `dev:edge` task); edge-disconnect + its ordering-vs-`down -v` is an M carry-forward owned by A1's `dev:edge:down`. This is the deliberate up/down asymmetry: `up`'s edge-attach is entirely A1's `dev:edge`; `down`'s volume reclaim is a concrete docker op A2 owns now.
- **F2 — offset "auto-release" is false on the re-up path → clear the markers on `down`.** D2 says "release is automatic (stack down → ports free)" — but that only holds for *fresh* selection. After `down`, the `.env` still records `PORT_OFFSET_FOR=<inst>` + `PORT_OFFSET=<n>`, so a later `up --ports` hits FWK94's reconcile-verbatim path and **reuses the recorded offset without introspecting** — and if another worktree grabbed it in the interim, that's a silent collision. `down` clears `PORT_OFFSET` + `PORT_OFFSET_FOR` (the symmetric counterpart to FWK94's marker write) so re-up re-introspects and picks fresh (same offset if still free, a new one if taken). `STACK_INSTANCE`/`COMPOSE_PROJECT_NAME` are **kept** (they identify the worktree; re-up reconciles deterministically; `down` stays idempotent).

## Global Constraints

- **`src/framework_cli/template/` is template payload, not framework source** — `worktree.py` must be valid, ruff/mypy-clean Python (the generated project lints it), but the framework's own `mypy src` excludes it. Keep it **Jinja-marker-free except the one intentional `{{.Ports}}`** (`grep -cE '\{\{|\{%'` → exactly `1`). The `importlib` load is unaffected.
- **`down` reads `STACK_INSTANCE` from the durable `.env`, NOT re-derived from the branch.** The intentional asymmetry vs `up` (design line 77): a branch renamed after `up` would otherwise tear down the wrong/nonexistent stack. Friendly error when `.env` has no `STACK_INSTANCE` ("nothing provisioned for this worktree").
- **`down` never removes the worktree.** Ordered *before* `git worktree remove`; it tears the stack down + prints the hint, and leaves the `git worktree remove` to the operator (design lines 84–86).
- **Seam is frozen, not renegotiable** — `STACK_INSTANCE`, the shared edge net name `swiftwater-shared-edge`, the network-isolation invariants are FWK88-frozen. The conformance guard asserts the frozen invariant against the **frozen name** even though the net itself is an A1 deliverable not yet present → the guard passes trivially today and becomes **load-bearing at the M rebase** (it verifies the rebase didn't leak a data store onto the shared edge net).
- **Tests are framework-venv `importlib` loads** (no render) for the `worktree.py` logic, exactly as FWK92/93/94. The Taskfile target + the conformance guard are **template-payload changes** → their checks are render assertions in `test_copier_runner.py`.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/framework_cli/template/scripts/worktree.py` | FWK92/93/94 (shipped) **+** `remove_env_vars`, `resolve_provisioned_instance`, `deprovision`, `main` `down` subparser. | Modify (append + extend `main`) |
| `tests/test_worktree.py` | FWK92/93/94 tests (shipped) **+** `.env` removal, instance-resolve, deprovision orchestration, `main down` tests. | Modify (append) |
| `src/framework_cli/template/Taskfile.yml.jinja` | Add `worktree:down` target to the managed block. | Modify |
| `tests/test_copier_runner.py` | Render assertion: rendered Taskfile exposes `worktree:down`; **network-isolation conformance guard** (data stores off `swiftwater-shared-edge`). | Modify (append) |

---

### Task 1: `down` orchestration — `.env` removal helper, instance resolver, `deprovision`, `main` `down`

**Files:** Modify `worktree.py`, `tests/test_worktree.py`.

**Interfaces:**
- `OFFSET_RELEASE_KEYS: tuple[str, ...] = ("PORT_OFFSET", "PORT_OFFSET_FOR")` — cleared on `down` (F2).
- `remove_env_vars(text: str, keys: set[str]) -> str` — drop any real `KEY=…` assignment whose key ∈ `keys`; **comments never matched** (symmetric to `merge_env_vars`); preserve the trailing-newline convention.
- `resolve_provisioned_instance(env_text: str) -> str` — `parse_env(env_text)["STACK_INSTANCE"]`; **raise `ValueError`** with a friendly "nothing provisioned for this worktree — run `worktree up` first" if absent/empty.
- `deprovision(*, run=subprocess.run, env_path: Path = ENV_PATH) -> int` — read `.env`; resolve instance; `run(["docker", "compose", "-p", instance, "down", "-v"], check=True)` (volume reclaim — the half `dev:down` deliberately skips); clear `OFFSET_RELEASE_KEYS` from the `.env` (write only if changed); `print` the `git worktree remove` hint; return `0`. **No `dev:edge:down` call** (F1 — M carry-forward).
- `main` `down` branch — `try: return deprovision(run=run) except ValueError as exc: parser.error(str(exc))`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_worktree.py`):

```python
# --- .env removal (FWK95) ------------------------------------------------


def test_remove_env_vars_drops_keys_keeps_comments_and_others():
    mod = _load()
    out = mod.remove_env_vars(_REALISTIC_ENV, {"PORT_OFFSET"})
    parsed = mod.parse_env(out)
    assert "PORT_OFFSET" not in parsed
    # The commented decoy + unrelated user content survive.
    assert "# PORT_OFFSET is shifted" in out
    assert "MY_OWN_VAR=keepme" in out
    assert parsed["APP_ENVIRONMENT"] == "dev"


def test_remove_env_vars_absent_key_is_noop():
    mod = _load()
    out = mod.remove_env_vars("STACK_INSTANCE=x-y\n", {"PORT_OFFSET"})
    assert out == "STACK_INSTANCE=x-y\n"


# --- resolve_provisioned_instance (FWK95) --------------------------------


def test_resolve_provisioned_instance_reads_env():
    mod = _load()
    assert (
        mod.resolve_provisioned_instance("STACK_INSTANCE=acme-store-wt-blue\n")
        == "acme-store-wt-blue"
    )


def test_resolve_provisioned_instance_absent_raises():
    mod = _load()
    with pytest.raises(ValueError):
        mod.resolve_provisioned_instance("PORT_OFFSET=0\n")


# --- deprovision orchestration (FWK95) -----------------------------------


def test_deprovision_tears_down_with_volume_reclaim_and_releases_offset(tmp_path):
    # The deliverable: `down -v` reclaims volumes (dev:down keeps them) + the offset
    # markers are cleared so a later `up --ports` re-introspects (F2 release).
    mod = _load()
    env = tmp_path / ".env"
    env.write_text(
        "STACK_INSTANCE=acme-store-wt-blue\n"
        "COMPOSE_PROJECT_NAME=acme-store-wt-blue\n"
        "PORT_OFFSET_FOR=acme-store-wt-blue\n"
        "PORT_OFFSET=1000\n"
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    rc = mod.deprovision(run=fake_run, env_path=env)
    assert rc == 0
    # The real teardown — project-scoped down WITH -v (volume reclaim).
    assert calls == [["docker", "compose", "-p", "acme-store-wt-blue", "down", "-v"]]
    # Offset released; STACK_INSTANCE kept (identifies the worktree; re-up reconciles).
    written = mod.parse_env(env.read_text())
    assert "PORT_OFFSET" not in written
    assert "PORT_OFFSET_FOR" not in written
    assert written["STACK_INSTANCE"] == "acme-store-wt-blue"


def test_deprovision_no_instance_raises(tmp_path):
    mod = _load()
    env = tmp_path / ".env"
    env.write_text("PORT_OFFSET=0\n")
    with pytest.raises(ValueError):
        mod.deprovision(run=lambda *a, **k: None, env_path=env)


def test_deprovision_missing_env_raises(tmp_path):
    # No .env at all → nothing provisioned → friendly error, no docker touched.
    mod = _load()
    env = tmp_path / ".env"  # not created
    with pytest.raises(ValueError):
        mod.deprovision(run=lambda *a, **k: None, env_path=env)


def test_main_down_resolves_from_env_and_tears_down(tmp_path, monkeypatch):
    mod = _load()
    env = tmp_path / ".env"
    env.write_text("STACK_INSTANCE=acme-store-wt-blue\nPORT_OFFSET_FOR=acme-store-wt-blue\nPORT_OFFSET=1000\n")
    monkeypatch.chdir(tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    rc = mod.main(["down"], run=fake_run)
    assert rc == 0
    assert ["docker", "compose", "-p", "acme-store-wt-blue", "down", "-v"] in calls


def test_main_down_no_instance_errors_friendly(tmp_path, monkeypatch, capsys):
    mod = _load()
    (tmp_path / ".env").write_text("PORT_OFFSET=0\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        mod.main(["down"], run=lambda *a, **k: None)
    assert "provisioned" in capsys.readouterr().err
```

- [ ] **Step 2: Run — confirm failure** — `uv run pytest tests/test_worktree.py -k "remove_env or provisioned_instance or deprovision or main_down" -v` → FAIL (names undefined).

- [ ] **Step 3: Implement** in `worktree.py` (append after the FWK94 `provision`/before `main`; extend `main`):

```python
# --- Deprovision: worktree:down (FWK95) ----------------------------------

# Cleared on `down` so a later `up --ports` re-introspects + picks fresh (offset
# "release"): the FWK94 reconcile-verbatim path would otherwise reuse a stale recorded
# offset another worktree may have grabbed. STACK_INSTANCE/COMPOSE_PROJECT_NAME are kept.
OFFSET_RELEASE_KEYS: tuple[str, ...] = ("PORT_OFFSET", "PORT_OFFSET_FOR")


def remove_env_vars(text: str, keys: set[str]) -> str:
    """Drop any real KEY=… assignment whose key is in `keys` (comments untouched).

    The symmetric counterpart to merge_env_vars: a commented `# PORT_OFFSET=` decoy is
    never matched, and the trailing-newline convention is preserved.
    """
    out_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            if stripped.partition("=")[0].strip() in keys:
                continue
        out_lines.append(line)
    result = "\n".join(out_lines)
    if not text or text.endswith("\n"):
        result += "\n"
    return result


def resolve_provisioned_instance(env_text: str) -> str:
    """Return the STACK_INSTANCE a prior `up` recorded; error if none.

    `down` reads the instance from the durable .env — NOT re-derived from the branch
    (design line 77): a branch renamed after `up` would otherwise tear down the wrong
    stack.
    """
    instance = parse_env(env_text).get("STACK_INSTANCE")
    if not instance:
        raise ValueError(
            "nothing provisioned for this worktree (.env has no STACK_INSTANCE) — "
            "run `worktree up` first"
        )
    return instance


def deprovision(
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    env_path: Path = ENV_PATH,
) -> int:
    """Tear down this worktree's stack (with volume reclaim) + release the port offset.

    `down -v` reclaims the named volumes the normal `dev:down` keeps by design (so the
    worktree path would otherwise leak 3–7 volumes). Edge-disconnect from the shared edge
    net (A1's `dev:edge:down`) is a Milestone-M carry-forward — pre-A1 there is no shared
    edge net to disconnect from. Ordered before `git worktree remove` (the operator's next
    step; this tool never removes the worktree itself).
    """
    env_text = env_path.read_text() if env_path.exists() else ""
    instance = resolve_provisioned_instance(env_text)
    run(["docker", "compose", "-p", instance, "down", "-v"], check=True)
    released = remove_env_vars(env_text, set(OFFSET_RELEASE_KEYS))
    if released != env_text:
        env_path.write_text(released)
    print(
        f"stack {instance!r} torn down (volumes reclaimed). "
        "Run `git worktree remove <path>` to remove this worktree."
    )
    return 0
```

Then add the `down` subparser to `main` (alongside `up`) and the dispatch branch:

```python
    sub.add_parser("down", help="tear down this worktree's stack + reclaim its volumes")
    ...
    if args.command == "down":
        try:
            return deprovision(run=run)
        except ValueError as exc:
            parser.error(str(exc))
```

(Place the `down` dispatch before the trailing `parser.error("unknown command …")` fallback.)

- [ ] **Step 4: Run — full file green** — `uv run pytest tests/test_worktree.py -v` → PASS (all FWK92/93/94 + the new FWK95 tests).

- [ ] **Step 5: Lint + format + marker count** — `uv run ruff check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py && uv run ruff format --check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py && grep -cE '\{\{|\{%' src/framework_cli/template/scripts/worktree.py` → clean; marker count still **1**.

- [ ] **Step 6: Commit** (stage `PLAN.md`/`ACTION_LOG.md` first per the commit-gate; `git add` sources+plan+log as one call, `git commit` separate — [[commit-gate-hook-timing]])

```
git commit -m "feat(fwk95): worktree down — down -v volume reclaim + offset release"
```

---

### Task 2: `worktree:down` Taskfile target + render assertion

**Files:** Modify `src/framework_cli/template/Taskfile.yml.jinja`, `tests/test_copier_runner.py`.

**Interfaces:** a `worktree:down` task in the managed `FRAMEWORK:BEGIN/END` block (next to `worktree:up`) → `uv run python scripts/worktree.py down`. Minimal form — **no go-task `{{.CLI_ARGS}}`/`{% raw %}`** (same Jinja caveat as FWK94 Task 4; `down` takes no flags anyway).

- [ ] **Step 1: Add the target** (place it immediately after `worktree:up:` in the managed block):

```yaml
  worktree:down:
    desc: Tear down THIS worktree's stack + reclaim its volumes, before `git worktree remove` (FWK74).
    preconditions:
      - sh: command -v docker
        msg: "Docker is required for `task worktree:down`. Run `task doctor` to check all host tools."
    cmds:
      - uv run python scripts/worktree.py down
```

- [ ] **Step 2: Add the render assertion** to `tests/test_copier_runner.py` — extend `test_render_worktree_tasks` (added in FWK94) or append a sibling:

```python
def test_render_worktree_down_task(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "worktree:down:" in taskfile
    assert "scripts/worktree.py down" in taskfile
```

- [ ] **Step 3: Render evidence** (template change → CLAUDE.md obligation; copier-only, `TMPDIR=/var/tmp`):

`TMPDIR=/var/tmp uv run pytest tests/test_copier_runner.py -k "worktree" -v` → PASS; rendered `Taskfile.yml` contains `worktree:down:` + `scripts/worktree.py down`, no stray `{{`/`{%`, `yaml.safe_load` valid.

- [ ] **Step 4: Lint + commit** (stage PLAN/LOG first)

```
git commit -m "feat(fwk95): worktree:down Taskfile target + render assertion"
```

---

### Task 3: Network-isolation conformance guard (data stores off `swiftwater-shared-edge`)

The frozen FWK88 invariant (design lines 88–94): only edge-routed services join the shared edge net; **data stores (`postgres`/`redis`/`mongo`) stay on the per-project `default` net** (else worktree A's app reaches B's Postgres; the `postgres` alias resolves ambiguously). The guard is written against the **frozen name `swiftwater-shared-edge`** — it passes trivially today (the net is an A1 deliverable not yet present) and becomes **load-bearing at the M rebase**: it verifies A1's shared-net wiring did not attach a data store to the shared edge.

**Files:** Modify `tests/test_copier_runner.py` (render-then-parse-YAML, in-gate, no docker).

**Implementation notes for the implementer:**
- Render a project whose dev stack actually **includes** the data stores (so the guard is non-vacuous) — select the batteries that render `postgres`/`redis`/`mongo` into the dev compose file set. Inspect the rendered `infra/compose/*.yml` to confirm which store services are present under the relevant battery selection (e.g. `redis`/`workers`/the default DB); assert at least `postgres` (or the present store set) is found before asserting the negative.
- `yaml.safe_load` each compose file the dev stack merges (`base.yml` + `observability.yml` + `dev.yml`, plus `services.yml` if the store lives there), build `service -> set(networks)`, and assert **no** data-store service lists a network named `swiftwater-shared-edge`. Compose's `networks:` under a service may be a list or a dict — handle both.
- Keep it render-based (robust to the `.jinja` templating), not regex-on-`.jinja`.

- [ ] **Step 1: Write the guard** — append `test_data_stores_never_on_shared_edge_net` to `tests/test_copier_runner.py`. Sketch:

```python
def test_data_stores_never_on_shared_edge_net(tmp_path: Path):
    # FWK88 frozen invariant: data stores stay on the per-project `default` net, never on
    # the shared edge net. Armed against the frozen name today (the net is an A1 deliverable
    # not yet present) → becomes load-bearing at the M rebase (verifies A1 didn't leak a
    # store onto the shared edge). Render a stack that INCLUDES stores so the guard is non-vacuous.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": [...]})  # batteries that render postgres/redis/mongo
    SHARED_EDGE = "swiftwater-shared-edge"
    STORES = {"postgres", "redis", "mongo"}
    compose_dir = dest / "infra" / "compose"
    found_stores: set[str] = set()
    for f in compose_dir.glob("*.yml"):
        doc = yaml.safe_load(f.read_text()) or {}
        for name, svc in (doc.get("services") or {}).items():
            if name in STORES:
                found_stores.add(name)
                nets = svc.get("networks") or []
                names = set(nets) if isinstance(nets, (list, dict)) else set()
                assert SHARED_EDGE not in names, f"{name} attached to {SHARED_EDGE} in {f.name}"
    assert found_stores, "non-vacuous guard: no data store rendered — fix the battery selection"
```

- [ ] **Step 2: Run** — `TMPDIR=/var/tmp uv run pytest tests/test_copier_runner.py -k "shared_edge" -v` → PASS (stores present, none on the shared edge net).

- [ ] **Step 3: Lint + commit** (stage PLAN/LOG first)

```
git commit -m "test(fwk95): conformance guard — data stores never on swiftwater-shared-edge"
```

---

## Verification (whole sub-PLAN)

- [ ] `uv run pytest tests/test_worktree.py -v` — all green (FWK92 + FWK93 + FWK94 + FWK95).
- [ ] `TMPDIR=/var/tmp uv run pytest tests/test_copier_runner.py -k "worktree or shared_edge" -v` — rendered Taskfile exposes `worktree:down`; conformance guard green + non-vacuous.
- [ ] `uv run ruff check` + `uv run ruff format --check` on the changed source + test files — clean.
- [ ] `grep -cE '\{\{|\{%' src/framework_cli/template/scripts/worktree.py` → exactly `1` (the `{{.Ports}}` idiom; no new markers).
- [ ] Offset released: `test_deprovision_*_releases_offset` green — `PORT_OFFSET`/`PORT_OFFSET_FOR` cleared, `STACK_INSTANCE` kept.
- [ ] Read-from-`.env`: `down` resolves the instance from the durable `.env`, friendly error when absent.
- [ ] `down -v` proven: the injected runner sees `["docker","compose","-p",<instance>,"down","-v"]` (volume reclaim, not bare `down`).

## Execution

Per CLAUDE.md's review-model policy ([[subagent-review-model-pattern]]), restated so the subagent-driven skill's generic "least powerful model" guidance does not collapse the reviewers:
- **Implementers → Sonnet** (`claude-sonnet-4-6`); small pure-Python + a Taskfile line + a render guard.
- **Spec-compliance review → Sonnet.**
- **Code-quality review → Opus** (`claude-opus-4-8`); a passing test is not a code-quality review.
- **Final whole-sub-PLAN review → Opus.**

**No stack is ever brought up in FWK95** — `docker compose down -v` is mocked via the injected runner; the conformance guard is render-only (no docker). So no teardown is owed before `/clear`.

## Milestone M carry-forwards (recorded — survive `/clear`)

1. **Edge-disconnect via A1's `dev:edge:down`** (F1 deferral): once rebased onto real A1 (`dev:edge:down` + the shared edge net `swiftwater-shared-edge`), wire `deprovision` to disconnect from the shared edge net, and **settle the edge-disconnect-vs-`down -v` ordering** (external nets aren't compose-managed; `down` detaches containers as it removes them — the explicit-disconnect semantics are A1's mechanism).
2. **Live 2-instance network-isolation conformance** (docker-tier): two instances up via `dev:edge` → assert their store `default` networks **and** the `postgres` alias are disjoint, and that only edge-routed services join `swiftwater-shared-edge`. Pre-A1 only the per-project `default` half is exercisable (docker-compose's own `COMPOSE_PROJECT_NAME` behavior, already unit-tested); the dangerous "stores off the shared net" half needs A1's net live. Won't run in gating CI (`gate` is `pytest --ignore=tests/acceptance`, FWK70) → sandbox-disabled, `TMPDIR=/var/tmp`.
3. **RE-KEY FWK92–96** to the next free range read from the then-current `main` PLAN (carving learning #5; the shared-counter triplicate-ID collision) — rename rows, spec, plans, `_memory`/doc cross-refs; commit-message IDs stay historical. Gates the A2→main merge (A1 lands first).
4. **Harden the static conformance guard against the aliased-external-net form** (whole-sub-PLAN review finding). `test_data_stores_never_on_shared_edge_net` currently matches the literal string `swiftwater-shared-edge` at the *service* `networks:` level only. A legal compose idiom — a top-level `networks: {edge: {external: true, name: swiftwater-shared-edge}}` referenced by a service as `networks: [edge]` — attaches a store to the shared edge net while the guard sees only `edge` → silent PASS. The carving spec freezes the net *name* + the *attach model*, NOT the compose-file key syntax (lines 124–134: "A1 retains latitude only in *how* it ensures the network"), so the direct-key idiom is likely but not forced. At M, resolve each service's network keys through the top-level `networks:` section's `name:` (default to the key) before matching `swiftwater-shared-edge`. Defer the fix to M (can't be exercised pre-A1 — no aliased net renders today). Note carry-forward #2 (live `docker network inspect`) is robust to this case but is docker-tier / out of gating CI, so the always-on in-gate guard is the one with the hole.

## Notes for the next sub-PLAN (FWK96)

- FWK96 is the worktree SDD-flow capture doc (`docs/maintenance/worktree-parallel-development.md`) — independent, integrates at the doc; written live across the experiment.
