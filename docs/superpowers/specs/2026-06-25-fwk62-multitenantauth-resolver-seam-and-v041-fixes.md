# FWK62 — multitenantauth pluggable authz-resolver seam + v0.4.0 adoption fixes (→ v0.4.1)

**Goal:** Ship the one battery design seam Meridian's de-fork needs (a pluggable resource-grant / subtree
resolver), plus the cross-version upgrade-path bugs their adoption surfaced, as a v0.4.1 patch.

**Architecture:** Finish a seam that already exists in spirit — the authz evaluator already delegates
`subtree_exists` / `resource_grant` to ctx callables; we only need a registration point so a consumer can
supply its own, since the file that wires them (`deps.py`) is integrity-locked. Plus three mechanical
upgrade-path fixes.

**Source:** Meridian's divergence report `docs/superpowers/assessments/2026-06-25-meridian-to-framework-v040-adoption-divergences.md`
(PR #81, DV-1..DV-6) + the reconciliation dialogue. **Tech stack:** Python/FastAPI/SQLAlchemy, Copier.

## Scope

| Item | Class | This release |
|---|---|---|
| **DV-5** pluggable resource-grant / subtree resolver | battery design seam | **build** (the core) |
| **DV-1** `upgrade` renders empty value for a question added after the project was created | upgrade-path bug | build + test |
| **DV-4** `.pre-commit-config.yaml` duplicate managed key on upgrade | upgrade-path bug | release-note + upgrade warning |
| **DV-6** `migrations_control` persisted-control-DB collision | upgrade-path (de-fork) | docs + release-note |
| **DV-2** env `stage`→`staging` · **DV-3** managed `AGENTS.md` | by-design | release-note FYI only |
| cross-repo Promote-Up-Record convention (report §intro) | process | **out of scope** — separate FWK item |

**Release:** v0.4.1 (patch — DV-5 is an additive, backward-compatible seam; defaults preserve today's
behavior. Phase 2 stays FWK61/v0.5.0).

### Scope decision (maintainer) — DV-5-only vs the bundle

Only **DV-5 is on Meridian's critical path** — it gates their seal-aware authz adoption. **DV-1 / DV-4 /
DV-6 are already worked around on Meridian's side** (manual `pi_prefix`, removed the redundant pre-commit
keys, dev-DB rebuild) — real bugs for *future* upgraders, but nothing is blocked on them today. Two ways
to cut v0.4.1:

- **(i) DV-5 only** — fast (the "couple of hours"), unblocks MD now, and the security-sensitive authz seam
  reviews cleanly on its own. DV-1/4/6 become a separate upgrade-path follow-up.
- **(ii) the bundle** (DV-5 + DV-1/4/6) — one release, but larger, and it rides the upgrade-CLI change +
  YAML-dedup-warning alongside the authz seam.

**Recommendation: (i)** — ship the seam now, batch the upgrade-path fixes after (none is blocking). The
rest of this spec documents the full set so the upgrade-path sections are ready when that follow-up is
picked up; if you prefer (ii), it all ships together.

---

## DV-5 — the pluggable authz-resolver seam (the core)

### Current state (verified in code)

- `authz/expr.py` evaluates a resource-scoped leaf by calling **ctx callables**: `subtree_exists(name,
  resource)` for a wildcard subtree, `resource_grant(name, path)` for a concrete resource. The evaluator
  is already generic — it asks whatever resolver the ctx carries.
- `multitenantauth/deps.py` (integrity-**LOCKED**) builds that ctx per request: `subtree_exists = lambda
  …: False` (inert; A-F10), `resource_grant = _resource_grant` — a closure over `(cs, user)` doing a
  **flat** control-DB membership→resource-role lookup.
- So the seam exists in the evaluator; the gap is only that `deps.py` hardcodes inert/flat **and is
  locked**, leaving no place for a consumer to plug in a hierarchical/seal resolver (Meridian's EDR-0004
  cross-plane ancestor-walk + nearest-seal-wins, kept local by design).

### Design — a per-request resolver **factory** registration

