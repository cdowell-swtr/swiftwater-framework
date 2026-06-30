# Design — CLI/template version lockstep via self-dispatch

**Date:** 2026-06-29
**Status:** approved (brainstorm) — pending spec review → plan
**FWK:** reframes **FWK138** (integrity silent-green on skew) + **FWK139** (#2 staleness signal; the "project-local pinned CLI" feature). Closes the BRG42 defect class (Bearing PR #112) and the same skew that bites Meridian. Relationship to **FWK68** noted in §10.

## 1. Problem

The `framework` CLI renders **version-pinned template payload** into a project and bakes the source version as `_commit` in `.copier-answers.yml`. `framework integrity` / `restore` render the canonical from the CLI's **own bundled** template and compare — so they are only correct when the **installed CLI version == the project's `_commit`**.

The CLI is installed as a **standing, unversioned global** (`uv tool install … → ~/.local/bin/framework`) that floats free of any project pin. The two drift apart constantly:

- A shared system-wide CLI leads a project's pin (the common case — Bearing on `_commit: v0.4.2` under CLI `0.4.5`; Meridian likewise).
- `framework upgrade` today (`self_bump.maybe_self_bump`) **mutates the global install** to the upgrade target, so upgrading project A floats the global to A's new version → project B (older pin) now skews.

Consequences (BRG42, verified against v0.4.5 `main`):

- **FWK138:** under skew, `framework integrity` prints "skipped …" and `raise typer.Exit(0)` (`cli.py:165-170`) — a CI/pre-commit gate **passes green while verifying nothing**.
- **FWK139 #2:** `framework check` reports the **installed CLI** version (`cli.py:149`), not the project's pin — nothing answers "is *this project* behind the latest release?"
- (`restore` already fails loud on skew — `require_version_sync` → `Exit(1)`; the BRG42 "restore exits 0" claim was the countered #3, since confirmed by Bearing.)

### Root cause

Installing a **version-coupled** tool as an **unversioned** global is a category error. A normal global tool (git, ripgrep) has no per-project correctness coupling — any recent version works on any repo. The framework is the opposite: its correctness is *relative to a per-project pin*. The skew is not bad luck; it is the predicted consequence of treating a version-coupled tool as version-free. The fix is not to make the floating global *honest about* skew — it is to **make skew impossible** by keeping the running CLI and the project's template in lockstep, per project.

## 2. Design — self-dispatch + per-project lockstep

**Core idea:** every project-scoped command runs the CLI version that matches the project's `_commit`, resolved *automatically* from the project (never passed on the command line). The CLI and template are always the same version per project, so integrity/restore are trivially correct — no skew, no silent-skip, **no backward-compat surface** (the running CLI never has to understand a template other than its own).

The user types `framework <cmd>` exactly as today. A thin, stable **dispatch front-end** in the CLI re-execs the project-pinned version when needed. This generalizes the existing `self_bump.py` re-exec, with one inversion: **ephemeral cached exec instead of mutating the global install.**

### 2.1 Dispatch rule (startup, before command logic)

On every invocation, the CLI front-end decides where to run, using `.copier-answers.yml` `_commit` for the pin:

| Situation | Runs |
|---|---|
| No project context (`new`, or cwd has no `.copier-answers.yml`) | **self** (whatever is installed — latest, by convention) — *bootstrap* |
| Version-advancing command (`upgrade [--to V]`) | the **target** version (default: latest release) — re-exec if self ≠ target |
| Any other project-scoped command (`integrity`, `check`, `restore`, `upskill`, …) | the project's **pinned** version (`_commit`) — re-exec if self ≠ pin |
| Already re-executed (loop guard env set) | **self** unconditionally |

"Re-exec" = `os.execvp` into `uvx --from git+$REPO@<ref> framework <argv…>` with a loop-guard env var (`FRAMEWORK_PINNED_EXEC=1`) so the target process does not re-dispatch. `uvx` resolves+builds the framework package at `<ref>` and **caches by ref**, so steady-state cost is uv's launch overhead; only the first invocation per (version) fetches.

### 2.2 The inversion vs. today's `self_bump`

`self_bump.run_uv_tool_install` does `uv tool install git+…@target` — it **mutates the global**. The new dispatch uses **`uvx --from git+…@<ref>`** — ephemeral, cached, **no global mutation**. This is the whole fix: the global install (if any) stops being load-bearing; its version no longer affects any project, because project-scoped commands always re-exec the pin. Floating the global becomes harmless.

`self_bump.py`'s reusable seams stay: `reexec`, `is_uv_tool_install` (still the safe-fallback detector), `parse_version`, `REPO_URL`. The mutate-global path (`run_uv_tool_install` for upgrade) is replaced by ephemeral exec; `--bump-cli` is retired (§2.3).

### 2.3 `upgrade` becomes atomic (CLI + template together), for free

`framework upgrade` advances the project to a target template version (`copier update` via `upgrade.py::upgrade_project`). Under the dispatch rule, `upgrade` runs the **target** CLI, which re-renders the template to the target and rewrites `_commit`. Because every *subsequent* project-scoped call reads `_commit`, the CLI is now pinned to the new version automatically — **the CLI and template advanced together in one operation**. The separate `upgrade --bump-cli` / `maybe_self_bump` global-mutation step is no longer needed and is removed. No global was changed; nothing else on the box is affected.

### 2.4 integrity / restore — trivially correct

No code change to the *comparison* logic is required for correctness: by the time `integrity`/`restore` run, the process **is** the pinned CLI, so its bundled template == the project's template by construction. The existing skew check (`project_version_skew`) becomes a near-dead branch on the happy path (self == pin). `restore`'s "disabled on skew" limitation disappears — it always runs at the pin. We **keep** a minimal version of the skew guard as a fail-loud floor (§2.6), not a silent skip.

### 2.5 Staleness signal (FWK139 #2) — homed in `upgrade`, not `check`

Orthogonal to skew: "is the project's pin behind the latest *release*?" Staleness is **detection that prompts an upgrade**, not part of upgrading — it accrues as new releases ship and the project (deliberately) sits at its pin. It therefore lives in the **`upgrade`** flow, for an architectural reason: under the dispatch rule `upgrade` runs the **target/latest** CLI (which reliably knows latest and carries current logic), whereas `check` would run the project's **pinned (old)** CLI (which may predate this feature and cannot be trusted to know "latest"). The detector must run where it dispatches to latest.

- `framework upgrade` previews the gap before acting: `v0.4.2 → v0.4.5 available` (or `already current`).
- `framework upgrade --dry-run` reports the gap and **does not apply** — this is the "am I behind?" answer (BRG42 #2).

Uses the existing `source.latest_release()` (`git ls-remote --tags` → newest `vX.Y.Z`). Degrades gracefully: no network / non-tag `_commit` (SHA pin) → "cannot determine staleness (offline or pinned to a non-release ref)", never a false "up to date". No proactive nudge from the dispatch front-end (it stays silent/fast); the report only fires on an explicit `framework upgrade [--dry-run]`. `check` carries **no** version/staleness role.

### 2.6 Fail-loud floor (FWK138 residual, defense-in-depth)

Self-dispatch makes skew impossible *through the normal path*. The residual is a **bypass**: someone runs a raw mismatched CLI directly (dispatch disabled, a non-`uv` environment where `uvx` is unavailable, or `FRAMEWORK_PINNED_EXEC` forced). In that case integrity must **exit non-zero** on "could not verify" instead of `Exit(0)`. This is the only surviving piece of FWK138 — demoted from headline to cheap insurance. When `uvx` is unavailable and self ≠ pin, the front-end fails loud with remediation (how to install uv / pin), never silently runs self against a mismatched project.

## 3. Components & interfaces

- **`framework_cli/dispatch.py`** (new) — pure dispatch policy `decide_dispatch(*, installed_tag, project_commit, command, reexecuted) -> Dispatch{action: "self"|"reexec", ref}` + the `uvx` re-exec I/O seam (monkeypatched in tests). Reuses `reexec`, `parse_version`, `REPO_URL`. Wired as the first step in the Typer entrypoint (`cli.py app` callback), before any command body.
- **`framework_cli/cli.py`** — add the dispatch callback; remove `--bump-cli` + `maybe_self_bump` from `upgrade`; integrity's skew branch → fail-loud floor (non-zero on could-not-verify); `upgrade` gains the pin-vs-latest gap preview + a `--dry-run` (report, don't apply); `check` loses its CLI-version/staleness reporting.
- **`framework_cli/self_bump.py`** — collapse into `dispatch.py` (keep `is_uv_tool_install`, `reexec`); delete the mutate-global upgrade path.
- **Generated payload** (template):
  - `Taskfile.yml.jinja` preconditions that call `framework integrity` — unchanged in *spelling* (the front-end dispatches), but the comment at the old skip site is removed.
  - `.github/workflows/ci.yml.jinja` — already pins via `uv tool install git+…@$_commit`; keep (it is the same lockstep, made explicit for an ephemeral runner). Optionally simplify to the shim model later; not required.
  - pre-commit local hook (if/where it invokes `framework`) — relies on dispatch.
- **Docs** — `README.md` + design spec: bootstrap is `framework new` on a **latest** install; document that project-scoped commands auto-run the project's pinned version; deprecate the "the global CLI must match your project" guidance. `framework new` install line stays `uv tool install` of latest (or `uvx` one-shot).

## 4. Edge cases

- **Loop guard:** `FRAMEWORK_PINNED_EXEC=1` set on re-exec; the target never re-dispatches.
- **SHA / non-tag `_commit`** (vendoring pattern): `uvx --from git+$REPO@<sha>` still works for dispatch; staleness reports "non-release pin, cannot compare." `parse_version` failures are caught → fail-loud, not crash.
- **Offline, first run of a version:** `uvx` cannot fetch → fail loud with remediation. Cached versions (the common kept-current case, where self == pin → **no exec at all**) are unaffected.
- **No `uv` / not a `uv tool` install:** `is_uv_tool_install()`-style safe detection; if `uvx` is unavailable and self ≠ pin → fail loud (do not silently run self). Self == pin always proceeds.
- **Framework-dev escape hatch:** an env var (e.g. `FRAMEWORK_NO_DISPATCH=1`) forces self — for developing the framework against the working tree. Also implicitly: running outside any project.
- **Performance:** self == pin (kept-current project) → zero exec overhead. self ≠ pin → one cached `uvx` launch. Pre-commit latency to be measured during implementation; escalate to a materialized project-local install only if measured-bad (explicitly out of scope now — YAGNI).

## 5. Migration

- Ship dispatch in the next release. A user upgrades their **global** CLI once to ≥ that release; thereafter every project auto-runs its pinned version. Existing projects need **no change** — `_commit` already records the pin.
- Existing projects pinned below the dispatch release still work: their pinned CLI (the old one) simply runs as today; the *new* global front-end is what dispatches to it.
- `upgrade --bump-cli` is removed; `framework upgrade` alone now moves both. Document the change.

## 6. What this obviates / drops

- **Pin-relative verification** (latest CLI rendering old templates) — and with it the **backward-compat requirement** on the CLI. Not needed: the running CLI never sees a foreign template version.
- **Project-local pinned *install* wrappers** (the A/B/C delivery options) and a separate shim artifact — dispatch lives in the CLI itself, so there is nothing extra to distribute or bootstrap.
- **FWK139's "project-local pinned CLI" as a distinct feature** — it *is* this design.

## 7. Testing

- **Dispatch policy (pure unit):** `decide_dispatch` over the matrix in §2.1 — bootstrap/self, version-advancing→target, project-scoped→pin, loop-guard→self, self==pin→self (no exec).
- **Re-exec seam (monkeypatched):** asserts the `uvx --from git+$REPO@<ref>` argv + loop-guard env; never mutates a global; SHA-ref passthrough.
- **Lockstep upgrade (integration):** `upgrade` re-renders to target + rewrites `_commit`; a follow-up `integrity` runs at the new pin and passes; **no** global mutation occurs.
- **Fail-loud floor:** skew + `uvx` unavailable → non-zero exit with remediation; integrity never `Exit(0)` on could-not-verify.
- **Staleness (in `upgrade`):** `upgrade --dry-run` reports `vX → vY available` for a behind-pin and applies nothing; `already current` when at latest; non-tag pin / offline → graceful "cannot determine", never false "up to date".
- **Conformance (the BRG42 close):** a skewed-project scenario (`_commit` < installed) that previously silent-greened now either dispatches to the pin and verifies for real, or fails loud — never green-while-verifying-nothing.
- Generated-project render/acceptance unchanged except payload comment/CI text; run the template-payload cadence ([[template-payload-tdd-loop]], [[eval-fixtures-coupled-to-template]]) if Taskfile/CI jinja changes anchor fixtures.

## 8. Review & release

Per the working agreement: implementers Sonnet (Haiku trivial); spec-compliance review Sonnet; **code-quality review Opus**; branch-end whole-branch review Opus ([[subagent-review-model-pattern]]). Ships a CLI change (+ minor template payload) → a tagged release (the dispatch behavior must be *in a release* for a global to pick it up). Release per [[release-cut-procedure]] / [[release-readiness-needs-render-not-local-gate]].

## 9. FWK reframe

- **FWK138** → *obviated* except the fail-loud floor (§2.6). Re-scope the row to "integrity fail-loud on bypass" (small).
- **FWK139** → #2 staleness signal kept (§2.5); the "project-local pinned CLI" feature is **closed as obviated by this design** (it is the design).
- New umbrella row for this spec (self-dispatch + atomic upgrade).

## 10. Relationship to FWK68

FWK68 ("convention-lock: exact-pin → presence + floor") is about `framework integrity`'s **convention-version** check tolerating a consumer that adopts a convention (PI/docs/git/cross-repo) *ahead* of the framework. That is a **different axis** from CLI↔template version coupling and is **not** resolved or blocked by this design — they are orthogonal and can proceed independently. Noted here only to prevent conflation.

## 11. Resolved decisions (spec review)

1. **Staleness home & exit code** — *resolved:* staleness moves out of `check` into **`framework upgrade [--dry-run]`** (the only command that dispatches to latest and can reliably know "latest"); `upgrade` previews the gap / `--dry-run` reports without applying. The separate staleness-in-`check` feature and its exit-code question are **dropped**. Staleness is advisory, not a gate (`integrity` is the gate).
2. **Proactive nudge** — *resolved:* none from the dispatch front-end (it stays silent/fast); the gap report fires only on an explicit `framework upgrade [--dry-run]`.
3. **CI alignment** — *resolved:* leave generated CI's explicit `uv tool install @$_commit` as-is (already correct for an ephemeral runner).
