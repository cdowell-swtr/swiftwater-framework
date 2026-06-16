# Runtime-Coverage Completeness Check (FWK29) — Design

> Design spec for **FWK29**: a deterministic, registry-driven completeness check that
> enforces *exercised-or-classified* over the framework template's provisioned
> operational surfaces — the **closed-world ratchet** half of the durable mechanism
> seeded by the FWK18 inventory. The **open-world** half (an agentic framework-native
> coverage-gap reviewer that finds surfaces *outside* this check's rules) is **FWK30**,
> a separate spec that defers to this one's registry. Status: approved (brainstorming,
> 2026-06-16).

## Context & goal

FWK18 inventoried template-provisioned runtime/build surfaces that no test exercises
(the FWK17 `docker build`-no-git and FWK8 Traefik-routes-nothing class). That
inventory is a **static snapshot** — it goes stale the moment the template changes.
FWK29 turns the durable part into an **executable ratchet**: a CI test that fails when
a *new* operational surface is added without being classified as exercised, intentionally
exempt, or a tracked known-gap.

Two existing patterns are the model:
- **`tests/test_obs_completeness.py`** — declaration-driven: `battery.obs` declares a
  surface, the test verifies the template provides the scrape/alert/dashboard.
- **`tests/integrity/test_classes.py`** — reverse-scan with explicit classification
  registries (`LOCKED_TRACKED`, `INTENTIONALLY_UNLOCKED`): every file must fall into a
  declared class; intentional exemptions are *registered with a reason*.

FWK29 is the second pattern applied to *operational coverage*.

**Closed-world by design.** This check only ever finds surface classes someone wrote an
enumeration rule for. That is a feature, not a limitation: it is a cheap, gating ratchet
for *foreseen* categories. Finding surfaces of an *unforeseen* kind is explicitly
**FWK30's** job (open-world judgment). The two compose: FWK30 discovers; recurring
discoveries graduate into FWK29's rules; FWK29 ratchets them for free thereafter.

## The classification registry

A typed Python module — `tests/runtime_coverage/registry.py` (framework **test**
infrastructure, not template payload; lives with the test that consumes it, the way
`tests/integrity/` consumes `integrity/classes.py`). It is purely the framework's own
test-coverage bookkeeping — no CLI/runtime use — so it belongs under `tests/`, not
`src/`; typed with a `dataclass` for clarity, though `tests/` is outside the gate's
`mypy src` scope (consistent with the rest of the test suite).

Each entry classifies one operational surface:

```python
class Status(enum.Enum):
    EXERCISED = "exercised"    # a test drives it — evidence names the test
    EXEMPT = "exempt"          # intentionally undriven — evidence is the reason
    KNOWN_GAP = "known_gap"    # real, open gap — evidence is "FWK<N> — reason"

@dataclass(frozen=True)
class SurfaceClass:
    key: str             # canonical enumeration key, e.g. "service:dev.yml:worker"
    provisioned_at: str  # "infra/compose/dev.yml.jinja:131-162"
    status: Status
    evidence: str        # test name | exemption reason | "FWK<N> — reason"

REGISTRY: tuple[SurfaceClass, ...] = ( ... )
```

**Three statuses, not two.** A strict exercised-or-exempt model would force all of
FWK19–28 to be closed before the check could go green. **KNOWN_GAP** lets the registry
encode today's reality honestly — the check passes now — while the ratchet still bites:
any *new* surface that is neither exercised, exempt, nor a registered known-gap fails.
Debt stays visible (each KNOWN_GAP carries its FWK id) instead of hiding.

## Enumeration rules (the closed-world boundary)

The check renders a **maximal (all-batteries, dependency-resolved) project once** as a
fixture — so every battery-gated surface is visible, not just baseline — then parses
that tree with six mechanical rules. Each yields canonical surface **keys** that must
each have exactly one registry entry:

