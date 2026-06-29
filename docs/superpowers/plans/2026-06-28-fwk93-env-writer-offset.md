# FWK93 — Durable per-worktree `.env` writer + idempotent reconcile + offset introspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the pure-ish building blocks that write/merge the worktree's durable `.env` idempotently (`STACK_INSTANCE`, `COMPOSE_PROJECT_NAME`, and — only with `--ports` — `PORT_OFFSET`) and select a free `PORT_OFFSET` from live docker introspection, with an idempotent reconcile so re-provisioning the same instance never re-picks or duplicates.

**Architecture:** Extend the existing plain (non-Jinja) template script `src/framework_cli/template/scripts/worktree.py` (FWK92 shipped its identity layer) with three groups of pure-ish functions: a line-oriented `.env` merge (`parse_env` / `merge_env_vars` / `write_env`), an offset layer (`select_port_offset` pure + `running_host_ports` with one injectable `run`), and a reconcile planner (`plan_provision`) that ties them together. The CLI/argparse/`task dev:edge` wiring is **out of scope — that is FWK94**. Tests `importlib`-load the script and exercise it in the framework venv with no project render, exactly as FWK92's `tests/test_worktree.py` already does.

**Tech Stack:** Python 3 stdlib only (`re`, `subprocess`, `pathlib`); pytest; the framework's `uv` toolchain.

## Global Constraints

