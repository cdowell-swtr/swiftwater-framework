<!-- PI-convention: v3 -->
## Planning Instrument
Read `PLAN.md` first. Maintain `PLAN.md` + `ACTION_LOG.md` at task grain as you
work (tick tasks; append a log entry on every completion and every deviation),
per `pi-convention.md`. Task IDs use this repo's prefix **`FWK`** (`FWK1, FWK2, …`).

<!-- CROSS-REPO-convention: v4 -->
## Cross-repo communication
Promoting a capability from a downstream reference impl up into a framework: keep a **Promote-Up Record**
in the absorbing repo (source, what was specialized, generalization decisions, sequence, status); migrate
**upstream-first** — generalize in the absorber, then the generator adopts and **deletes its copy**, gated
by a conformance suite seeded from the generator. Never leave both copies standing (permanent fork).
When a promote-up needs **iterative rounds**, escalate to a **Negotiation Thread** — semi-live, generator-initiated rounds in a GitHub issue (side-labeled `[role/repo]`; `RESOLVED`/`CONCUR`/`DISSENT`; one operator gate) that crystallize into the PUR.
**Companion repos** (two halves of one product): keep a root `COMPANION.md` naming your counterpart + the **seam** (what must stay in sync vs. may diverge); a seam change updates both halves + both manifests; symmetric (neither drives). If a repo has `COMPANION.md`, read it.
Sync the absorption field before each session and rebase the adopt-PR immediately before merging (per Git convention) — clean auto-merges, conflict resolves.
Full rule: `cross-repo-convention.md`.

Full working agreement & conventions: see `CLAUDE.md`.
