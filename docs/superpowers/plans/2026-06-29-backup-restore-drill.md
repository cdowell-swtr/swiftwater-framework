# Battery-aware Encrypted Backups + Restore-Drill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a battery-aware, age-encrypted backup + restore-drill capability into the base scaffold so every generated project can recover its data, with a completeness gate that makes backup handling a mandatory registration requirement for any new data-persistence battery.

**Architecture:** Backups are a **base scaffold capability** (Postgres is base → recovery is base, not a `--with` battery). `task backup` dumps every *active* durable store, encrypts each with `age`, and writes to a configurable `$BACKUP_DEST` (this box → a `/mnt/<gdrive>` folder). A `data` disposition on `BatterySpec` (mirroring the existing `obs` field) declares how each *optional* data-persistence battery contributes; a static gate (`tests/test_backup_completeness.py`, fast tier) scrapes rendered volumes ↔ declarations so a new stateful battery can't ship without backup handling, and a docker restore-drill (`tests/acceptance/test_backup_drill.py`, full tier) round-trips each store against battery-correct images.

**Tech Stack:** Python 3.12, Copier/Jinja templates, bash, `age` (encryption), `pg_dump`/`pg_restore`, `mongodump`/`mongorestore`, Docker Compose, systemd (operator-wired timer), pytest.

**Spec:** `docs/superpowers/specs/2026-06-29-backup-battery-design.md`.

## Global Constraints

- **`src/framework_cli/template/` is template payload, not framework source** — `.jinja`/`.py`/config files there render into generated projects; do not lint/type them as framework code. Validate by rendering + the generated project's own tests (`tests/test_copier_runner.py`, `tests/acceptance/`).
- **Template changes require re-running render + acceptance tests.** A freshly generated project must make a clean first `pre-commit` pass (`test_rendered_project_precommit_runs_clean`).
- **`.env.example.jinja`, `Taskfile.yml.jinja`, `base.yml.jinja` are eval-fixture-anchored.** When you edit them, ALSO run `tests/review/test_evals.py::test_every_fixture_realizes` in your cadence (fixture drift is otherwise invisible). See `_memory/eval-fixtures-coupled-to-template.md`.
- **Quality gate (green before every commit):** `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy src` · `task test:fast`. Run `task test:full` (adds docker acceptance) at branch end.
- **Backups are core, not a battery.** Base Postgres backup always renders (`infra/backup/`). `BatterySpec.data` is only for the optional data-persistence batteries (mongodb/age/pgvector/timescaledb/redis).
- **Encryption is on from day 1** — dumps are always `age`-encrypted before hitting `$BACKUP_DEST`. Interim key custody (identity-file-on-box + off-box DR copy); the only FWK85 seam is *how the key is fetched*.
- **Model policy:** implementers → Sonnet (Haiku for trivial); spec-compliance review → Sonnet; code-quality + branch-end review → Opus. Pass `model` per role.

---

## File Structure

**Framework source (Python, type-checked):**
- `src/framework_cli/batteries.py` — add `DataSurface` Literal + `data` kw_only field on `BatterySpec` + a disposition for every battery.
- `tests/test_backup_completeness.py` *(new)* — the static registration gate (fast tier).

**Template payload (rendered into projects):**
- `src/framework_cli/template/infra/backup/backup.sh` *(new)* — battery-aware dump → encrypt → write → prune.
- `src/framework_cli/template/infra/backup/prune.sh` *(new)* — GFS-lite retention.
- `src/framework_cli/template/infra/backup/restore.sh` *(new)* — guarded restore into the live stores.
- `src/framework_cli/template/infra/backup/restore_drill.sh` *(new)* — restore latest into a throwaway instance + verify.
- `src/framework_cli/template/infra/backup/{{ project_slug }}-backup.service.jinja` *(new)* — systemd oneshot unit (disabled by default).
- `src/framework_cli/template/infra/backup/{{ project_slug }}-backup.timer.jinja` *(new)* — systemd timer (disabled by default).
- `src/framework_cli/template/infra/backup/README.md.jinja` *(new)* — runbook (key custody, `/mnt` wiring, RPO/RTO, restore).
- `src/framework_cli/template/Taskfile.yml.jinja` — add `backup`, `backup:prune`, `restore`, `backup:verify` targets.
- `src/framework_cli/template/.env.example.jinja` — add the `BACKUP_*` config block.
- `src/framework_cli/template/.gitignore` — ignore `backups/` (the local default dest).

**Acceptance (full tier, docker-gated):**
- `tests/acceptance/test_backup_drill.py` *(new)* — the execution gate.

**Wiring:**
- `tests/test_test_tiers.py` — register the new acceptance file in `ACCEPTANCE_DOCKER_EXCEPTIONS`.
- `tests/test_copier_runner.py` — render-level structure assertions.
- `docs/maintenance/backups.md` *(new)* — the maintainer-facing coverage contract (points at the gate).

---

## Task 1: `BatterySpec.data` disposition + per-battery declarations

**Files:**
- Modify: `src/framework_cli/batteries.py:7` (add Literal) and `:23` (add field) and each battery entry `:27-117`.
- Test: `tests/test_batteries_data_surface.py` *(new)*.

**Interfaces:**
- Produces: `BatterySpec.data: DataSurface` where `DataSurface = Literal["none", "store", "rebuildable", "postgres-extension"]`. Consumed by Task 2's gate and the spec's mental model.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_batteries_data_surface.py
import pytest
from framework_cli.batteries import battery_names, get_battery

# The declared backup disposition for every battery. A new battery added without an entry
# here fails this test — forcing the author to consciously classify its data surface.
EXPECTED_DATA = {
    "webhooks": "none",
    "llm": "none",
    "agents": "none",
    "claudesubscriptioncli": "none",
    "websockets": "none",
    "workers": "rebuildable",          # redisdata: broker/result backend, rebuildable
    "graphql": "none",
    "pgvector": "postgres-extension",  # vector data in pgdata; restore needs the extension image
    "mongodb": "store",                # mongodata: a new durable store, dumped via mongodump
    "timescaledb": "postgres-extension",
    "age": "postgres-extension",
    "redis": "rebuildable",            # redisdata: cache/sessions, rebuildable
    "react": "rebuildable",            # frontend_node_modules: build cache
    "consumers": "none",
    "docs": "none",
    "multitenantauth": "none",         # control-plane DB co-located in pgdata (core backup)
}


def test_every_battery_declares_a_data_surface():
    assert set(battery_names()) == set(EXPECTED_DATA), (
        "a battery was added/removed without updating EXPECTED_DATA — classify its data surface"
    )


