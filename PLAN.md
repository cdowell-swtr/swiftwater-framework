# PLAN — swiftwater-framework

> Current state only (Next + recent Done). Full history: git + the frozen
> meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) + `_archive/`.
> Maintained per `pi-convention.md` (PI-convention: v2).

## Next
- [ ] FWK3 — Plan 22c: per-agent reviewer reference docs (the 19 reviewers; retire the two promissory notes in working/review-system.md)
- [ ] FWK4 — Plan 23: agent self-improvement tooling (capture the Plan 21 audit→synthesis→adversarial method as repeatable tooling)
- [ ] FWK15 — **Rename the shipped `agents`-core battery → `--with llm`** (token, `llm/` module, `LLMService`/`LLM*` identifiers, `/llm/complete` route, `app_llm_*` metrics + alert/dashboard, `APP_LLM_*` settings, tests). What shipped in v0.2.5 is an LLM runtime, not an agent; the agent loop is FWK14. Re-release as v0.2.6 so Meridian upgrades onto the honest name.  deps: FWK12
- [ ] FWK13 — `--with hotswapllm` battery: subscription↔API hot-swap — a **transport extension of `--with llm`** (`requires=("llm",)`) via the externalized claude-cli plugin dependency. **Precedes FWK14** (finish the LLM capability before layering the agent loop on it).  deps: FWK11, FWK15  ⚠ write the generated-project dep as a PEP 508 direct reference (`litellm-claude-cli @ git+…@vX.Y.Z`), NOT `[tool.uv.sources]` (FWK11 review I2)  ◦ fold in the deferred llm nit: fail-fast `LLMError` when `llm_api_key` is empty (unset key → a confusing 502 on first call)
- [ ] FWK14 — `--with agents` battery (**the real agent**): tool registry + bounded run loop + read-only Item DB tool + agentic route + loop/tool obs. `requires=("llm",)` — builds the tool loop on the FWK15 `llm` runtime.  deps: FWK15  plan: `docs/superpowers/plans/2026-06-14-agents-battery-loop.md` (re-anchor to `llm`/`agents` names)
- [ ] FWK6 — Plan 29: data-store runtime parity (services.yml/dev.yml; unblock the hardcoded co-located-container assumption)
- [ ] FWK7 — Plan 30: full reverse integrity-coverage check + 23-file battery-infra classification  deps: consumes INTENTIONALLY_UNLOCKED (shipped v0.2.4)
- [ ] FWK8 — Traefik docker-provider acceptance coverage (the gap that hid the v3.1 → Docker 27 `task dev` break)
- [ ] FWK9 — Propagate the PI + MEMORY conventions into generated projects (template payload)  deps: FWK1, FWK2

## Done
- [x] FWK12 — Plan: agents battery slice 1 (runtime core), shipped in **v0.2.5** as `--with agents` (LiteLLM-backed `AgentService` completion + structured output, SecretStr key, usage→metrics, demo route, in-process obs, litellm dep + mypy override, tests; branch-end Opus = APPROVE). **Superseded by FWK15** — renamed to `--with llm` (the honest name) in v0.2.6.  → log:#0039–#0045
- [x] FWK11 — Externalized the claude-cli CustomLLM plugin to its own public package (`cdowell-swtr/litellm-claude-cli` @ v0.1.1, git-tag dep); framework deleted its in-tree copy and depends on it; entry-point auto-reg NO-GO in litellm 1.88.1 → explicit `register()`. Unblocks FWK13  → log:#0033
- [x] FWK5 — Plan 27: review/eval engine onto LiteLLM (claude -p re-homed as an in-process CustomLLM provider; near-zero adapter, so the adapter-removal step was dropped). Spike-gated on `anthropic_messages`; parity + live smoke + caching all green  → log:#0027
- [x] FWK10 — PI v2 migration + gh-only convention re-pointing  → log:#0017
- [x] FWK2 — Plan 26: adopt the Committed Memory convention  → log:#0013
- [x] FWK1 — Plan 25: adopt the PI convention  → log:#0005
- (recent pre-adoption milestones — no PI task IDs; full record in the frozen meta-plan)
  Plan 28: lock-taxonomy + task doctor + Traefik fix (v0.2.4, `3f166dc`/`da7ea65`); Plan 24: framework upgrade (v0.2.3, `bb31bac`).
