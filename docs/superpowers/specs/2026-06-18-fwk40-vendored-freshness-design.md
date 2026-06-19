# FWK40 — docs-layout validator re-vendor freshness check

*Design spec. 2026-06-18. Status: approved (brainstorming → writing-plans). Follow-up to FWK9.*

## Summary

FWK9 vendored the docs-layout validator into the template
(`src/framework_cli/template/scripts/docs_layout_check.sh`) from the **private**
`cdowell-swtr/patterns` repo at tag `docs-layout/v1`, recorded only by a
provenance comment. Nothing detects when upstream ships `docs-layout/v2`, so the
vendored copy can silently rot.

Add a **local, auth-gated pytest check** that, where `cdowell-swtr/patterns` is
reachable (the maintainer's authenticated machine), (1) FAILS if a newer
`docs-layout/v*` tag exists than the one pinned in the provenance comment, and
(2) verifies the vendored copy is byte-identical to upstream at the pinned tag.
Where patterns is unreachable (CI, no `gh` auth, offline), it **skips** — so it
never blocks PRs or merges and adds no secret or workflow.

## Goals / non-goals

**Goals**
- A re-vendor signal fires the moment `docs-layout/v2` ships, visible on the
  maintainer's normal `pytest` run (and at release time).
- A fidelity guard catches accidental local edits / silent divergence of the
  vendored script from its pinned upstream.
- **Zero secrets, zero new workflow, no private-repo coupling in CI.** The check
  is inert anywhere patterns auth is absent.

**Non-goals**
- No scheduled/CI automation requiring a patterns-read PAT (rejected: it
  reintroduces the private-repo dependency FWK9 designed out).
- The framework's own root-vendored `pi-convention.md` / `memory-convention.md`
  are out of scope — they are pinned at *main HEAD* (a SHA), not a tag, so their
  staleness model differs. Noted as a sibling follow-up, not part of FWK40.

## Why this shape (decisions)

1. **Local auth-gated test, not a scheduled workflow.** The framework is public
   and its CI `GITHUB_TOKEN` cannot read the private patterns repo; a proactive
   cron check would need a PAT secret and would re-couple automation to the
   private repo. The maintainer already has patterns auth and runs the suite
   (notably before releases — the natural re-vendor trigger), so an auth-gated
   local test is the lightweight, secret-free fit.
2. **Hard FAIL on staleness, not a warn.** It only fails where patterns is
   reachable (the maintainer's machine), never in CI, so it cannot block a PR or
   merge. A hard local fail is an actionable forcing function; the failure
   message *is* the re-vendor instruction.
3. **Include a fidelity check.** The vendoring approach relies on byte-fidelity
   to upstream `docs-layout/v1`; a second assertion (vendored == upstream @ pin,
   modulo the provenance line) is cheap and catches a distinct failure mode.
4. **Pure helpers + thin live wiring.** Network/auth assertions can't be TDD'd
   deterministically, so the logic is factored into pure functions unit-tested
   over fixtures; only the `gh` calls are live-only.

## Architecture

A new module `tests/test_vendored_freshness.py` plus a small pure-logic helper.

### Pure helpers (deterministic, unit-tested)
Placed in the test module (or a tiny `tests/_vendor_freshness.py` helper if the
test module would otherwise grow tangled):
- `parse_pinned_tag(provenance_text: str) -> int` — extract the integer `N` from
  the `docs-layout/vN` reference in the vendored file's provenance comment.
  Raises if no provenance reference is found.
- `latest_version(tag_names: Iterable[str]) -> int | None` — given patterns tag
  names, return the max `N` among `docs-layout/vN` tags, or `None` if none match.
- `strip_provenance(vendored_text: str) -> str` — return the vendored script with
  the single inserted provenance line removed, for byte-comparison to upstream.

### Live wiring (auth-gated, skips without patterns access)
- A `patterns_reachable()` probe: run `gh api repos/cdowell-swtr/patterns`
  (or equivalent), return False on any non-zero exit / missing `gh` / error. A
  module-level skip helper calls it once and `pytest.skip(...)` when False.
- `test_docs_layout_validator_pin_is_latest`: read the vendored file, parse the
  pinned `N`; fetch patterns tags (`gh api repos/cdowell-swtr/patterns/tags
  --jq '.[].name'`), compute `latest_version`; assert `latest <= pinned` — i.e.
  no newer tag. On failure: a message naming `docs-layout/v<latest>` and
  instructing to re-vendor `src/framework_cli/template/scripts/docs_layout_check.sh`.
- `test_docs_layout_validator_matches_upstream_at_pin`: fetch upstream
  `hooks/docs-layout-check.sh` @ the pinned tag (`gh api
  repos/cdowell-swtr/patterns/contents/hooks/docs-layout-check.sh?ref=docs-layout/v<pinned>
  --jq .content | base64 -d`); assert `strip_provenance(vendored) == upstream`.

## Error handling

- `gh` absent / patterns unreachable / offline / CI → **skip** (never fail).
- Provenance comment missing or unparseable in the vendored file → the
  `parse_pinned_tag` assertion **fails** (a real defect; FWK9's
  `test_render_docs_layout_validator_is_zero_dep_bash` already asserts the
  provenance string is present, so this is a backstop).
- Upstream has no `docs-layout/v*` tags (shouldn't happen) → `latest_version`
  returns `None` → skip with a clear reason (can't determine staleness).

## Testing

- **Unit (deterministic, in CI):** `parse_pinned_tag`, `latest_version`,
  `strip_provenance` over inline fixtures — including edge cases (multi-digit
  `vN`, unsorted/mixed tag lists, non-`docs-layout` tags ignored, missing
  provenance raises).
- **Live (auth-gated, maintainer machine):** the two integration tests above,
  which skip in CI. Demonstrate non-vacuity by confirming they currently PASS
  against `docs-layout/v1` and would FAIL if the pin were edited to `v0`
  (staleness) or the vendored body altered (fidelity).

## Out of scope / future

- A unified freshness check also covering `pi-convention.md` /
  `memory-convention.md` (HEAD-pinned, not tag-pinned). Possible future item.
