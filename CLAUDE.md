# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-24 (8a-2 Task 2: owned-files two-render diff — `owned_files()` + `_render_paths()` added to `downskill.py`; renders WITH/WITHOUT battery, returns set difference; 5 tests green, ruff + mypy clean)
- **Where we are:** Plans 1–6b + **Plan 7 (7a–7d) all merged to `master`** (7d FF `a92b85e`): the full Layer-3 review-agent system — the `framework review` runner, the 12-agent set + dynamic CI matrix, the aggregator + single sticky PR comment (`framework review-aggregate`), and the hermetic eval harness (`framework eval` + golden fixtures for all 12 agents + `agent-evals.yml`). Detail in `docs/superpowers/plans/2026-05-23-{review-aggregator,eval-harness}.md`. ⚠ **7d is not yet e2e-tested** (no real Anthropic key in this env; thresholds provisional) — see **Known follow-ups**; Plan 9 validates it.
- **Plan 8 (batteries) progress:** **8a-1 (battery mechanism) merged** (FF `ea9a192`) — `batteries.py` registry + `resolve()`, `framework new/upskill --with`, router autodiscovery (route batteries are pure file-adds), conditional rendering via a `type: yaml` `batteries` answer, framework-owned battery record in `.copier-answers.yml` (Copier drops the subdir answer through the portable `_subdirectory` source on update — `upskill_project` re-records). **8e websockets** delivered as the 8a-1 vehicle. Detail: `docs/superpowers/plans/2026-05-24-battery-mechanism.md`.
- **Plan 8b (webhooks battery) — merged to `master` (FF `5af2006`).** A thin HMAC-SHA256-signed ingress (`POST /webhooks`, constant-time verify, empty-secret rejects) → DB **transactional inbox** dedup (`webhook_events`, `idempotency_key` UNIQUE, key=`sha256(raw_body)`, dedup+effect in one tx) → a builder `handle_event` **dispatch seam** (composes with workers/8c later), fast 2xx; a malformed body → **400** (parsed before the inbox, so it leaves no row); a duplicate → 200 no-op. The signing secret is the **first managed-section injection** — `APP_WEBHOOK_SIGNING_SECRET` into `.env.example`'s checksummed `FRAMEWORK:BEGIN/END` section + a `settings.py` field + a conditional `0002_webhook_events` migration. Because that section's checksum is now battery-dependent, two integrity fixes landed: **`restore` is battery-set-aware** (`_answers` preserves the `batteries` list, not `str()`-coerced) and **`upskill_project` regenerates the manifest** after `run_update` (guarded on the lock; also closes the latent plain-upskill gap). See `docs/superpowers/plans/2026-05-24-webhooks-battery.md`.
- **Verification (8b):** `ruff`/`mypy`/`uv lock --check` clean (no new runtime deps — hmac/hashlib stdlib), **full suite 262 passed / 0 failed** (incl. Docker acceptance + a new **with-webhooks** variant: the generated functional tests [valid-sig 200 / bad-sig 401 / duplicate-dedup / malformed-400] run against real Postgres, asserting `routes/webhooks.py` 100% coverage). Built subagent-driven across 6 TDD tasks, each spec + code-quality reviewed. Real defects caught + fixed: (1) the Task-4 restore test wasn't a true regression test (old `str()`-coercion substring-matched by accident) → added a direct `_answers`-returns-a-list test; (2) a non-ASCII signature header 500'd → `verify` compares bytes; (3) **the final whole-branch review caught the malformed-JSON-after-valid-signature 500** (spec §5 wants 4xx; 5xx triggers provider retry storms) → fixed to 400 + a generated test. The headline integrity coupling was verified with a **real `run_update` upskill round-trip + a negative control** (corrupt the checksum → integrity fails → `write_manifest` → passes). Battery files are template payload (not shipped in the wheel); the no-battery render is byte-identical to before.
- **Next (▶ RESUME HERE):** continue Plan 8: **8a-2** (battery removal `--downskill`/`--without` + usage-detection — now richer: removal must un-inject the `.env.example` managed-section secret AND regenerate the manifest [the inverse of 8b], and battery migrations can't be removed by deleting files [need a down-migration]); **8c** workers (+ Plan 4 DLQ; webhooks' `handle_event` seam composes with it; also the place for the `review-architecture` "simplistic-webhook-vs-workers" heuristic); **8d** graphql (+`review-api-design`); **8f** db paradigm batteries + wizard; **8g** react (+`review-accessibility`/`review-usability`); **8h** consumers. Also: **5c-2**, **9** (dogfooding CI + `SECRETS.md` + e2e-validate 7d), **10** (docs pack). Conventions in auto-memory ([[key-label-convention]]). Next slice: `writing-plans` directly for 8a-2 (design in the meta-plan) or `brainstorming` for a fresh battery → subagent-driven.

