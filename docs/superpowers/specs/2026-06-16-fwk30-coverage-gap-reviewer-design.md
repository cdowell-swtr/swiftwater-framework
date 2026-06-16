# FWK30 — Agentic coverage-gap reviewer (design)

> Status: approved design (2026-06-16). Next: writing-plans → implementation plan.
> Open-world half of the durable runtime-coverage mechanism; closed-world half is
> FWK29 (`tests/runtime_coverage/`, shipped). Source assessment:
> `docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md`.

## Problem

FWK29 shipped the **closed-world ratchet**: `tests/runtime_coverage/enumerate.py` has 6
rules that scrape an all-batteries render for surface *instances* (compose overlays,
services, Dockerfile stages, scripts, workflow jobs, hooks → 91 surfaces), and a
`gate`-tier set-equality test forces every instance into `registry.py` as
EXERCISED / EXEMPT / KNOWN_GAP. For those 6 kinds, every new instance is already
mechanically forced into a human classification.

Two classes of coverage gap are structurally invisible to that mechanism:

1. **New *kinds* of operational surface** — a PR adds provisioned surface that matches
   *no* enumeration rule (e.g. a systemd unit, a k8s manifest, a Makefile target, a new
   `infra/` shape). `enumerate.py` never sees it, the completeness test stays green, and
   it ships unexercised.
2. **In-app code-path surfaces** — `create_app`/lifespan bootstrap, DB engine/pool
   lifecycle, per-battery live routes, worker tracing. These are not mechanically
   enumerable; `registry.py`'s docstring explicitly hands them to "the FWK30 open-world
   reviewer."

FWK30 is the **open-world** complement: a judgment-based, framework-native review agent
that watches the broad operational surface, defers to FWK29's registry for everything
enumerable, and flags only what the closed-world ratchet cannot see.

## Mandate (scope: both halves)

The agent covers **both** classes above:

- **(A) New-kind / unclassified surface.** Reads `enumerate.py` to learn the 6 known
  kinds; flags provisioned operational surface in the template that falls outside all of
  them and is therefore never forced into a classification.
- **(B) In-app code-path surfaces.** Reasons about whether bootstrap / DB-lifecycle /
  live-route / worker-tracing paths introduced by the change are exercised on their real
  runtime path. **Diff-anchored (B-i):** the agent assesses the in-app surface *this PR
  touches or introduces*, not a whole-tree audit of the pre-existing app. A whole-tree
  sweep is the FWK18-style periodic assessment, not a per-PR reviewer — as a per-PR agent
  it would re-flag the same standing gaps every run and bury the signal. The agent may
  read surrounding files via tools for context, but findings anchor to the diff.

## The coverage lens (boundary against neighboring agents)

The prompt holds a hard line so FWK30 does not become a second `architecture` or
`observability` agent:

| Agent | Question it answers |
|-------|---------------------|
| `architecture` | Is the design sound? (coupling, boundaries, layering) |
| `observability*` | Is it instrumented? (spans / metrics / logs / dashboards / alerts) |
| **`coverage-gap` (FWK30)** | **Is this provisioned surface exercised by a test on its real runtime path?** |

"Exercised" is defined narrowly. A test must **drive** the surface on its real path.
The following do **not** count when the surface's value is the live path (these are the
recurring shapes 2–4 from the assessment):

- render-text-checked only (asserted to *render*, never *run*);
- `docker build` succeeds with `returncode==0` but the artifact is never *run*;
- unit coverage via `TestClient` / eager-Celery / mocked beacon when the point of the
  surface is the *live* ASGI / Traefik / broker / worker path.

## Defer-to-registry rule

Before flagging any **enumerable-kind** surface, the agent checks `registry.py`. Any
status there — EXERCISED, EXEMPT, **or** KNOWN_GAP (with its `FWK<N>` id) — means
"handled, stay silent." Only a **new kind** (no enumeration rule) or an **unclassified
in-app path** (which the registry excludes by design) is flaggable.

The defer is asymmetric:
- For the 6 enumerable kinds, the registry is authoritative — never re-flag a classified
  instance.
- For in-app paths, the registry says nothing by design, so the agent reasons from
  scratch (bounded by B-i).

The agent learns "what's already classified" by **reading the source directly**
(`registry.py` is ~28 KB, under the 50 KB `read_file` cap; `enumerate.py` is tiny). No
generated manifest — the registry is the single source of truth, and reading it straight
avoids a sync-drift bug class. If eval shows turn-burn or misparsing, a generated
manifest becomes a cheap later optimization.

## Inputs & wiring

### Diff seed — the target-scope wrinkle resolution

Today every framework agent shares `framework_diff()` (`review/diff.py`), which **excludes**
`src/framework_cli/template` because template-payload *quality* is deliberately out of the
framework's self-review. FWK30 is the principled exception: it reviews the template
payload, but only through the **coverage** lens, never for general quality.

