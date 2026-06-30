# Incoming (from bearing) — CLI ↔ project `_commit` version-coupling defect + proposed fix

**Date:** 2026-06-29
**Source:** `cdowell-swtr/bearing` (BRG42), observed during its BRG41 v0.4.5 adoption.
**Genre:** downstream consumer defect report + proposed fix (companion-style cross-repo input).
**Status:** `proposed`

## Seam

The framework **CLI** is installed system-wide (one `uv tool install` per machine, shared across
every project), while each project pins a **template version** in `.copier-answers.yml`
(`_commit: vX.Y.Z`). These two version axes are independent: a machine's CLI can move ahead of any
given project's pin. The integrity/staleness commands sit exactly on this seam — and currently
fail it.

## Defect (observed on bearing — CLI `0.4.5`, project pin `_commit: v0.4.2`)

Three commands misbehave when the CLI version leads the project pin. **All three return exit 0**,
so nothing downstream (a CI gate, pre-commit) can detect the degraded state.

**1. `framework integrity` silently self-disables — and exits 0:**
```
framework integrity: skipped — your framework CLI is v0.4.5 but this project is pinned v0.4.2, so
integrity cannot verify against the matching template version (and `framework restore` is disabled
until they match). Either upgrade the project (`framework upgrade`), or pin a matching CLI: uv tool
install git+https://github.com/cdowell-swtr/swiftwater-framework@v0.4.2.
# exit code: 0
```
A CI/pre-commit gate that runs `framework integrity` expecting it to *verify scaffolding* passes
**green while verifying nothing**. The scaffolding-integrity guarantee is silently absent.

**2. `framework check` reports the CLI version, not the project's staleness — and exits 0:**
```
framework check: up to date (v0.4.5).
# exit code: 0
```
The project is pinned `v0.4.2`, i.e. **three releases stale**, yet `check` reports "up to date
(v0.4.5)" — it is reading the installed **CLI** version, not the project `_commit`. There is no
command that answers "is *this project* behind the latest release?"

**3. `framework restore` is disabled — and the error exits 0:**
```
Error: This project is pinned v0.4.2 but your framework CLI is v0.4.5. Either upgrade the project
(`framework upgrade`), or pin a matching CLI: uv tool install
git+https://github.com/cdowell-swtr/swiftwater-framework@v0.4.2.
# exit code: 0
```
The locked-file repair mechanism is unavailable for exactly the projects that most need an integrity
check, and even the hard error returns success.

## Impact

For **any** project whose pin trails the system CLI — the common case for a shared CLI across many
repos — the framework's headline scaffolding-integrity guarantee is unavailable and, worse,
**indistinguishable from passing**. The three exit-0 returns mean no automated gate can catch it;
a team only discovers the gap by reading stdout. On bearing this manifested as `framework integrity`
sitting in `task ci` while actually verifying nothing, until the BRG41 upgrade to a matching pin
closed the gap.

## Proposed fix

1. **Make `check`/`integrity` pin-aware and degrade gracefully.**
   - `check` should compare the project `_commit` against the latest *release* and report **project**
     staleness ("project is v0.4.2; latest is v0.4.5; run `framework upgrade`"), distinct from the
     CLI's own version.
   - `integrity` should **verify what it can** against the project's pinned template version (fetch /
     cache that template ref) rather than fully self-disabling on any CLI≠pin mismatch. If it
     genuinely cannot verify, it should exit **non-zero** (or offer an explicit `--require-match`),
     so a gate fails loud instead of passing silent.
2. **Non-zero exit on skip/error.** `integrity` (skipped) and the `restore` hard error must not
   return exit 0; a gate must be able to distinguish "verified OK" from "could not verify".
3. **Support + document a project-local pinned CLI** so the authoritative CLI travels with the
   project — e.g. `uv tool install git+…@<_commit>` into a project-local environment, or a
   `task`-wrapped pinned invocation — documented as the recommended setup for shared machines.

`framework upgrade --bump-cli` already exists, but it is *remediation* (move the project forward),
not the missing *guard* (detect/keep correctness while a project legitimately lags a release).

## Provenance

Confirmed by bearing's BRG41 probe pass: once bearing was upgraded to a matching `_commit: v0.4.5`,
`framework integrity` returned **OK** and `framework restore` re-enabled — establishing the
CLI/pin mismatch as the sole cause. Full per-seam notes live in bearing at
`_docs/cross-repo/2026-06-29-fwk-cli-version-coupling.md`.

## Routing

Filed as a FWK PR (this branch). Escalate to a Negotiation Thread only if the fix design becomes
contested.