## Keeping state current (required before every commit)

Before every commit, update the **Current State** pointer above — including **Last updated** as a datetime with timezone (e.g. `2026-05-21 09:19 PDT`, since we commit several times a day) — and the meta-plan's status table when a plan's status changes, then `git add CLAUDE.md`. This keeps the repo's state accurate as we move across machines and environments. A `PreToolUse` hook in `.claude/settings.json` enforces this — it blocks `git commit` until `CLAUDE.md` is staged. Run `/hooks` to review or disable it.

## How we build here
- Work proceeds plan-by-plan per the meta-plan, using the superpowers subagent-driven flow: a feature branch → an implementer per task (TDD) → controller verification → a final review → merge to `master`.
- TDD is required: write the failing test first, confirm red, implement the minimum, confirm green.

## Quality gate (must be green before commit / merge)
```bash
uv run pytest -q          # all tests
uv run ruff check .       # lint
uv run mypy src           # type-check (framework source only)
```
`uv` is the package manager — run all tooling via `uv run`. If `uv` is not found, make sure its install directory is on PATH (restart the session after a fresh install).

## Critical conventions
- **`src/framework_cli/template/` is template *payload*, not framework source.** Those `.jinja` / `.py` / config files are rendered into generated projects — do not refactor or lint them as framework code. The framework's own `mypy` excludes that directory. The template is validated by rendering it and exercising the generated project: `tests/test_copier_runner.py` (files render / interpolate) and `tests/acceptance/test_rendered_project.py` (the generated project's own tests, coverage gate, and pre-commit pass).
- Brace-named paths like `src/framework_cli/template/src/{{package_name}}/` are intentional Copier path templating — leave them.
- The CLI (`src/framework_cli/`) is a thin shell over Copier; keep logic in focused modules (`naming.py`, `copier_runner.py`, `cli.py`).
- Changing the template means re-running the render + acceptance tests. A freshly generated project must make a clean first `pre-commit` pass — enforced by `test_rendered_project_precommit_runs_clean`.

## Known follow-ups
- **⚠ Plan 7d is NOT e2e-tested.** The eval harness suite is fully green but **hermetic** — no real Anthropic call has ever exercised it (no `ANTHROPIC_API_KEY` was available). The agents have never actually been scored against the golden fixtures, so the `0.67`/`0.34` thresholds are **provisional** and an agent's real recall/precision is unknown. **Resolution:** set the `ANTHROPIC_FRAMEWORK_CI_EVAL` repo secret and let the first scheduled `agent-evals.yml` run produce a real scorecard (then tune `tests/eval/fixtures/thresholds.yaml`). **Plan 9 (dogfooding) must explicitly verify this** — a real eval run is the e2e gate 7d couldn't perform itself.
- *(resolved in Plan 6b)* `.copier-answers.yml` now records a portable `_src_path` (`gh:cdowell-swtr/swiftwater-framework`) + `_commit` (`vX.Y.Z`); the repo-root `copier.yml` makes `git+<repo>@<tag>` a Copier source, so `framework upskill` / `copier update` work across machines.
