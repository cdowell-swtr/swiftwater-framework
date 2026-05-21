# Observability Logs (Plan 3b-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the generated app's structlog JSON logs to Loki via Promtail and make them queryable in Grafana (Loki datasource auto-provisioned) alongside the 3b-1 metrics — all in the local `dev` Compose profile.

**Architecture:** Add three things to the generated project's `dev` profile: **Loki** (single-binary, filesystem storage) to store logs; **Promtail** to collect every Compose container's stdout via **Docker service discovery** (mounted Docker socket, the same pattern Traefik uses), parse the structlog JSON, and push to Loki, labelling each stream by Compose service name; and a **Grafana Loki datasource** (file-provisioned) so logs sit beside metrics in Grafana. No app code changes — 3a already emits JSON logs to stdout; the `service` label is derived by Promtail relabeling, not the app. This is **Plan 3b-2**; traces (Tempo + OTEL → 3b-3) are separate.

**Tech Stack:** Loki, Promtail (Grafana logging stack), Docker Compose profiles, Grafana file provisioning; Copier/Jinja; `pytest` (+ `PyYAML`, already a framework dev dep). No new Python runtime/test logic — validation is render-test (structural) + a Docker-gated live test.

**Spec reference:** `docs/superpowers/specs/2026-05-20-framework-design.md` — §8 (Observability Stack: Loki = structured log aggregation; Promtail = log shipping to Loki; structured logging via structlog; trace-to-log correlation noted but trace side is 3b-3) and §3 (`infra/observability/` tree: `loki/`, `promtail` shipping). Builds on **3a** (structlog JSON → stdout via `logging_config.py`; `dev` Compose profile in `infra/compose/dev.yml.jinja`; Grafana `provisioning/` layout) and **3b-1** (Grafana service + datasource/dashboard provisioning + the `infra/observability/` tree).

**Scope boundaries (NOT in this plan):**
- **Traces** (Tempo, OpenTelemetry instrumentation, the unified OTEL Collector pipeline, trace↔log correlation links) → **Plan 3b-3**. Promtail extracts `correlation_id` as a label here, which 3b-3 will use to wire trace↔log correlation in Grafana.
- **Log shipping in non-dev profiles / production log pipeline** — out of scope; this is the local `dev` stack. `lite` stays app-only.
- **Loki retention/limits tuning, auth, multi-tenant** — local dev defaults (no auth, filesystem, short retention).
- **No app code change** — structlog already emits JSON (3a). If a future need arises to add a `service` field *in* the log, that's deferred; the Promtail relabel-derived `service` label suffices for querying.

---

## Design Decisions (made per "decide & document")