| Rule | Source | Key form |
|---|---|---|
| Compose overlays | each `infra/compose/*.yml` | `overlay:prod.yml` |
| Compose services | each (overlay, service) | `service:dev.yml:worker` |
| Dockerfile stages | each `FROM … AS <stage>` in `infra/docker/*Dockerfile*` | `docker-stage:runtime` |
| Operational scripts | `scripts/*.{sh,py}`, `infra/deploy/**/*.sh` | `script:scripts/entrypoint.sh` |
| Workflow jobs | each job in `.github/workflows/*.yml` | `job:ci.yml:gate` |
| Hooks | `.pre-commit-config.yaml` hooks + `.claude/hooks/*` | `hook:gitleaks` |

Expected scale: ~50–60 keys.

**Explicitly out of scope (reviewer-owned).** In-app **code-path** surfaces — the
`create_app`/lifespan bootstrap, DB engine/pool lifecycle, per-battery live routes,
worker tracing — are *not* mechanically enumerable (they are code, not files/services).
The check does **not** attempt to enumerate them; the registry module documents this
boundary in its docstring. The gap between "what the rules enumerate" and "the full
operational surface" is precisely **FWK30's** mandate. Keeping the boundary explicit is
what makes the closed-world check trustworthy — it never pretends to cover what it can't
see.

## The check

A single `gate`-tier test — `tests/runtime_coverage/test_completeness.py` (no docker:
render + parse only, so it is CI-enforced and free):

1. Render the all-batteries fixture; run the six rules → the live key set.
2. **Set-equality** against the registry keys:
   - enumerated key with no entry → **fail**: *"unclassified operational surface `<key>`
     — classify it in `tests/runtime_coverage/registry.py` as EXERCISED / EXEMPT /
     KNOWN_GAP."*
   - registry entry with no enumerated key → **fail**: *"stale registry entry `<key>` (no
     longer rendered)."*
3. **Per-status well-formedness:**
   - EXERCISED → the named test function **must exist** (grep `tests/`). Catches registry
     rot when a test is renamed/deleted. (Verifies the test *exists*, not that it *drives*
     the surface — beyond mechanical reach; that is the reviewer's job.)
   - KNOWN_GAP → evidence matches `^FWK\d+ — ` so every gap stays linked to a task.
   - EXEMPT → non-empty reason.

The contract is **classification completeness + reference integrity** — the same
guarantee `integrity/test_classes` gives for files. It does **not** assert a surface is
actually exercised.

## Seeding the registry (this is the re-rank)

Classifying the ~50–60 keys is the bulk of the work and where the additional
re-ranking lands. Per key: grep `tests/` to confirm a driving test → EXERCISED; or judge
it intentionally undriven → EXEMPT; or a real open gap → KNOWN_GAP (FWK id). Seeded
methodically (grep-classify, the deploy-model rigor), not a fresh agent sweep — the set
is bounded and the hard reasoning is done.

**Loop-closing is part of the task.** When a classification disagrees with the FWK18
inventory (a "gap" that is already covered, or another consumer-implemented seam like
`prod.yml`), the inventory
(`docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md`) is corrected to
match. The registry becomes the executable, always-current successor to the static
inventory; the FWK19–28 KNOWN_GAP entries are its open-work view.

## The FWK30 seam

FWK29 ships the registry with a docstring stating its contract so FWK30 has a stable
interface:
- **Deferral target** — FWK30's reviewer treats anything classified here as handled and
  flags only what is *not* in it.
- **Graduation target** — when FWK30 keeps finding a new *enumerable* category, a rule is
  added to the table above and it becomes a free ratchet (same spirit as FWK4).

## Non-goals

- **Not docker / not an exerciser.** Static render + parse only. It guards that nothing
  ships unclassified and no reference rots — not that a surface actually runs under test.
- **Not in-app code paths.** Those are FWK30's open-world domain.
- **Not the reviewer.** FWK30 is a separate spec.

## Testing / build order (TDD)

Write the enumeration rules + the check first → red (everything unclassified) → seed the
registry to green → inventory-correction fallout lands in the same branch. The check runs
in the `gate` tier (framework's own quality gate), so it is enforced on every PR.

## PLAN

- **FWK29** → this design: `tests/runtime_coverage/{registry.py,test_completeness.py}` +
  the six enumeration rules + the seeded classification of ~50–60 surfaces + inventory
  reconciliation. Framework **test-only** (no `src/framework_cli` wheel change, no template
  payload change) → **no release**. Gates in CI. Unblocks **FWK30** (the agentic reviewer).
