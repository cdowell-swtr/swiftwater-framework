<!-- vendored from cdowell-swtr/patterns cross-repo-convention.md @ 8db2c286894db3dd58d8414b84e90cf5e84a8066 (tag cross-repo/v4) on 2026-06-25; re-vendor when a later cross-repo/v tag supersedes it -->

<!-- CROSS-REPO-convention: v4 -->
# Cross-Repo Convention

*Authoritative definition. Version: `CROSS-REPO-convention: v4`. How agents coordinate work across separate repos that form one whole — without the repos drifting. Two relationship patterns: **promote-up** (a capability moves from a downstream reference impl up into a framework) and **companion** (two halves of one product evolve together). Consumer-adoptable. Enforcement: agent-upheld (no validator). Multi-product **federation** is planned for a later version.*

## The patterns
Cross-repo communication has a shared substrate — the conventions/memory layer both repos adopt — and **relationship patterns** that differ by how much negotiation a change needs and how many repos stand together. The convention ships two; pick the one matching your repos' relationship:
- **Promote-up** — *directional, a high-negotiation event*: a capability moves downstream→upstream and is generalized; one **absorber drives**; it ends.
- **Companion** — *symmetric, a low-coordination standing relationship*: two halves of one product evolve together; **neither drives**; it never ends.

(Multi-product **federation** — maximizing autonomy across many sub-products — is planned for a later version.)

## Promote-up — directional
When a sub-product (the *reference implementation*) proves out a capability that belongs in the framework, the capability must move **up** and be **generalized** — once, cleanly, with the downstream copy retired. This convention makes that promote-up a repeatable, low-friction discipline carried between two repos by durable artifacts, not live coordination.

## The communication model
You (the operator) run agents in each repo; they coordinate through **durable artifacts** — the Promote-Up Record and a conformance suite — plus a fixed **sequence**. How the *negotiation itself* is carried escalates along a **latency spectrum**:
- **Operator-relay (batch)** — the baseline. The agents run at different times and never talk live; you carry context between the two sessions, and the one-shot PUR holds the settled negotiation. Right when the generalization is clear-cut.
- **Negotiation Thread (semi-live)** — when a promote-up needs *iterative rounds*: the two sides negotiate in an append-only GitHub-issue thread at comment latency (no PR/CI per round), crystallizing into the PUR. See *Negotiation Thread — semi-live promote-up*.
- **Live bridge** — an MCP bridge, reserved for the can't-relay case. See *Escalation levers*.

## The three pieces

**1. Promote-Up Record (PUR).** A decision doc that lives in the **absorbing repo** (the framework) — the post-migration source of truth. Place it per your docs layout (e.g. `_docs/<capability>/promote-up.md`). It records:
- **Source / generator** — the downstream repo + the specialized capability.
- **What was specialized** — the reference-impl assumptions baked in.
- **Generalization decisions** — what becomes configurable/injected, what is dropped, what stays.
- **Migration sequence** — the upstream-first steps below.
- **Status** — `proposed → in-migration → adopted → downstream-copy-deleted`. When a Negotiation Thread is used the lifecycle opens at **`negotiating`** (set by the generator when it seeds the PUR) and may terminate at **`withdrawn`** if the negotiation is abandoned (`negotiating → proposed → …`, or `negotiating → withdrawn`).

The PUR *is* the negotiation, made durable. The generator's session reads it during its adopt phase (paste it in, or fetch the single file via `gh`).

**2. Upstream-first sequence.** The order is the rule:
1. **Generalize in the absorber first** — build the capability product-agnostic.
2. **Seed a conformance suite from the generator's *current* behavior** (piece 3).
3. **Ship** the generalized capability in the absorber (tagged).
4. **The generator adopts it and *deletes its local copy*** — gated on the conformance suite passing.
5. **Mark the PUR `adopted`.**

Never the reverse — never lift the generator's copy into the absorber and leave both standing.

**3. Conformance contract.** An acceptance/behavior suite **seeded from the generator's current behavior** (the things the reference impl relies on), captured *before* migration and run against the generalized capability *after* the generator wires it in. Green = the generalization preserved what mattered. Match it to the boundary: a code/library capability gets a conformance test suite that travels with it in the absorber; only a genuine deployed service-to-service boundary warrants contract-broker tooling (e.g. Pact).

## Anti-pattern — the permanent fork
Both repos keep a copy of the capability and drift apart: a distributed-monolith-in-miniature. Step 4 — the generator **deletes** its copy, contract-gated — exists to prevent exactly this. Upstream-first is what makes the deletion safe. **If both copies still exist when the PUR says `adopted`, the promote-up failed.**

