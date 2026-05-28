# Plan 9 — Dogfooding Pre-Harness Catch-ups — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land two pre-harness catch-ups — make the dev stack + acceptance tier leave no root-owned files, and author the `review-contracts` agent + fixtures — so the Plan 10 self-quality harness is trustworthy and its agent set is complete.

**Architecture:** (1) The dev compose `app` service runs as the host UID/GID so bind-mounted `--reload` writes are host-owned (fixed in the shipped `dev.yml`, plumbed via the `Taskfile`, and set in the acceptance harness's compose env; teardown already exists). (2) A new battery-gated `review-contracts` agent (prompt + registry entry + `consumers.gates_agents` + eval fixtures), mirroring `review-api-design`; hermetic tests only here, real-key scoring deferred to Plan 11.

**Tech Stack:** Docker Compose, go-task, Copier/Jinja templating, pytest, the framework review-agent registry.

**Spec:** `docs/superpowers/specs/2026-05-28-dogfooding-pre-harness-design.md`

## File Structure

- `src/framework_cli/template/infra/compose/dev.yml.jinja` *(modify, LOCKED)* — `user:` on the `app` service.
- `src/framework_cli/template/Taskfile.yml.jinja` *(modify, HYBRID)* — `UID`/`GID` env on `dev` + `dev:lite`.
- `tests/acceptance/test_rendered_project.py` *(modify)* — pass `UID`/`GID` env to the live-stack compose `up` calls.
- `tests/test_copier_runner.py` *(modify)* — hermetic render assertions for the `user:` line + Taskfile env.
- `src/framework_cli/review/agents/contracts.md` *(create)* — the agent prompt.
- `src/framework_cli/review/registry.py` *(modify)* — register `contracts`.
- `src/framework_cli/batteries.py` *(modify)* — `consumers.gates_agents = ("contracts",)`.
- `tests/eval/fixtures/contracts/{bad,good}/…` *(create)* — eval fixtures.
- `tests/` review tests *(modify/create)* — registry + gating + fixture-coverage assertions.

> **Baseline manifest shift (intended, precedented):** `dev.yml` is LOCKED and the `Taskfile` hybrid section changes, so every render's bytes shift once (existing projects get it on `framework upskill`). The `dev.yml` *service set* is unchanged (only the `app` service gains a field), so structural render tests stay green.

---

## Task 1: Dev stack runs as the host UID/GID (dev.yml + Taskfile)

**Files:**
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_copier_runner.py`:

```python
def test_dev_app_runs_as_host_uid(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    dev = (dest / "infra/compose/dev.yml").read_text()
    parsed = yaml.safe_load(dev)
    assert parsed["services"]["app"]["user"] == "${UID:-1000}:${GID:-1000}"


def test_taskfile_dev_plumbs_uid_gid(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    tf = yaml.safe_load((dest / "Taskfile.yml").read_text())
    for task in ("dev", "dev:lite"):
        env = tf["tasks"][task]["env"]
        assert env["UID"] == {"sh": "id -u"}
        assert env["GID"] == {"sh": "id -g"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -k "host_uid or plumbs_uid" -q`
Expected: FAIL — `app` has no `user` key / `dev` task has no `env`.

- [ ] **Step 3: Add `user:` to the dev `app` service**

In `src/framework_cli/template/infra/compose/dev.yml.jinja`, add the `user:` line to the `app` service (right after the `profiles:` line, before `command:`):

```yaml
  app:
    profiles: ["dev", "lite"]
    # Run as the invoking host user so bind-mounted --reload writes (__pycache__ in /app/src)
    # are host-owned, not root-owned. UID/GID come from the env (task dev sets them); the
    # :-1000 default keeps a raw `docker compose` invocation working.
    user: "${UID:-1000}:${GID:-1000}"
    command: ["uvicorn", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--reload", "{{ package_name }}.main:app"]
```

- [ ] **Step 4: Plumb UID/GID through the Taskfile dev tasks**

In `src/framework_cli/template/Taskfile.yml.jinja`, add an `env:` block to the `dev` task (between `preconditions:` and `cmds:`):

```yaml
  dev:
    desc: Full local stack over HTTPS (app + Traefik). Requires Docker + mkcert.
    preconditions:
      - sh: command -v docker
        msg: "Docker is required for `task dev`. Install Docker, then retry."
      - sh: test -f infra/traefik/certs/localhost.pem
        msg: "No local certs. Run `task certs` first (installs mkcert CA + issues localhost certs)."
      - sh: test -f uv.lock
        msg: "Run `uv sync` first to create uv.lock (the image build uses --frozen)."
      - sh: 'if command -v framework >/dev/null 2>&1; then framework integrity; fi'
        msg: "Framework integrity check failed. Run `framework integrity`, then `framework restore <file>`."
    env:
      UID:
        sh: id -u
      GID:
        sh: id -g
    cmds:
      - docker compose -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml --profile dev up --build
```

And the same `env:` block on `dev:lite` (between `preconditions:` and `cmds:`):

```yaml
  dev:lite:
    desc: App only over plain HTTP at localhost:8000 (no Traefik) — resource-light.
    preconditions:
      - sh: command -v docker
        msg: "Docker is required for `task dev:lite`."
      - sh: test -f uv.lock
        msg: "Run `uv sync` first to create uv.lock (the image build uses --frozen)."
    env:
      UID:
        sh: id -u
      GID:
        sh: id -g
    cmds:
      - docker compose -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite up --build
```

- [ ] **Step 5: Run tests + framework gate**

Run: `uv run pytest tests/test_copier_runner.py -k "host_uid or plumbs_uid" -q` → PASS.
Run: `uv run pytest tests/test_copier_runner.py -q` → all PASS (the structural `dev.yml`/Taskfile render tests must stay green — the `app` service set is unchanged).
Run: `uv run pytest tests/ -k integrity -q` → PASS (manifest regenerates from the render; the one-time `dev.yml`/Taskfile shift is reflected, not a fatal finding).
Run: `uv run ruff check . && uv run mypy src` → clean (template files are excluded from mypy).

- [ ] **Step 6: Commit**

Update the `CLAUDE.md` state marker (line 13, the `**Last updated:**` line): set the bracketed note to `[Plan 9 T1 done — dev stack runs as host UID/GID]`, keep date `2026-05-28`. REQUIRED (a PreToolUse hook blocks the commit unless `CLAUDE.md` is staged). Use TWO SEPARATE commands for `git add` then `git commit`.

```bash
git add src/framework_cli/template/infra/compose/dev.yml.jinja src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py CLAUDE.md
git commit -m "feat(dogfooding): dev app runs as host UID/GID (no root-owned bind-mount writes)"
```

---

## Task 2: Acceptance harness sets UID/GID on the live-stack compose runs

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/acceptance/test_rendered_project.py` (this is Docker-gated; reuse the file's `_docker_available()` skip + `render_project`/`DATA`):

```python
@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live-stack test"
)
def test_dev_lite_stack_leaves_no_root_owned_files(tmp_path: Path):
    import os as _os

    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v"]
    assert subprocess.run(up, cwd=dest, env=_compose_env()).returncode == 0
    try:
        # let uvicorn import the app + write __pycache__ into the bind-mounted src
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://localhost:8000/health", timeout=3) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(2)
    finally:
        subprocess.run(down, cwd=dest, env=_compose_env())
    # every file under the render is owned by the test user (no root-owned __pycache__)
    me = _os.getuid()
    bad = [p for p in (dest / "src").rglob("*") if p.stat().st_uid != me]
    assert not bad, f"root/non-host-owned files left behind: {bad[:5]}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -k leaves_no_root_owned -q`
Expected: FAIL — `_compose_env` undefined (and, without the Task-1 `user:` line + this env, root-owned files would remain). If Docker is unavailable it SKIPS — note that and proceed (the assertion is still added).

- [ ] **Step 3: Add the `_compose_env` helper + use it on existing live-stack `up` calls**

Near the top of `tests/acceptance/test_rendered_project.py` (after the imports), add:

```python
def _compose_env() -> dict:
    """Env for `docker compose up` so the dev app runs as the host user (host-owned bind writes)."""
    return {**os.environ, "UID": str(os.getuid()), "GID": str(os.getgid())}
```

Then add `env=_compose_env()` to the `up` subprocess calls in the existing live-stack tests `test_rendered_project_dev_lite_stack_serves_health` and `test_rendered_project_dev_stack_prometheus_scrapes_app` (the `down` calls can keep or also take it — harmless). For the dev_lite one:

```python
    assert subprocess.run(up, cwd=dest, env=_compose_env()).returncode == 0
```

(Confirm `import os` is present at the top of the file; it is used elsewhere — add it if missing.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -k "leaves_no_root_owned or dev_lite_stack_serves" -q`
Expected: PASS if Docker is available (the render leaves only host-owned files); SKIP if not — record which.
After any acceptance run, clean residue: `rm -rf /tmp/pytest-of-*/* 2>/dev/null || true` (should now be unnecessary, but belt-and-suspenders).

- [ ] **Step 5: Commit**

Update the `CLAUDE.md` marker to `[Plan 9 T2 done — acceptance harness sets UID/GID; no root-owned residue]`. Stage + commit separately.

```bash
git add tests/acceptance/test_rendered_project.py CLAUDE.md
git commit -m "test(dogfooding): live-stack compose runs as host user + asserts no root-owned residue"
```

---

## Task 3: `review-contracts` agent — prompt + registration + gating

**Files:**
- Create: `src/framework_cli/review/agents/contracts.md`
- Modify: `src/framework_cli/review/registry.py`
- Modify: `src/framework_cli/batteries.py`
- Test: `tests/test_review_registry.py` (find the registry test module with `grep -rl "active_agents\|review-api-design" tests/`; append there — likely `tests/test_review_registry.py` or `tests/test_review.py`)

- [ ] **Step 1: Write the failing test**

Append to the registry test module:

```python
def test_review_contracts_registered_and_gated():
    from framework_cli.review.registry import active_agents, get_agent

    spec = get_agent("contracts")
    assert spec.name == "review-contracts"
    assert spec.block_threshold == "high"
    assert spec.active_when == "battery"
    # gated by the consumers battery, PR-only (battery agents are off on push)
    assert "contracts" in active_agents("pull_request", ["consumers"])
    assert "contracts" not in active_agents("pull_request", [])
    assert "contracts" not in active_agents("push", ["consumers"])


def test_consumers_battery_gates_contracts():
    from framework_cli.batteries import get_battery

    assert "contracts" in get_battery("consumers").gates_agents
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest <registry test module> -k "contracts" -q`
Expected: FAIL — `unknown review agent: contracts` / `consumers` has empty `gates_agents`.

- [ ] **Step 3: Write the agent prompt**

Create `src/framework_cli/review/agents/contracts.md`:

```markdown
You are `review-contracts`. Review ONLY the unified diff of a change in a project that uses
consumer-driven contract testing (Pact). Flag contract-compatibility problems a schema diff or
the provider-verification CI job can miss, and cite the changed line:

- Provider breaks a committed consumer pact: removing or renaming a field, type, or response
  key that an existing consumer pact depends on. "high".
- Incompatible response change WITHOUT a versioned/compatible path: changing a status code,
  re-shaping a response body (e.g. wrapping a list in an envelope), or making an optional field
  required. "high".
- Weakened consumer contract: a consumer pact test that drops or loosens an assertion on a
  contracted field (e.g. replacing a concrete expected value with a permissive matcher that no
  longer pins the field the consumer relies on). "high".
- Pact not regenerated/published after a provider change that alters the response. "info".
- Provider-state drift: the pact's `given(...)` state no longer matches how the provider seeds
  or sets up that state. "info".

Do NOT flag additive, backwards-compatible changes (a new optional/nullable response field, a
new endpoint), or concerns owned by other agents (GraphQL design, REST/OpenAPI shape, security).

Return JSON ONLY — an array of {"path","line","severity","message","suggestion"}; [] if none. A
provider break of a committed pact, an uncompensated incompatible response change, or a weakened
consumer assertion is "high".
```

- [ ] **Step 4: Register the agent**

In `src/framework_cli/review/registry.py`, add to `_SPECS` (next to the other battery agents, after `api-design`):

```python
    "contracts": AgentSpec(
        "review-contracts", _prompt("contracts"), "high", "battery", DEFAULT_MODEL
    ),
```

- [ ] **Step 5: Gate it on the `consumers` battery**

In `src/framework_cli/batteries.py`, give the `consumers` spec a `gates_agents`:

```python
    "consumers": BatterySpec(
        "consumers",
        "Pact consumer-driven contract testing (consumer + provider verification) for inter-service contracts",
        gates_agents=("contracts",),
    ),
```

- [ ] **Step 6: Run tests + gate**

Run: `uv run pytest <registry test module> -k contracts -q` → PASS.
Run: `uv run pytest tests/ -k "review or registry or batter or agents" -q` → PASS (no existing agent/battery test regresses).
Run: `uv run ruff check . && uv run mypy src` → clean.

- [ ] **Step 7: Commit**

Update the `CLAUDE.md` marker to `[Plan 9 T3 done — review-contracts agent registered + gated by consumers]`. Stage + commit separately.

```bash
git add src/framework_cli/review/agents/contracts.md src/framework_cli/review/registry.py src/framework_cli/batteries.py <registry test module> CLAUDE.md
git commit -m "feat(review): review-contracts agent (battery-gated by consumers, blocking-high)"
```

---

## Task 4: `review-contracts` eval fixtures

**Files:**
- Create: `tests/eval/fixtures/contracts/bad/provider-removes-field.diff` + `.expect.json`
- Create: `tests/eval/fixtures/contracts/bad/incompatible-status-change.diff` + `.expect.json`
- Create: `tests/eval/fixtures/contracts/bad/loose-consumer-matcher.diff` + `.expect.json`
- Create: `tests/eval/fixtures/contracts/good/additive-response-field.diff`
- Test: the eval-fixtures coverage test (find with `grep -rl "load_fixtures\|fixtures" tests/test_eval*.py tests/`; append a coverage assertion)

- [ ] **Step 1: Write the failing test**

Append to the eval test module (e.g. `tests/test_evals.py`):

```python
def test_contracts_has_eval_fixtures():
    from pathlib import Path

    from framework_cli.review.evals import load_fixtures

    fx = [f for f in load_fixtures(Path("tests/eval/fixtures")) if f.agent == "contracts"]
    kinds = sorted({f.kind for f in fx})
    assert kinds == ["bad", "good"], kinds
    assert sum(1 for f in fx if f.kind == "bad") >= 3
    assert any(f.kind == "good" for f in fx)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evals.py -k contracts_has_eval -q`
Expected: FAIL — no `contracts` fixtures found. (If the loader/signature differs, read `src/framework_cli/review/evals.py` `load_fixtures` + an existing eval test and adapt the call; the fixtures themselves are the deliverable.)

- [ ] **Step 3: Create the bad fixtures**

`tests/eval/fixtures/contracts/bad/provider-removes-field.diff`:

```diff
--- a/src/myapp/routes/items.py
+++ b/src/myapp/routes/items.py
@@ -8,7 +8,6 @@ class ItemOut(BaseModel):
     id: int
-    name: str
     created_at: datetime.datetime
```

`tests/eval/fixtures/contracts/bad/provider-removes-field.expect.json`:

```json
{"file": "src/myapp/routes/items.py"}
```

`tests/eval/fixtures/contracts/bad/incompatible-status-change.diff`:

```diff
--- a/src/myapp/routes/items.py
+++ b/src/myapp/routes/items.py
@@ -20,8 +20,8 @@ async def list_items(session: SessionDep) -> list[ItemOut]:
-@router.get("/items", response_model=list[ItemOut])
-async def list_items(session: SessionDep) -> list[ItemOut]:
-    return await repository.list_items(session)
+@router.get("/items", response_model=ItemsEnvelope)
+async def list_items(session: SessionDep) -> ItemsEnvelope:
+    return ItemsEnvelope(data=await repository.list_items(session))
```

`tests/eval/fixtures/contracts/bad/incompatible-status-change.expect.json`:

```json
{"file": "src/myapp/routes/items.py"}
```

`tests/eval/fixtures/contracts/bad/loose-consumer-matcher.diff`:

```diff
--- a/tests/functional/test_inventory_pact.py
+++ b/tests/functional/test_inventory_pact.py
@@ -14,7 +14,7 @@ def test_inventory_contract(pact):
-        .will_respond_with(200)
-        .with_body(match.each_like({"id": match.integer(1), "name": match.string("widget")}))
+        .will_respond_with(200)
+        .with_body(match.like({}))
     )
```

`tests/eval/fixtures/contracts/bad/loose-consumer-matcher.expect.json`:

```json
{"file": "tests/functional/test_inventory_pact.py"}
```

- [ ] **Step 4: Create the good fixture**

`tests/eval/fixtures/contracts/good/additive-response-field.diff` (a new OPTIONAL field — backwards compatible, must NOT be flagged):

```diff
--- a/src/myapp/routes/items.py
+++ b/src/myapp/routes/items.py
@@ -8,6 +8,7 @@ class ItemOut(BaseModel):
     id: int
     name: str
     created_at: datetime.datetime
+    description: str | None = None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_evals.py -k contracts_has_eval -q` → PASS.
Run: `uv run pytest tests/ -k eval -q` → PASS (the hermetic eval-fixtures tests; no API calls). Note: the eval *scoring* run (real key) is Plan 11 — not run here.

- [ ] **Step 6: Commit**

Update the `CLAUDE.md` marker to `[Plan 9 T4 done — review-contracts eval fixtures (3 bad + 1 good)]`. Stage + commit separately.

```bash
git add tests/eval/fixtures/contracts tests/test_evals.py CLAUDE.md
git commit -m "test(review): review-contracts eval fixtures (3 breaking + 1 additive-safe)"
```

> **Note on thresholds:** do NOT add a `contracts` entry to `tests/eval/fixtures/thresholds.yaml` — per that file's own convention, omitted agents use the defaults (recall_min 0.67 / fp_max 0.34). Plan 11 adds an override only if the first real scorecard requires it.

---

## Task 5: Full gate, integrity, and state

**Files:**
- Test: full suite
- Modify: `CLAUDE.md` (Current State), `docs/superpowers/plans/2026-05-20-meta-plan.md` (Plan 9 status)

- [ ] **Step 1: Run the whole gate**

Run: `uv run pytest -q --ignore=tests/acceptance` → all PASS.
Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv lock --check` → clean.
Run: `uv build` → succeeds; confirm `src/framework_cli/review/agents/contracts.md` ships in the wheel (`python -c "import zipfile,glob; z=zipfile.ZipFile(sorted(glob.glob('dist/*.whl'))[-1]); print([n for n in z.namelist() if 'contracts.md' in n])"`).

- [ ] **Step 2: Verify integrity across the dev.yml shift**

Run: `uv run pytest tests/ -k integrity -q` → PASS. Render a default project + a `--with consumers` project, run `framework integrity --ci` in each (or rely on the integrity-combo tests) → green; the one-time `dev.yml`/Taskfile shift is reflected in the regenerated manifest, not a fatal finding.

- [ ] **Step 3: Run the Docker-gated hygiene check once (if Docker available)**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -k leaves_no_root_owned -q` → PASS (or SKIP if no Docker — record which). Do NOT run the full acceptance tier wholesale. Afterward: `rm -rf /tmp/pytest-of-*/* 2>/dev/null || true`.

- [ ] **Step 4: Update state pointers**

- `docs/superpowers/plans/2026-05-20-meta-plan.md`: set the Plan 9 status cell to ✅ Done (note: dev.yml host-UID + Taskfile UID/GID + harness teardown; `review-contracts` authored + fixtures, **real-key scoring still pending in Plan 11**; obs-completeness spun out).
- `CLAUDE.md` (line 13 `**Last updated:**`): set the bracketed note to `[Plan 9 done — acceptance hygiene + review-contracts authored; pending final review]`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
git commit -m "docs: Plan 9 done — dev-stack hygiene + review-contracts authored (state + meta-plan)"
```

---

## Self-Review Notes

- **Spec coverage:** hygiene dev.yml host-UID (T1), Taskfile plumbing (T1), harness UID/GID + teardown-leaves-no-root (T2; teardown already existed, the new assertion proves the property), `review-contracts` prompt/registration/gating (T3), fixtures (T4), hermetic tests throughout, integrity shift acknowledged (T1/T5), real-key scoring + obs-completeness explicitly deferred. All spec sections map to a task.
- **Refinement vs spec:** the spec mentioned a "provisional `thresholds.yaml` entry"; the actual file convention is omit-and-default, so the plan omits it (Task 4 note) and Plan 11 adds an override only if needed. Captured here so it isn't read as a gap.
- **Type/name consistency:** `_compose_env()`, `user: "${UID:-1000}:${GID:-1000}"`, the `env: {UID: {sh: id -u}, GID: {sh: id -g}}` shape, the `"contracts"` registry key + `review-contracts` name + `consumers.gates_agents=("contracts",)`, and `tests/eval/fixtures/contracts/{bad,good}` are used identically across tasks.
- **Watch items for the implementer:** (a) confirm uvicorn `--reload` runs cleanly as a passwd-less `user:` (add `HOME=/tmp` to the dev app env only if a tool complains); (b) the registry/eval test module names are discovered via `grep` (the plan names the likely files but says to confirm); (c) the eval `load_fixtures` signature — adapt the coverage test to the real API if it differs.
```