The resolver needs request context (the control `Session`, the `AppUser`, **and the resolved active
tenant id**) to walk the hierarchy, so the seam registers a **factory**, not a bare function. The factory
binds tenant ONCE in its closure; the per-call resolver it returns is **tenant-free**.

**Scope decision (v0.4.1): ship the `resource_grant` override only.** Meridian's divergence report asks
for "a pluggable `resource_grant`"; `subtree_exists` (wildcard-subtree existence) was scope this spec
added, and **no shipped battery route uses a wildcard subtree** (verified: the only `resource:*` leaf is a
test probe). So the wildcard-subtree resolver stays the inert default (A-F10) and is **not
consumer-overridable** in this release — deferred to a real need with a properly-designed shape. This
halves the grant surface the focused security review must cover. A factory may still return a
`subtree_exists` key; the battery **ignores** it (the wildcard leaf stays fail-closed), pinned by a test.

New, in the (locked) `multitenantauth/deps.py`:

```python
# A mapping whose resource_grant value is a (perm_name, resource_id) -> bool resolver.
ResourceResolvers = dict[str, Callable[..., bool]]
# Factory: per-request control session + caller + the RESOLVED, membership-gated active tenant id.
AuthzResolverFactory = Callable[[Session, "m.AppUser", str], ResourceResolvers]

_resolver_factory: AuthzResolverFactory | None = None

def register_authz_resolver_factory(factory: AuthzResolverFactory | None) -> None:
    """Register a per-request authz-resolver factory (or None to reset to the flat default).

    guard calls `factory(cs, user, active_tenant_id)` per request — only AFTER the membership-404
    precondition, so `active_tenant_id` is the resolved, membership-gated tenant, never a raw value.
    The returned `resource_grant` — `(perm_name, resource_id) -> bool`, TENANT-FREE — replaces the
    flat default for resource-scoped leaves. A registered factory OWNS resource grants: absent key /
    raise / non-mapping all DENY (fail-closed), NOT a fall-back to flat (registration is opt-in).
    Call this from your own (unlocked) startup, e.g. create_app().
    """
    global _resolver_factory
    _resolver_factory = factory
```

**The per-call contract is tenant-free; the battery adapts it.** The locked evaluator still calls the ctx
`resource_grant(name, path)` (it passes the discrete path dict — A-F1, unchanged). `deps.py` wraps the
consumer resolver in a small **adapter** that extracts the **bare** `path["resource_id"]` (the battery
owns the `resource:{resource_id}` route convention) and calls the consumer's `(perm_name, resource_id)` —
so the consumer never touches path params or a per-call tenant. Tenant binds once, in the factory closure.
This delivers the tenant-free contract **without editing the locked evaluator or A-F1**:

```python
resource_grant = _resource_grant  # flat default (no factory)
if _resolver_factory is not None and active_tenant_id is not None:
    resource_grant = _deny  # a registered factory OWNS grants: absent/raise/non-mapping -> deny
    try:
        consumer_grant = _resolver_factory(cs, user, active_tenant_id).get("resource_grant")
    except Exception:
        logger.warning("authz resolver factory failed; denying (fail-closed)", exc_info=True)
    else:
        if consumer_grant is not None:
            resource_grant = _adapt_resource_grant(consumer_grant)  # extracts bare resource_id, fail-closed
ctx = {..., "subtree_exists": _deny, "resource_grant": resource_grant}  # subtree inert (A-F10)
```

**Resolved discriminator (confirmed with MD):** the battery's per-call `resource_id` is a **bare** id
(`path["resource_id"]`, e.g. `"widget-1"` — stored verbatim in `ResourceRoleAssignment.resource_id`, no
tenant segment). Bare is MD's "ideal" case: cross-tenant conflation is structurally impossible (tenant
comes only from the closure), so no resource-tenant mismatch assert is needed.

**Pattern-awareness boundary (documented, not a gap):** the adapter reads `path["resource_id"]` — it is
correct for the single `resource:{resource_id}` convention every shipped route uses, but does **not** do
pattern-aware param selection across multi-resource routes (that would need the locked-evaluator change;
deferred). A consumer with a non-`resource_id` param fails closed.