- **The "durable per-worktree `.env`" IS the project `.env`** (the gitignored file copied from `.env.example`), not a separate parallel file — the `dev:*` tasks already source it, `PORT_OFFSET=0` already lives in its `FRAMEWORK:BEGIN/END` block, and A1 owns the `dotenv:` wiring. A worktree has its own working tree, so its `.env` is naturally per-worktree. The merge must therefore cope with a **realistic** `.env` (managed block, the full `*_HOST_PORT` set, dozens of commented `# APP_*=` lines), never an empty one.
- **Reconcile gate = "this instance is already provisioned", NOT "`PORT_OFFSET ≠ 0`"** (the `/clear` protocol, advisor finding #1). The default `.env` always carries `PORT_OFFSET=0`, so a value-based gate is meaningless. The real discriminator is **`STACK_INSTANCE` already recorded for this instance** (absent in a fresh `.env`). On the reconcile path, read the recorded `PORT_OFFSET` back **verbatim** — never re-introspect a live stack (introspection would see its ports bound and pick a *different* offset than the stack actually runs on).
- **Write resolved literal values, never an unexpanded `$STACK_INSTANCE`** (advisor finding #2). The spec's `COMPOSE_PROJECT_NAME=$STACK_INSTANCE` is shorthand for "the same value" — whether a `$`-ref expands depends on the consumer (shell-source vs `--env-file` vs plain KEY=VAL parse). Writing the already-resolved literal (`COMPOSE_PROJECT_NAME=acme-store-wt-blue`) is correct under every parser and defeats the misnaming-everything failure mode.
- **One mockable impurity** (advisor finding #4): the only docker touch is an injectable `run` (default `subprocess.run`) inside `running_host_ports`. Everything else (`select_port_offset`, `plan_provision`, all `.env` functions) is pure and tested with no docker.
- **Instance-string contract (FROZEN seam, FWK88):** `STACK_INSTANCE` is a single `^[a-z0-9-]+$` DNS label — already enforced by FWK92's `build_stack_instance` / `resolve_stack_instance`. FWK93 consumes that value; it does not re-derive it.
- **`src/framework_cli/template/` is template payload, not framework source** — `worktree.py` must be valid, ruff/mypy-clean Python (the generated project lints it), but the framework's own `mypy src` excludes it. Keep it **Jinja-marker-free** (`grep -cE '\{\{|\{%'` → `0`) so the `importlib` load works and it renders verbatim.
- **Seam is frozen, not renegotiable** — a wrong cut against FWK88 is a loud finding, not a quiet adaptation.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/framework_cli/template/scripts/worktree.py` | FWK92 identity layer (shipped) **+** FWK93's `.env` merge, offset, and reconcile-planner functions. | Modify (append) |
| `tests/test_worktree.py` | FWK92 identity tests (shipped) **+** FWK93's `.env` / offset / reconcile tests. | Modify (append) |

No new files. FWK93 is additive to the FWK92 module — the functions are cohesive (all serve the one `worktree.py` provisioning engine), so splitting would fragment a single small module.

---

### Task 1: `.env` line-oriented merge (`parse_env`, `merge_env_vars`, `write_env`)

**Files:**
- Modify: `src/framework_cli/template/scripts/worktree.py`
- Test: `tests/test_worktree.py`

**Interfaces:**
- Consumes: nothing new (stdlib `pathlib.Path`, already imported).
- Produces (Task 3 + FWK94 rely on these exact names/types):
  - `parse_env(text: str) -> dict[str, str]` — plain KEY=VAL reader: splits on the first `=`, strips whitespace, **skips** blank lines, comment lines (`#…`), and lines without `=`. Last occurrence wins.
  - `merge_env_vars(text: str, updates: dict[str, str]) -> str` — returns the `.env` text with each key in `updates` **updated in place** if it appears as a real (non-comment) `KEY=…` assignment, else **appended** at the end. Comment lines (`# PORT_OFFSET=…`) are never matched. Preserves a trailing newline iff the input had one (or was empty).
  - `write_env(updates: dict[str, str], path: Path = ENV_PATH) -> None` — reads `path` (empty string if absent), merges, writes back. `ENV_PATH = Path(".env")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_worktree.py`:

```python
# --- .env merge (FWK93) --------------------------------------------------

# A realistic durable .env: the managed FRAMEWORK block carries PORT_OFFSET=0 and the
# host-port set, plus a commented decoy and user content below the closing marker.
_REALISTIC_ENV = """\
# FRAMEWORK:BEGIN
APP_ENVIRONMENT=dev
# PORT_OFFSET is shifted to run a second stack alongside this one.
PORT_OFFSET=0
HTTP_HOST_PORT=8000
# APP_LOG_LEVEL=
# FRAMEWORK:END

# Your app's config below.
MY_OWN_VAR=keepme
"""


def test_parse_env_skips_comments_and_blanks():
    mod = _load()
    parsed = mod.parse_env(_REALISTIC_ENV)
    assert parsed["PORT_OFFSET"] == "0"
    assert parsed["APP_ENVIRONMENT"] == "dev"
    assert parsed["MY_OWN_VAR"] == "keepme"
    assert "APP_LOG_LEVEL" not in parsed  # commented-out line is not a value


def test_merge_updates_existing_port_offset_in_place_exactly_once():
    mod = _load()
    out = mod.merge_env_vars(_REALISTIC_ENV, {"PORT_OFFSET": "3000"})
    # Updated in place — exactly one real PORT_OFFSET assignment, value changed.
    assert "\nPORT_OFFSET=3000\n" in out
    assert [ln for ln in out.splitlines() if ln == "PORT_OFFSET=3000"] == ["PORT_OFFSET=3000"]
    assert "PORT_OFFSET=0" not in out
    # The commented decoy is untouched; user content survives.
    assert "# PORT_OFFSET is shifted" in out
    assert "MY_OWN_VAR=keepme" in out


def test_merge_appends_absent_keys():
    mod = _load()
    out = mod.merge_env_vars(
        _REALISTIC_ENV, {"STACK_INSTANCE": "acme-store-wt-blue"}
    )
    assert "STACK_INSTANCE=acme-store-wt-blue" in out
    # Appended (absent before) — original PORT_OFFSET line is untouched.
    assert "PORT_OFFSET=0" in out


def test_merge_resolved_literal_round_trips_through_a_plain_parser():
    # advisor #2: COMPOSE_PROJECT_NAME must be the RESOLVED literal, so a plain
    # KEY=VAL reader sees the instance, never the unexpanded string "$STACK_INSTANCE".
    mod = _load()
    out = mod.merge_env_vars(
        _REALISTIC_ENV,
        {
            "STACK_INSTANCE": "acme-store-wt-blue",
            "COMPOSE_PROJECT_NAME": "acme-store-wt-blue",
        },
    )
    reparsed = mod.parse_env(out)
    assert reparsed["COMPOSE_PROJECT_NAME"] == "acme-store-wt-blue"
    assert "$" not in reparsed["COMPOSE_PROJECT_NAME"]


def test_merge_empty_file_just_appends():
    mod = _load()
    out = mod.merge_env_vars("", {"STACK_INSTANCE": "x-y"})
    assert out == "STACK_INSTANCE=x-y\n"


def test_write_env_creates_then_reconciles(tmp_path):
    mod = _load()
    env = tmp_path / ".env"
    mod.write_env({"STACK_INSTANCE": "x-y"}, path=env)
    assert "STACK_INSTANCE=x-y" in env.read_text()
    # Re-write updates in place — no duplicate line.
    mod.write_env({"STACK_INSTANCE": "x-z"}, path=env)
    lines = [ln for ln in env.read_text().splitlines() if ln.startswith("STACK_INSTANCE=")]
    assert lines == ["STACK_INSTANCE=x-z"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_worktree.py -k "parse_env or merge or write_env" -v`
Expected: FAIL — `parse_env` / `merge_env_vars` / `write_env` not defined.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/framework_cli/template/scripts/worktree.py` (after `resolve_stack_instance`):

```python
# --- Durable per-worktree .env (FWK93) -----------------------------------

# The durable .env is the project's gitignored .env (per-worktree by working tree).
ENV_PATH = Path(".env")


def parse_env(text: str) -> dict[str, str]:
    """Plain KEY=VAL reader: skip blanks/comments/non-assignments; last wins."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip()
    return result


def merge_env_vars(text: str, updates: dict[str, str]) -> str:
    """Update each key in place where it is a real KEY=… assignment, else append.

    Comment lines are never matched, so a commented `# PORT_OFFSET=` decoy cannot be
    mistaken for the live assignment.
    """
    remaining = dict(updates)
    out_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in remaining:
                out_lines.append(f"{key}={remaining.pop(key)}")
                continue
        out_lines.append(line)
    out_lines.extend(f"{key}={value}" for key, value in remaining.items())
    result = "\n".join(out_lines)
    if not text or text.endswith("\n"):
        result += "\n"
    return result


def write_env(updates: dict[str, str], path: Path = ENV_PATH) -> None:
    """Idempotently merge `updates` into the durable .env at `path` (create if absent)."""
    text = path.read_text() if path.exists() else ""
    path.write_text(merge_env_vars(text, updates))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_worktree.py -k "parse_env or merge or write_env" -v`
Expected: PASS (all six).

- [ ] **Step 5: Lint + format the changed files**

Run: `uv run ruff check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py && uv run ruff format --check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py`
Expected: no errors (per [[ruff-format-check-after-inline-edits]], `format --check` catches long-line reflow `check` alone misses).

- [ ] **Step 6: Commit**

Stage `PLAN.md`/`ACTION_LOG.md` (tick FWK93 progress; append a log entry) FIRST per the commit-gate, then `git add` the two source files + `PLAN.md` + `ACTION_LOG.md` as one call, and `git commit` as a separate call (chaining trips the hook — [[commit-gate-hook-timing]]):

```
git commit -m "feat(fwk93): durable .env line-merge — parse/merge/write, in-place + literal"
```

---

### Task 2: Offset introspection + selection (`running_host_ports`, `select_port_offset`)

**Files:**
- Modify: `src/framework_cli/template/scripts/worktree.py`
- Test: `tests/test_worktree.py`

**Interfaces:**
- Consumes: nothing new (`re`, `subprocess` already imported).
- Produces (Task 3 + FWK94 rely on these):
  - `BASE_HOST_PORTS: tuple[int, ...]` — the host-port defaults mirrored from `scripts/compose.sh` (the all-battery superset; over-reserving is conservative and safe).
  - `OFFSET_STEP: int` — `1000` (the FWK31 step).
  - `running_host_ports(run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> set[int]` — the **one** mockable docker touch: runs `docker ps --format "{{.Ports}}"`, parses every `:<port>->` host port, returns the set. Injectable `run` for tests.
  - `select_port_offset(occupied: set[int], *, base_ports: tuple[int, ...] = BASE_HOST_PORTS, step: int = OFFSET_STEP) -> int` — pure: the lowest non-negative multiple of `step` whose shifted port window `{p + offset for p in base_ports}` is disjoint from `occupied` and stays ≤ 65535; raises `RuntimeError` if the whole pool is occupied.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_worktree.py`:

```python
# --- offset selection (FWK93) --------------------------------------------


def test_select_offset_zero_when_nothing_occupied():
    mod = _load()
    assert mod.select_port_offset(set()) == 0


def test_select_offset_skips_window_with_any_collision():
    mod = _load()
    # The main stack is up on offset 0 (its app port 8000 is bound) → 0 is rejected,
    # next free window is offset 1000.
    assert mod.select_port_offset({8000}) == 1000


def test_select_offset_handles_cross_window_self_collision():
    # advisor #4 / FWK88 note: grafana base 3000 shifted by 5000 == app base 8000.
    # If a stack at offset 0 binds app:8000, an offset-5000 window's grafana would
    # collide — the port-set disjointness check rejects it with no special-casing.
    mod = _load()
    chosen = mod.select_port_offset({8000})
    shifted = {p + chosen for p in mod.BASE_HOST_PORTS}
    assert 8000 not in shifted


def test_select_offset_raises_when_pool_exhausted():
    mod = _load()
    # Occupy every candidate window's app port so no offset is free.
    occupied = {8000 + off for off in range(0, 60000, mod.OFFSET_STEP)}
    with pytest.raises(RuntimeError):
        mod.select_port_offset(occupied)


def test_running_host_ports_parses_docker_ps(monkeypatch):
    import subprocess as _sp

    mod = _load()

    def fake_run(cmd, **kwargs):
        assert cmd[:2] == ["docker", "ps"]
        out = (
            "0.0.0.0:8000->8000/tcp, :::8000->8000/tcp\n"
            "0.0.0.0:5432->5432/tcp\n"
            "\n"  # a container with no published ports
        )
        return _sp.CompletedProcess(cmd, 0, stdout=out, stderr="")

    assert mod.running_host_ports(run=fake_run) == {8000, 5432}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_worktree.py -k "offset or running_host_ports" -v`
Expected: FAIL — `select_port_offset` / `running_host_ports` / `BASE_HOST_PORTS` not defined.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/framework_cli/template/scripts/worktree.py`. Add `from collections.abc import Callable` to the top import block.

```python
# --- PORT_OFFSET selection via live introspection (FWK93) -----------------

# Host-port defaults mirrored from scripts/compose.sh (FWK31). The all-battery
# superset: over-reserving a port a disabled battery wouldn't publish is safe
# (it only makes selection more conservative, never less).
BASE_HOST_PORTS: tuple[int, ...] = (
    80,  # TRAEFIK_HTTP
    443,  # TRAEFIK_HTTPS
    3000,  # GRAFANA
    3100,  # LOKI
    3200,  # TEMPO
    5173,  # FRONTEND
    5432,  # POSTGRES
    6379,  # REDIS
    8000,  # HTTP (app)
    9090,  # PROMETHEUS
    9093,  # ALERTMANAGER
    9121,  # REDIS_EXPORTER
    9187,  # POSTGRES_EXPORTER
    9216,  # MONGODB_EXPORTER
    9808,  # CELERY_EXPORTER
    27017,  # MONGO
)

OFFSET_STEP = 1000

_MAX_HOST_PORT = 65535
_PUBLISHED_PORT = re.compile(r":(\d+)->")


def running_host_ports(
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> set[int]:
    """Return the set of host ports currently published by running containers.

    The single docker touch in this module — `run` is injectable so unit tests
    can feed canned `docker ps` output with no daemon.
    """
    out = run(
        ["docker", "ps", "--format", "{{.Ports}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {int(port) for port in _PUBLISHED_PORT.findall(out.stdout)}


def select_port_offset(
    occupied: set[int],
    *,
    base_ports: tuple[int, ...] = BASE_HOST_PORTS,
    step: int = OFFSET_STEP,
) -> int:
    """Lowest multiple of `step` whose shifted port window avoids `occupied`.

    The port-set disjointness check subsumes the offset-diff self-collision (a
    higher window's low port landing on a lower window's high port) with no
    special-casing. Raises RuntimeError when every in-range window is occupied.
    """
    highest = max(base_ports)
    offset = 0
    while highest + offset <= _MAX_HOST_PORT:
        window = {port + offset for port in base_ports}
        if window.isdisjoint(occupied):
            return offset
        offset += step
    raise RuntimeError(
        "no free PORT_OFFSET: every candidate host-port window is occupied"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_worktree.py -k "offset or running_host_ports" -v`
Expected: PASS (all five).

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py && uv run ruff format --check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py`
Expected: no errors.

- [ ] **Step 6: Commit**

Stage `PLAN.md`/`ACTION_LOG.md` first, then `git add` the sources + plan/log as one call, `git commit` separate:

```
git commit -m "feat(fwk93): PORT_OFFSET selection — docker-ps introspection + pure window picker"
```

---

### Task 3: Reconcile planner (`plan_provision`) — ties identity + `.env` + offset together

**Files:**
- Modify: `src/framework_cli/template/scripts/worktree.py`
- Test: `tests/test_worktree.py`

**Interfaces:**
- Consumes: `parse_env` (Task 1), `select_port_offset` (Task 2).
- Produces (FWK94's `main()` calls this, then passes the result to `write_env`):
  - `plan_provision(env_text: str, instance: str, *, with_ports: bool, occupied: set[int] | None = None) -> dict[str, str]` — returns the key→value updates to merge into the durable `.env`:
    - always `STACK_INSTANCE` and `COMPOSE_PROJECT_NAME`, both set to the **resolved** `instance` literal.
    - `PORT_OFFSET` **only** when `with_ports`. On the reconcile path (the `.env` already records `STACK_INSTANCE == instance`) the recorded `PORT_OFFSET` is reused **verbatim** (`/clear` protocol — no re-introspection). On a fresh provision it is `str(select_port_offset(occupied or set()))`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_worktree.py`:

```python
# --- provision planner / reconcile (FWK93) -------------------------------


def test_plan_provision_sets_resolved_literals_no_ports():
    mod = _load()
    updates = mod.plan_provision("", "acme-store-wt-blue", with_ports=False)
    assert updates == {
        "STACK_INSTANCE": "acme-store-wt-blue",
        "COMPOSE_PROJECT_NAME": "acme-store-wt-blue",
    }
    # No --ports → PORT_OFFSET is left to the .env default, not written.
    assert "PORT_OFFSET" not in updates


def test_plan_provision_fresh_selects_offset():
    mod = _load()
    # Fresh .env (no STACK_INSTANCE recorded) with the main stack up on offset 0.
    updates = mod.plan_provision(
        "PORT_OFFSET=0\n", "acme-store-wt-blue", with_ports=True, occupied={8000}
    )
    assert updates["STACK_INSTANCE"] == "acme-store-wt-blue"
    assert updates["PORT_OFFSET"] == "1000"


def test_plan_provision_reconciles_recorded_offset_verbatim():
    # advisor #1: the .env already records THIS instance at offset 3000. A re-run
    # (e.g. after /clear, stack still up) must reuse 3000 — NOT re-introspect and
    # pick a different window — even though `occupied` here would otherwise select 1000.
    mod = _load()
    env_text = "STACK_INSTANCE=acme-store-wt-blue\nPORT_OFFSET=3000\n"
    updates = mod.plan_provision(
        env_text, "acme-store-wt-blue", with_ports=True, occupied={8000}
    )
    assert updates["PORT_OFFSET"] == "3000"


def test_plan_provision_recorded_other_instance_is_not_reconciled():
    # A DIFFERENT instance recorded → this is a fresh provision for `instance`, so
    # the recorded offset is not reused; a free offset is selected.
    mod = _load()
    env_text = "STACK_INSTANCE=other-stack\nPORT_OFFSET=3000\n"
    updates = mod.plan_provision(
        env_text, "acme-store-wt-blue", with_ports=True, occupied=set()
    )
    assert updates["PORT_OFFSET"] == "0"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_worktree.py -k "plan_provision" -v`
Expected: FAIL — `plan_provision` not defined.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/framework_cli/template/scripts/worktree.py`:

```python
# --- Provision planner: identity + .env + offset reconcile (FWK93) --------


def plan_provision(
    env_text: str,
    instance: str,
    *,
    with_ports: bool,
    occupied: set[int] | None = None,
) -> dict[str, str]:
    """Compute the durable-.env updates for provisioning `instance`.

    STACK_INSTANCE / COMPOSE_PROJECT_NAME are always the resolved `instance` literal.
    PORT_OFFSET is written only with `with_ports`: reused verbatim when the .env
    already records this instance (the /clear reconcile — never re-introspect a live
    stack), else freshly selected from `occupied`.
    """
    updates = {"STACK_INSTANCE": instance, "COMPOSE_PROJECT_NAME": instance}
    if with_ports:
        recorded = parse_env(env_text)
        if recorded.get("STACK_INSTANCE") == instance and "PORT_OFFSET" in recorded:
            updates["PORT_OFFSET"] = recorded["PORT_OFFSET"]
        else:
            updates["PORT_OFFSET"] = str(select_port_offset(occupied or set()))
    return updates
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_worktree.py -k "plan_provision" -v`
Expected: PASS (all four).

- [ ] **Step 5: Full-file test + lint + format**

Run: `uv run pytest tests/test_worktree.py -v && uv run ruff check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py && uv run ruff format --check tests/test_worktree.py src/framework_cli/template/scripts/worktree.py`
Expected: PASS (FWK92 + all FWK93 tests); no lint/format errors.

- [ ] **Step 6: Commit**

Stage `PLAN.md`/`ACTION_LOG.md` first (tick FWK93 done; log entry), then `git add` sources + plan/log as one call, `git commit` separate:

```
git commit -m "feat(fwk93): provision planner — idempotent /clear reconcile of recorded offset"
```

---

## Verification (whole sub-PLAN)

- [ ] `uv run pytest tests/test_worktree.py -v` — all green (FWK92 + FWK93).
- [ ] `uv run ruff check src/framework_cli/template/scripts/worktree.py tests/test_worktree.py` — clean.
- [ ] `uv run ruff format --check src/framework_cli/template/scripts/worktree.py tests/test_worktree.py` — clean.
- [ ] `grep -cE '\{\{|\{%' src/framework_cli/template/scripts/worktree.py` → exactly `1` — the single expected occurrence is the `docker ps --format "{{.Ports}}"` Go-template idiom in Task 2's `running_host_ports`. This is **safe**: `worktree.py` is a non-`.jinja` file and copier's `_templates_suffix: .jinja` copies it verbatim (precedent: `test_copier_runner.py:843` locks `${{ github.repository }}` and `:1418` `{{ $value }}` preserved verbatim in other non-jinja files). The `importlib` load is unaffected (it's a literal Python string). No `{%…%}` block markers.
- [ ] Reconcile is idempotent: `test_plan_provision_reconciles_recorded_offset_verbatim` proves a re-run keeps the recorded offset; `test_write_env_creates_then_reconciles` proves no duplicate line.
- [ ] `COMPOSE_PROJECT_NAME` is written as the resolved literal — `test_merge_resolved_literal_round_trips_through_a_plain_parser`.

## Execution

Per CLAUDE.md's review-model policy ([[subagent-review-model-pattern]]), restated here so the subagent-driven skill's generic "least powerful model" guidance does not collapse the reviewers:
- **Implementers → Sonnet** (`claude-sonnet-4-6`); these are small pure-Python tasks.
- **Spec-compliance review → Sonnet.**
- **Code-quality review → Opus** (`claude-opus-4-8`); a passing test is not a code-quality review.
- **Final whole-sub-PLAN review → Opus.**

Pure logic + dry-run only — **no stack is ever brought up** in FWK93 (the docker touch is mocked), so no teardown is owed before `/clear` into FWK94.

## Notes for the next sub-PLAN (FWK94)

- FWK94 wires the CLI: `argparse` (`up` / `down`, `--ports`, `--obs`, `--instance` override), `main()` calling `resolve_stack_instance` → `running_host_ports` → `plan_provision` → `write_env`, then exporting the vars and exec'ing `task dev:edge`. **The stub-vs-wait call is made in FWK94** (real `task dev:edge` from A1 if landed, else a fenced stub deleted at Milestone M).
- The `--instance` override threads a user string in ahead of `current_branch()` — `build_stack_instance` already accepts an explicit instance, and it is the escape hatch for a branch that legitimately sanitizes into the reserved `t-*` namespace.
- Known edge deferred to FWK94: re-running a previously-`--ports`-less instance now **with** `--ports` reconciles to the recorded `PORT_OFFSET=0` (the default) rather than selecting fresh; FWK94's CLI can warn or force re-selection. Not a concern for FWK93's building blocks.
