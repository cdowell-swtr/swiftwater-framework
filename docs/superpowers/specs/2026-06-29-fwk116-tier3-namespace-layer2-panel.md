# FWK116 tier-3 per-worktree namespace — internal layer-2 adversarial panel + verified scheme

> **Date:** 2026-06-29 · **Sub-PLAN FWK128** (S1/exp-2, parent FWK116) · the fractal layer-2 panel
> the carving mandates (`2026-06-29-…-carving-design.md` §"S1 · FWK116"). The tier-2↔tier-3
> `COMPOSE_PROJECT_NAME` disjointness is a **SAFETY property** (a collision destroys shared docker
> volumes), so the namespace scheme is hardened by an adversarial panel **before** implementing —
> the carving pattern applied one level down. This note is the panel record + the verified scheme
> FWK129 implements.

## The panel — 3 adversarial lenses on the proposed `<slug>-<inst>-t-<uuid>` fold

| Lens | Focus | Verdict |
|---|---|---|
| A | tier-2↔tier-3 + tier-3↔tier-3 collision / disjointness | HOLDS-WITH-AMENDMENT |
| B | the `<inst>` source + fallback robustness | HOLDS-WITH-AMENDMENT (source-as-specified BROKEN) |
| C | sweep semantics + FWK99/FWK74 regression | HOLDS-WITH-AMENDMENT |

The panel **rejected the proposed scheme's `<inst>` source** (branch-derived + fixed-token
fallback) and converged on a path-hash inst + anchored-regex membership + infix ban + split sweep.
What the proposed scheme got right: the *fold itself* (inst into the prefix) and the tier-2 infix
ban are sound. What it got wrong (caught by the panel, not by the author): three independent
structural holes, below.

### The three holes the panel caught

1. **Branch-derived `<inst>` fails on the dominant path (Lens B).** `_tier3.py` runs in pytest
   session hooks — non-interactive, cannot fail-loud like `worktree.py:main()`. `actions/checkout`
   leaves **detached HEAD** by default, so `git symbolic-ref --short HEAD` fails on **every CI run**
   → the fallback fires for *all* of CI. A **fixed-token** fallback (`ci`/slug) is one shared value →
   two detached sessions (two self-hosted runners, or two `task test:full`) both get `demo-ci-t-` →
   the first to finish reaps the other's live stacks. The namespace collapses back to one shared
   namespace — *worse* than today, since it bites CI.
2. **Free-form variable-length `<inst>` breaks `startswith` scoping (Lens A & B & C).** With a
   variable-length inst, one worktree's prefix can be a string-prefix of another's full stack name.
   Worktree A on branch `wt` → prefix `demo-wt-t-`; worktree B on branch `wt-t-blue` (a legal branch,
   does not start with `t-`) → stack `demo-wt-t-blue-t-<uuid>`, which `startswith("demo-wt-t-")` →
   **A's finish-sweep reaps B's live stack mid-run.** An everyday branch name, no detached HEAD. The
   fold's payoff (per-worktree finish isolation) is *false* as written.
3. **The FWK74 ban must invert atomically (Lens A & B & C).** Under the fold the reserved marker
   moves from a *prefix* (`demo-t-…`) to an *infix* (`demo-<inst>-t-…`), so the tier-2 collision
   condition becomes "`inst2` **contains** `-t-`", not "starts with `t-`". A tier-2 branch
   `blue-t-deadbeef…32hex` (no `t-` prefix → old ban allows it) collides exactly with a tier-3
   `demo-blue-t-deadbeef…` → the tier-3 reap (`down -v`) destroys the tier-2 dev volumes →
   **FWK88 SAFETY violated.** The old `t-foo`-banned/`demo-t`-allowed guard *inverts*: `t-foo` is now
   safe (no `-t-`), `foo-t-bar` is the new danger.

## The verified scheme (FWK129 implements this)

1. **`<inst>` = `sha256(canonical worktree root path)[:12]`** — fixed-width 12-char lowercase hex.
   **No branch derivation, no fixed-token fallback.** Always resolvable (no git → hermetic, works in
   detached-HEAD/CI), deterministic-per-worktree-across-runs (own-crash start-sweep reaping
   preserved; survives a branch switch), structurally unique per worktree (two worktrees can't share
   an absolute realpath; two self-hosted runners have distinct `_work` paths). Fixed-width hex ⇒ no
   inst is a string-prefix of another **and** none contains `-t-`. (Box-agnosticism — FWK74's reason
   for a branch-derived inst — is irrelevant for transient local test stacks no human reads.)