**`active_tenant_id`-None edge (documented):** a resource Perm with no `{tenant_id}` in its `on=` pattern
makes `needs_tenant` False, so `active_tenant_id` stays None and the factory is **not** consulted — the
flat default applies. The factory assumes a resolved tenant context; a tenant-less resource leaf falls
through to the flat control-DB resolver (fail-closed for a non-member). All shipped resource routes are
tenant-scoped, so this is a documented assumption, not a live path.

**Tenant placeholder naming (consumer requirement):** the membership-404 precondition and the factory
consult both gate on `needs_tenant = "tenant_id" in resource_params()` — the **literal** param name. A
consumer route naming its tenant placeholder anything other than `{tenant_id}` (e.g. `{org_id}`) is
**fail-closed** — uniform 403, no leak — but silently skips the seam (the factory is never consulted). So
a consumer's tenant-scoped resource routes **MUST** name the tenant path param `tenant_id`. (Surfaced and
refuted as finding **t3** in the focused security review — fail-closed, not an over-grant; see the
`2026-06-25-fwk62-dv5-resolver-seam-security-review` scorecard.)

### Integrity-lock interaction — no locked-file edit

`register_authz_resolver_factory` lives in the **locked** `deps.py` (framework-owned seam). The consumer
**calls** it from their own **unlocked** code (`src/<pkg>/main.py` is unmanaged — confirmed: it is in no
lock set, and `restore` rejects it as "not a restorable file"). So Meridian wires it in `create_app()`:

```python
from <pkg>.multitenantauth.deps import register_authz_resolver_factory
register_authz_resolver_factory(my_seal_resolver_factory)  # their EDR-0004 logic, kept local
```

