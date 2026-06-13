---
name: obs-completeness-guard-already-exists
description: "A per-battery obs-completeness guard test already exists; extend it (don't reinvent). Also — explore for existing tests before planning a \"new\" file."
scope: project
metadata: 
  node_type: memory
  type: reference
  originSessionId: 49f13a1d-7e1e-4c24-8e52-b50a128128c4
---

`tests/test_obs_completeness.py::test_battery_obs_matches_declared_surface` is a pre-existing, comprehensive **per-battery obs-completeness guard** (commit `46906df`): it renders each battery vs a no-battery baseline and asserts the obs delta matches the battery's declared `get_battery(name).obs` classification — `"service"` ⇒ must add scrape job + alert + dashboard + prod service + prod exporter; `"in-process"` ⇒ alert + dashboard, no scrape; `"rides-existing"` ⇒ no new obs artifacts. So batteries already have a "scrape+alert+dashboard" invariant.

It does NOT cover **base obs infra** (otel-collector, prometheus) — those aren't batteries, so they're invisible to the per-battery delta check. The 2026-06-01 obs-infra slice added `test_base_obs_components_are_self_monitored` **alongside** it for base components.

**Why this matters / how to apply:** when doing more obs-completeness work, EXTEND `test_obs_completeness.py` (and the `battery.obs` classification in `framework_cli/batteries`), don't write a parallel/duplicate guard. **Process lesson:** during brainstorm exploration, grep for an existing test before a plan says "Create `tests/test_X.py`" — I planned to *create* this file, an implementer subagent then *overwrote* the existing one, and it had to be restored (`git restore`) + the new coverage appended. Cross-ref [[subagent-implementers-stop-before-commit]].
