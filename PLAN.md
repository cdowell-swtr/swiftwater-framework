# PLAN — swiftwater-framework

> Current state only (Next + recent Done). Full history: git + the frozen
> meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) + `_archive/`.
> Maintained per `pi-convention.md` (PI-convention: v2).

## Next
- [ ] FWK3 — Plan 22c: per-agent reviewer reference docs (the 19 reviewers; retire the two promissory notes in working/review-system.md)
- [ ] FWK4 — Plan 23: agent self-improvement tooling (capture the Plan 21 audit→synthesis→adversarial method as repeatable tooling)
- [ ] FWK6 — Plan 29: data-store runtime parity (services.yml/dev.yml; unblock the hardcoded co-located-container assumption)
- [ ] FWK7 — Plan 30: full reverse integrity-coverage check + 23-file battery-infra classification  deps: consumes INTENTIONALLY_UNLOCKED (shipped v0.2.4)
- [ ] FWK8 — Traefik docker-provider acceptance coverage (the gap that hid the v3.1 → Docker 27 `task dev` break)
- [ ] FWK9 — Propagate the PI + MEMORY conventions into generated projects (template payload)  deps: FWK1, FWK2

## Done
- [x] FWK17 — **Dockerfile builder needs `git`** for the `claudesubscriptioncli` git dep (Meridian consumer brief, 2026-06-15). Battery-gated `apt-get install git` in `infra/docker/Dockerfile`'s builder stage (the uv image has none → `docker build`'s `uv sync` couldn't clone `litellm-claude-cli @ git+…` → `"Git executable not found"`). + a docker-build regression test (`--target builder`) — the host-uv-sync acceptance tier missed it. Shipped **v0.2.10**. (Deferred: PyPI-publish the lib (durable Option 2); private-dep BuildKit secret.)  → log:#0073
- [x] FWK14 — **`--with agents`** battery (slice: the real agent). Bounded tool-calling loop (`AgentRunner` over `LLMService.respond()`, the one llm-battery change), read-only `Item` tools, `POST /agents/run`, tool/run obs (`app_agent_*`), `agent_max_iterations`. `requires=("llm",)`; inherits profiles + the subscription backend (`run(profile="sub")`). Per-task + branch-end Opus reviews = APPROVE. Shipped **v0.2.9**.  → log:#0063–#0071
- [x] FWK16 — **`--with claudesubscriptioncli`** battery (slice 2): `requires=("llm",)`, `obs="rides-existing"`. Adds the `litellm-claude-cli` PEP 508 git dep (+ `[tool.hatch.metadata] allow-direct-references`) + a `create_app` startup call to the package's idempotent `register()`, so a `provider:"claude-cli"` profile routes through the Claude subscription (keyless; needs an authenticated `claude` on PATH). **Zero base-llm change** (FWK13's keyless + duck-typed-exhaustion seam handles it). Per-task + branch-end review = APPROVE. Shipped **v0.2.8**.  → log:#0057–#0061
- [x] FWK13 — **LLM profiles in `--with llm`** (slice 1). Named profiles (`APP_LLM_PROFILES` JSON; `default`=back-compat single config) + per-call `provider`/`model` override + per-profile cost/usage metrics + key fail-fast + duck-typed (`reset_hint`) exhaustion (subscription-ready, no plugin import). Per-task + branch-end Opus reviews = APPROVE (fixed a plaintext-key repr leak, dashboard kind breakdown). Shipped **v0.2.7**.  → log:#0051–#0055
- [x] FWK15 — Renamed the shipped `agents`-core battery → **`--with llm`** (token/module/`LLMService`/`app_llm_*`/`/llm/complete`/`APP_LLM_*`/obs), honest taxonomy: it's an LLM runtime, not an agent. Caught a pathlib-join straggler the rename script missed via rendered-project grep. Shipped **v0.2.6** (PR #34); roadmap re-ordered llm → claudesubscriptioncli → agents.  → log:#0047–#0048
- [x] FWK12 — Plan: agents battery slice 1 (runtime core), shipped in **v0.2.5** as `--with agents` (LiteLLM-backed `AgentService` completion + structured output, SecretStr key, usage→metrics, demo route, in-process obs, litellm dep + mypy override, tests; branch-end Opus = APPROVE). **Superseded by FWK15** — renamed to `--with llm` (the honest name) in v0.2.6.  → log:#0039–#0045
- [x] FWK11 — Externalized the claude-cli CustomLLM plugin to its own public package (`cdowell-swtr/litellm-claude-cli` @ v0.1.1, git-tag dep); framework deleted its in-tree copy and depends on it; entry-point auto-reg NO-GO in litellm 1.88.1 → explicit `register()`. Unblocks FWK13  → log:#0033
- [x] FWK5 — Plan 27: review/eval engine onto LiteLLM (claude -p re-homed as an in-process CustomLLM provider; near-zero adapter, so the adapter-removal step was dropped). Spike-gated on `anthropic_messages`; parity + live smoke + caching all green  → log:#0027
- [x] FWK10 — PI v2 migration + gh-only convention re-pointing  → log:#0017
- [x] FWK2 — Plan 26: adopt the Committed Memory convention  → log:#0013
- [x] FWK1 — Plan 25: adopt the PI convention  → log:#0005
- (recent pre-adoption milestones — no PI task IDs; full record in the frozen meta-plan)
  Plan 28: lock-taxonomy + task doctor + Traefik fix (v0.2.4, `3f166dc`/`da7ea65`); Plan 24: framework upgrade (v0.2.3, `bb31bac`).