## Roles & registry
Adopting this convention means a repo follows its relevant cross-repo pattern. For **promote-up**: **both** participants adopt and the **absorber drives** — *drives* meaning it owns the generalization decisions, the migration sequence, and the crystallization, **not** that it speaks first (a Negotiation Thread is **generator-initiated**: the generator proposes, the absorber disposes). A repo's role is per-promote-up (recorded in each PUR), not a fixed property — it can be generator in one and absorber in another. For **companion**: both halves adopt **as a pair** and **neither drives**. Either way role is never a registry column — the implementer registry stays role-free (`Repo | Local path | Synced version | Adopted`); companion adopters simply register in pairs.

## Composition (reuse, don't restate)
- **Git convention** owns the cross-repo *write* (the generator's adopt PR and any registration go via a clone or `gh`, never the live working copy; single-writer holds) **and the remote-sync discipline** — sync the **absorption field** before each session, and rebase the adopt-PR immediately before merging: **clean → auto-merge, conflict → resolve** (per Git convention's "Sync with the remote"). The absorption field is where a generator's landing is most likely to actually conflict.
- **Docs-layout convention** owns where the PUR lives.
- **Planning Instrument** owns logging the promote-up (`PLAN.md` / `ACTION_LOG.md`, task grain).
- **The shared conventions/memory layer** is the substrate both patterns sit on (both repos adopt the same conventions). For companion, the pairing manifest lives at repo root (`COMPANION.md`, beside `AGENTS.md` / `PLAN.md`) — outside the `_docs/` tree, so no docs-layout conflict.

## You must uphold — promote-up
No validator — this is agent-upheld. On any promote-up:
- [ ] A PUR exists in the absorbing repo and names source, what-was-specialized, generalization decisions, sequence, and status.
- [ ] Migration runs **upstream-first** (generalize in the absorber before the generator adopts).
- [ ] A conformance suite seeded from the generator's current behavior gates the generator's copy-deletion.
- [ ] The generator's local copy is **deleted** before the PUR is marked `adopted` (no permanent fork).
- [ ] The promote-up is logged under PI; cross-repo writes follow the Git convention.

## Negotiation Thread — semi-live promote-up
The one-shot PUR is a *monologue* — the absorber records the settled decision and the generator reads it. When a promote-up's **generalization decisions need iterative rounds** (too much to settle up front; too costly to iterate by amending the PUR through a PR + CI each round), escalate to a **Negotiation Thread**: a semi-live channel that runs the rounds at comment latency and crystallizes back into the PUR. This is the **negotiation-intensity** escalation — it applies even solo. The one-shot PUR stays the default for clear-cut promote-ups.

**The surface.** A **GitHub issue in the absorbing repo** (co-located with the PUR). Each round is a comment — **no PR, no GHA per round**. The thread is append-only and atomic, so both sides can attend it concurrently without corrupting it.

