# Battery Mechanism — Additive (Plan 8a-1) — Design Spec

**Date:** 2026-05-24
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 6b (the repo-root `copier.yml` + `_subdirectory`/`_exclude`, `render_project`, `record_portable_source`, `framework upskill`/`run_update`), Plan 6a-2 (the `FRAMEWORK:BEGIN/END` hybrid managed sections), Plan 7b (the review `registry.py` with `active_when="battery"`). First sub-project of Plan 8.

---

## 1. Purpose & scope

Generated projects today are single-shape: every project gets the same scaffold. The framework design (§8) calls for **batteries** — optional capability bundles activated at scaffold time (`framework new --with <battery>`) and added later (`framework upskill --with <battery>`). 8a-1 builds the **additive** mechanism: battery selection, conditional rendering, the battery registry, the recorded battery set, and conditional review-agent gating — proven end-to-end with one small vehicle battery (**websockets**).

**In scope:**
- A CLI-side **battery registry** (`batteries.py`): valid batteries, their dependencies/implications, and the review agent each gates.
- **`framework new --with <battery>`** (repeatable, non-interactive) + **`framework upskill --with <battery>`** (add to an existing project), validated + dependency-resolved against the registry.
- **Conditional rendering** driven by a list-valued `batteries` Copier answer (`{% if "<b>" in batteries %}` in templated paths / files).
- A **router-autodiscovery convention** in the always-on base app, so route-adding batteries are purely additive files (no shared-file edit).
- Recording the resolved battery set in `.copier-answers.yml` (framework-owned), surfaced to `review-data-integrity`/`review-data-lineage`.
- Conditional review-agent gating (`active_when="battery"`).
- The **websockets** vehicle battery.

**Out of scope (deferred):**
- **Battery removal** (`--downskill`/`--without`) + usage-detection → **Plan 8a-2**.
- The other batteries → **8b–8h**; the database **paradigm batteries + wizard** → **8f**; interactive selection prompts → the wizard work.
- **Managed-section injection** for batteries that must modify shared files (deps/services/settings) → defined here as the approach, but **not exercised by 8a-1** (websockets needs none); first used by a battery that adds a dependency/service (e.g. `workers`/8c).

## 2. Decisions (settled in brainstorm)

- **Flag-driven, non-interactive selection** (`--with`), preserving today's non-interactive `framework new`; interactive prompts deferred to the wizard work.
- **websockets** is the 8a-1 vehicle (no dependency, no service → isolates the mechanism).
- **Additive-by-convention first** (router autodiscovery makes route batteries pure file-adds); **managed `FRAMEWORK:BEGIN/END` sections** reserved for the unavoidable shared-file changes later batteries need.
- **The framework owns the battery-set record** in `.copier-answers.yml` (extending `record_portable_source`), not Copier's multiselect serialization — so it's the single source of truth `upskill --with` appends to and `--downskill` (8a-2) reads.
- **Relational (PostgreSQL) stays always-on, not a battery**; the recorded battery set is the *additional* paradigm/store declaration fed to the data agents (per the meta-plan Plan 8 sub-slicing).
- A **CLI-side `batteries.py` registry** is the single source of truth for valid batteries, dependencies, and agent gating (mirroring the review `registry.py`).
- **Spike-validated** (controller spike): a list `batteries` answer drives conditional file rendering, conditional directory rendering, and in-file injection; the real (git) template writes `.copier-answers.yml`.

## 3. The battery registry — `src/framework_cli/batteries.py`

```python
@dataclass(frozen=True)
class BatterySpec:
    name: str                      # the token used in templates + --with (e.g. "websockets")
    summary: str                   # one line, for --help / errors
    requires: tuple[str, ...] = () # batteries this one implies (e.g. pgvector -> ("postgres",) later)
    gates_agent: str | None = None # review agent activated when present (e.g. graphql -> "api-design")
```

- `_BATTERIES: dict[str, BatterySpec]` — 8a-1 registers **`websockets`** (`requires=()`, `gates_agent=None`). Future batteries are added here.
- `battery_names() -> list[str]` (sorted), `get_battery(name) -> BatterySpec` (raises `KeyError` on unknown).
- **`resolve(selected: Iterable[str]) -> list[str]`** — validate each name (unknown → `ValueError` naming it), compute the dependency-closure over `requires` (deterministic, sorted), return the closed set. This is what both `--with` and the future wizard call so direct and guided selection produce identical sets.
- Battery → agent gating is *declared here* (`gates_agent`); the review `registry.py` already supports `active_when="battery"`, so 8a-1 only needs to connect "is this agent's battery in the project's set?" (the agent activation reads the recorded battery set — §6).

## 4. Selection & the CLI

