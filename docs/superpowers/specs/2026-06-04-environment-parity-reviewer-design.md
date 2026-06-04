# Environment-Parity Reviewer — `review-env-parity` (Plan 17) — Design Spec

**Date:** 2026-06-04
**Plan:** 17 (meta-plan `docs/superpowers/plans/2026-05-20-meta-plan.md`)
**Depends on:** Plan 11 (context-aware review spine — agentic tier), Plan 16 (frontend-obs surface exists to guard)
**Status:** approved (brainstorm), pending implementation plan

---

## 1. Purpose & boundary

A new **agentic** review agent, `review-env-parity`, that guards the **dev→ci→stage→prod
environment chain** against the *dev-only-not-prod* antipattern: a runtime service, environment
variable, or its declaration present in one environment but missing (or unreachable) in another.

This class has bitten the framework **twice, each caught by a human, never by an agent**:

- **OBS-PROD** — the entire observability stack was `dev`-profile only; prod ran blind.
- **SVC-PROD** — battery services (worker/beat/mongo/redis) were `dev.yml`-only; a battery-using
  project deployed to prod with no background processing and no data stores.

The design spec's promise is environment parity "dev through prod" (§Environment Model, §9). This
reviewer is the automated guard that makes a regression of that promise a blocking finding.

**Boundary — domain split with `review-observability-infra`.** The existing
`review-observability-infra` agent already owns the *observability* slice of parity (a scrape job /
exporter / alert rule that's dev-only). To keep a clean separation of concerns and avoid disturbing
a calibrated agent, `review-env-parity` owns the **non-observability** parity classes only:

| Concern | Owner |
|---|---|
| Obs scrape/exporter/alert/dashboard that's dev-only or incomplete | `review-observability-infra` (unchanged) |
| **Runtime service** (app/worker/beat/datastore) that doesn't reach an env it should | **`review-env-parity`** |
| **Environment variable** declared/consumed inconsistently across `.env.example` ↔ compose ↔ settings | **`review-env-parity`** |
| PII/secret *content* in a config value | `review-privacy` / `review-security` (unchanged) |

`review-observability-infra` is **not modified** by this plan. A change that touches
`observability.yml` *and* adds a worker may legitimately draw a finding from each agent — but on
different facets (the missing alert vs the dev-only service), which is correct, not a conflict.

---

## 2. Scope — divergence classes

**In scope (the two classes the reviewer flags):**

1. **Service parity (recall-biased / greedy).** A runtime service defined in a dev-scoped overlay
   that does not reach an environment it should — primarily staging/prod. The repeated real failure
   mode is *missing* dev-only things, so the reviewer is deliberately **greedy**: it enumerates
   every service per environment and treats **any service that exists only in a dev-scoped overlay
   as a finding, unless it is unmistakably local-developer-experience tooling** (TLS termination for
   local HTTPS such as Traefik/mkcert, a mail catcher, a DB admin UI). Even for those, the bias is
   toward a finding that gets *acknowledged* via the decisions log (§5) over silent omission. A
   false alarm is cheap; a prod-blind miss is the defect we are eliminating.

2. **Environment-variable parity.** A variable that is inconsistent across the three declaration
   surfaces — `.env.example` (the contract shipped to every environment), compose `environment:` /
   `${VAR}` interpolations, and `src/<pkg>/config/settings.py` (the consumer). Concretely:
   - consumed in `settings.py` but **absent from `.env.example`** → a prod deploy is silently
     missing required config;
   - referenced as `${APP_FOO}` in a compose overlay but **never declared** in `.env.example`;
   - declared in `.env.example` but read in `settings.py` under a **divergent name** (drift).

**Out of scope (YAGNI):**

3. **Generic config-*value* divergence** (a feature flag on in dev, off in prod). Divergence of
   *values* across environments is the intended purpose of overlays, so an agent here would
   over-fire on correct design. Excluded. The reviewer flags *presence/declaration* parity, not
   *value* parity.

---

## 3. The parity oracle — how the agent reasons

An environment is **not a single file**; it is a *composition of overlays*. "In `dev.yml` but not
`prod.yml`" is therefore **not** a sound signal on its own. The authoritative env→overlay
composition lives in two places the agentic reviewer must read:

- **`Taskfile.yml`** — local environments:
  - `dev` = `base.yml` + `observability.yml` + `dev.yml` (`--profile dev`)
  - `dev:lite` = `base.yml` + `dev.yml` (`--profile lite`) — the deliberate obs opt-out
  - `test` = `base.yml` + `test.yml` (`--profile test`)
- **`infra/deploy/strategy.sh`** + **`infra/deploy/README.md`** — deployed environments:
  - `staging` / `prod` = `base.yml` + `<env>.yml` + `services.yml` + `observability.yml`

**Reasoning rule the agent applies:** a service/variable *reaches* an environment iff it is defined
in an overlay that environment composes. A service defined **only** in `dev.yml` does **not** reach
staging/prod — flag it (the correct home for a prod-reaching service is `base.yml`, or
`services.yml` for battery services) unless it is clearly local-dev tooling (§2.1). Because the
reviewer is **agentic** (Plan 11 spine), it has root-confined `read_file` / `grep` / `glob` and
follows these references across files rather than diffing one overlay against another.

The agent prompt explicitly names these composition sources so it never reduces the check to a naive
file-vs-file diff — the nuance that prevents both false positives (flagging legitimately dev-only
Traefik) and false negatives (missing a worker that's only in `dev.yml`).

---

## 4. Reviewer registration

A single `AgentSpec` added to `_SPECS` in `src/framework_cli/review/registry.py`, plus its prompt
file `src/framework_cli/review/agents/env-parity.md`:

| Field | Value | Rationale |
|---|---|---|
| registry key | `env-parity` | short name; decision files target `review-env-parity` |
| `name` | `review-env-parity` | |
| `block_threshold` | `high` | a genuine parity gap blocks the gate (§ Plan-17 decision) |
| `active_when` | `file-trigger` | parity can only break when the parity surface changes |
| `model` | `AGENTIC_MODEL` (`claude-opus-4-8`) | multi-file reference-following loop |
| `on_push` | `False` | the file-trigger already scopes it; not in the reduced push subset |
| `trigger_globs` | `("infra/*", ".env.example", "src/*/config/settings.py")` | the parity surface |
| `context` | `ContextPolicy("agentic")` | tool-using loop, no static globs |

`trigger_globs` is the **union** of the compose/deploy surface (`infra/*` — overlays +
`strategy.sh`), the env contract (`.env.example`), and the consumer (`config/settings.py`). Matches
`observability-infra`'s `file-trigger` shape; the two coexist on `infra/*` by design (§1).

---

## 5. Decisions-log integration (the pressure-release for the greedy posture)

A greedy reviewer surfaces intentional dev-only choices, so those need a one-time "acknowledged"
path instead of re-firing every PR. **No new code is required** — `review-env-parity` rides the
existing, agent-agnostic decisions mechanism (`src/framework_cli/review/decisions.py`, spec
2026-06-01):

- `runner.py` injects the decisions protocol block into **every** agent's prompt.
- An `accepted` (or `deferred`) decision file under `docs/superpowers/decisions/` with
  `agents: [review-env-parity]` and a `premise` is matched by the agent: when the premise still
  holds it **still emits** the finding but tags it `acknowledged: "<id>"`; `analyze.py` segregates
  acknowledged findings into a non-actionable section, so they **don't block and don't re-surface**.
- If the **premise breaks** (the acknowledged dev-only service later acquires a prod dependency),
  the agent re-emits a normal blocking finding tagged `stale: "<id>"`. Self-healing suppression.

**Example.** Traefik is intentionally dev-only (the platform LB terminates TLS in prod). Record one
decision: `agents: [review-env-parity]`, `concern: traefik dev-only`, `premise: "prod TLS is
terminated by the platform load balancer, not an in-stack reverse proxy"`. Thereafter the reviewer
acknowledges Traefik silently — and re-fires if a future change makes the app depend on Traefik in a
deployed environment.

The plan ships at least one such decision **fixture/example** so the workflow is demonstrated and
tested. The decisions directory is review-target-relative and fail-open when absent (generated
projects' builders use the same mechanism).

---

## 6. Eval fixtures & calibration

Following the established `tests/eval/fixtures/<agent>/{bad,good}/<case>/` layout
(`fixture.yaml` + `change.patch` [+ `expect.json` naming the seeded `file` for bad cases]).
**Three bad + one good**, rendered-project fixtures (Plan 11 agentic-tier convention):

- `bad/service-dev-only` — a worker (or datastore) service added to `dev.yml` only, never reaching
  `services.yml`/`base.yml`. `expect.json → {"file": "infra/compose/dev.yml"}`.
- `bad/env-var-consumed-not-declared` — `settings.py` reads a new `APP_*` that `.env.example` never
  declares. `expect.json → {"file": "src/<pkg>/config/settings.py"}` (or `.env.example` — fixed at
  build time to the line the agent is expected to cite).
- `bad/env-var-in-compose-not-declared` — a compose overlay interpolates `${APP_*}` with no
  `.env.example` declaration. `expect.json → {"file": "infra/compose/<overlay>.yml"}`.
- `good/parity-preserved` — a new service added to `base.yml` (reaches every env) **with** its
  variable declared in `.env.example` **and** consumed in `settings.py`. Fully parity-complete →
  the reviewer must stay silent (false-positive guard). The good fixture is deliberately *not* a
  legitimate-dev-only-tool case, to avoid testing against the greedy posture.

**Threshold philosophy (recall-first).** Calibrated during `/reviewers:tune` in the plan, but the
policy is explicit: this agent protects **recall** at the cost of a higher `fp_max` ceiling
(comparable to `observability-infra`'s `fp_max: 0.43`), because a missed parity gap is the
high-cost, twice-shipped defect. Entry added to `tests/eval/fixtures/thresholds.yaml` with the
observed-value comments, per the calibration convention (`recall_min = observed − 0.10`,
`fp_max = observed + 0.10`, recall floor never below the policy unless the agent honestly
under-finds).

---

## 7. Tests & guards

- **Registry/coverage invariants (already enforced):** registering the agent forces it through the
  existing gates — `test_every_registered_agent_has_fixtures` (T-style coverage), the registry
  shape tests, and the eval scoring harness. The plan satisfies these in the same task that
  registers the agent (mirrors how `review-contracts`/`-observability-*` landed).
- **Prompt-fit / behavior:** the agent's eval pass (3 bad detected, 1 good clean) is the primary
  behavioral test, run via `/reviewers:tune` against the rendered fixtures.
- **Decisions integration test:** a test (or the shipped decision example) demonstrating an
  `accepted` decision targeting `review-env-parity` produces an `acknowledged` (non-blocking)
  finding, and a broken premise produces a `stale` finding.
- **No template-payload change → no integrity/manifest shift.** This plan is framework-side only
  (a prompt, a registry entry, fixtures, a threshold row, an example decision). It ships the prompt
  in the wheel (like every `agents/*.md`); it does **not** touch `src/framework_cli/template/`, so
  there is no baseline manifest shift and no render/acceptance change. (Confirm in the gate.)

---

## 8. Separation of concerns (explicit)

| Agent | Owns | Does NOT |
|---|---|---|
| `review-env-parity` (new) | non-obs service & env-var presence/declaration parity across the env→overlay chain | obs surfaces; config *values*; PII/secret content |
| `review-observability-infra` | obs scrape/exporter/alert/dashboard parity & completeness | non-obs services; env-var declaration |
| `review-privacy` | PII handling/exposure in code & config | parity/presence |
| `review-security` | secret management, attack surface | parity/presence |

This mirrors the user's standing separation-of-concerns line (PII stays in `review-privacy`; obs
stays in `review-observability-*`).

---

## 9. Out of scope (YAGNI)

- Config *value* divergence across environments (§2.3).
- Modifying or re-tuning `review-observability-infra` (the obs parity clause stays where it is).
- Any template-payload change, new compose overlay, or new runtime surface.
- A paid real-key eval anchor for the new agent — that is Plan 18 (optional), which scores the
  *complete* roster including this agent.
- Frontend/build-tool parity beyond what the env→overlay model covers.

---

## 10. Implementation details deferred to the plan

- Exact agent-prompt wording (the §3 reasoning rule, the §2.1 greedy clause + the local-dev-tooling
  exception list, the JSON-only output contract matching the other agents).
- The precise seeded defects and `expect.json` cite-lines for each fixture.
- The calibrated `thresholds.yaml` numbers (set by `/reviewers:tune`).
- The example decision file's id/wording.
- Task breakdown (TDD): prompt + registration + fixtures (coverage gate) → tune/calibrate →
  decisions example/test → branch-end review.
