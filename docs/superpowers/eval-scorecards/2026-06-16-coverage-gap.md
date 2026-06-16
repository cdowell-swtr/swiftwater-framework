# coverage-gap (FWK30) — calibration scorecard (2026-06-16)

**Verdict: PASS.** `review-coverage-gap   recall 1.00  fp 0.00`.

| metric | observed | floor/ceiling (thresholds.yaml) |
| --- | --- | --- |
| recall | 1.00 | recall_min 0.90 (= observed − 0.10) |
| fp | 0.00 | fp_max 0.10 (= observed + 0.10) |

## Run

`framework eval coverage-gap --backend api --repeat 3 --require-fixtures` (paid api backend,
Opus `claude-opus-4-8`, the agent's agentic runtime model). Fixtures are **framework-shaped**
(coverage-gap reviews the framework's own template source + the FWK29 registry, not a rendered
project — see `evals._FRAMEWORK_SHAPED_AGENTS`).

## What the run proves

- **Recall (bad/unexercised-k8s-manifest):** all 3 repeats flagged
  `src/framework_cli/template/infra/k8s/deployment.yaml.jinja` (severity medium) as a NEW-KIND
  surface, with accurate reasoning — the agent read `enumerate.py`, confirmed `infra/k8s/`
  matches none of the six enumeration rules, and that FWK29's completeness test therefore stays
  green while the manifest ships unexercised.
- **Precision (good/classified-cache-overlay):** all 3 repeats returned `[]`. The agent
  recognised the compose overlay as an ENUMERABLE kind (FWK29's territory) and that the same
  change classifies both derived keys — deferring rather than flagging.

## Calibration note — the fixture the agent corrected

The first paid run scored **fp 1.00**: the agent flagged the "good" fixture. Inspection showed
this was a *fixture* defect, not a prompt defect — and a demonstration of the agent's competence.
`enumerate.py` enumerates overlays/services from the **rendered** tree (`infra/compose/*.yml`),
so the keys are `overlay:cache.yml` and `service:cache.yml:cache` (rendered names). The fixture's
registry entry used `overlay:cache.yml.jinja` (template name) and omitted the service key
entirely — so the classification would *not* have satisfied FWK29, and the agent correctly said
so. The good fixture was regenerated with the correct rendered keys for **both** derived surfaces;
fp then went to 0.00. Lesson: a "defer" fixture for coverage-gap must classify the surface with
the exact rendered key(s) enumerate.py would emit.

## Engine bug surfaced (fixed on the same branch)

coverage-gap is the framework's first **always-multi-turn** agentic agent (it must read
`registry.py`/`enumerate.py`), and the first run via the **paid api backend**. That exercised a
latent bug: the agentic loop stored backend block dataclasses in `messages`, which litellm could
not JSON-serialize on the second request (`TextBlock is not JSON serializable`). Fixed by
wire-formatting the assistant turn (`agentic._assistant_turn`); also fixes the production review
runtime path. Regression test: `test_agentic_multi_turn_messages_are_json_serializable`.
