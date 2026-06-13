# PLAN — swiftwater-framework

> Current state only (Next + recent Done). Full history: git + the frozen
> meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) + `_archive/`.
> Maintained per `pi-convention.md` (PI-convention: v2).

## Next
- [ ] FWK10 — PI v2 migration + gh-only convention re-pointing (FWK prefix; vendor pi/memory conventions; AGENTS.md pointer + @import; register by PR)  → docs/superpowers/plans/2026-06-13-pi-v2-migration.md
- [ ] FWK3 — Plan 22c: per-agent reviewer reference docs (the 19 reviewers; retire the two promissory notes in working/review-system.md)
- [ ] FWK4 — Plan 23: agent self-improvement tooling (capture the Plan 21 audit→synthesis→adversarial method as repeatable tooling)
- [ ] FWK5 — Plan 27: refactor the review/eval engine onto LiteLLM (re-target SubagentBackend as an in-process claude -p CustomLLM provider)
- [ ] FWK6 — Plan 29: data-store runtime parity (services.yml/dev.yml; unblock the hardcoded co-located-container assumption)
- [ ] FWK7 — Plan 30: full reverse integrity-coverage check + 23-file battery-infra classification  deps: consumes INTENTIONALLY_UNLOCKED (shipped v0.2.4)
- [ ] FWK8 — Traefik docker-provider acceptance coverage (the gap that hid the v3.1 → Docker 27 `task dev` break)
- [ ] FWK9 — Propagate the PI + MEMORY conventions into generated projects (template payload)  deps: FWK1, FWK2

## Done
- [x] FWK2 — Plan 26: adopt the Committed Memory convention  → log:#0013
- [x] FWK1 — Plan 25: adopt the PI convention  → log:#0005
- (recent pre-adoption milestones — no PI task IDs; full record in the frozen meta-plan)
  Plan 28: lock-taxonomy + task doctor + Traefik fix (v0.2.4, `3f166dc`/`da7ea65`); Plan 24: framework upgrade (v0.2.3, `bb31bac`).
