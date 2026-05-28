# Unified Configurable Wizard (8f-w) — Design

**Date:** 2026-05-27
**Plan ref:** Plan 8f-w (meta-plan `docs/superpowers/plans/2026-05-20-meta-plan.md`) — the last item in Plan 8.
**Status:** Design approved; awaiting implementation plan (writing-plans).

## Summary

`framework new` gains a guided, interactive front-end — a **wizard** — with two halves plus a reconfigure path:

1. **DB-paradigm selection** — a needs-language interview that *resolves to existing atomic batteries* (`pgvector` / `mongodb` / `timescaledb` / `age` / `redis`). Pure `new`-time UX; no new payload.
2. **Alert-channel selection** — brand-new recorded state (`alert_channels`) that drives the alertmanager receivers + the secrets the deploy materializes, with a hard guarantee that a configured-but-undeliverable channel **fails loudly instead of silently swallowing alerts**.

Both are scaffold-time configuration, built together (per the roadmap). The wizard engine is built **generically** (registry-driven) but populated only with these two questions in this slice; adding more questions later is registry data, not new machinery.

## Goals

- Give builders a friendly `framework new` interview instead of memorizing `--with <battery>` tokens, while keeping flags first-class for experts and CI.
- Add multi-channel alert configuration (Slack / email / PagerDuty, alongside the existing generic webhook) as framework-managed, integrity-tracked config.
- **Kill the silent no-op**: the current alertmanager `url_file` pattern tolerates a missing secret file (notifications silently no-op). A configured channel with missing connection details, or a genuinely undeliverable channel, must fail loudly — this is the dev-only-not-prod / silent-failure defect class the framework exists to eliminate.

## Non-Goals (this slice)

- Non-db batteries in the **interactive** wizard (webhooks/workers/websockets/graphql/react/consumers stay `--with`-only for now; the engine is built so adding them later is registry data).
- Hermetic local-sink delivery testing (MailHog/mock HTTP) — considered and deferred; #1 + #3 (below) cover the guarantee.
- Severity-based alertmanager route trees / multi-receiver routing — a single `default` receiver only.
- Per-environment channel sets — one scaffold-time channel set applies across environments.

---

## 1. Wizard Engine

A generic, registry-driven question runner inside the CLI, using **`questionary`** (promoted from a transitive dep — via Copier — to a **direct framework runtime dependency**; it runs inside `framework new`, so it is a real runtime dep, not template-only. It is already in the resolved lock tree, so this adds no new transitive surface).

**Interactive vs non-interactive fallback** (the Copier-style model, implemented in the CLI):

- `framework new MyApp` on a **TTY** with **no wizard-relevant flag** → interactive prompts.
- Any wizard-relevant flag passed (`--with`, `--alerts`, …) → that question is **skipped** (the flag is the answer); other questions may still prompt interactively.
- stdin is **not a TTY** (CI, tests, scripts, pipes) → **no prompts**; every unspecified question takes its default.

The orchestration is roughly: for each registered question, if its backing flag was supplied use it; else if interactive prompt; else use the default. This is ~a dozen lines around the existing call. **All answers continue to flow through the same `render_project(data=…)` dict** — the wizard only *sources* answers; it does not change the render path, naming, or battery-resolution logic.

The engine is a small registry of question specs (id, prompt text, kind [checkbox/select/confirm], options, backing flag, default, and a resolver hook). This slice registers two: `data_needs` and `alert_channels`.

---

## 2. DB-Paradigm Half

A `checkbox` of capabilities in **needs-language**, each option mapped to a battery. (Capability-first phrasing follows the "offload architecture, don't delegate it" principle — the builder picks a need, the framework resolves the technology.)

| Prompt option | Resolves to |
|---|---|
| Relational (always on) | — (baseline; shown locked/informational, not selectable-off) |
| Document store | `mongodb` |
| Vector / similarity search | `pgvector` |
| Time-series | `timescaledb` |
| Graph (Cypher) | `age` |
| Cache / key-value | `redis` |

Selections are **unioned** with any `--with` flags, then passed through the existing `resolve_batteries` (dependency-closure + validation unchanged). No new scaffolding — this is purely a friendlier mouth onto the battery system.

