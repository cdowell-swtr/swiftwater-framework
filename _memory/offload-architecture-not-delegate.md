---
name: offload-architecture-not-delegate
description: Framework philosophy — scaffold/offload strategic & architectural decisions FROM the builder; never punt them; pre-empt antipatterns and null patterns.
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e0527716-ed95-4c2c-8aef-4738edf745af
---

The swiftwater-framework's purpose is to **offload** strategic and architectural decisions away from the builder — not to delegate them back. We do **not** trust the builder to make good architectural choices, and we do **not** trust them to avoid antipatterns/null patterns on their own. So scaffold as much as can be prefigured, using whichever vehicle fits (working code, opinionated skeletons, or prescriptive docs like DEPLOY.md).

Distinguish a genuine builder *choice* from work we're avoiding: e.g. the deploy **target** (compose-over-SSH / Fly / Render / k8s) is the builder's choice and the strategy can't be *fully* written without it — but the deploy **strategy's** patterns (release versioning, rollback semantics, no-downtime cutover, expand/contract migration timing, runtime-secrets discipline, health-gating) are target-independent and MUST be prescribed. Reduce the builder's remaining job to *configuration*, not *architecture*. A loud "not configured / implement these 7 functions" stub is itself the null pattern to avoid.

**Why:** the framework exists to take quality/observability/testing/deployment concerns off the builder (spec §1 antipatterns) — handing back an empty contract contradicts that mission. A subtly-broken "complete" scaffold is also an antipattern, so where full correctness needs the target, ship the correct *pattern* + opinionated guidance rather than wrong code.

**How to apply:** when a plan reaches an extension point, default to maximal scaffolding — pre-write the correct sequence/pattern with inline antipattern guards and call out the spec's antipatterns explicitly; mark only the genuinely target-specific commands as gaps; provide a worked default. If a fully-correct concrete implementation is a real subproject, prefer an opinionated skeleton now + a dedicated follow-up plan over shipping something half-correct. See [[plan-5b-deploy-seam]].