@pytest.mark.parametrize("name", battery_names())
def test_battery_data_matches_expected(name):
    assert get_battery(name).data == EXPECTED_DATA[name]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_batteries_data_surface.py -q`
Expected: FAIL — `BatterySpec.__init__() missing ... 'data'` / `AttributeError: ... 'data'`.

- [ ] **Step 3: Add the `DataSurface` type and the `data` field**

In `src/framework_cli/batteries.py`, after line 7 (`ObsSurface = ...`):

```python
ObsSurface = Literal["service", "in-process", "rides-existing"]
# §FWK133 backup surface — REQUIRED, keyword-only. Forces every battery author to declare
# whether it adds durable state and how recovery handles it; verified against the rendered
# template by tests/test_backup_completeness.py.
#   "none"               -> stateless: adds no named volume, no effect on backup
#   "store"              -> adds a NEW durable store that `task backup` dumps (e.g. mongodb)
#   "rebuildable"        -> adds a named volume intentionally NOT backed up (cache/broker/build)
#   "postgres-extension" -> no new volume; changes the base Postgres dump/restore (restore needs
#                           the extension-loaded postgres image)
DataSurface = Literal["none", "store", "rebuildable", "postgres-extension"]
```

Add the field to `BatterySpec` (after the `obs` field, line 23):

```python
    obs: ObsSurface = field(kw_only=True)
    data: DataSurface = field(kw_only=True)
```

- [ ] **Step 4: Declare `data=` on every battery**

Add the matching `data=` kwarg to each `BatterySpec(...)` entry. Values (verbatim from the test's `EXPECTED_DATA`):

```python
# examples — apply the same kwarg to every entry:
    "workers": BatterySpec(
        "workers",
        "Celery + Redis async task workers with a DB-backed dead-letter queue and beat scheduler",
        obs="service",
        data="rebuildable",
    ),
    "mongodb": BatterySpec(
        "mongodb",
        "MongoDB document store (pymongo) with a documents collection + full observability",
        obs="service",
        data="store",
    ),
    "age": BatterySpec(
        "age",
        "Apache AGE openCypher graph queries on Postgres (no new service)",
        obs="rides-existing",
        data="postgres-extension",
    ),
    # pgvector, timescaledb -> data="postgres-extension"
    # redis, react          -> data="rebuildable"
    # all others            -> data="none"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_batteries_data_surface.py -q`
Expected: PASS (17 tests).

- [ ] **Step 6: Confirm nothing else broke + types clean**

Run: `uv run mypy src && uv run pytest tests/test_obs_completeness.py -q`
Expected: PASS (the new required kwarg is set everywhere).

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/batteries.py tests/test_batteries_data_surface.py
git commit -m "feat(FWK133): BatterySpec.data backup disposition + per-battery declarations"
```

---

## Task 2: Static completeness gate (`tests/test_backup_completeness.py`)

**Files:**
- Create: `tests/test_backup_completeness.py`.

**Interfaces:**
- Consumes: `BatterySpec.data` (Task 1); the rendered compose volumes; the rendered `infra/backup/backup.sh` `BACKUP-STORES:` manifest line (Task 3 produces it — until then, the `store`/base assertions that read `backup.sh` are written but xfail-guarded as noted).
- Produces: the registration gate. A new battery that adds a volume with no matching `data` disposition fails this test.

> NOTE: this task writes the *volume↔disposition* assertions, which pass against Task 1 alone (they read only compose volumes + the extension image). The assertions that read `infra/backup/backup.sh` (the `store` manifest + the base `pg_dump` check) are included but marked with `pytest.mark.skipif(backup.sh absent)` so this task is green now and the check activates automatically once Task 3 lands the script. Task 3 Step 6 flips them to hard.

- [ ] **Step 1: Write the gate test**

```python
# tests/test_backup_completeness.py
from pathlib import Path

import pytest
import yaml

from framework_cli.batteries import battery_names, get_battery
from framework_cli.copier_runner import render_project

_BASE = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}
_COMPOSE = Path("infra/compose")
# Every overlay that can declare a named volume.
_OVERLAYS = ("base.yml", "dev.yml", "services.yml", "prod.yml", "staging.yml", "test.yml", "observability.yml")
_BACKUP = Path("infra/backup/backup.sh")
# obs telemetry volumes are base + retention-bounded (not SoT); declared rebuildable by convention.
_BASE_REBUILDABLE = {"promdata", "lokidata", "tempodata"}


def _named_volumes(root: Path) -> set[str]:
    vols: set[str] = set()
    for f in _OVERLAYS:
        p = root / _COMPOSE / f
        if not p.is_file():
            continue
        data = yaml.safe_load(p.read_text()) or {}
        vols |= set((data.get("volumes") or {}).keys())
    return vols


def _backup_stores(root: Path) -> set[str]:
    """Parse the `# BACKUP-STORES: postgres mongo` manifest line from backup.sh."""
    p = root / _BACKUP
    if not p.is_file():
        return set()
    for line in p.read_text().splitlines():
        if line.strip().startswith("# BACKUP-STORES:"):
            return set(line.split(":", 1)[1].split())
    return set()


@pytest.fixture(scope="module")
def baseline(tmp_path_factory) -> Path:
    dest = tmp_path_factory.mktemp("bk-base") / "demo"
    render_project(dest, {**_BASE, "batteries": []})
    return dest


@pytest.mark.parametrize("name", battery_names())
def test_battery_data_matches_rendered_volumes(name: str, baseline: Path, tmp_path: Path) -> None:
    dest = tmp_path / "demo"
    render_project(dest, {**_BASE, "batteries": [name]})
    new_volumes = _named_volumes(dest) - _named_volumes(baseline)
    data = get_battery(name).data
    stores = _backup_stores(dest)

    if data == "none":
        assert not new_volumes, f"{name}: a 'none' battery must add no named volume; got {new_volumes}"
    elif data == "rebuildable":
        assert new_volumes, f"{name}: a 'rebuildable' battery must add the volume it declares"
        for v in new_volumes:
            store = v.removesuffix("data")
            assert store not in stores, f"{name}: rebuildable volume {v!r} must NOT be in BACKUP-STORES"
    elif data == "store":
        assert new_volumes, f"{name}: a 'store' battery must add a named volume"
        if _BACKUP.exists := (dest / _BACKUP).is_file():  # hardened in Task 3
            for v in new_volumes:
                store = v.removesuffix("data")
                assert store in stores, f"{name}: store volume {v!r} not dumped in infra/backup/backup.sh"
    elif data == "postgres-extension":
        assert not new_volumes, f"{name}: a 'postgres-extension' battery shares pgdata, adds no volume"
        dev = (dest / _COMPOSE / "dev.yml").read_text()
        assert "postgres.Dockerfile" in dev, (
            f"{name}: a 'postgres-extension' battery must build the extension postgres image "
            "(so restore is extension-correct)"
        )