**The loop.**
1. **Generator initiates.** The generator writes the PUR skeleton (source, what-was-specialized, its *proposed* generalization decisions), opens the issue, writes the issue reference into the PUR, and lands the PUR in the absorber at the docs-layout location — status `negotiating`. That seed is the generator's one cross-repo *file* write (via clone/PR, per the Git convention); every round after it is a comment.
2. **Absorber responds.** You point the absorber session at the committed PUR; it answers in the thread. Both sides then attend the thread.
3. **Rounds.** Proposal → counter → resolution. **Every comment is side-labeled `[role/repo]`** — e.g. `[absorber/swiftwater-framework]`, `[generator/meridian]`. A small **round cap** (operator-set) bounds the exchange; no convergence within it escalates to you rather than looping.
4. **Resolution.** The absorber posts **`RESOLVED`** — a *proposal*, not a unilateral close. The generator replies **`CONCUR`** or **`DISSENT: <unmet need>`**.
5. **The one gate.** You sign off, acting as **arbiter**: `CONCUR` → a light confirm; a standing `DISSENT` → you decide (sign off over it, or send it back for more rounds). **Crystallization may not proceed while a `DISSENT` stands unless you explicitly override it.** This is the only mandatory human gate, and it sits *before* the irreversible step (the PUR commit and the generator's copy-deletion).
6. **Crystallize.** The absorber writes the settled decisions + a short rationale digest into the PUR (one commit), links and closes the issue, and moves the status to `proposed`/`in-migration`. Migration then proceeds upstream-first, unchanged.

**The `[role/repo]` label is load-bearing.** Both sessions post under one `gh` identity, so a side decides *"is this the counterpart, is it my turn?"* from the **label, not the comment author**. A missing label — or an unlabeled human comment — can make a side answer itself; the label is mandatory on every round.

**Hands-off is a harness concern, not a rule.** This convention specifies the **protocol** (the labels, `RESOLVED`/`CONCUR`/`DISSENT`, the round cap, the gate) and the **discipline** (*each side attends the thread and posts its next round once the counterpart has responded*). *How* a session attends — polling cadence, mechanism — is your harness's job, not the convention's.

**Abandon path.** If the round cap escalates and you end the negotiation, give the `negotiating` PUR a terminal state — **`withdrawn`** (issue closed unresolved) — never leave it orphaned against a stale issue.

**Backstops.** The generator can't be steamrolled (a standing `DISSENT` blocks auto-proceed and forces your call) and can't deadlock either (you arbitrate; it holds no unilateral veto). And "needs met" is ultimately *tested*, not just asserted — the **conformance suite** still gates the generator's copy-deletion downstream.

### You must uphold — Negotiation Thread (when used)
- [ ] The generator seeds the PUR (status `negotiating`) with the issue reference before rounds begin.
- [ ] Every round is side-labeled `[role/repo]`.
- [ ] Resolution runs `RESOLVED` → `CONCUR`/`DISSENT`; a standing `DISSENT` blocks crystallization unless the operator overrides.
- [ ] The operator signs off before crystallization (the one gate, before the irreversible step).
- [ ] An abandoned negotiation is marked `withdrawn`, never left orphaned.

## Companion repos — symmetric
Two halves of one product that evolve together but are different *kinds* of repo — e.g. a prose **book** repo and the **tooling** repo that supports its writing/editing/research. Neither absorbs the other; they must simply stay **coherent** at the boundary between them. Lowest-coordination pattern: a shared conventions layer + one small standing artifact per repo.

**The pairing manifest — a root `COMPANION.md`, one per repo (symmetric).** Each half keeps its own, naming the other. Fields:
- **Counterpart** — the companion repo + how to reach it (clone URL / `gh` path / local path).
- **Seam** — the explicit boundary between the halves: **must-stay-in-sync** (the interface neither half changes unilaterally) vs. **may-diverge** (what each half owns freely — prose content; tool internals).
- **Seam-check** — changing the seam in one half **updates the counterpart and both `COMPANION.md` manifests in one change-set** (a cross-repo write, per the Git convention). Everything outside the seam, each half changes alone.

Surface it: root files aren't agent-autoloaded, so add a one-line `AGENTS.md` pointer ("this repo has a companion — see `COMPANION.md`") so a session in either half discovers it. **Symmetric** — neither half drives; both maintain their manifest. **No conformance suite** (companion is lower-stakes than promote-up): the test is simply *does the other half still work with this seam change?*

### Anti-pattern — incoherent drift
The two halves silently diverge at the seam — the tooling changes break the book's workflow, or the book restructures past what the tooling supports. The manifest + seam-check exist to prevent exactly this. **If a seam change lands in one half without the other, the pairing broke.**

### Worked example (illustrative)
A prose **book** repo ↔ its **tooling** repo (writing/editing/research support). Seam = the capabilities the tooling provides that the book's production depends on, plus the content structure the tooling targets; prose and tool internals diverge freely. *(The motivating case the pattern is designed for — not a registered pair.)*

### You must uphold — companion
- [ ] Each repo has a root `COMPANION.md` naming its counterpart + reach-path, surfaced via `AGENTS.md`.
- [ ] The seam is explicit (must-stay-in-sync vs. may-diverge).
- [ ] A seam change updates **both** halves + **both** manifests in one change-set (per the Git convention).
- [ ] The change is logged under PI.

## Escalation levers
- **A promote-up needs iterative rounds** (the negotiation-intensity axis) → the **Negotiation Thread** above (semi-live GitHub-issue rounds). The common escalation — it applies even solo. A **second person owning the downstream repo** routes to the same thread, which doubles as durable multi-party async.
- **~A dozen+ repos coordinating** (the standing-scale axis) → a **per-event ledger** (a role-bearing coordination registry). This is the planned **federation** pattern (a later version). The threshold is a heuristic.
- **An agent that genuinely cannot check out a repo** → an **MCP bridge** exposing it. Reserve for the can't-relay case (fully live, above the thread).

## When to adopt (applicability)
Adopt when repos form one whole: a framework + sub-products that promote capabilities upstream (**promote-up**), or two halves of one product that must stay coherent (**companion**). A flat single-repo project runs neither. Adoption is cheap (a pointer + the discipline) and has no whole-repo gate, so nothing to grandfather.

## Adopt in a repo
1. Pull this convention from the latest `cross-repo/v*` tag (see `_docs/cross-repo/adoption-runbook.md`).
2. Add the AGENTS.md rule block (below); for Claude Code, ensure `@AGENTS.md` in `CLAUDE.md`.
3. Follow the discipline on your next promote-up; log it under PI.
4. Register by PR to `cdowell-swtr/patterns` (`_docs/cross-repo/implementers.md`).

Find adopters / versions: `grep -rIn "CROSS-REPO-convention:" <your projects root>`.

### AGENTS.md rule (copy this block)
```
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
```