- **`framework new <name> --with <battery>`** — `with_: list[str] = typer.Option([], "--with")` (repeatable). Resolve via `resolve(with_)`; on `ValueError`, echo a clear error + `Exit(1)`. Pass the resolved list to the render as the `batteries` answer (§5). Non-interactive (no Copier prompt — the answer is pre-seeded).
- **`framework upskill <project> --with <battery>`** — read the project's current battery set from `.copier-answers.yml` (§6), union with `resolve(--with)`, re-run the Copier update (the 6b `run_update` path) with the new `batteries` answer, then re-record the set + run `task test` (existing upskill behavior). Adding a battery is additive (new files appear; the autodiscovery convention wires routers with no merge conflict).
- `--with` with no batteries is the current default behavior (empty set; identical to today's output).

## 5. Conditional rendering

- **`render_project(dest, data)`** gains `batteries` in `data` (a `list[str]`); `framework new` passes the resolved set. Default `[]` (unchanged output).
- **Battery files are additive**, included via **templated paths** conditioned on the set — the spike-proven idioms:
  - a conditional file: a templated filename that renders empty when the battery is absent → Copier skips it;
  - a conditional directory: a templated dir name → the whole dir is included/skipped.
- **Router autodiscovery (the base-app change).** Today `main.py` does `from .routes import health, items` + an explicit `app.include_router(...)` per router. Replace that with a discovery helper (e.g. `routes/__init__.py: include_routers(app)`) that imports every module in the `routes/` package (sorted, deterministic) and includes its `router` attribute when present. Then a route battery is **purely additive**: it drops `routes/websockets.py` (templated path gated on the battery) exposing `router`, and it's auto-included — `main.py` is untouched. This is an always-on base-scaffold change (every generated project), and it's what makes route batteries cleanly additive and trivially removable in 8a-2.
- **Unavoidable shared-file changes** (a later battery adding a dependency to `pyproject.toml`, a service to `compose`, or a field to `settings`) use the **6a-2 managed `FRAMEWORK:BEGIN/END` section** in that file with an in-section `{% if "<b>" in batteries %}` block — tamper-evident, upskill-safe, and the framework owns the region. **8a-1 does not exercise this** (websockets needs no such change); it is specified so 8c+ has the pattern.

## 6. Recording the battery set

- The framework writes the resolved `batteries` set into `.copier-answers.yml` as the single source of truth — extend `source.record_portable_source` (which already rewrites `_src_path`/`_commit`) to also (re)write a `batteries:` entry from the resolved set. This avoids depending on Copier's multiselect serialization and gives `upskill --with` (append) and `--downskill` (8a-2, remove) a stable record to read.
- **Surfaced to the data agents:** `review-data-integrity` and `review-data-lineage` read the recorded battery set (the *additional* paradigm/store declaration, atop always-on relational) as context for "cross-paradigm writes with no consistency strategy" / "data flows across all stores". 8a-1 records the set and documents the contract; richer per-paradigm context arrives with 8f.

## 7. The websockets vehicle battery

- **Files (additive, gated on `"websockets" in batteries`):**
  - `routes/websockets.py` — an `APIRouter` with a `@router.websocket("/ws")` endpoint using the connection manager. Auto-included via §5's convention; no `main.py` edit.
  - `connection_manager.py` (e.g. under `src/{{package_name}}/websockets/`) — a minimal connection registry (connect/disconnect/broadcast).
  - A test (`tests/.../test_websockets.py`) exercising connect + echo/broadcast via `fastapi.testclient`'s WebSocket support.
- **No dependency** (FastAPI/Starlette WebSockets are built in), **no compose service** — so the battery touches zero shared files; it is the clean proof of the additive path.

## 8. Review-agent gating

- `active_when="battery"` agents (none in 8a-1's registered set — websockets gates none) activate only when their `gates_agent` battery is in the project's recorded set. The plumbing: the agent-activation path (CI `review-agents` / `active_agents`) consults the recorded battery set. 8a-1 wires the *connection* (battery set → agent gating) but registers no battery-gated agent yet (those land with graphql/8d and react/8g). The 7d eval harness auto-covers a battery agent once it's registered + given fixtures.

## 9. Testing

- **`batteries.py` registry (hermetic):** `resolve` validates unknown names (raises naming the battery), computes the dependency closure deterministically, returns sorted; `battery_names`/`get_battery`.
- **CLI (hermetic, `CliRunner`):** `framework new --with websockets` renders the battery files; `framework new` (no `--with`) renders identically to today (no battery files); `--with bogus` → exit 1 with a clear error.
- **Conditional render (`tests/test_copier_runner.py`):** render with `batteries=["websockets"]` → `routes/websockets.py` + the connection manager exist; render with `[]` → they don't, and `main.py`/route set is unchanged.
- **Router autodiscovery:** the rendered base app includes all `routes/` routers (health, items) via the convention — a unit test of `include_routers` over a package fixture, plus the acceptance suite confirming the live app still serves `/health` + `/items`.
- **Answers record:** after `framework new --with websockets`, `.copier-answers.yml` records `batteries: [websockets]`; `upskill --with` unions correctly.
- **Acceptance (Docker):** a **with-websockets variant** renders, lints, type-checks, and its own suite passes (the WS endpoint test runs green); the default (no-battery) variant stays green by construction.
- **Generated-project cleanliness:** a freshly generated project (both variants) makes a clean first `pre-commit` pass.

## 10. Self-review

- **Placeholders:** none — the registry shape, `--with` flow, the conditional-render idioms (spike-proven), the router-autodiscovery convention (grounded in the actual `routes/` + `main.py` structure), the answers-record extension, the websockets files, and the tests are concrete. Managed-section injection is specified as the pattern but explicitly not exercised in 8a-1 (YAGNI — first real use is 8c).
- **Internal consistency:** `resolve` is the one selection-resolution path for both `--with` and the future wizard; the framework-owned answers record is what `upskill --with`/`--downskill` read; additive-by-convention is why removal (8a-2) is "delete files"; relational stays always-on (the recorded set is the *additional* declaration).
- **Scope:** one cohesive subsystem (select → resolve → render additively → record → gate). Removal, the other batteries, the wizard, and managed-section injection are deferred.
- **Ambiguity:** "interactive" is pinned to deferred (8a-1 is flag-only); "battery touches a shared file" is split into the additive/autodiscovery path (8a-1) vs. the managed-section path (later); the battery record lives in `.copier-answers.yml`, framework-owned.

---

*End of design. Next step: `superpowers:writing-plans` for Plan 8a-1.*