def test_no_unclassified_volume_in_baseline(baseline: Path) -> None:
    """Every base named volume is either pgdata (core backup) or a known rebuildable telemetry store."""
    vols = _named_volumes(baseline)
    assert "pgdata" in vols, "base scaffold must declare the pgdata volume"
    unclassified = vols - {"pgdata"} - _BASE_REBUILDABLE
    assert not unclassified, f"base render has unclassified durable volume(s): {unclassified}"


@pytest.mark.skipif(True, reason="activated by Task 3 (backup.sh)")  # Task 3 deletes this marker
def test_base_postgres_is_core_backed_up(baseline: Path) -> None:
    backup = baseline / _BACKUP
    assert backup.is_file(), "core backup script infra/backup/backup.sh must render in the base scaffold"
    text = backup.read_text()
    assert "pg_dump" in text, "core backup must pg_dump the base postgres"
    assert "postgres" in _backup_stores(baseline), "BACKUP-STORES must list postgres in the base render"
```

> Replace the `if _BACKUP.exists :=` walrus line with a plain guard if your reviewer prefers: `if (dest / _BACKUP).is_file():`. (The walrus is only to keep the diff one line; behaviour is identical.)

- [ ] **Step 2: Run to verify it passes against Task 1**

Run: `uv run pytest tests/test_backup_completeness.py -q`
Expected: PASS — volume↔disposition assertions hold; the base-postgres check is `skipif`-skipped until Task 3.

- [ ] **Step 3: Commit**

```bash
git add tests/test_backup_completeness.py
git commit -m "test(FWK133): static backup-completeness gate (volumes <-> data disposition)"
```

---

## Task 3: Core Postgres backup — `backup.sh` + `.env` keys + `task backup`

**Files:**
- Create: `src/framework_cli/template/infra/backup/backup.sh`.
- Create: `src/framework_cli/template/infra/backup/prune.sh` (stub now; filled in Task 4).
- Modify: `src/framework_cli/template/.env.example.jinja` (add the `BACKUP_*` block).
- Modify: `src/framework_cli/template/Taskfile.yml.jinja` (add the `backup` target).
- Modify: `src/framework_cli/template/.gitignore` (ignore `backups/`).
- Test: `tests/test_copier_runner.py` (add render-structure assertions).

**Interfaces:**
- Produces: a rendered `infra/backup/backup.sh` carrying a `# BACKUP-STORES: postgres[ mongo]` manifest line, dumping each store as `age`-encrypted files in `$BACKUP_DEST`. Consumed by Tasks 2, 4, 5, 9.

- [ ] **Step 1: Write the failing render-structure test**

Add to `tests/test_copier_runner.py`:

```python
def test_backup_core_renders_in_baseline(tmp_path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": []})  # DATA = the module's canonical answers
    backup = dest / "infra/backup/backup.sh"
    assert backup.is_file(), "core backup.sh must render with no batteries"
    text = backup.read_text()
    assert "# BACKUP-STORES: postgres" in text
    assert "pg_dump" in text and "age -r" in text
    assert "{{" not in text and "{%" not in text, "backup.sh has unrendered Jinja"
    env = (dest / ".env.example").read_text()
    assert "BACKUP_DEST=" in env and "BACKUP_PUBKEY=" in env
    task = (dest / "Taskfile.yml").read_text()
    assert "backup:" in task
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_backup_core_renders_in_baseline -q`
Expected: FAIL — `backup.sh` does not exist.

- [ ] **Step 3: Create `infra/backup/backup.sh`**

```bash
#!/usr/bin/env bash
# Battery-aware encrypted backup. Dumps each active durable store, encrypts each with age, writes
# to $BACKUP_DEST, then prunes old dumps. Run via `task backup` or the systemd timer.
# See infra/backup/README.md for setup (age key custody, $BACKUP_DEST, the timer).
#
# BACKUP-STORES: postgres{% if "mongodb" in batteries %} mongo{% endif %}
set -euo pipefail
cd "$(dirname "$0")/../.."

: "${BACKUP_DEST:=./backups}"
: "${BACKUP_PUBKEY:?set BACKUP_PUBKEY to your age recipient public key (see infra/backup/README.md)}"
command -v age >/dev/null || { echo "age not installed (see infra/backup/README.md)" >&2; exit 1; }

mkdir -p "$BACKUP_DEST"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
slug="{{ project_slug }}"

echo "backup: postgres -> $BACKUP_DEST"
./scripts/compose.sh exec -T postgres pg_dump -Fc -U app app \
  | age -r "$BACKUP_PUBKEY" > "$BACKUP_DEST/${slug}-postgres-${ts}.dump.age"
{% if "mongodb" in batteries %}
echo "backup: mongo -> $BACKUP_DEST"
./scripts/compose.sh exec -T mongo mongodump --archive --gzip --db app \
  | age -r "$BACKUP_PUBKEY" > "$BACKUP_DEST/${slug}-mongo-${ts}.archive.gz.age"
{% endif %}
./infra/backup/prune.sh
echo "backup complete (${ts})"
```

- [ ] **Step 4: Create a `prune.sh` placeholder (real logic in Task 4)**

```bash
#!/usr/bin/env bash
# GFS-lite retention for $BACKUP_DEST. Filled in by the prune task; no-op until then.
set -euo pipefail
: "${BACKUP_DEST:=./backups}"
exit 0
```

- [ ] **Step 5: Add the `.env.example.jinja` backup block**

Append after the database block (the file uses a `FRAMEWORK:BEGIN` managed region — keep this inside it):

```jinja
# ── backups (core; see infra/backup/README.md) ───────────────────────────────
# Destination for encrypted dumps. Local dir by default; on this box point at a
# Google-Drive-synced folder under /mnt to survive WSL-VM and host loss.
BACKUP_DEST=./backups
# age recipient PUBLIC key (safe to commit). Generate a keypair with `age-keygen`.
BACKUP_PUBKEY=
# Path to the age PRIVATE identity on this box (read by restore + the drill). ALSO custody a
# copy OFF the box (password manager) — losing it makes the off-box backups unrecoverable.
BACKUP_IDENTITY=~/.config/{{ project_slug }}/backup-identity.txt
# GFS-lite retention.
BACKUP_RETENTION_DAILY=7
BACKUP_RETENTION_WEEKLY=4
```