1. **Promtail uses `docker_sd_configs`** (Docker service discovery over the mounted `/var/run/docker.sock`, `:ro`) rather than the Loki Docker-driver plugin (which requires a host `docker plugin install` — too invasive for a scaffold) or tailing `*-json.log` files (fragile across Docker setups). This mirrors how Traefik already reads the socket.
2. **The `service` label is the Compose service name**, set by a Promtail relabel from `__meta_docker_container_label_com_docker_compose_service`; `container` from `__meta_docker_container_name`. So `{service="app"}` queries the app's logs. No app change needed.
3. **Promtail parses the structlog JSON** in a `pipeline_stages` `json` stage to extract `level` and `correlation_id`; `level` is promoted to a label (low-cardinality), `correlation_id` is kept as an extracted field (high-cardinality → not a label, to avoid Loki stream explosion). The raw JSON line remains the stored log content.
4. **Loki is single-binary, filesystem-backed, `auth_enabled: false`** — the standard local config. Pinned `grafana/loki:3.2.1` / `grafana/promtail:3.2.1` (matched versions).
5. **Everything is `dev`-profile only** (like 3b-1's Prometheus/Grafana/Alertmanager); `lite` stays app-only.
6. **Validation:** render tests assert the configs render + parse and the services/datasource are wired; a Docker-gated live test brings up `dev`, generates app traffic, and queries Loki for the app's logs (skips without Docker). Loki/Promtail config *correctness* is the key review focus (version-sensitive) — the Opus code-quality review should scrutinise it.

---

## File Structure

Template additions/edits under `src/framework_cli/template/`:

```
src/framework_cli/template/
  infra/observability/
    loki/loki-config.yml                              # NEW (static): single-binary Loki, filesystem, no auth
    promtail/promtail-config.yml                      # NEW (static): docker_sd + JSON pipeline -> push to Loki
    grafana/provisioning/datasources/loki.yml         # NEW (static): Grafana Loki datasource (uid: loki)
  infra/compose/dev.yml.jinja                         # EDIT: add loki + promtail services (profile dev)
  SERVICES.md.jinja                                   # EDIT: add loki/promtail rows
  README.md.jinja                                     # EDIT: note logs in Grafana / Loki
tests/test_copier_runner.py                           # EDIT: render assertions (configs, services, datasource)
tests/acceptance/test_rendered_project.py             # EDIT: Docker-gated live log-query test
docs/superpowers/plans/2026-05-20-meta-plan.md        # EDIT (Task 3): mark 3b-2 done (controller does this at finish)
```

**Responsibilities:** `loki-config.yml` owns log storage; `promtail-config.yml` owns collection/parsing/shipping; the Grafana `loki.yml` datasource owns the read path. The Compose `dev` overlay wires them. All are declarative config; there is no Python unit logic in this plan.

---

## Task 1: Loki + Promtail config and services (the log pipeline)

**Files:**
- Create: `src/framework_cli/template/infra/observability/loki/loki-config.yml` (static)
- Create: `src/framework_cli/template/infra/observability/promtail/promtail-config.yml` (static)
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja` (add `loki` + `promtail` services)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

In `tests/test_copier_runner.py` add (`import yaml` already present):

```python
def test_render_loki_promtail(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    obs = dest / "infra" / "observability"

    loki = yaml.safe_load((obs / "loki" / "loki-config.yml").read_text())
    assert loki["auth_enabled"] is False
    assert loki["server"]["http_listen_port"] == 3100

    pt = yaml.safe_load((obs / "promtail" / "promtail-config.yml").read_text())
    assert pt["clients"][0]["url"] == "http://loki:3100/loki/api/v1/push"
    sc = pt["scrape_configs"][0]
    assert any("docker_sd_configs" == k for k in sc)
    # JSON pipeline extracts level + correlation_id from the structlog output
    stages = sc["pipeline_stages"]
    json_stage = next(s["json"] for s in stages if "json" in s)
    assert "level" in json_stage["expressions"]
    assert "correlation_id" in json_stage["expressions"]

    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    for name in ("loki", "promtail"):
        assert dev["services"][name]["profiles"] == ["dev"]
    assert any("3100" in str(p) for p in dev["services"]["loki"]["ports"])
    # promtail mounts the docker socket read-only and waits for loki
    vols = " ".join(dev["services"]["promtail"]["volumes"])
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in vols
    assert "loki" in dev["services"]["promtail"]["depends_on"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_loki_promtail -q`
Expected: FAIL — the Loki/Promtail config files do not exist.

- [ ] **Step 3: Create `loki/loki-config.yml`** (static)

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9095
  log_level: warn

common:
  instance_addr: 127.0.0.1
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: "2024-01-01"
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  allow_structured_metadata: true
  retention_period: 168h

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
```

- [ ] **Step 4: Create `promtail/promtail-config.yml`** (static)

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ["__meta_docker_container_name"]
        regex: "/(.*)"
        target_label: container
      - source_labels: ["__meta_docker_container_label_com_docker_compose_service"]
        target_label: service
    pipeline_stages:
      - json:
          expressions:
            level: level
            correlation_id: correlation_id
      - labels:
          level:
```

- [ ] **Step 5: Add `loki` + `promtail` services to `dev.yml.jinja`**

Append under `services:` in `infra/compose/dev.yml.jinja` (existing services unchanged):

```yaml
  loki:
    image: grafana/loki:3.2.1
    profiles: ["dev"]
    command: ["-config.file=/etc/loki/loki-config.yml"]
    ports:
      - "3100:3100"
    volumes:
      - "../observability/loki/loki-config.yml:/etc/loki/loki-config.yml:ro"

  promtail:
    image: grafana/promtail:3.2.1
    profiles: ["dev"]
    command: ["-config.file=/etc/promtail/promtail-config.yml"]
    volumes:
      - "../observability/promtail/promtail-config.yml:/etc/promtail/promtail-config.yml:ro"
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
    depends_on:
      - loki
```

- [ ] **Step 6: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_loki_promtail -q`
Expected: PASS. (The existing `test_render_compose_structure` / `test_render_observability_services_in_dev` still pass — additive only.)

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/infra/observability/loki/ \
        src/framework_cli/template/infra/observability/promtail/ \
        src/framework_cli/template/infra/compose/dev.yml.jinja \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" commit -m "feat(template): loki + promtail log pipeline in the dev profile"
```

---

## Task 2: Grafana Loki datasource

**Files:**
- Create: `src/framework_cli/template/infra/observability/grafana/provisioning/datasources/loki.yml` (static)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

In `tests/test_copier_runner.py` add:

```python
def test_render_grafana_loki_datasource(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ds = yaml.safe_load(
        (dest / "infra" / "observability" / "grafana" / "provisioning" / "datasources" / "loki.yml").read_text()
    )
    d = ds["datasources"][0]
    assert d["uid"] == "loki"
    assert d["type"] == "loki"
    assert d["url"] == "http://loki:3100"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_grafana_loki_datasource -q`
Expected: FAIL — `loki.yml` datasource does not exist.

- [ ] **Step 3: Create the Loki datasource** `grafana/provisioning/datasources/loki.yml` (static)

```yaml
apiVersion: 1
datasources:
  - name: Loki
    uid: loki
    type: loki
    access: proxy
    url: http://loki:3100
```

> Grafana loads every `*.yml` in `provisioning/datasources/`, so this sits beside the existing `prometheus.yml` (3b-1) and both are provisioned. No change to the existing datasource or the dashboard provider.

- [ ] **Step 4: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_grafana_loki_datasource -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/infra/observability/grafana/provisioning/datasources/loki.yml \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" commit -m "feat(template): grafana loki datasource"
```

---

## Task 3: Docs, Docker-gated live log test, meta-plan

**Files:**
- Modify: `src/framework_cli/template/SERVICES.md.jinja`
- Modify: `src/framework_cli/template/README.md.jinja`
- Modify: `tests/test_copier_runner.py`
- Modify: `tests/acceptance/test_rendered_project.py`
- Modify: `docs/superpowers/plans/2026-05-20-meta-plan.md` (controller, at finish)

- [ ] **Step 1: Add loki/promtail rows to `SERVICES.md.jinja`**

Add to the services table:

```markdown
| loki | `loki:3100` | `http://localhost:3100` | Log store; queried in Grafana (dev profile) |
| promtail | `promtail:9080` | (no host port) | Ships container logs to Loki via the Docker socket (dev profile) |
```

- [ ] **Step 2: Note logs in `README.md.jinja`**

In the `## Local stack (HTTPS)` section, extend the observability paragraph (add a sentence):

```markdown
Application logs (structlog JSON) are shipped to Loki by Promtail and queryable in Grafana under the Loki datasource — e.g. `{service="app"}` (filter by `level`, find a request by its `correlation_id`).
```

- [ ] **Step 3: Add render assertion for the docs**

In `tests/test_copier_runner.py` add:

```python
def test_render_docs_mention_logs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "loki:3100" in (dest / "SERVICES.md").read_text()
    assert '{service="app"}' in (dest / "README.md").read_text()
```

- [ ] **Step 4: Add the Docker-gated live log test**

In `tests/acceptance/test_rendered_project.py` append (reuses `_docker_available()` + the imports present from 3a/3b-1):

```python
@pytest.mark.skipif(not _docker_available(), reason="uv and docker are required for the live-stack test")
def test_rendered_project_app_logs_reach_loki(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        # generate some app logs (each request is logged by the observability middleware)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen("http://localhost:8000/heartbeat", timeout=3).read()
                break
            except OSError:
                time.sleep(2)
        for _ in range(5):
            try:
                urllib.request.urlopen("http://localhost:8000/heartbeat", timeout=3).read()
            except OSError:
                pass
        # query Loki for the app's logs (Promtail ship + Loki ingest has a lag, so poll)
        import urllib.parse

        deadline = time.time() + 90
        found = False
        while time.time() < deadline and not found:
            q = urllib.parse.urlencode(
                {"query": '{service="app"}', "limit": "5", "start": str(int((time.time() - 600) * 1e9))}
            )
            try:
                with urllib.request.urlopen(
                    f"http://localhost:3100/loki/api/v1/query_range?{q}", timeout=5
                ) as resp:
                    data = json.loads(resp.read())
                    result = data.get("data", {}).get("result", [])
                    if result and any(stream.get("values") for stream in result):
                        found = True
                        break
            except OSError:
                pass
            time.sleep(3)
        assert found, "no app logs reached Loki within the timeout"
    finally:
        subprocess.run(down, cwd=dest)
```

> The middleware skips recording metrics for `/heartbeat` but still **logs** every request (the `request` log line), so hitting `/heartbeat` produces app log lines for Promtail to ship. Log ingest has a lag, hence the poll. This test skips without Docker.

- [ ] **Step 5: Run the framework gate**

Run (in-sandbox): `uv run pytest tests/test_copier_runner.py -q` (incl. the new render assertions), `uv run ruff check .`, `uv run mypy src` → all green. `uv run pytest tests/acceptance/test_rendered_project.py --collect-only -q` → the new test collects without error.
Run (sandbox-disabled): `uv run pytest tests/acceptance/test_rendered_project.py -q -rs` → rendered suite passes; the Docker-gated tests (now three) skip here.

- [ ] **Step 6: Meta-plan + CLAUDE.md (controller, at finish)**

The controller updates `docs/superpowers/plans/2026-05-20-meta-plan.md` (mark `3b-2` ✅, repoint Next → 3b-3) and the `CLAUDE.md` Current State at the finish — NOT in a task commit. Implementers must not touch `CLAUDE.md`/meta-plan.

- [ ] **Step 7: Commit (the implementer commits only the template + test files)**

```bash
git add src/framework_cli/template/SERVICES.md.jinja src/framework_cli/template/README.md.jinja \
        tests/test_copier_runner.py tests/acceptance/test_rendered_project.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" commit -m "feat(template): logs docs + docker-gated loki log-shipping test"
```

---

## Self-Review

**1. Spec coverage (Plan 3b-2 subset of §8):**
- Loki = structured log aggregation → Task 1 (`loki-config.yml` + service). ✓
- Promtail = log shipping to Loki → Task 1 (`promtail-config.yml` docker_sd + push). ✓
- structlog structured logs flow through → no app change needed (3a emits JSON); Promtail parses it (Task 1 pipeline). ✓
- Logs viewable in Grafana beside metrics → Task 2 (Loki datasource) + Task 3 docs. ✓
- **Deferred (stated):** Tempo/OTEL traces + trace↔log correlation (3b-3); production log pipeline; Loki tuning/auth.

**2. Placeholder scan:** No "TBD"/"handle appropriately". Every config file is shown complete; the live test is complete. Loki/Promtail configs are version-pinned (3.2.1) minimal-but-complete configs; their runtime correctness is validated by the Docker-gated live test and scrutinised in the Opus code-quality review (render tests only check structure).

**3. Type/consistency check:** Service names `loki`/`promtail` and ports `3100`/`9080` match across `dev.yml.jinja`, `promtail-config.yml` (`http://loki:3100/loki/api/v1/push`), the Grafana datasource (`http://loki:3100`), `SERVICES.md`, and the render/live tests. The datasource `uid: loki` is distinct from 3b-1's `uid: prometheus`. Promtail's `service` label (from the compose service name `app`) is what the live test queries (`{service="app"}`) and what the README documents. The docker-socket mount string matches Traefik's existing `:ro` mount form. `_docker_available()` is the 3a Task 11 helper. All `dev`-profile-only; `lite` untouched.

---

*End of plan.*
