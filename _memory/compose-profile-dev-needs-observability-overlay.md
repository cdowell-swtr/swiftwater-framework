---
name: compose-profile-dev-needs-observability-overlay
description: "A docker acceptance test that brings up `--profile dev` MUST include `-f infra/compose/observability.yml` in the merge, or compose config-validation fails on the image-less grafana stanza."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 3248cc2a-470c-4aa5-9ff1-5d9cf4d914a4
---

When writing a framework acceptance test that runs the generated project's **`--profile dev`** stack, the compose file list must mirror `task dev`'s real merge: **`-f base.yml -f observability.yml -f dev.yml`** (in that order). 

**Why:** `dev.yml`'s `grafana` stanza is a deliberately **image-less override fragment** (it only adds anonymous-auth env: `GF_AUTH_ANONYMOUS_*`); the actual `grafana: image: grafana/grafana:...` lives in `observability.yml`. Under `--profile dev`, grafana is enabled and compose **config-validates the whole merged file** — so omitting `observability.yml` makes validation fail on the incomplete grafana service (no image). Note `dev:lite` does NOT hit this (grafana is `profiles: ["dev"]` only, so `--profile lite` never enables it — which is why the older dev:lite guard works with just `base+dev`).

**How to apply:** include `observability.yml` in the `-f` list. You can still `up` only the services you want (e.g. `up -d --build worker beat` or `... frontend`) — naming services starts just those + their `depends_on`, so the obs containers (grafana/prometheus/...) never actually start; observability.yml is only there to make config-validation pass. **Do NOT "fix" this by adding an `image:` to `dev.yml`'s grafana** — `task dev` merges dev.yml LAST, so a dev.yml grafana image would silently override observability.yml's version (a real bug rejected during Plan 12). Discovered Plan 12 (FF b24806f) writing the worker/beat + frontend live guards. Related: [[dind-e2e-harness-gotchas]], [[template-payload-tdd-loop]].