- [ ] **Step 6: Add the `backup` Taskfile target + harden the gate**

In `Taskfile.yml.jinja`, add (match the existing two-space indent + `desc:`/`cmds:` shape):

```yaml
  backup:
    desc: Encrypted backup of every active durable store to $BACKUP_DEST (see infra/backup/README.md).
    cmds:
      - ./infra/backup/backup.sh
```

Then make the backup files executable in the template and delete the `skipif` marker on `test_base_postgres_is_core_backed_up` in `tests/test_backup_completeness.py` (Task 2) so the base-postgres check goes hard:

```bash
chmod +x src/framework_cli/template/infra/backup/backup.sh src/framework_cli/template/infra/backup/prune.sh
# in tests/test_backup_completeness.py: remove the @pytest.mark.skipif(...Task 3...) line
```

- [ ] **Step 7: Run the render + gate tests**

Run: `uv run pytest tests/test_copier_runner.py::test_backup_core_renders_in_baseline tests/test_backup_completeness.py -q`
Expected: PASS (the base-postgres check is now active and green).

- [ ] **Step 8: Run the eval-fixture realizer (env/Taskfile are anchored)**

Run: `uv run pytest tests/review/test_evals.py::test_every_fixture_realizes -q`
Expected: PASS. If a fixture fails to realize, re-anchor per `_memory/eval-fixtures-coupled-to-template.md`.

- [ ] **Step 9: Commit**

```bash
git add src/framework_cli/template/infra/backup/backup.sh src/framework_cli/template/infra/backup/prune.sh \
        src/framework_cli/template/.env.example.jinja src/framework_cli/template/Taskfile.yml.jinja \
        src/framework_cli/template/.gitignore tests/test_copier_runner.py tests/test_backup_completeness.py
git commit -m "feat(FWK133): core encrypted Postgres backup (backup.sh + task backup + .env)"
```

---

## Task 4: GFS-lite retention — `prune.sh` + `task backup:prune`