FWK30's seed is the **full repo diff** (no template exclusion) for the review range —
reusing the non-excluding diff path. Rationale: the agent sees the template surface *and*
any same-PR `registry.py` / `enumerate.py` classification side-by-side, so its
defer-to-registry judgment is based on the PR's actual end state, not a half-view. The
framework's own CLI source in the diff is ignored noise the prompt scopes away.

Mechanism: a **per-agent diff scope**. The audit path already computes a per-agent diff
(`delta_diff(base_sha)` in `_build_audit_items`); only the live single-shot path
(`cli.py:1803`, which hands one shared `framework_diff()` to all framework agents) needs
to honor a per-agent override. The other five framework agents keep `framework_diff()`
unchanged.

### Tools

The existing agentic tools (`read_file` / `grep` / `glob`, confined to repo root) are
sufficient. The agent reads `registry.py`, `enumerate.py`, the template tree, and
`tests/` to determine whether a surface is driven.

### Activation — gate by globs

`active_when="file-trigger"`, `trigger_globs=("src/framework_cli/template/**",
"tests/runtime_coverage/**")`. FWK30 spends Opus tokens only when the PR touches the
shipped surface or the registry — a large share of framework PRs touch only CLI/review
code and give the agent nothing to assess.

This requires teaching the **framework-target dispatch** to honor `active_when` /
`trigger_globs`. Today `cli.py:489` runs all of `FRAMEWORK_AGENTS` unconditionally (the
file-trigger filtering in `active_agents()` is only used for the generated-project
target). The change: on the framework target, filter file-trigger agents by their globs
against the changed set, while the five `always` agents stay unconditional. Contained and
back-compatible for the existing agents.

## Output

JSON findings (existing `Finding` schema). Each finding carries:

- the surface (path / name);
- **which** open-world gap it is — new-kind (enumerable but ruleless) vs unclassified
  in-app path;
- severity;
- a concrete suggestion — either a test that would exercise the surface on its real path,
  or, for an enumerable new-kind, the `registry.py` / `enumerate.py` classification it
  needs.

Advisory (`block_threshold=None`): findings surface in the report, never block the gate
(consistent with `documentation` / `dependency` and `_finalize_gate` skipping
advisory agents).

## Graduation loop (process, not code)

When FWK30 repeatedly flags the same *new kind* of surface, a human promotes it into a
7th `enumerate.py` rule plus the corresponding `registry.py` entries — moving it from
open-world judgment to closed-world determinism. Documented as a process note in the
agent prompt / this spec; no tooling in the first cut.

## Testing & registration

Per the registration-completeness rule (a new review agent must pass **all** of
`tests/review/`, not just the registry tests):

- `test_context_policy` — FWK30 in the correct tier / strategy sets (agentic, advisory,
  file-trigger).
- `_EXPECTED_PR` — the expected agent set updated.
- `test_registry` — the new `AgentSpec` resolves, prompt loads.
- `test_evals` — scoring wiring.
- `FRAMEWORK_AGENTS` membership test in `tests/` updated, and the `context.py` comment
  block (which currently explains why the *app-domain* agents are excluded) extended to
  note FWK30 as the deliberate template-payload exception.

Plus an **eval fixture pair** calibrating the defer-to-registry behavior:

- **positive** — a template change that adds an unexercised operational surface → FWK30
  must flag it;
- **negative** — a template change that adds a surface *and* classifies/tests it in the
  same change → FWK30 must stay silent (defer to the same-PR registry entry).

(Watch the eval-fixture coupling gotchas: new-file fixtures realize to an empty diff and
only agentic agents detect them; fixtures anchored on template files break when the
template moves. See the project memories on eval-fixture coupling.)

## Out of scope (first cut)

- A generated classification manifest (optimization; revisit only if eval shows
  turn-burn).
- Whole-tree in-app audit (B-ii) — that remains the periodic FWK18-style assessment.
- Tooling for the graduation loop — manual promotion for now.
- Making FWK30 blocking — advisory until calibration data justifies a threshold.

## Approach alternatives considered

- **Narrow scope (A only) vs both halves.** Chose both — the `architecture` agent has a
  genuinely different job (design soundness, not coverage), and the prompt boundary makes
  the two coexist. Rejected narrowing to new-kind detection only.
- **Generated manifest vs read-the-source.** Chose read-the-source — single source of
  truth, no sync-drift bug class.
- **Template-only vs full-diff seed.** Chose full diff — the agent must see the
  classification side-by-side with the surface.
- **Always-on vs glob-gated.** Chose glob-gated — nothing to assess when neither template
  nor registry changed.
- **Diff-anchored (B-i) vs whole-tree audit (B-ii) for the in-app half.** Chose B-i — a
  per-PR reviewer assesses the change, not the whole app.
