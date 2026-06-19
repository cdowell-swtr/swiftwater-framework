# FWK7 — full reverse integrity-coverage check + battery-infra classification — design

> **Date:** 2026-06-18 · **Status:** approved (brainstorm) · **Ships in:** next release (test/integrity-infra; the new manifest behavior ships on the next cut)
> **Spec for:** the FWK7 framework slice. Plan to follow via writing-plans.

## Context

The integrity classification in `src/framework_cli/integrity/classes.py` is **one-directional**:
tests assert every *registered* path exists in a render (no stale entries), but nothing asserts
every *framework-infra* file is registered. A new framework-managed file therefore escapes
integrity coverage silently until someone lists it. FWK7 (Plan 30 in the frozen meta-plan) is the
reverse check that closes this gap, paired with the per-file classification audit it forces.

This was deliberately deferred from the v0.2.4 lock-taxonomy slice
(`docs/superpowers/specs/2026-06-12-lock-taxonomy-and-doctor-design.md`), which added the
`INTENTIONALLY_UNLOCKED` tuple precisely so this future check would have an allowlist to consume.
That slice estimated **23 unclassified files**; an all-batteries render on 2026-06-18 measured
**29** (more batteries since; FWK6 added `infra/tls/ca/.gitkeep`; FWK31 added `scripts/compose.sh`).

**The check earns its keep immediately:** the audit found `scripts/compose.sh` (FWK31, a baseline
framework-owned PORT_OFFSET wrapper) had escaped `LOCKED_TRACKED` — exactly the silent-escape class
this check exists to catch.

### Ground-truth measurement (all-batteries render, 2026-06-18)

Surface roots scanned: `infra/`, `scripts/`, `.github/workflows/`. 75 files total, 46 already
classified, **29 unclassified**, splitting cleanly into three buckets:

- **5 baseline escapees** (render in a *baseline* project; framework-owned; belong in `LOCKED_TRACKED`):
  `scripts/compose.sh`, and the static obs files
  `infra/observability/grafana/dashboards/otel-collector.json`,
  `infra/observability/grafana/dashboards/prometheus.json`,
  `infra/observability/prometheus/alerts/otel_collector_alerts.yml`,
  `infra/observability/prometheus/alerts/prometheus_alerts.yml`.
- **22 battery-conditional** framework-owned files (present only when a gating battery is active;
  see the gate table below).
- **2 placeholders** with no content to checksum: `infra/traefik/certs/.gitkeep`,
  `infra/tls/ca/.gitkeep`.

A correction to the v0.2.4 spec's framing: the battery observability dashboards/alerts are **not**
regenerated at consumer time by `gen_observability.py` (that script writes only the SLO pair,
`slo.json` / `slo_alerts.yml`). They are **hand-authored static `.jinja` payload** with conditional
filenames (e.g. `{{ 'redis.json' if ('redis' in batteries or 'workers' in batteries) else '' }}.jinja`),
rendering to stable committed files — exactly the same nature as their **locked** base siblings
`postgres.json` / `postgres_alerts.yml`. They are therefore cleanly checksummable, and the
consistent decision is to **lock** them (otherwise `postgres_alerts.yml` is locked but
`redis_alerts.yml` is not, for two files of identical origin).

## Principle

Locks earn their keep on **invariant framework infrastructure** the framework fixes once and
protects everywhere; they are the wrong tool for **composition seams** a project is invited to
replace (recorded in `INTENTIONALLY_UNLOCKED`). FWK7 does not relitigate that line — every one of
the 29 files is framework-owned infra or an empty placeholder, none is a composition seam. The work
is to (a) make these files *trackable despite being battery-conditional*, and (b) build the
standing check that prevents the next escapee.

## Goals

- **Classify all 29 unclassified infra-surface files** into the right category.
- **Add a battery-gated lock mechanism** so battery-conditional framework files are checksummed in
  the projects that have them, without breaking `LOCKED_TRACKED`'s "present in a baseline render"
  invariant.
- **Build the reverse-coverage check**: a `gate`-tier test that fails if any file under the scanned
  surface roots is unclassified, with an **extensibility seam** so the scanned roots can be widened
  later without re-architecting (scope decision: tight-now-plus-seam).
- **Anti-stale symmetry**: assert no registered battery-locked / exempt path has rotted out of the
  render.