**Files:**
- Modify: `src/framework_cli/template/infra/backup/prune.sh`.
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`.
- Test: `tests/test_copier_runner.py`.

**Interfaces:**
- Consumes: `$BACKUP_DEST`, `BACKUP_RETENTION_DAILY`, `BACKUP_RETENTION_WEEKLY`.
- Produces: keeps the newest N daily dumps per store + M weekly, deletes the rest. Called by `backup.sh` (Task 3) and `task backup:prune`.

- [ ] **Step 1: Write the failing render test**

```python
def test_prune_renders_with_retention(tmp_path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": []})
    prune = (dest / "infra/backup/prune.sh").read_text()
    assert "BACKUP_RETENTION_DAILY" in prune and "BACKUP_RETENTION_WEEKLY" in prune
    assert (dest / "Taskfile.yml").read_text().count("backup:prune") >= 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_prune_renders_with_retention -q`
Expected: FAIL — placeholder `prune.sh` has no retention vars.

- [ ] **Step 3: Implement `prune.sh`**

```bash
#!/usr/bin/env bash
# GFS-lite retention for $BACKUP_DEST: keep the newest $BACKUP_RETENTION_DAILY dumps per store,
# plus one per ISO-week for the last $BACKUP_RETENTION_WEEKLY weeks; delete the rest.
set -euo pipefail
: "${BACKUP_DEST:=./backups}"
: "${BACKUP_RETENTION_DAILY:=7}"
: "${BACKUP_RETENTION_WEEKLY:=4}"
slug="{{ project_slug }}"

prune_store() {  # $1 = glob prefix, e.g. demo-postgres
  local prefix="$1"
  mapfile -t all < <(ls -1t "$BACKUP_DEST/${prefix}-"*.age 2>/dev/null || true)
  [ "${#all[@]}" -gt 0 ] || return 0
  declare -A keep=()
  # newest N daily
  for f in "${all[@]:0:$BACKUP_RETENTION_DAILY}"; do keep["$f"]=1; done
  # one per ISO-week for the last M weeks (filename ts is ...-YYYYMMDDThhmmssZ...)
  declare -A week_seen=()
  for f in "${all[@]}"; do
    local ts week
    ts="$(basename "$f" | grep -oE '[0-9]{8}T[0-9]{6}Z' | head -1)" || continue
    week="$(date -u -d "${ts:0:8}" +%G-%V 2>/dev/null || echo "")"
    [ -n "$week" ] || continue
    if [ -z "${week_seen[$week]:-}" ] && [ "${#week_seen[@]}" -lt "$BACKUP_RETENTION_WEEKLY" ]; then
      week_seen[$week]=1; keep["$f"]=1
    fi
  done
  for f in "${all[@]}"; do [ -n "${keep[$f]:-}" ] || { echo "prune: rm $(basename "$f")"; rm -f "$f"; }; done
}

prune_store "${slug}-postgres"
{% if "mongodb" in batteries %}prune_store "${slug}-mongo"{% endif %}
```

- [ ] **Step 4: Add the `backup:prune` target**

```yaml
  backup:prune:
    desc: Apply GFS-lite retention to $BACKUP_DEST (also run automatically by `task backup`).
    cmds:
      - ./infra/backup/prune.sh
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_prune_renders_with_retention -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/infra/backup/prune.sh src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git commit -m "feat(FWK133): GFS-lite backup retention (prune.sh + task backup:prune)"
```

---

## Task 5: Restore + restore-drill — `restore.sh`, `restore_drill.sh`, `task restore` / `backup:verify`

**Files:**
- Create: `src/framework_cli/template/infra/backup/restore.sh`.
- Create: `src/framework_cli/template/infra/backup/restore_drill.sh`.
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`.
- Test: `tests/test_copier_runner.py`.

**Interfaces:**
- Consumes: `$BACKUP_DEST`, `$BACKUP_IDENTITY`, the dump files from Task 3.
- Produces: `task restore` (guarded, live) and `task backup:verify` (the drill — decrypt latest → restore into a throwaway instance → verify `alembic_version` at head → tear down). The drill's behaviour is proven by Task 9 under docker; this task only ships the scripts + render-structure assertions.

- [ ] **Step 1: Write the failing render test**

```python
def test_restore_and_drill_render(tmp_path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": []})
    restore = (dest / "infra/backup/restore.sh").read_text()
    drill = (dest / "infra/backup/restore_drill.sh").read_text()
    assert "age -d" in restore and "pg_restore" in restore
    assert "yes" in restore  # explicit confirmation guard
    assert "age -d" in drill and "alembic_version" in drill
    task = (dest / "Taskfile.yml").read_text()
    assert "restore:" in task and "backup:verify" in task
    for sh in (restore, drill):
        assert "{{" not in sh and "{%" not in sh
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_restore_and_drill_render -q`
Expected: FAIL — files missing.

- [ ] **Step 3: Create `restore.sh` (guarded live restore)**

```bash
#!/usr/bin/env bash
# Restore the LATEST encrypted dump into the LIVE stores. DESTRUCTIVE — requires typed confirmation.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${BACKUP_DEST:=./backups}"
: "${BACKUP_IDENTITY:=$HOME/.config/{{ project_slug }}/backup-identity.txt}"
slug="{{ project_slug }}"

latest() { ls -1t "$BACKUP_DEST/${slug}-$1-"*.age 2>/dev/null | head -1; }

pg="$(latest postgres)"; [ -n "$pg" ] || { echo "no postgres dump in $BACKUP_DEST" >&2; exit 1; }
read -r -p "Restore $(basename "$pg") into the LIVE postgres? This OVERWRITES data. [type 'yes']: " ok
[ "$ok" = "yes" ] || { echo "aborted"; exit 1; }
age -d -i "$BACKUP_IDENTITY" "$pg" \
  | ./scripts/compose.sh exec -T postgres pg_restore --clean --if-exists --no-owner -U app -d app
{% if "mongodb" in batteries %}
mg="$(latest mongo)"; if [ -n "$mg" ]; then
  age -d -i "$BACKUP_IDENTITY" "$mg" \
    | ./scripts/compose.sh exec -T mongo mongorestore --archive --gzip --drop --db app
fi
{% endif %}
echo "restore complete"
```

- [ ] **Step 4: Create `restore_drill.sh` (verify into a throwaway instance)**

```bash
#!/usr/bin/env bash
# Restore-drill: decrypt the latest postgres dump into a THROWAWAY postgres (the battery-correct
# image, so extensions restore), assert alembic is at head, tear down. Proves the WHOLE chain incl.
# decryption — a missing/wrong age key fails loudly here, not mid-recovery.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${BACKUP_DEST:=./backups}"
: "${BACKUP_IDENTITY:=$HOME/.config/{{ project_slug }}/backup-identity.txt}"
slug="{{ project_slug }}"

pg="$(ls -1t "$BACKUP_DEST/${slug}-postgres-"*.age 2>/dev/null | head -1)"
[ -n "$pg" ] || { echo "no postgres dump to drill in $BACKUP_DEST" >&2; exit 1; }

# Build the same postgres image the stack uses (extension-loaded when needed), via compose.
img="$(./scripts/compose.sh -f infra/compose/base.yml -f infra/compose/dev.yml config --images | grep -E '(^|/)postgres' | head -1)"
[ -n "$img" ] || img="postgres:17"
{% set _pre = [] %}{% if "timescaledb" in batteries %}{% set _ = _pre.append("timescaledb") %}{% endif %}{% if "age" in batteries %}{% set _ = _pre.append("age") %}{% endif %}
cmd=(postgres){% if _pre %} ; cmd+=(-c "shared_preload_libraries={{ _pre | join(',') }}"){% endif %}

cid="$(docker run -d -e POSTGRES_USER=app -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=drill "$img" "${cmd[@]}")"
trap 'docker rm -f "$cid" >/dev/null 2>&1 || true; rm -f "$tmp"' EXIT
for _ in $(seq 1 30); do docker exec "$cid" pg_isready -U app -d drill -q && break; sleep 1; done

tmp="$(mktemp)"; age -d -i "$BACKUP_IDENTITY" "$pg" > "$tmp"
{% if "age" in batteries %}docker exec -i "$cid" psql -v ON_ERROR_STOP=1 -U app -d drill -c "CREATE EXTENSION IF NOT EXISTS age; LOAD 'age';"{% endif %}
{% if "timescaledb" in batteries %}docker exec -i "$cid" psql -v ON_ERROR_STOP=1 -U app -d drill -c "SELECT timescaledb_pre_restore();"{% endif %}
docker exec -i "$cid" pg_restore --clean --if-exists --no-owner -U app -d drill < "$tmp"
{% if "timescaledb" in batteries %}docker exec -i "$cid" psql -v ON_ERROR_STOP=1 -U app -d drill -c "SELECT timescaledb_post_restore();"{% endif %}

n="$(docker exec "$cid" psql -tAX -U app -d drill -c "SELECT count(*) FROM alembic_version;")"
[ "$n" = "1" ] || { echo "drill FAILED: alembic_version has $n rows (expected 1)" >&2; exit 1; }
echo "restore-drill OK: latest postgres dump restores + alembic at head"
```

- [ ] **Step 5: Add `restore` + `backup:verify` targets**

```yaml
  restore:
    desc: DESTRUCTIVE — restore the latest dump into the LIVE stores (typed confirmation required).
    cmds:
      - ./infra/backup/restore.sh
  backup:verify:
    desc: Restore-drill — verify the latest dump restores into a throwaway instance (needs docker + the age identity).
    cmds:
      - ./infra/backup/restore_drill.sh
```

- [ ] **Step 6: chmod + run the render test**

```bash
chmod +x src/framework_cli/template/infra/backup/restore.sh src/framework_cli/template/infra/backup/restore_drill.sh
uv run pytest tests/test_copier_runner.py::test_restore_and_drill_render -q
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/infra/backup/restore.sh src/framework_cli/template/infra/backup/restore_drill.sh \
        src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git commit -m "feat(FWK133): guarded restore + restore-drill (task restore / backup:verify)"
```

---

## Task 6: systemd timer units + runbook + `.gitignore`

**Files:**
- Create: `src/framework_cli/template/infra/backup/{{ project_slug }}-backup.service.jinja`.
- Create: `src/framework_cli/template/infra/backup/{{ project_slug }}-backup.timer.jinja`.
- Create: `src/framework_cli/template/infra/backup/README.md.jinja`.
- Modify: `src/framework_cli/template/.gitignore`.
- Test: `tests/test_copier_runner.py`.

**Interfaces:**
- Produces: a disabled-by-default oneshot service + daily timer the operator enables, and the runbook documenting key custody / `/mnt` wiring / RPO-RTO / restore.

- [ ] **Step 1: Write the failing render test**

```python
def test_systemd_units_and_runbook_render(tmp_path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": []})
    svc = dest / "infra/backup/demo-backup.service"
    tmr = dest / "infra/backup/demo-backup.timer"
    readme = dest / "infra/backup/README.md"
    assert svc.is_file() and tmr.is_file() and readme.is_file()
    assert "ExecStart=" in svc.read_text()
    assert "OnCalendar=" in tmr.read_text()
    r = readme.read_text()
    for token in ("BACKUP_DEST", "age", "RPO", "RTO", "systemctl"):
        assert token in r, f"runbook missing {token}"
    assert "backups/" in (dest / ".gitignore").read_text()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_systemd_units_and_runbook_render -q`
Expected: FAIL — units/readme missing.

- [ ] **Step 3: Create the service unit (`{{ project_slug }}-backup.service.jinja`)**

```ini
[Unit]
Description=Encrypted backup of the {{ project_name }} stack
Documentation=file:%h/{{ project_slug }}/infra/backup/README.md

[Service]
Type=oneshot
WorkingDirectory=%h/{{ project_slug }}
# Load BACKUP_* from the project .env (edit the path if your checkout lives elsewhere).
EnvironmentFile=%h/{{ project_slug }}/.env
ExecStart=%h/{{ project_slug }}/infra/backup/backup.sh
```

- [ ] **Step 4: Create the timer unit (`{{ project_slug }}-backup.timer.jinja`)**

```ini
[Unit]
Description=Daily encrypted backup of the {{ project_name }} stack

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 5: Create the runbook (`README.md.jinja`)**

```markdown
# Backups & recovery

Encrypted, battery-aware backups of every durable store this stack runs. **Core capability**
(Postgres ships base) — `task backup` always backs up Postgres; Mongo is added when the
`mongodb` battery is on; AGE / TimescaleDB / pgvector data lives in Postgres and is restored
extension-correctly by the drill. Redis + observability stores are rebuildable and not backed up.

## One-time setup
1. **Install `age`** (single static binary): `apt install age` (or from github.com/FiloSottile/age).
2. **Generate a keypair:** `age-keygen -o ~/.config/{{ project_slug }}/backup-identity.txt`.
   It prints the **public** key (`age1...`).
3. **Configure `.env`:** set `BACKUP_PUBKEY=age1...`, `BACKUP_IDENTITY=~/.config/{{ project_slug }}/backup-identity.txt`,
   and `BACKUP_DEST` to your off-box destination (this box: a Google-Drive-synced folder under `/mnt`).
4. **Custody the PRIVATE key OFF the box** (password manager / a second location). **Losing it makes
   every off-box backup unrecoverable** — this is interim custody until secrets-backing (FWK85) lands.
5. **Verify the whole chain now:** `task backup && task backup:verify`. The drill decrypts + restores
   into a throwaway DB; if your key is wrong it fails *here*, not during a real recovery.

## Schedule it (operator-wired, disabled by default)
```bash
mkdir -p ~/.config/systemd/user
cp infra/backup/{{ project_slug }}-backup.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now {{ project_slug }}-backup.timer   # nightly 02:00
```
(Run `loginctl enable-linger $USER` so the timer fires while you're logged out.)

## Recovery
- **Drill (safe, non-destructive):** `task backup:verify`.
- **Restore into the live stack (DESTRUCTIVE):** `task restore` (asks for typed confirmation).

## RPO / RTO
- **RPO ≈ 24h** (nightly timer) — at most a day of data lost.
- **RTO ≈ minutes** — `task restore` from the latest decrypted dump.

Durability layers on this box: dump → `/mnt/<gdrive>` (Windows host, survives a WSL-VM reset) →
Google Drive sync (off-machine, survives host loss).
```

- [ ] **Step 6: Ignore the local backups dir**

Append to `src/framework_cli/template/.gitignore`:

```gitignore
# local backup dumps (default BACKUP_DEST)
backups/
```

- [ ] **Step 7: Run the render test**

Run: `uv run pytest tests/test_copier_runner.py::test_systemd_units_and_runbook_render -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/template/infra/backup/ src/framework_cli/template/.gitignore tests/test_copier_runner.py
git commit -m "feat(FWK133): systemd timer units + backup runbook + gitignore backups/"
```

---

## Task 7: Battery-aware Mongo store (`store` disposition exercised)

**Files:**
- (No new template files — `backup.sh`/`restore.sh`/`prune.sh` already carry the `{% if "mongodb" %}` branches from Tasks 3–5.)
- Test: `tests/test_copier_runner.py` (mongo render assertions) + the completeness gate already covers it.

**Interfaces:**
- Consumes: the `mongodb` battery render (adds `mongodata` + a `mongo` service).
- Produces: confirmation that a `store` battery's volume is dumped (`BACKUP-STORES` lists `mongo`) and round-trips (Task 10).

- [ ] **Step 1: Write the failing render test**

```python
def test_mongo_store_is_in_backup_when_present(tmp_path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})
    backup = (dest / "infra/backup/backup.sh").read_text()
    assert "# BACKUP-STORES: postgres mongo" in backup
    assert "mongodump" in backup
    assert "mongorestore" in (dest / "infra/backup/restore.sh").read_text()
```

- [ ] **Step 2: Run to verify it passes (branches landed in Tasks 3–5)**

Run: `uv run pytest tests/test_copier_runner.py::test_mongo_store_is_in_backup_when_present tests/test_backup_completeness.py -k mongodb -q`
Expected: PASS — the `store` gate finds `mongo` in `BACKUP-STORES`. If it FAILS, the `{% if "mongodb" %}` branch or the manifest line is wrong; fix `backup.sh`.

- [ ] **Step 3: Commit (only if the test required a fix; otherwise skip)**

```bash
git add tests/test_copier_runner.py
git commit -m "test(FWK133): mongo store is backed up when the mongodb battery is present"
```

---

## Task 8: Battery-aware Postgres extensions (AGE / TimescaleDB / pgvector restore-correctness)

**Files:**
- (Drill branches already in `restore_drill.sh` from Task 5.)
- Test: `tests/test_copier_runner.py` (extension drill assertions).

**Interfaces:**
- Consumes: `age` / `timescaledb` / `pgvector` renders (build the extension `postgres.Dockerfile`).
- Produces: confirmation the drill restores extension-correctly (AGE `CREATE EXTENSION ... LOAD` before data; TimescaleDB pre/post-restore hooks; pgvector via the extension image). Behaviour proven in Task 10.

- [ ] **Step 1: Write the failing render test**

```python
import pytest

@pytest.mark.parametrize("battery,needle", [
    ("age", "CREATE EXTENSION IF NOT EXISTS age"),
    ("timescaledb", "timescaledb_pre_restore()"),
    ("timescaledb", "timescaledb_post_restore()"),
])
def test_extension_drill_has_correct_dance(tmp_path, battery, needle):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": [battery]})
    drill = (dest / "infra/backup/restore_drill.sh").read_text()
    assert needle in drill, f"{battery} drill missing {needle!r}"
    # pgvector needs no SQL dance — just the extension image, asserted by the completeness gate.
    assert "shared_preload_libraries" in drill or battery == "pgvector"
```

- [ ] **Step 2: Run to verify it passes (branches landed in Task 5)**

Run: `uv run pytest "tests/test_copier_runner.py::test_extension_drill_has_correct_dance" -q`
Expected: PASS. If FAIL, the `{% if "age" %}` / `{% if "timescaledb" %}` branches in `restore_drill.sh` are missing the SQL — fix them.

- [ ] **Step 3: Confirm pgvector restore-correctness via the gate**

Run: `uv run pytest tests/test_backup_completeness.py -k "pgvector or age or timescaledb" -q`
Expected: PASS — each `postgres-extension` battery builds `postgres.Dockerfile` (the gate's assertion), so the drill's throwaway image has the extension.

- [ ] **Step 4: Commit**

```bash
git add tests/test_copier_runner.py
git commit -m "test(FWK133): extension-correct restore-drill (AGE load-order, timescale pre/post-restore)"
```

---

## Task 9: Execution gate — baseline Postgres round-trip (acceptance, docker)

**Files:**
- Create: `tests/acceptance/test_backup_drill.py`.
- Modify: `tests/test_test_tiers.py` (register the new acceptance file as a documented fast-tier exception).

**Interfaces:**
- Consumes: the rendered baseline project; docker; `age` on the host.
- Produces: proof that `backup.sh` → encrypted dump → `restore_drill.sh` actually round-trips real Postgres data.

- [ ] **Step 1: Write the acceptance test**

```python
# tests/acceptance/test_backup_drill.py
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from framework_cli.copier_runner import render_project

DATA = {"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"}


def _tools_available() -> bool:
    return all(shutil.which(t) for t in ("docker", "age", "age-keygen", "uv")) and (
        subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
    )


pytestmark = pytest.mark.skipif(not _tools_available(), reason="needs docker + age + uv")


def _sh(cmd, cwd, env=None, check=True):
    return subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})},
                          capture_output=True, text=True, check=check)


