# 8h — `consumers` Battery (Pact contract testing) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `consumers` battery — the full Pact (consumer-driven contract) loop with `pact-python` v3: the generated app as a consumer of a downstream service and as a provider of its own `/items` API.

**Architecture:** A gated outbound client (`clients/inventory.py`) + a fast consumer Pact test (mock server → writes a pact) demonstrate the consumer side. A committed example consumer pact + a provider-verification test (Pact `Verifier` replays it against the app started over a testcontainers Postgres) demonstrate the provider side. Pacts are local files in `pacts/`; a real Pact Broker is an opt-in env-var escape hatch (no broker service). All gated `{% if "consumers" in batteries %}`, byte-identical without the battery.

**Tech Stack:** Copier/Jinja, `pact-python>=3.4` (Rust-core v3; test dep), httpx, FastAPI/uvicorn, testcontainers Postgres, pytest.

**Spec:** `docs/superpowers/specs/2026-05-27-consumers-battery-design.md`

**Verified `pact-python` v3 API (from the 3.x docs — confirm against the installed 3.4.0 in Task 1):**
- Consumer: `from pact import Pact, match`; `pact = Pact("consumer", "provider").with_specification("V4")`; `pact.upon_receiving("desc").given("state").with_request("GET", "/path").will_respond_with(200).with_body({"k": match.int(1)})`; `with pact.serve() as srv: <run client against str(srv.url)>`; `pact.write_file(Path("pacts"))`.
- Provider: `from pact import Verifier`; `Verifier("app").add_source("pacts/").add_transport(url="http://127.0.0.1:PORT").verify()`; provider states via `.state_handler({"state name": callable}, teardown=True)` or a URL.

