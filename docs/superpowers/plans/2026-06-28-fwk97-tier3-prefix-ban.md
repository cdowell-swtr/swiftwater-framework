# FWK97 (child of FWK74 / A2) — tier-3 `t-` prefix ban (pinned-contract enforcement)

> **Date:** 2026-06-28 · **Status:** plan · **Author:** Chris (with Claude)
> **Parent:** FWK74 (A2). **Closes** the FWK74 design's open coordination point #1 (exact tier-3
> reserved token). **Provisional ID** — re-keyed at Milestone M per carving learning #5; do NOT
> renumber now (A1 merges ahead → the re-key happens once, above main's max).

## Why now (independent of A1)

The carving's tier-2↔tier-3 name-disjointness marker, left unpinned at fork time ("e.g.
`<slug>-t-<uuid>`"), is now **PINNED on `main`** (carving spec, *Tier-2 ↔ tier-3 name disjointness*,
pinned 2026-06-28 by the operator; raised as a loud finding by stream B's decomposition):

- tier-3 transient project names are **`<slug>-t-<uuid>`**; the **`<slug>-t-` prefix is reserved**;
- the disjointness is **structural, not coincidental** — A2's tier-2 generator (`<slug>-<inst>`)
  **MUST reject any `<inst>` beginning with `t-`** so the two never collide on `COMPOSE_PROJECT_NAME`.

FWK92 shipped a **conservative** guard (`RESERVED_TIER3_MARKER = "t"`, rejecting any instance whose
first dash-segment equals `"t"`). That over-rejects a bare `t` (`<slug>-t`, which is **not** in
tier-3's `<slug>-t-<uuid>` namespace) and is keyed to a then-unconfirmed token. This task tightens it
to the pinned structural ban. **The trailing hyphen is load-bearing:** `demo-tango` is fine (the `t`
is not followed by `-`); `demo-t-foo` is not (it sits inside tier-3's reserved `demo-t-` prefix).

This needs **no A1 code** and no rebase — the contract is a doc already canonical on `main`; my
branch's carving copy stays pre-pin until the Milestone-M rebase, which is where I verify my code
against the in-tree pinned spec. **Per the operator: do not fix the ID/log collisions now** — A1
merges ahead and the re-key would be redone; defer the whole rebase + re-key to Milestone M.

## Change (one TDD task, controller-direct + focused review)

`src/framework_cli/template/scripts/worktree.py`:

- `RESERVED_TIER3_MARKER = "t"` → **`RESERVED_TIER3_PREFIX = "t-"`** (the pinned reserved prefix, with
  a comment citing the pinned carving section as the authority).
- `build_stack_instance`: `inst.split("-", 1)[0] == RESERVED_TIER3_MARKER` →
  **`inst.startswith(RESERVED_TIER3_PREFIX)`**; update the error message to name the `t-` prefix.

Behavioral delta vs FWK92: **bare `t` is now allowed** (`<slug>-t`, structurally disjoint from every
`<slug>-t-<uuid>`); every `t-*` instance still raises `Tier3NamespaceError`. All other cases unchanged.

## Tests (`tests/test_worktree.py`) — RED first

1. **RED driver:** `build_stack_instance("demo", "t")` must return `"demo-t"` (bare `t` allowed — the
   trailing hyphen is load-bearing). Fails today (FWK92 raises on first-segment `"t"`).
2. **Refusal:** `build_stack_instance("demo", "t-foo")` raises `Tier3NamespaceError` (already true;
   re-anchored on the pinned prefix). Keep the existing `t-1234` and `t/1234`-branch cases.
3. **Structural disjointness assertion:** for a spread of accepted branches (`tango`, `test-branch`,
   `t`, `feature/foo`, …) the result **never** begins with the tier-3 reserved prefix `demo-t-`; and a
   `t-*` instance is refused. Proves tier-2 names can never enter tier-3's reserved prefix by
   construction, not by coincidence.
4. Update `test_build_stack_instance_tier3_only_guards_exact_t_segment` to reflect the
   trailing-hyphen semantics (rename + document `demo-tango` fine vs `demo-t-foo` not, bare `t` fine).

Framework-venv importlib tests (no render — pure logic), per the FWK92 precedent.

## Records

- Update the FWK74 design's open-coordination-point #1 → **RESOLVED** (pinned; `t-` prefix ban).
- PLAN: new `[ ]`→`[x]` FWK97 child row under FWK74 (provisional). ACTION_LOG entry.
- Docs/maintainer-tooling + template-payload guard semantics only; no consumer-visible behavior change
  beyond the (correct) bare-`t` allowance → rides A2's eventual release, no separate cut.