2. **tier-3 project name** = `<slug>-<inst>-t-<uuid>` (uuid = `uuid4().hex`, 32 hex).
3. **Membership = anchored exact regex** `^<slug>-<inst>-t-[0-9a-f]+$` (Lens C Fix 1), not a bare
   `startswith`. The hex-only uuid tail is the structural guarantee — a peer's
   `demo-<other>-t-<uuid>` (different inst) and any prefix-extension fail the anchor. Defense-in-depth
   atop the fixed-width-hex inst.
4. **FWK74 tier-2 ban lockstep (same commit)**: `worktree.py`'s `RESERVED_TIER3_PREFIX` semantics
   change from "inst2 **startswith** `t-`" → "inst2 **contains** the reserved marker `-t-`"
   (substring → `Tier3NamespaceError`). Fix the now-inverted `test_worktree.py` guards (`t-foo`/`t`/
   `feature/foo`/`main`/`test-branch` allowed — none contain `-t-`; `foo-t-bar`/`a-t-b` rejected).
   This is the FWK88 dev-volume SAFETY guarantee.
5. **Split sweep scoping (Lens C Fix 3 — recovers deleted-worktree GC)**:
   - **finish-sweep**: exact this-worktree namespace (`^<slug>-<inst>-t-[0-9a-f]+$`) → can never
     touch a peer's stacks.
   - **start-sweep**: inst-**agnostic** + `stale_only` over `^<slug>-[0-9a-f]+-t-[0-9a-f]+$` → reaps
     stale orphans of ANY worktree (incl. a `git worktree remove`d one whose inst never recurs),
     grace-filter spares young peers (FWK99's own safety argument). Without this, per-worktree exact
     scoping would leak a deleted worktree's crashed stacks forever — a GC regression vs today's
     shared `demo-t-` namespace. Stays tier-2-disjoint under the item-4 `-t-` ban.
6. **Cross-layer coupling test (Lens B Hole 4)**: the tier-3 *producer* (`_tier3.py`, framework test
   code) and the tier-2 *ban* (`worktree.py`, template payload) are in different layers with no
   shared constant / import path → the `-t-` marker can drift silently (invisible to render/integrity
   + each module's own unit tests). Add a test that importlib-loads both and asserts (i) the `-t-`
   marker is byte-identical on both sides and (ii) the tier-2 generator rejects every inst containing
   it.
7. **Hermetic + git-free**: resolve `<inst>` from `__file__`'s worktree root (deterministic, no git
   shell-out, no import-time side effect); keep the fast-tier contract tests git-free with an
   **injectable** inst (don't regress the determinism the static `f"{slug}-t-"` pin gives today).

## Test pins to update (FWK129)
- `tests/acceptance/test_tier3_contract.py`: `TIER3_PREFIX == f"{slug}-{inst}-t-"` with an injected
  inst; `inst` matches `^[0-9a-f]{12}$`; `tier3_project_name()` matches
  `^<slug>-<inst>-t-[0-9a-f]+$`; add the **peer-exclusion** pins (with `inst` fixed: a peer
  `demo-<other>-t-<hex>` and a prefix-extension `demo-<inst>-...-t-<hex>` are both excluded by
  membership and by `list_tier3_projects`); a new `inst`-is-per-worktree-unique pin.
- `tests/acceptance/conftest.py`: finish-sweep exact-inst, start-sweep inst-agnostic+`stale_only`.
- `tests/test_worktree.py`: ban now rejects `-t-`-containing insts, allows `t-foo`/bare `t`.
- New cross-layer coupling test (per item 6).

## Outcome
The layer-2 panel did its job: it caught that the proposed branch-derived scheme was **broken on the
dominant (CI) path** and converged on a path-hash + anchored-regex + infix-ban + split-sweep design
whose tier-2↔tier-3 disjointness and per-worktree finish-isolation are **structural, not value
coincidences**. The safety verification lived inside the worktree (this note), not as a gate on the
whole experiment — the carving's fractal-freeze pattern, validated.