**Lifecycle:** the db half is a `new`-time front-end only. Post-`new` changes ride the existing battery commands (`framework upskill --with`, `framework downskill`). No new lifecycle code for the db half.

---

## 3. Alert-Channel Half

### Recording

A new framework-owned answer **`alert_channels`** (a list, exactly like `batteries`) recorded in `.copier-answers.yml`, surfaced into the render `data` dict, and recorded by the CLI. **Default value: `["webhook"]`.**

### Channels & receiver model

The prompt offers `{webhook, slack, email, pagerduty}`, with `webhook` pre-selected. The selected set *defines* the single `default` receiver's `*_configs` blocks in `alertmanager.yml`.

**Key invariant:** when `alert_channels == ["webhook"]` (the default), `alertmanager.yml` renders **byte-identical to the current committed file** → **no baseline manifest shift**. Any other set renders the chosen receivers. This follows the established LOCKED-file conditional-render precedent (`ci.yml` / `dev.yml` are byte-identical without their gating battery; the integrity manifest is already answer-aware).

`webhook` remains a real, selectable channel (the generic HTTP integration); it is not special beyond being the default.

### Secrets — file-mount, per channel

Each channel delivers its secret via a **mounted file** (consistent with the existing `url_file`; the busybox alertmanager image has no `envsubst`). Verified field names (Alertmanager docs): `slack_api_url_file`, `smtp_auth_password_file`, `routing_key_file`.

| Channel | alertmanager field(s) | `.env.example` managed-section var(s) |
|---|---|---|
| webhook | `url_file` | `APP_ALERT_WEBHOOK_URL` *(exists today)* |
| slack | `api_url_file` (or global `slack_api_url_file`) | `APP_ALERT_SLACK_API_URL` |
| pagerduty | `routing_key_file` | `APP_ALERT_PAGERDUTY_ROUTING_KEY` |
| email | `auth_password_file` + plain config | `APP_ALERT_SMTP_SMARTHOST`, `APP_ALERT_SMTP_FROM`, `APP_ALERT_SMTP_TO`, `APP_ALERT_SMTP_AUTH_USERNAME`, `APP_ALERT_SMTP_AUTH_PASSWORD` |

Each selected channel's vars are gated into the `.env.example` `FRAMEWORK:BEGIN/END` section (hybrid-integrity-tracked; its checksum is already answer-dependent since 8b). Secret files are materialized on deploy and mounted into the alertmanager container via `observability.yml` (also LOCKED, also conditionally rendered, byte-identical for the `["webhook"]` default).

> **Email note:** email is the only channel needing non-secret config alongside its secret (smarthost/from/to/username). Those are plain `.env` vars in the managed section; only the password uses `auth_password_file`.

---

## 4. Deliverability Guarantees

### #1 — Secrets-present precondition (hermetic; the silent-no-op killer)

A standalone check script invoked as a **deploy precondition in `strategy.sh`**, *before* alertmanager comes up: for every channel in `alert_channels`, its required secret(s) must materialize **non-empty**, else **hard-fail the deploy**. The `_file` mechanism tolerates absence at notify time (the silent no-op); this external gate makes the absence loud.

**Framework-side test:** render a project with a channel selected, leave its env var empty, run the precondition → assert non-zero exit; set it → assert zero. Fully hermetic, always-on.

> CI of the *generated project* does not hold the deploy-environment secrets, so the presence check's real home is the deploy precondition (where secrets are materialized from env). The hermetic framework test exercises the script directly.

### #3 — Real delivery smoke at deploy (advisory; fidelity)

A deploy-seam smoke step (Plan 5b Phase 1/2): fire a **synthetic, clearly-labeled, auto-resolved** test alert into alertmanager, then read alertmanager's own metric `alertmanager_notifications_failed_total{integration=…}` — if it incremented for a configured channel, the channel is genuinely misconfigured → report failure.

