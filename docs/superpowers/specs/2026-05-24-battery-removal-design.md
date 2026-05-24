# Battery Removal — `downskill` (Plan 8a-2) — Design Spec

**Date:** 2026-05-24
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 8a-1 (the additive mechanism: `batteries.py` registry + `resolve`, `render_project`, `read_batteries`/`record_batteries`, the framework-owned `.copier-answers.yml` battery record), 8b (battery-aware `restore` section-splice, `write_manifest` regen on battery-set change, the first managed-section injection). Removal counterpart to 8a-1; unblocked now that real batteries (websockets, webhooks) exist to test against.

---

## 1. Purpose & scope

`framework downskill <project> <battery>` removes a previously-added battery from a generated project. Removal is the **asymmetric, riskier** inverse of `--with`: Copier cannot un-render, so it must be **framework-owned**.

**Spike-confirmed (controller spike):** `run_update` with a *reduced* `batteries` answer does **not** delete the now-unrendered files or strip the injected managed-section line (a same-version answer change is a no-op; `run_update` keys on version change). `run_copy` only adds/overwrites, never deletes. So removal can reuse neither — it is implemented directly by the framework.

**In scope:**
- A `framework downskill <project> <battery> [--force]` command (+ `downskill_project(...)`), mirroring `upskill_project`.
- **Owned-file enumeration via a two-render diff** (the template is the source of truth — no battery→files manifest).
- Stripping the battery's **managed-section** content (reuse 8b's battery-aware section-restore).
- The hard cases: **preserve migrations + warn**, **leave non-managed builder fields + warn**, a **usage-detection** scan (warn/refuse unless `--force`), a **reverse-dependency** refusal.
- Re-record the reduced battery set + **regenerate the integrity manifest** (the inverse of 8b's upskill regen) + run `task test`.

**Out of scope (deferred):**
- Auto-removing a battery's **migration/table** (a DB may have applied it) → the builder writes a contract down-migration (5c-1 discipline); downskill only warns.
- Auto-editing **non-managed builder files** (`settings.py`) → leave + warn.
- Removing **multiple** batteries in one invocation (run it per battery for v1).
- Deep/dynamic usage analysis → the scan is a heuristic guardrail, not a guarantee.

## 2. Decisions (settled in brainstorm + spike)

- **Framework-owned removal** (spike-confirmed `run_update`/`run_copy` can't do it).
- **Owned files = a two-render set difference:** `owned(X) = files(render(batteries=current)) − files(render(batteries=current−{X}))`. No tracked battery→files list; the bundled template is authoritative.
- **Migrations preserved, not deleted** (excluded from the delete set) + warn.
- **Managed-section content stripped** by re-rendering the section at the reduced set (reuse `restore`); **non-managed builder-file content left** + warn (don't clobber builder edits).
- **Usage scan** warns and refuses unless `--force`; **reverse-dep** refuses outright.
- **Re-record + regenerate the manifest** so `framework integrity` stays green and `restore` reproduces the post-removal canonical.
- **Command:** dedicated `framework downskill <project> <battery> [--force]`; git-tracked project required (review/revert the diff).

## 3. The removal mechanic (`downskill_project`)

`downskill_project(project: Path, battery: str, *, force: bool = False) -> bool` — returns whether the project's tests pass afterward (mirrors `upskill_project`). Steps, in order:

1. **Validate:** `battery` is registered (`get_battery`); `battery ∈ read_batteries(project)` (else "not active"); the project is git-tracked (else `UpskillError`/a removal error — reuse the `_is_git_tracked` guard).
2. **Reverse-dep check:** for each active battery `B ≠ X`, if `X` is in `resolve([B])`'s closure (B requires X) → refuse with a clear error naming B. (Inert today; live for 8f's `pgvector ⇒ postgres`.)
3. **Usage scan:** scan the project's builder code/config (everything **except** `owned(X)`, which is about to go) for references to the battery — its package import (`<package_name>.<battery>`), its route path, its env var, its model name. If any hit → print them and **refuse unless `force`**.
4. **Enumerate owned files** via the two-render diff (render the bundled template twice into temp dirs with the project's real answers — name/package/etc. from `_answers` — at `current` and `current − {X}`; relative-path set difference). **Delete** each from the project **except** any under `migrations/versions/` (preserved — see §4).
5. **Strip managed-section content:** for each `HYBRID_TRACKED` file (`.env.example`, …) whose section differs at the reduced set, re-render its `FRAMEWORK:BEGIN/END` section at `current − {X}` and splice it in (reuse the 8b/`restore` section-splice). This removes the battery's injected lines (e.g. `APP_WEBHOOK_SIGNING_SECRET`).
6. **Record + regenerate:** `record_batteries(project, current − {X})`; `write_manifest(project, installed_framework_version())` (guarded on the lock existing, as in 8b) so the integrity manifest matches the post-removal state.
7. **`task test`** (as in `upskill_project`) → report green/red; a removal that broke builder code surfaces here (the usage scan's backstop).

## 4. The hard cases

- **Migrations — preserve + warn.** The two-render diff flags the battery's `0002_webhook_events.py` as owned, but deleting it is unsafe: a DB already at revision `0002` would point at a missing script (broken Alembic history). So `migrations/versions/*` is **excluded from deletion**, and downskill warns: *"the `<battery>` migration and its table remain — write a contract down-migration (5c-1 expand/contract) to drop the table if you want it gone."* Schema teardown is the builder's deliberate call.
- **Non-managed builder files (`settings.py`) — leave + warn.** The `webhook_signing_secret` field is `{% if %}`-gated but `settings.py` has no `FRAMEWORK` markers and isn't locked (builder-extendable app source). Auto-editing risks clobbering builder code, and the dead field (default `""`, read by nothing once the route is gone) is harmless. So **leave + warn** ("a `<field>` setting remains; remove it manually if desired"). Deliberate asymmetry with the `.env.example` secret, which *is* stripped because it lives in a framework-owned managed section.
- **Usage detection — heuristic guardrail.** Scans for the battery's import path / route / env var / model in builder files (excluding `owned(X)`). Refuses unless `--force`; honest that it can't catch dynamic references. `task test` (step 7) is the backstop.
- **Reverse-dependency — refuse.** Built on the registry's `requires`; inert until 8f.

## 5. Command & reporting

`framework downskill <project> <battery> [--force]` calls `downskill_project`. On a usage-scan/reverse-dep refusal: a clear error + non-zero exit (and, for usage, "re-run with `--force` to remove anyway"). On success, report: the files removed; the **preserved** migration (+ how to drop the table); the **left** settings field; and the `framework integrity` + `task test` result. Like `upskill`, conflicts/breakage are surfaced, not hidden.

## 6. Testing (hermetic where possible; Docker for the round-trip)

- **Unit:** the two-render owned-files diff returns the battery's whole files and **excludes** `migrations/versions/*`; the reverse-dep refusal (synthetic `A.requires = (B,)` → removing B while A active → refused); the usage scan flags a planted `<pkg>.<battery>` import in a builder file.
- **CLI (bundled, no Docker):** `framework new --with webhooks` → `framework downskill <proj> webhooks` →
  - `routes/webhooks.py`, the `webhooks/` package, and `tests/functional/test_webhooks.py` are **gone**;
  - the `0002_webhook_events.py` migration is **preserved** (+ a warning in the output);
  - the `.env.example` `APP_WEBHOOK_SIGNING_SECRET` line is **stripped**;
  - the `settings.py` field is **left** (+ a warning);
  - `read_batteries == []`; `framework integrity --ci` is **green** (manifest regenerated).
  - Usage scan: a project whose builder code imports the battery → downskill **refuses** without `--force`, **proceeds** with it.
- **Acceptance (Docker):** downskill a webhooks project → the remaining generated suite passes (`task test` green) — removal leaves a working project.

## 7. Self-review

- **Placeholders:** none — the mechanic (two-render diff), each hard case, the command/flow, and the tests are concrete; the spike settled the keystone (framework-owned, not `run_update`). Schema teardown + multi-battery removal + deep usage analysis are explicitly deferred (YAGNI), not hand-waved.
- **Internal consistency:** removal reuses 8a-1/8b machinery (`render_project`, `read_batteries`/`record_batteries`, the section-restore, `write_manifest`); the manifest regen is the exact inverse of 8b's upskill regen, keeping `integrity`/`restore` consistent; the two-render diff makes the template the single source of truth (no separate battery→files map to drift).
- **Scope:** one cohesive operation (validate → guard → delete owned → strip sections → re-record → test). Migration/settings teardown and multi-removal deferred.
- **Ambiguity:** "owned files" is pinned to the two-render set difference; managed-section stripping (re-render) vs. non-managed leaving (warn) is made explicit; the usage scan is explicitly a heuristic with `task test` as the backstop.

---

*End of design. Next step: `superpowers:writing-plans` for Plan 8a-2.*