**Conventions (read before starting):**
- `src/framework_cli/template/` is **template payload** (don't lint/type-check as framework code; the framework mypy/ruff exclude it). The `pact-python`/httpx toolchain is template-only — **do NOT add it to the framework's `pyproject.toml`/`uv.lock`**; never `uv add`/`uv sync` in the framework root.
- Framework fast gate (green before each commit): `uv run --frozen pytest -q --ignore=tests/acceptance && uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen mypy src`. Run `ruff format --check .` as its OWN command (a pipe to `tail` masks its exit code).
- **⚠ /tmp HAZARD:** the Docker `tests/acceptance` tier renders into `/tmp` as root + can fill it (wedge). Run AT MOST a named acceptance test, then `rm -rf /tmp/pytest-of-chris/* 2>/dev/null` + `df -h /tmp`. Never the full acceptance tier.
- **COMMIT-GATE HOOK:** `git commit` is blocked unless `CLAUDE.md` is staged. The hook greps the **entire tool-input JSON incl. your Bash `description`** — NEVER put the literal word c-o-m-m-i-t in a description or any git command except the real `git commit`. SEPARATE `git add` then `git commit` calls. Each task: edit the `CLAUDE.md` `- **Last updated:**` marker (e.g. `[8h Tn]`) and stage it.
- `render_project(dest, {**DATA, "batteries":[...]})`, `DATA={"project_name":"Demo","project_slug":"demo","package_name":"demo","python_version":"3.12"}`.
- **The generated project's test tiers** are `tests/unit`, `tests/functional`, `tests/e2e` (pyproject `testpaths`); `coverage.sh` runs them. So: the **consumer** pact test goes in `tests/functional/` (fast, mocked → collected + gated). The **provider** verification test goes in `tests/contract/` (NOT in `testpaths` → not collected by `coverage.sh`; run explicitly by the gated CI job, since it needs a running app + DB).

---

## File Structure

**Framework CLI:** `src/framework_cli/batteries.py` (register `consumers`).

**Template payload (`src/framework_cli/template/`):**
- Create: `src/{{package_name}}/{% if "consumers" in batteries %}clients{% endif %}/{__init__.py,inventory.py}`; `tests/functional/{{ 'test_consumer_inventory.py' if 'consumers' in batteries else '' }}.jinja`; `tests/contract/{{ 'test_provider_pact.py' if 'consumers' in batteries else '' }}.jinja`; `pacts/{{ 'examplewebapp-app.json' if 'consumers' in batteries else '' }}` (committed example pact, fixed provider name "app"); `scripts/{{ 'pact-publish.sh' if 'consumers' in batteries else '' }}`.
- Modify: `src/{{package_name}}/config/settings.py.jinja` (`inventory_url`); `pyproject.toml.jinja` (conditional `pact-python` dev dep + `httpx` runtime dep); `.gitignore.jinja` (`pacts/` rule); `.github/workflows/ci.yml.jinja` (gated `consumers` provider+broker steps); `Taskfile.yml.jinja` (gated `contract:pact` task); `README.md.jinja`/`CLAUDE.md.jinja` (broker workflow note).

---

## Task 1: Foundation — register `consumers`, settings, deps, the inventory client

**Files:** `src/framework_cli/batteries.py`; `src/{{package_name}}/{% if "consumers" in batteries %}clients{% endif %}/{__init__.py,inventory.py}`; `settings.py.jinja`; `pyproject.toml.jinja`; `tests/test_batteries.py`; `tests/test_copier_runner.py`.

- [ ] **Step 1: Verify the pact-python v3 API (de-risk).** In a THROWAWAY dir (NOT the framework repo, NOT touching its pyproject/lock), confirm pact-python 3.4.0 installs + the API matches: `cd /tmp && uv venv pact-spike && . pact-spike/bin/activate && uv pip install 'pact-python>=3.4' && python -c "from pact import Pact, match, Verifier; print('ok', Pact, match, Verifier)" ; deactivate`. If the imports differ (e.g. `from pact.v3 import ...`), note the correct paths and use them throughout. (This only de-risks; it pollutes nothing in the framework.)

- [ ] **Step 2: Write the failing tests.** Add to `tests/test_batteries.py`:
```python
def test_consumers_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "consumers" in battery_names()
    assert get_battery("consumers").requires == ()
    assert get_battery("consumers").gates_agents == ()
    assert resolve(["consumers"]) == ["consumers"]
```
Add to `tests/test_copier_runner.py`:
```python
def test_render_consumers_foundation(tmp_path):
    dest = tmp_path / "c"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    assert (dest / "src" / "demo" / "clients" / "inventory.py").exists()
    assert "inventory_url" in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    pyproject = (dest / "pyproject.toml").read_text()
    assert "pact-python" in pyproject and "httpx" in pyproject
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "src" / "demo" / "clients").exists()
    assert "inventory_url" not in (base / "src" / "demo" / "config" / "settings.py").read_text()
```

- [ ] **Step 3: Run → FAIL:** `uv run --frozen pytest tests/test_batteries.py::test_consumers_battery_registered tests/test_copier_runner.py::test_render_consumers_foundation -q`

- [ ] **Step 4: Register the battery.** In `src/framework_cli/batteries.py`, add to `_BATTERIES` (after `react`):
```python
    "consumers": BatterySpec(
        "consumers",
        "Pact consumer-driven contract testing (consumer + provider verification) for inter-service contracts",
    ),
```

- [ ] **Step 5: The inventory client.** Create `src/{{package_name}}/{% if "consumers" in batteries %}clients{% endif %}/__init__.py` (empty) and `.../clients/inventory.py`:
```python
import httpx


def get_stock(base_url: str, item_id: int) -> int:
    """Fetch an item's stock level from the downstream inventory service.

    base_url is injected (the app passes settings.inventory_url; the consumer Pact
    test passes the mock server URL) so the call is contract-testable in isolation.
    """
    res = httpx.get(f"{base_url.rstrip('/')}/inventory/{item_id}", timeout=5.0)
    res.raise_for_status()
    return int(res.json()["in_stock"])
```

- [ ] **Step 6: Settings.** In `settings.py.jinja`, after the mongodb block (before the `@property`), add:
```jinja
{%- if "consumers" in batteries %}

    # Downstream inventory service (Pact consumer demo). Override per environment.
    inventory_url: str = "http://inventory:8080"
{%- endif %}
```

- [ ] **Step 7: Deps.** In `pyproject.toml.jinja`: the inventory client needs `httpx` at RUNTIME (it's currently dev-only), and the contract tests need `pact-python`. Add to `[project.dependencies]` (gated):
```jinja
{% if "consumers" in batteries %}    "httpx>=0.28",
{% endif %}
```
Add to the `dev` dependency-group (gated):
```jinja
{% if "consumers" in batteries %}    "pact-python>=3.4",
{% endif %}
```
(httpx in both runtime+dev when consumers is present is fine — `uv` dedupes. Match the existing conditional-dep placement style, e.g. how `pymongo`/`testcontainers[mongodb]` are gated.)

- [ ] **Step 8: Run the tests → PASS.** Confirm `[consumers]` renders the client + settings + deps; `[]` baseline has none. Render `[]` and confirm settings.py/pyproject byte-identical.

- [ ] **Step 9: Fast gate + commit.** Stage batteries.py, clients/, settings.py.jinja, pyproject.toml.jinja, the two test files, CLAUDE.md (`[8h T1]`). `git commit -m "feat(consumers): register battery + inventory client + settings + deps"`.

---

## Task 2: Consumer Pact test (generates a pact against the mock server)

**Files:** `tests/functional/{{ 'test_consumer_inventory.py' if 'consumers' in batteries else '' }}.jinja`; `.gitignore.jinja`; `tests/test_copier_runner.py`; (acceptance later).

- [ ] **Step 1: Failing render test.** Add to `tests/test_copier_runner.py`:
```python
def test_render_consumers_consumer_test(tmp_path):
    dest = tmp_path / "c"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    t = (dest / "tests" / "functional" / "test_consumer_inventory.py").read_text()
    assert "from pact import Pact" in t and "get_stock" in t and "pact.serve()" in t
    assert "pacts/" in (dest / ".gitignore").read_text()
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "tests" / "functional" / "test_consumer_inventory.py").exists()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Create the consumer test** `tests/functional/{{ 'test_consumer_inventory.py' if 'consumers' in batteries else '' }}.jinja`:
```python
from pathlib import Path

from pact import Pact, match

from {{ package_name }}.clients.inventory import get_stock


def test_inventory_consumer_contract():
    """Consumer-driven contract: our client's expectations of the inventory service.

    Runs the real client against a Pact mock server and writes pacts/{{ package_name }}-inventory.json.
    """
    pact = Pact("{{ package_name }}", "inventory").with_specification("V4")
    (
        pact.upon_receiving("a stock query for item 1")
        .given("item 1 is in stock")
        .with_request("GET", "/inventory/1")
        .will_respond_with(200)
        .with_body({"item_id": match.int(1), "in_stock": match.int(5)})
    )
    with pact.serve() as srv:
        assert get_stock(str(srv.url), 1) == 5
    pact.write_file(Path("pacts"))
```
(Verify the v3 method names against Task-1's spike output; adjust `match.int`/`with_body`/`serve`/`write_file` if the installed 3.4.0 differs.)

- [ ] **Step 4: `.gitignore`** — add a gated rule keeping generated pacts out of git while committing the example pact (Task 3). In `.gitignore.jinja`:
```jinja
{% if "consumers" in batteries %}# Pact: generated consumer contracts (the example provider pact is committed)
pacts/*.json
!pacts/examplewebapp-app.json
{% endif %}
```

- [ ] **Step 5: Run the render test → PASS.** Baseline `[]` byte-identical (`.gitignore` unchanged without the battery — it's already `.gitignore.jinja` from 8g).

- [ ] **Step 6: Fast gate + commit.** Stage the consumer test, .gitignore.jinja, test_copier_runner.py, CLAUDE.md (`[8h T2]`). `git commit -m "feat(consumers): consumer Pact test (mock server -> generated pact) + pacts/ gitignore"`.

---

## Task 3: Provider verification (committed example pact + Verifier against the running app)

**Files:** `pacts/{{ 'examplewebapp-app.json' if 'consumers' in batteries else '' }}` (committed, GENERATED in this task); `tests/contract/{{ 'test_provider_pact.py' if 'consumers' in batteries else '' }}.jinja`; `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render test.** Add to `tests/test_copier_runner.py`:
```python
def test_render_consumers_provider(tmp_path):
    import json

    dest = tmp_path / "c"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    pact_file = dest / "pacts" / "examplewebapp-app.json"
    assert pact_file.exists()
    doc = json.loads(pact_file.read_text())  # valid JSON pact
    assert doc["provider"]["name"] == "app"
    t = (dest / "tests" / "contract" / "test_provider_pact.py").read_text()
    assert "from pact import Verifier" in t and "add_transport" in t
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "pacts").exists()
    assert not (base / "tests" / "contract").exists()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: GENERATE the committed example pact** (don't hand-write the JSON — produce a real v4 pact so the Verifier parses it). In a throwaway dir with pact-python installed (the Task-1 spike venv), run a one-off consumer script describing an `examplewebapp` consumer of `provider "app"`'s `GET /items`:
```python
# /tmp/gen_example_pact.py — run once with pact-python installed
from pathlib import Path
from pact import Pact, match
pact = Pact("examplewebapp", "app").with_specification("V4")
(pact.upon_receiving("a list-items request")
    .given("items exist")
    .with_request("GET", "/items")
    .will_respond_with(200)
    .with_body(match.each_like({"id": match.int(1), "name": match.str("alpha")})))
# We only need the contract file, not a live client call here; serve+exit writes it:
with pact.serve():
    import httpx  # call the mock so the interaction is recorded
    httpx.get(str(_srv_url) + "/items")   # use the serve() context's url
pact.write_file(Path("/tmp/genpacts"))
```
(Adjust to the verified v3 API — the goal is a valid `examplewebapp-app.json` v4 pact with one interaction: provider state "items exist", `GET /items` → 200, body = an array of `{id:int, name:str}` via `match.each_like`.) Copy the generated JSON to the template at `pacts/{{ 'examplewebapp-app.json' if 'consumers' in batteries else '' }}` (verbatim — NOT a `.jinja` file; provider name fixed to `"app"` so no per-project interpolation/brace-escaping is needed). If generating live is infeasible in-sandbox, hand-author a minimal valid v4 pact JSON for that interaction and validate it parses + the Verifier loads it in the acceptance test (Task 5).

- [ ] **Step 4: Create the provider verification test** `tests/contract/{{ 'test_provider_pact.py' if 'consumers' in batteries else '' }}.jinja`. It starts the app on a free port over the testcontainers Postgres (reuse the session `engine` fixture from `tests/conftest.py` — fixtures apply to `tests/contract/` since it's under `tests/`), seeds the `"items exist"` state, and runs the Verifier:
```python
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from pact import Verifier
from sqlalchemy import Engine


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def provider_url(engine: Engine, monkeypatch: pytest.MonkeyPatch):
    # Point the app at the test DB + seed the "items exist" provider state.
    from {{ package_name }}.db.engine import build_session_factory
    from {{ package_name }}.db.repository import create_item

    factory = build_session_factory(engine)
    with factory() as session:
        create_item(session, "alpha")
        create_item(session, "beta")
        session.commit()

    monkeypatch.setenv("APP_DATABASE_URL", str(engine.url))
    from {{ package_name }}.config.settings import get_settings

    get_settings.cache_clear()  # pick up the test DB URL

    port = _free_port()
    config = uvicorn.Config("{{ package_name }}.main:app", host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/heartbeat", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.2)
    else:
        raise RuntimeError("provider app did not start")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_items_provider_honors_example_pact(provider_url: str):
    """Verify the real /items API satisfies the committed example consumer pact."""
    (
        Verifier("app")
        .add_source("pacts/examplewebapp-app.json")
        .add_transport(url=provider_url)
        .verify()
    )
```
(Verify the v3 `Verifier` API — `add_source` may take a file or dir; `add_transport(url=)`; state handling. If the `"items exist"` state needs an explicit handler beyond the pre-seed, add `.state_handler({...})`. The engine fixture builds `engine` from the testcontainers `pg_url` with alembic applied — confirm `str(engine.url)` is the right URL form for `APP_DATABASE_URL`; adjust if a different DSN is needed. This is the intricate part — the acceptance test in Task 5 is the proof.)

- [ ] **Step 5: Run the render test → PASS.** Confirm the committed pact is valid JSON with `provider.name == "app"`; `tests/contract/` + `pacts/` absent at baseline.

- [ ] **Step 6: Fast gate + commit.** Stage the example pact, the provider test, test_copier_runner.py, CLAUDE.md (`[8h T3]`). `git commit -m "feat(consumers): provider verification — committed example pact + Verifier against the running app"`.

---

## Task 4: CI wiring + broker hooks + Taskfile

**Files:** `.github/workflows/ci.yml.jinja`; `scripts/{{ 'pact-publish.sh' if 'consumers' in batteries else '' }}`; `Taskfile.yml.jinja`; `README.md.jinja` (or CLAUDE.md.jinja convention); `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render test.** Add to `tests/test_copier_runner.py`:
```python
def test_render_consumers_ci_and_broker(tmp_path):
    import yaml

    dest = tmp_path / "c"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "test_provider_pact" in ci or "contract:pact" in ci
    yaml.safe_load(ci)  # valid YAML
    assert (dest / "scripts" / "pact-publish.sh").exists()
    assert "PACT_BROKER_URL" in (dest / "scripts" / "pact-publish.sh").read_text()
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert "test_provider_pact" not in (base / ".github" / "workflows" / "ci.yml").read_text()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Gated CI steps.** In `ci.yml.jinja`, add a gated `consumers` job (after `build`, matching whitespace control so `[]` is byte-identical — the graphql/react precedent). It runs the provider verification (which spins up the app over a Postgres service; reuse the `test` job's Postgres approach — or start postgres via a services: block) and the env-gated broker publish:
```jinja
{%- if "consumers" in batteries %}

  # Pact: provider verification (replays the committed example consumer pact against the app) +
  # opt-in broker publish (only when PACT_BROKER_URL is set). The consumer pact test runs in the
  # `test` job (functional tier). Docker provides the Postgres the provider verification needs.
  contracts:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - name: provider verification (Pact)
        run: uv run pytest tests/contract/test_provider_pact.py -q
      - name: publish pacts to broker (opt-in)
        if: {% raw %}${{ env.PACT_BROKER_URL != '' }}{% endraw %}
        env:
          PACT_BROKER_URL: {% raw %}${{ secrets.PACT_BROKER_URL }}{% endraw %}
          PACT_BROKER_TOKEN: {% raw %}${{ secrets.PACT_BROKER_TOKEN }}{% endraw %}
        run: bash scripts/pact-publish.sh
{%- endif %}
```
(The provider verification test uses testcontainers Postgres internally — confirm the CI runner has Docker; GitHub `ubuntu-latest` does. If `tests/contract/` needs the consumer test to have run first to generate its pact, note the ordering — provider verification only needs the COMMITTED example pact, so it's independent.)

- [ ] **Step 4: Broker publish script** `scripts/{{ 'pact-publish.sh' if 'consumers' in batteries else '' }}`:
```bash
#!/usr/bin/env bash
# Publish generated pacts to a Pact Broker (opt-in). No-ops if PACT_BROKER_URL is unset.
# Real multi-repo flow: consumers publish here; providers verify against broker pacts +
# `pact-broker can-i-deploy` gates releases. See README for the full workflow.
set -euo pipefail
if [ -z "${PACT_BROKER_URL:-}" ]; then
  echo "PACT_BROKER_URL unset — skipping pact publish (local-file flow only)."
  exit 0
fi
uv run pact-broker publish pacts/ \
  --broker-base-url "${PACT_BROKER_URL}" \
  --consumer-app-version "$(git rev-parse --short HEAD)" \
  ${PACT_BROKER_TOKEN:+--broker-token "${PACT_BROKER_TOKEN}"}
```
(Confirm the `pact-broker` CLI ships with `pact-python` 3.4.0 — if not, the script documents the intent + uses whatever the installed package provides; the acceptance test doesn't run the broker path.)

- [ ] **Step 5: Taskfile.** In `Taskfile.yml.jinja`, add a gated task (match the existing gated-task block style):
```jinja
{% if "consumers" in batteries %}
  contract:pact:
    desc: Run Pact contract tests (consumer + provider verification).
    cmds:
      - uv run pytest tests/functional/test_consumer_inventory.py tests/contract/test_provider_pact.py -q
{% endif %}
```

- [ ] **Step 6: README/CLAUDE convention.** In `README.md.jinja` (and/or the generated `CLAUDE.md.jinja` conventions), add a short "Contract testing (Pact)" note: consumer test generates `pacts/`; provider verification replays the committed example pact; set `PACT_BROKER_URL`/`PACT_BROKER_TOKEN` to publish/verify against a real broker (the multi-repo flow); local files are the default.

- [ ] **Step 7: Run the render test → PASS.** `[consumers]` ci.yml valid YAML with the contracts job; `[]` byte-identical (no `contracts:`/`test_provider_pact`).

- [ ] **Step 8: Fast gate + commit.** Stage ci.yml.jinja, pact-publish.sh, Taskfile.yml.jinja, README/CLAUDE, test_copier_runner.py, CLAUDE.md (`[8h T4]`). `git commit -m "feat(consumers): gated CI contracts job + opt-in broker publish hooks + Taskfile"`.

---

## Task 5: Integrity, downskill, and live acceptance

**Files:** `tests/test_copier_runner.py`; `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Integrity across combos.** Add (match existing `test_integrity_*` imports/shape):
```python
import pytest


@pytest.mark.parametrize("batteries", [[], ["consumers"], ["consumers", "graphql"], ["consumers", "workers"]])
def test_integrity_green_for_consumers_combos(tmp_path, batteries):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": batteries})
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []
```
Run it. `[]` MUST be green (no baseline manifest shift). Fix any gated-LOCKED-file (`ci.yml`/`.gitignore`) whitespace until baseline + every combo is green.

- [ ] **Step 2: Downskill (force=False).** Add (reuse the existing `_git_init_commit` helper + `remove_battery` shape):
```python
def test_downskill_consumers_no_force(tmp_path):
    from framework_cli.downskill import remove_battery
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "consumers", force=False)
    assert not (dest / "src" / "demo" / "clients").exists()
    assert not (dest / "tests" / "contract").exists()
    assert not (dest / "pacts").exists()
    assert "inventory_url" not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "test_provider_pact" not in (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert check(dest, ci=True) == []
```
Run it. If `--force` is demanded, confirm the byte-identity exclusion covers the gated shared files; report rather than forcing if a genuine builder-shared file trips it.

- [ ] **Step 3: Run the new fast-tier tests → green.** `uv run --frozen pytest tests/test_copier_runner.py -k "consumers" tests/test_batteries.py -k consumers -q`

- [ ] **Step 4: Live acceptance test.** Add to `tests/acceptance/test_rendered_project.py`:
```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: pact consumer + provider verification (app over testcontainers Postgres)",
)
def test_rendered_consumers_battery_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    # Consumer Pact test (fast, mocked → generates pacts/demo-inventory.json):
    consumer = subprocess.run(
        ["uv", "run", "pytest", "tests/functional/test_consumer_inventory.py", "-q"],
        cwd=dest, capture_output=True, text=True,
    )
    assert consumer.returncode == 0, "consumer pact test failed:\n" + consumer.stdout + consumer.stderr
    assert (dest / "pacts" / "demo-inventory.json").exists(), "consumer test did not write its pact"
    # Provider verification (app over testcontainers Postgres replays the committed example pact):
    provider = subprocess.run(
        ["uv", "run", "pytest", "tests/contract/test_provider_pact.py", "-q"],
        cwd=dest, capture_output=True, text=True,
    )
    assert provider.returncode == 0, "provider verification failed:\n" + provider.stdout + provider.stderr
```

- [ ] **Step 5: Run it, then CLEAN /tmp.** `uv run --frozen pytest "tests/acceptance/test_rendered_project.py::test_rendered_consumers_battery_passes" -q`; then `rm -rf /tmp/pytest-of-chris/* 2>/dev/null; df -h /tmp`. This installs pact-python (Linux wheel — should work in-sandbox, unlike react's Node) + runs the consumer test (generates the pact) + the provider verification (uvicorn app over testcontainers Postgres + Verifier). If the v3 API differs from the docs, fix the rendered tests; if the provider harness (uvicorn/state/DB URL) needs adjustment, fix it here — this acceptance test is the real proof of the full loop. If a piece is genuinely un-runnable in-sandbox, report DONE_WITH_CONCERNS with specifics (CI-gated) — do NOT weaken the assertions.

- [ ] **Step 6: Full fast gate + commit.** Stage tests + CLAUDE.md (`[8h T5]`). `git commit -m "test(consumers): integrity combos + downskill + live consumer+provider acceptance"`.

---

## Final Review (controller, after all tasks)

Dispatch an opus whole-branch reviewer that RUNS the tooling: fast gate + counts; `uv lock --check` (NO new framework dep — pact-python/httpx are template-only; confirm none leaked to the root pyproject) + `uv build`. Empirically: `consumers` registered (`requires=()`, no gates_agents); render `[consumers]`/`[]` — client/consumer-test/provider-test/example-pact/CI-job present for consumers, absent + byte-identical baseline (integrity `[]` green = no manifest shift); the committed example pact is valid JSON (`provider.name == "app"`); the `.gitignore` keeps generated pacts out but commits the example. Run ONLY `test_rendered_consumers_battery_passes` (clean /tmp after) — the consumer pact generates + the provider verification passes (or a clearly-reported CI-gated subset). Confirm the gated `ci.yml` edits don't break baseline live-stack tests. Verdict: READY TO MERGE or NOT READY + blockers.

Then proceed to `superpowers:finishing-a-development-branch`.

---

## Notes & Risks
- **pact-python v3 API churn** — Task 1 spikes the exact API; all tests verify against 3.4.0; the acceptance test is the proof.
- **Provider verification harness** (uvicorn on a port + testcontainers DB + provider state + `APP_DATABASE_URL`/`get_settings.cache_clear()`) is the intricate part — Task 3 builds it, Task 5 proves it; adjust empirically.
- **Committed example pact** is GENERATED (valid v4) not hand-written, provider name fixed `"app"` (no jinja-in-JSON / per-project interpolation).
- **In-sandbox feasibility** is better than react's (pact-python is a Python+Rust wheel, not Node; testcontainers/uvicorn work in-sandbox) — but if any piece can't run, it's CI-gated + reported, never weakened.
- **No new framework Python dep**; never touch the root `pyproject.toml`/`uv.lock`.
- **Byte-identity** of gated LOCKED `ci.yml`/`.gitignore` is the #1 regression class — Jinja whitespace control + the `[]` integrity guard (Task 5).
