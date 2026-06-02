---
id: DEC-0001
status: accepted
agents: [data-integrity]
concern: "prune_expired commits its own DB session internally"
premise: >
  The only caller is the prune_expired_records beat task, which scopes a dedicated
  session for the prune. If prune_expired is ever called inside a caller's outer
  transaction (a shared session), this decision is STALE.
date: 2026-06-01
---

A standalone maintenance prune is intentionally self-committing — see the template's
`tasks/dead_letter.py` / `webhooks/inbox.py` `prune_expired`, and the v0.1.0 release-fix
(commit `935588f`), where this was reviewed and documented by-design. Re-raise if the
caller set changes (i.e. if `prune_expired` is invoked from within another unit-of-work).