- **Advisory / non-rollback** — a third-party (Slack/PagerDuty) blip must not fail the deploy or trigger a rollback (recoverability ethos). It reports, it does not gate.
- **Non-paging** — the test alert is synthetic and immediately resolved; it must not page a human on every deploy.
- Using alertmanager's own failure metric verifies *actual* deliverability (not merely "queued"), on-ethos (the obs stack's own signals).
- **Cannot run hermetically in-sandbox** → CI/deploy-gated caveat class (react/pact precedent). The smoke script's *logic* is unit-tested against a faked alertmanager metrics endpoint; the real run happens in a deploy environment.

### Bonus — steady-state meta-alert (included)

An always-on `AlertmanagerNotificationsFailing` alert rule on `alertmanager_notifications_failed_total`, so delivery breakage in steady-state (not just at deploy) surfaces in Grafana rather than silently swallowing alerts. Reinforces "no silent failures" beyond deploy time.

---

## 5. Lifecycle & Integrity

- **`new`** — wizard records both `batteries` and `alert_channels`; render + manifest as today.
- **`framework upskill <proj> --alerts slack,email`** — re-renders `alertmanager.yml` + the `.env.example` managed section, re-records `alert_channels`, regenerates the integrity manifest (mirrors `upskill --with` for batteries). **Set-replacement semantics**: *removing* a channel is `--alerts` with a smaller set, so no separate downskill-for-channels is needed.
- **Integrity** — `alertmanager.yml` + `observability.yml` become conditionally-rendered LOCKED files (byte-identical when `alert_channels == ["webhook"]` → no baseline manifest shift). The `.env.example` hybrid section is already answer-aware. Non-default channel sets shift the manifest only for that project, as expected.

---

## 6. Testing Strategy

- **Engine (unit):** TTY-detect + skip-prompted-question-when-flag-passed (mock `isatty`/questionary); needs→battery mapping; channel parsing/validation.
- **Render:** each `alert_channels` variant produces the right receiver blocks + `.env` vars; **byte-identical assertion for the `["webhook"]` default**.
- **Integrity:** green across channel combinations; no baseline manifest shift for the default.
- **#1 precondition (hermetic):** render project + channel, run precondition with the secret unset → non-zero; set → zero.
- **`upskill --alerts`:** re-render + re-record + integrity green; reducing the set strips the right vars/receivers.
- **Config validity (acceptance):** `amtool check-config` (or `docker compose config`) on `alertmanager.yml` for each channel combo.
- **#3 smoke:** unit-test the smoke script's logic against a faked alertmanager metrics endpoint; the real run is **deploy/CI-gated** (documented caveat).

---

## 7. Surfaces Touched

- `src/framework_cli/cli.py` — `new` gains the wizard front-end + `--alerts` option; `upskill` gains `--alerts` reconfigure.
- `src/framework_cli/` — a new wizard engine module (generic question registry + interactive/fallback runner); an alert-channels resolver/recorder (sibling of the batteries recording in `source.py`).
- `pyproject.toml` / `uv.lock` — `questionary` promoted to a direct dependency.
- Template (conditionally rendered, byte-identical for the default):
  - `infra/observability/alertmanager/alertmanager.yml` (LOCKED) → `.jinja`, conditional receivers.
  - `infra/compose/observability.yml` (LOCKED) → conditional secret-file mounts.
  - `.env.example` (HYBRID) → per-channel managed-section vars.
  - `infra/deploy/strategy.sh` + a new alert-secrets precondition script.
  - A new deploy-seam alert-smoke script (#3).
  - `infra/observability/prometheus/alerts/` → the `AlertmanagerNotificationsFailing` rule.
- `src/framework_cli/integrity/classes.py` — no new LOCKED entries (the touched files are already tracked); confirm answer-aware rendering covers them.

## 8. Open Questions / Risks

- **`questionary` UX in odd terminals** — confirm graceful behavior under no-TTY and dumb terminals (the fallback path covers it; verify in tests).
- **Email config breadth** — the email channel pulls in several non-secret vars; keep the managed-section block tidy and well-commented.
- **#3 metric timing** — `alertmanager_notifications_failed_total` is asynchronous; the smoke needs a short bounded wait/poll before reading it. Tune in the plan.
- **Spike to confirm** exact alertmanager `*_file` field placement (global vs per-receiver) for slack/email/pagerduty when templating the receivers.