Meridian's hierarchical/seal logic then runs **through** the battery guard, replacing the parallel-guard
stopgap. The seam also generalizes — any consumer with resource hierarchies / scoped visibility benefits;
it ships consumer-general (a resolver factory, not Meridian's resolver).

### Contract — confirmed with MD (was: open decision)

The factory signature is `(Session, AppUser, active_tenant_id) -> {"resource_grant": resolver}`, with a
**tenant-free** per-call resolver `resource_grant(perm_name, resource_id) -> bool`. MD's two load-bearing
refinements, both incorporated:

1. **Third factory arg = the resolved active tenant id.** MD's real `has_product_permission` is cross-plane
   (it needs `tenant_id` to resolve membership AND to route the seal-walk's tenant DB). `active_tenant_id`
   is the battery's **membership-gated, 404-safe** resolved value — never a raw request value — because
   grants match on `membership_id AND product/resource together`; feeding a non-resolved tenant would break
   cross-tenant compartmentalization. (The battery does **not** hand over a tenant-DB handle — MD's resolver
   opens its own tenant DB; the battery stays routing-agnostic.)
2. **Per-call is tenant-free; tenant binds once in the closure.** The second arg is the **bound resource
   id** (bare `resource_id`), not the raw path dict — so the resolver is not pattern-blind and cannot
   re-derive / trust a path tenant. Delivered via the battery-side adapter (above), leaving the locked
   evaluator and A-F1 untouched.

Meridian's seal-walk / nearest-seal-wins / tenant-DB routing / product model all stay **local** inside
their registered resolver — the battery ships consumer-general (a `resource_grant` factory, not Meridian's
resolver). Colonization line held.

### Security

This is a **deliberate, bounded exception to the Option-B integrity lock** — stated plainly so it doesn't
read as quietly reopening what the lock closed. Option B's promise is that consumers cannot edit the authz
*mechanism*; DV-5 opens exactly **one controlled injection point** into the authz decision path, by design.
The boundaries that keep it safe:

- **Bounded blast radius:** the resolver governs only **resource-scoped leaves** — tenant- and
  platform-domain authz (`tenant_perms`/`platform_perms`) are untouched, and the registration API + the
  evaluator themselves stay locked. The default (no factory registered) is exactly today's flat/inert
  behavior.
- **Grant-capable is the consciously riskier choice.** A deny-only overlay (e.g. a parallel guard that can
  only further-*restrict*) cannot escalate — but it also cannot express what Meridian needs: a
  **hierarchical ancestor-walk that GRANTS** a descendant from an ancestor's permission. So the resolver
  *replaces* `resource_grant` and **can grant, not just filter**. That power is precisely why the focused
  security review below is **non-optional** — not a nicety to drop under time pressure.
- **The focused security review** (before merge), with **grant-via-ancestor reachability as an explicit
  lens** (MD's load-bearing ask): can a registered resolver be coerced to over-grant beyond the consumer's
  intent — in particular, can an ancestor's permission be walked to GRANT a descendant resource the caller
  should not reach, and is that reachability bounded by the membership-gated `active_tenant_id`? Plus: is
  the resource/tenant binding still IDOR-safe through the seam (bare `resource_id` + closure tenant ⇒ no
  cross-tenant conflation)? does the fail-closed mode hold on every miss? It is lighter than the full
  Layer-2 (additive seam, safe default, one injection point) but real, because it touches the GRANT
  decision. All stages on Opus (per the crown-jewels review policy).
- **Fail-closed:** an exception raised inside a registered resolver **denies (403)** — never 500s, never
  allows.

**Review outcome (2026-06-25, ran against `9db22b7`):** the focused all-Opus review **PASSED** — 0 confirmed
Critical/High. 5 raw findings across 6 lenses (grant-via-ancestor ran as lens #1); triage promoted 4; the
default-to-refuted Opus verify refuted all four as concrete battery breaks (0 survivors). The one genuine
residual (t2: a hypothetical multi-distinct-resource route over-granting on its secondary resource) is
**not reachable on the shipped artifact** and **equally affects the flat default** (pre-existing, not
seam-introduced). No hardening lands in v0.4.1 — re-touching the locked mechanism after the gate blessed
`9db22b7` would ship unreviewed grant-path code; t2/t4 + a sample resolver are tracked as a hardening
follow-up. Full scorecard: `docs/superpowers/eval-scorecards/2026-06-25-fwk62-dv5-resolver-seam-security-review.md`.

### Tests (TDD) — `tests/functional/test_auth_deps.py`

- **Defaults unchanged:** no factory registered → all existing authz-fitness + `test_authz_service` /
  `test_auth_deps` pass byte-for-byte (the seam is invisible when unused). A-F10 default-deny + a static
  drift guard (exactly one `subtree_exists` ctx construction site in `deps.py`).
- **Grant through the guard:** a registered factory's `resource_grant` GRANTS a leaf the flat default
  DENIES (bare member 403 → 200 after register).
- **Tenant-free bare-id contract:** the resolver's second arg is asserted **exactly** `== "widget-1"`
  (not truthy) — proves it receives the bare id, not the path dict or a tenant-qualified composite.
- **Resolved-tenant:** the factory's third arg is the resolved active tenant (`== "acme"`).
- **404-before-factory:** a non-member is 404 and the factory is **never** built (a grant-all factory
  cannot rescue a non-member).
- **Fail-closed (all assert 403, member HAS the resource role so flat would grant 200):** a resolver that
  raises; a factory that raises; a factory returning a non-mapping.
- **Absent ⇒ deny (opt-in):** a factory that omits `resource_grant` DENIES (403), does NOT fall back to
  flat.
- **Subtree deferral pinned:** a factory supplying a grant-all `subtree_exists` key is ignored — the
  wildcard leaf stays inert (403).
- **Isolation:** autouse fixture resets `register_authz_resolver_factory(None)` after each test (a leaked
  grant-capable factory would make a later test pass spuriously — the worst authz failure mode).

---

## Upgrade-path hardening

### DV-1 — `upgrade` must apply a derived default for a question added after the project was created
A project created before a question existed (Meridian: pre-FWK9, no persisted `pi_prefix`) upgrades to a
template that *uses* it → the managed block renders with an empty value. **Fix:** in the upgrade/update
core, for any copier question absent from the project's `.copier-answers.yml`, apply its derived default
(copier already computes these for a fresh render; the update path must too). **Test:** an acceptance test
that upgrades a project whose answers are missing a later-added question and asserts the rendered managed
block carries the derived default, not empty.

### DV-4 — `.pre-commit-config.yaml` duplicate managed key on upgrade
v0.4.0 moved `conventional-pre-commit` + `default_install_hook_types` into the managed region; a project
that had hand-added them ends up with a duplicate top-level `default_install_hook_types` → invalid YAML →
`check-yaml` fails the first post-upgrade commit. Auto-de-dupe is unsafe (we can't tell a builder's
intentional override from a redundant copy). **Fix:** (a) a release-note for upgraders, and (b) a
non-fatal upgrade-time **warning** if the post-render `.pre-commit-config.yaml` has a duplicate top-level
key. (Hybrid-region restore already owns the managed span; this only warns about builder-side dupes.)

### DV-6 — persisted-control-DB migration collision (de-forking consumers)
The battery's `migrations_control` ships `c0001`/`c0002` ids with *different* schema under a *new* version
table. Fresh control DB → clean replay. A consumer with a **persisted** control DB from a prior chain
(Meridian's fork) → the new version table is empty → `alembic upgrade head` re-runs `CREATE TABLE` against
existing objects → fails. A generic `upskill --with multitenantauth` consumer has no prior control DB and
is unaffected; only a de-forking consumer hits it. **Fix:** documentation — a "persisted control DB on
adoption" section in the battery docs + release-note: rebuild (`task dev:reset`, dev) or hand-`stamp` the
new version table (prod). No code change (the framework can't know a consumer's prior fork chain).

### DV-2 / DV-3 — by-design, release-note only
`stage`→`staging` (the deliberate B-F1 env-token remap) and the FWK9 framework-managed `AGENTS.md` are
both intended. One-line upgrade-note mentions so upgraders expect them.

---

## Validation

- TDD throughout; the DV-5 seam gets a **focused security review** (resolver path, fail-closed, over-grant)
  before merge — lighter than the full Layer-2 (additive seam, defaults safe), but real because it touches
  the authz decision path.
- Render-matrix is the proof (the multitenantauth + full combos must stay green); the new acceptance tests
  (DV-1 upgrade-default, DV-5 resolver) gate.
- Release readiness per [[release-readiness-needs-render-not-local-gate]]; cut **v0.4.1** by the standard
  procedure ([[release-cut-procedure]]).

## Out of scope (separate FWK item)
The cross-repo **Promote-Up-Record** convention the report opens with (the framework, as the absorber,
adopting cross-repo + standing up the auth PUR + the formal fork-deletion gate). Real and worth doing, but
it's a process/convention task, not a v0.4.1 code fix. Track separately.

**DV-5 seam hardening (deferred follow-up).** The focused review surfaced three non-reachable,
defense-in-depth residuals that are deliberately NOT landed in v0.4.1 (re-touching the locked mechanism
after the gate blessed `9db22b7` would ship unreviewed grant-path code):
- **t2** — a **fitness test** (additive, non-locked, ships to consumer CI; mirror the wildcard-under-ALL
  guard at `authz/expr.py:52-78`) requiring any resource-scoped Perm leaf to bind the canonical
  `resource_id` param. The in-mechanism options (construction-time guard / pass the per-leaf bound resource
  to `resource_grant`) are explicitly out — the fitness-test form is the only acceptable shape.
- **t4** — reorder `deps.py` so `ctx['platform_perms']` is computed BEFORE the factory call (removes the
  privilege-influence adjacency; not request-reachable today).
- **t3/t1** — ship a **sample correct consumer resolver** scoping `resource_id` by the closure tenant, and
  (optionally) generalize `needs_tenant` detection beyond the literal `tenant_id` param name.

See the `2026-06-25-fwk62-dv5-resolver-seam-security-review` scorecard.