## Non-goals / Deferred work

- **Widening the scanned surface roots beyond `infra/`, `scripts/`, `.github/workflows/`.** Policing
  the *whole* render tree reopens the fuzzy "framework-managed vs builder space" boundary
  (`src/{{package_name}}/` app code, `docs/`, `tests/` are builder-owned) that the integrity system
  answers file-by-file today. Out of scope; the `_SURFACE_ROOTS` seam makes a future widening a
  one-line change plus its own audit.
- **Version-floor / content-policy checks** on the classified files — FWK7 answers "is it
  classified," not "is its content still correct beyond the checksum."
- **Refactoring `Rule` into a unified battery-predicate model** (the brainstorm's Option 2). The
  additive `BATTERY_LOCKED` dict is the minimal change; folding all classes into one predicate-bearing
  `rules()` list touches every consumer of the flat `LOCKED_TRACKED` tuple for no functional gain.

## Design

### 1. Data model (`src/framework_cli/integrity/classes.py`)

**`scripts/compose.sh` + the 4 static obs escapees → appended to `LOCKED_TRACKED`.** They render in a
baseline project, so they satisfy the existing "present in a baseline render" invariant as-is.

**New `EXEMPT: tuple[str, ...]`** — framework-shipped files with no content to checksum, recorded
explicitly (like `INTENTIONALLY_UNLOCKED`) so the reverse check can tell "deliberately uncovered"
from "escaped":

```python
# Framework-shipped placeholders with no checksummable content (empty .gitkeep files that only
# exist to keep an otherwise-empty directory in git). Recorded so the reverse-coverage check can
# distinguish "deliberately uncovered" from "a framework file that escaped classification".
EXEMPT: tuple[str, ...] = (
    "infra/traefik/certs/.gitkeep",  # local-TLS cert dir placeholder
    "infra/tls/ca/.gitkeep",         # FWK6 CA-bundle dir placeholder
)
```

**New `BATTERY_LOCKED: dict[str, tuple[str, ...]]`** — rendered path → the batteries that gate it.
The lock applies when **any** listed battery is active (matching the jinja `or` conditionals). Gates
are transcribed directly from the template's conditional filenames (single source of truth):

| Path (under the rendered project root) | Gate (`tuple`) |
|---|---|
| `infra/observability/grafana/dashboards/agents.json` | `("agents",)` |
| `infra/observability/prometheus/alerts/agents_alerts.yml` | `("agents",)` |
| `infra/observability/grafana/dashboards/frontend.json` | `("react",)` |
| `infra/observability/prometheus/alerts/frontend_alerts.yml` | `("react",)` |
| `infra/observability/grafana/dashboards/graphql.json` | `("graphql",)` |
| `infra/observability/prometheus/alerts/graphql_alerts.yml` | `("graphql",)` |
| `infra/observability/grafana/dashboards/llm.json` | `("llm",)` |
| `infra/observability/prometheus/alerts/llm_alerts.yml` | `("llm",)` |
| `infra/observability/grafana/dashboards/mongodb.json` | `("mongodb",)` |
| `infra/observability/prometheus/alerts/mongodb_alerts.yml` | `("mongodb",)` |
| `infra/observability/grafana/dashboards/redis.json` | `("redis", "workers")` |
| `infra/observability/prometheus/alerts/redis_alerts.yml` | `("redis", "workers")` |
| `infra/observability/grafana/dashboards/webhooks.json` | `("webhooks",)` |
| `infra/observability/prometheus/alerts/webhooks_alerts.yml` | `("webhooks",)` |
| `infra/observability/grafana/dashboards/websockets.json` | `("websockets",)` |
| `infra/observability/prometheus/alerts/websockets_alerts.yml` | `("websockets",)` |
| `infra/observability/grafana/dashboards/workers.json` | `("workers",)` |
| `infra/observability/prometheus/alerts/workers_alerts.yml` | `("workers",)` |
| `infra/docker/postgres.Dockerfile` | `("pgvector", "timescaledb", "age")` |
| `scripts/export-graphql-schema.sh` | `("graphql",)` |
| `scripts/pact-publish.sh` | `("consumers",)` |
| `.github/workflows/docs.yml` | `("docs",)` |

> `postgres.Dockerfile` is gated by the template's computed `uses_postgres_extension` flag, whose
> definition is `pgvector or timescaledb or age` (see `copier.yml`); the gate tuple lists those three
> batteries so the "any active" rule reproduces the flag.

**`rules()` gains a battery parameter:**

```python
def rules(batteries: Sequence[str] = ()) -> list[Rule]:
    """Baseline locked + hybrid + gitignored rules, plus battery-locked rules for any active battery.

    Default empty `batteries` reproduces the prior baseline-only behavior, so existing callers and
    the baseline render tests are unchanged.
    """
    active = set(batteries)
    locked = [Rule(p, "locked", "tracked") for p in LOCKED_TRACKED]
    battery = [
        Rule(p, "locked", "tracked")
        for p, gate in BATTERY_LOCKED.items()
        if active.intersection(gate)
    ]
    hybrid = [Rule(p, "hybrid", "tracked") for p in HYBRID_TRACKED]
    gitignored = [Rule(p, "locked", "gitignored") for p in GITIGNORED_EXISTENCE]
    return locked + battery + hybrid + gitignored
```

Update the `classes.py:13-18` header comment: the reverse check is no longer deferred; document
`BATTERY_LOCKED` and `EXEMPT` and the all-but-two-buckets-now-closed state.

### 2. Manifest integration (`src/framework_cli/integrity/generate.py`)

`build_manifest()` reads the project's own batteries and passes them to `rules()`:

```python
from framework_cli.source import read_batteries
...
def build_manifest(project: Path, framework_version: str) -> Manifest:
    batteries = read_batteries(project)
    ...
    for rule in rules(batteries):
        ...
```

A `--with redis` project then records `redis.json` / `redis_alerts.yml` in its `integrity.lock`; a
baseline project does not. **No checker change** — `checker.check()` is manifest-driven and already
battery-agnostic. The existing `AuthoringError` ("declared a framework file but was not rendered")
self-catches an *over*-broad gate: if a gate wrongly includes a file the active batteries don't
produce, manifest generation fails loudly at scaffold/upgrade time.

`read_batteries` returns `[]` for a project without a recorded battery list (e.g. a fixture lacking
`.copier-answers.yml`), which reproduces today's baseline behavior — safe.

### 3. The reverse check (`src/framework_cli/integrity/coverage.py` + `tests/integrity/test_coverage.py`)

A pure, unit-testable helper module:

```python
# integrity/coverage.py
_SURFACE_ROOTS: tuple[str, ...] = ("infra", "scripts", ".github/workflows")  # extensibility seam

def classified_paths() -> set[str]:
    return (
        set(LOCKED_TRACKED) | set(HYBRID_TRACKED) | set(GITIGNORED_EXISTENCE)
        | set(INTENTIONALLY_UNLOCKED) | set(BATTERY_LOCKED) | set(EXEMPT)
    )

def infra_surface_files(project: Path) -> list[str]:
    """Every file under the scanned surface roots, as project-root-relative posix paths."""
    ...

def unclassified_infra_files(project: Path) -> list[str]:
    return sorted(set(infra_surface_files(project)) - classified_paths())
```

`tests/integrity/test_coverage.py` (`gate` tier — render-only, no docker):

1. **Forward (the core check):** render **all batteries** (precedent:
   `tests/runtime_coverage/test_completeness.py` already renders all-batteries in the gate tier),
   assert `unclassified_infra_files(project) == []`. Failure message lists the escapees.
2. **Anti-stale, battery-locked:** every `BATTERY_LOCKED` path appears in an all-batteries render
   (no rotted entries).
3. **Anti-stale, exempt:** every `EXEMPT` path appears in an all-batteries render.
4. **Genuinely battery-gated:** every `BATTERY_LOCKED` path is **absent** from a baseline render
   (proves it is mis-filed neither as a baseline file nor here by mistake).

The two renders (all-batteries, baseline) are shared via module-scoped fixtures to keep the tier
fast.

### 4. `test_battery_locked_gating_is_accurate` (the under-lock guard)

The one silent failure mode the checks above miss is an **under-broad / wrong** gate: a path listed
in `BATTERY_LOCKED` with a gate that does not actually match the battery that produces it. Such a
file is still "classified" (forward check passes) and still appears in all-batteries (anti-stale
passes), but a real `--with <battery>` project would *not* lock it. This test closes that:

For each **distinct gate battery** appearing across `BATTERY_LOCKED`, render a project with **only
that battery** (`resolve([battery])` to pull implied deps), then assert, for every `BATTERY_LOCKED`
path whose gate contains that battery:

- the file **is present** in that single-battery render, **and**
- it lands in the built manifest — `rule paths from rules(read_batteries(project))` (equivalently,
  `build_manifest(...)` succeeds and the path is among its entries).

This is the **cost knob**: it adds roughly one baseline+1 render per distinct gate battery (~11).
These are cheaper than all-batteries renders, but if the gate tier drags, the documented fallback is
to keep the all-batteries presence assertions (checks 2-4 above) and exercise the single-battery
manifest path on 2-3 representative batteries (`redis` for the multi-gate `or` case, `graphql` for a
script+obs combo, `docs` for a workflow). The user approved including the full per-gate version.

### 5. Docs

- Update the `classes.py` header comment (§1).
- Update any integrity/upgrading doc that enumerates the managed set to mention `BATTERY_LOCKED`
  (battery-conditional locked files) and `EXEMPT`.

## Testing (TDD throughout)

- **Bite-proof the forward check**: temporarily drop one `BATTERY_LOCKED` entry → the forward test
  goes RED with that path named; restore → GREEN. (Demonstrated in the task, not committed.)
- **Bite-proof the escapee fix**: confirm the forward check is RED *before* `scripts/compose.sh` +
  the 4 obs escapees are added to `LOCKED_TRACKED`, GREEN after.
- **`rules()` battery param**: unit test — `rules()` (empty) returns exactly today's set;
  `rules(["redis"])` adds the two redis obs Rules; `rules(["workers"])` also adds them (shared gate);
  a non-gating battery adds none.
- **Manifest integration**: a rendered `--with redis` project's manifest contains `redis.json`; a
  baseline project's does not. An all-batteries render builds a manifest without `AuthoringError`
  (proves no gate is over-broad).
- **`test_battery_locked_gating_is_accurate`** as in §4.
- **Anti-stale + genuinely-gated** as in §3.
- Standard gate green throughout (`uv run pytest -q`, `ruff check .`, `ruff format --check .`,
  `mypy src`). No new template payload, so no acceptance-tier requirement beyond the existing render
  tests; the all-batteries render runs in the gate tier.

## Rollout

Framework test/integrity-infra change → **no standalone release**. The one behavior change —
`build_manifest` now locking battery-conditional files in projects that have them — ships to
consumers on the next routine cut; existing projects pick it up at their next `framework upgrade`
(the manifest is regenerated from `rules(batteries)` during the update). No consumer action required.

## FWK29 runtime-coverage note

`scripts/compose.sh` is already an EXERCISED entry in `tests/runtime_coverage/registry.py` (FWK31).
Adding it to `LOCKED_TRACKED` is an *integrity*-classification change, orthogonal to FWK29's
*operational-surface* registry; no FWK29 reconciliation is expected. Confirm during implementation
that no new `scripts/*.sh` / workflow / compose surface is introduced (none is — FWK7 adds only
Python + a test), so `test_every_surface_is_classified` stays green.

## Execution note

Per the repo's review-model policy (CLAUDE.md / [[subagent-review-model-pattern]]): implementers →
Sonnet (Haiku for trivial); spec-compliance review → Sonnet; code-quality review → **Opus**;
branch-end whole-branch review → **Opus**. Pass `model` explicitly per role. The plan is authored via
writing-plans and executed subagent-driven, TDD per task.

## Appendix — final classification of the 29

- **`LOCKED_TRACKED` (5 added):** `scripts/compose.sh`,
  `infra/observability/grafana/dashboards/otel-collector.json`,
  `infra/observability/grafana/dashboards/prometheus.json`,
  `infra/observability/prometheus/alerts/otel_collector_alerts.yml`,
  `infra/observability/prometheus/alerts/prometheus_alerts.yml`.
- **`BATTERY_LOCKED` (22):** the 18 battery obs files + `infra/docker/postgres.Dockerfile` +
  `scripts/export-graphql-schema.sh` + `scripts/pact-publish.sh` + `.github/workflows/docs.yml`
  (gates in §1's table).
- **`EXEMPT` (2):** `infra/traefik/certs/.gitkeep`, `infra/tls/ca/.gitkeep`.