@pytest.fixture
def project(tmp_path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": []})
    # age keypair
    ident = tmp_path / "id.txt"
    kg = _sh(["age-keygen", "-o", str(ident)], cwd=tmp_path)
    pub = next(l.split(": ")[1].strip() for l in kg.stderr.splitlines() if "public key" in l)
    env = {"BACKUP_DEST": str(tmp_path / "backups"), "BACKUP_PUBKEY": pub,
           "BACKUP_IDENTITY": str(ident), "UID": str(os.getuid()), "GID": str(os.getgid()),
           "COMPOSE_PROJECT_NAME": f"bkdrill{os.getpid()}"}
    yield dest, env
    _sh(["./scripts/compose.sh", "-f", "infra/compose/base.yml", "-f", "infra/compose/dev.yml",
         "--profile", "lite", "down", "-v"], cwd=dest, env=env, check=False)


def test_baseline_backup_drill_round_trips(project):
    dest, env = project
    up = ["./scripts/compose.sh", "-f", "infra/compose/base.yml", "-f", "infra/compose/dev.yml",
          "--profile", "lite", "up", "-d", "--wait", "postgres"]
    _sh(up, cwd=dest, env=env)
    # seed a row the drill can later see (alembic table is created by migrations on app boot; here
    # we assert pg_dump/restore of a known marker table survives the encrypt->decrypt->restore chain).
    _sh(["./scripts/compose.sh", "exec", "-T", "postgres", "psql", "-U", "app", "-d", "app",
         "-c", "CREATE TABLE alembic_version(version_num varchar primary key); "
               "INSERT INTO alembic_version VALUES ('drill-marker');"], cwd=dest, env=env)
    _sh(["./infra/backup/backup.sh"], cwd=dest, env=env)
    dumps = list((Path(env["BACKUP_DEST"])).glob("demo-postgres-*.dump.age"))
    assert dumps, "no encrypted dump produced"
    drill = _sh(["./infra/backup/restore_drill.sh"], cwd=dest, env=env, check=False)
    assert drill.returncode == 0, f"drill failed:\n{drill.stdout}\n{drill.stderr}"
    assert "restore-drill OK" in drill.stdout
```

- [ ] **Step 2: Run it (docker required; sandbox off, `TMPDIR=/var/tmp`)**

Run: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_backup_drill.py::test_baseline_backup_drill_round_trips -q`
Expected: PASS (skips cleanly if docker/age absent).

- [ ] **Step 3: Register the acceptance file as a documented fast-tier exception**

In `tests/test_test_tiers.py`, add the new file to `ACCEPTANCE_DOCKER_EXCEPTIONS` with its reason (mirror the existing entries):

```python
    "tests/acceptance/test_backup_drill.py":
        "docker + age round-trip of the encrypted backup/restore-drill; heavy + dind-flaky, full tier only",
```

- [ ] **Step 4: Run the tier guard**

Run: `uv run pytest tests/test_test_tiers.py -q`
Expected: PASS (the new `--ignore` is documented; fast tier and CI gate stay in sync).

- [ ] **Step 5: Commit**

```bash
git add tests/acceptance/test_backup_drill.py tests/test_test_tiers.py
git commit -m "test(FWK133): acceptance drill — baseline postgres backup round-trips (full tier)"
```

---

## Task 10: Execution gate — all-batteries (Mongo + extensions) round-trip + docs

**Files:**
- Modify: `tests/acceptance/test_backup_drill.py` (add the all-batteries case).
- Create: `docs/maintenance/backups.md`.

**Interfaces:**
- Consumes: an all-data-batteries render (`mongodb`, `age`, `timescaledb`, `pgvector`, `redis`).
- Produces: proof the battery-aware paths (mongodump + extension-correct restore) round-trip; the maintainer coverage contract.

- [ ] **Step 1: Add the all-batteries drill case**

```python
def test_all_data_batteries_backup_drill_round_trips(tmp_path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb", "age", "timescaledb", "pgvector", "redis"]})
    ident = tmp_path / "id.txt"
    kg = _sh(["age-keygen", "-o", str(ident)], cwd=tmp_path)
    pub = next(l.split(": ")[1].strip() for l in kg.stderr.splitlines() if "public key" in l)
    env = {"BACKUP_DEST": str(tmp_path / "backups"), "BACKUP_PUBKEY": pub, "BACKUP_IDENTITY": str(ident),
           "UID": str(os.getuid()), "GID": str(os.getgid()), "COMPOSE_PROJECT_NAME": f"bkall{os.getpid()}"}
    files = ["-f", "infra/compose/base.yml", "-f", "infra/compose/dev.yml"]
    try:
        _sh(["./scripts/compose.sh", *files, "--profile", "lite", "up", "-d", "--wait", "--build",
             "postgres", "mongo"], cwd=dest, env=env)
        _sh(["./scripts/compose.sh", "exec", "-T", "postgres", "psql", "-U", "app", "-d", "app",
             "-c", "CREATE EXTENSION IF NOT EXISTS age; CREATE EXTENSION IF NOT EXISTS timescaledb; "
                   "CREATE EXTENSION IF NOT EXISTS vector; "
                   "CREATE TABLE alembic_version(version_num varchar primary key); "
                   "INSERT INTO alembic_version VALUES ('drill-marker');"], cwd=dest, env=env)
        _sh(["./infra/backup/backup.sh"], cwd=dest, env=env)
        assert list(Path(env["BACKUP_DEST"]).glob("demo-mongo-*.archive.gz.age")), "no mongo dump"
        drill = _sh(["./infra/backup/restore_drill.sh"], cwd=dest, env=env, check=False)
        assert drill.returncode == 0, f"drill failed:\n{drill.stdout}\n{drill.stderr}"
    finally:
        _sh(["./scripts/compose.sh", *files, "--profile", "lite", "down", "-v"], cwd=dest, env=env, check=False)
```

- [ ] **Step 2: Run it**

Run: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_backup_drill.py -q`
Expected: PASS (both cases; skips without docker/age). If the extension drill fails, fix the SQL dance in `restore_drill.sh` (Task 5/8) and re-run.

- [ ] **Step 3: Write the maintainer coverage contract `docs/maintenance/backups.md`**

```markdown
# Backups — coverage contract

Backups are a **base scaffold capability** (Postgres is base → recovery is base). `task backup`
dumps every active durable store (age-encrypted) to `$BACKUP_DEST`; `task backup:verify` drills the
restore; `task restore` recovers the live stack. Operator-wired systemd timer (disabled by default).

## The gate (why a store can't be silently unbacked)
- **Static (fast tier), `tests/test_backup_completeness.py`:** renders each battery and scrapes the
  named volumes ↔ its `BatterySpec.data` disposition. A new battery that adds a volume with no
  declared disposition (`store` dumped / `rebuildable` skipped / `postgres-extension` no-volume)
  **fails the build**. Mandatory registration test for any data-persistence battery.
- **Execution (full tier), `tests/acceptance/test_backup_drill.py`:** actually round-trips
  baseline + all-data-batteries through encrypt → decrypt → restore into the battery-correct image.

## Per-store handling
| Store / battery | `data` | Method |
|---|---|---|
| Postgres (base) | core | `pg_dump -Fc` / `pg_restore` |
| `mongodb` | `store` | `mongodump`/`mongorestore` |
| `age` / `timescaledb` / `pgvector` | `postgres-extension` | restored into the extension image (AGE load-order; timescale pre/post-restore hooks) |
| `redis` / `workers` | `rebuildable` | broker/cache — not backed up |
| `react` | `rebuildable` | build cache — not backed up |
| obs (loki/prom/tempo) | rebuildable (base) | retention-bounded telemetry |

## Interim & follow-ups
- age key custody is **interim** (identity-on-box + off-box DR copy) — superseded by **FWK85**
  (secrets-backing); only the key-fetch seam changes.
- **FWK134** encryption-at-rest, **FWK135** container log rotation — separate rows.
```

- [ ] **Step 4: Branch-end full gate**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && task test:fast`
Then: `TMPDIR=/var/tmp task test:full` (adds the docker acceptance incl. the two drills).
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/acceptance/test_backup_drill.py docs/maintenance/backups.md
git commit -m "test(FWK133): all-batteries restore-drill + backups coverage-contract doc"
```

---

## Self-Review

**Spec coverage** (spec §→task):
- §4 flow / task targets → Tasks 3 (backup), 4 (prune), 5 (restore + drill). ✔
- §4 config (`BACKUP_*`) → Task 3 Step 5. ✔
- §4 scheduling (systemd, disabled) → Task 6. ✔
- §4 `age` host prereq → Task 6 runbook Step 5. ✔
- §5 encryption + interim key custody + drill-decrypts-loudly → Tasks 3/5 (age pipe + drill), 6 (runbook custody), 9 (real key round-trip). ✔
- §6 declared `data` surface → Task 1; §6 per-store table (AGE/timescale/pgvector/mongo/redis/obs) → Tasks 3/5/7/8 + gate. ✔
- §7 two-layer gate → Task 2 (static) + Tasks 9/10 (execution). ✔
- §8 file layout → File Structure + each task. ✔
- §9 testing (template-payload loop, fast static, full drill, eval-fixture) → Tasks 2/3 (render + eval realizer) + 9/10. ✔
- §10 RPO/RTO → Task 6 runbook. ✔
- §11 follow-ups (FWK85 driver / FWK134 / FWK135) → already filed in PLAN.md (#0403); restated in Task 10 doc. ✔
- §12 decisions (core-not-battery, encryption day 1, backups-now) → reflected throughout. ✔

**Placeholder scan:** every code step carries real content. The one intentional staged item — Task 2's `skipif` on `test_base_postgres_is_core_backed_up` — is explicitly flipped to hard in Task 3 Step 6.

**Type consistency:** `DataSurface = Literal["none","store","rebuildable","postgres-extension"]` defined in Task 1 and used identically by Task 2's gate and Task 10's doc table. `BACKUP_DEST`/`BACKUP_PUBKEY`/`BACKUP_IDENTITY`/`BACKUP_RETENTION_DAILY`/`BACKUP_RETENTION_WEEKLY` names match across `.env` (Task 3), scripts (Tasks 3–5), units (Task 6), and tests (Tasks 9–10). The `# BACKUP-STORES:` manifest format is produced in Task 3 and parsed identically in Task 2. Dump filename pattern `{{ project_slug }}-<store>-<utc-ts>.(dump|archive.gz).age` is consistent across backup/prune/restore/drill.

**Note for the implementer:** the bash drill (Task 5) is the most intricate file; its correctness is *proven* by the docker acceptance tests (Tasks 9–10), so iterate there if a round-trip fails rather than reasoning about the script in isolation.
