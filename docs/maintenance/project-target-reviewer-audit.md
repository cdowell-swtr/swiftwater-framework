# Auditing the review agents as applied to generated projects

> Closes FWK48. Companion code: `src/framework_cli/review/audit/` (the pipeline),
> `src/framework_cli/review/project_reviewers.py` (consumer reviewers). Design:
> `docs/superpowers/specs/2026-06-29-fwk48-project-target-reviewer-audit-design.md`.

`reviewer-audit` calibrates review-agent prompts (audit → reconcile → refute → preview
changelist; nothing is auto-applied, per FWK4). Historically it only ran against the
framework's own roster (`agent_names()`) and fixtures. The same agents also review
*generated projects* via `framework audit --target project` (the `active_agents()` set),
so they need a calibration path **as applied to a project**. There are two halves; both
reuse one target-aware pipeline.

## Half 1 — the framework-repo oracle (maintainer-run)

The committed fixtures under `tests/eval/fixtures/<agent>/` are already diffs against a
**rendered demo project** (`src/demo/...`) — they realize against a real render
(`test_evals.py::test_every_fixture_realizes`). So auditing the project roster against them
*is* the render-then-audit oracle:

```bash
# (optional) materialize the audit subject the fixtures are authored against:
uv run framework template-render --out /var/tmp/demo-audit

# audit the agents a generated project actually runs, against the render-based fixtures:
uv run framework reviewer-audit --target project
#   --target project  → the active_agents() roster (excludes framework_only agents)
#   fixtures default  → tests/eval/fixtures (the render-based set) in the framework repo
```

The emitted `changelist.json` / `apply-preview.*` are the maintainer's reconciliation
input. **Applying** stays a deliberate, eval-gated hand-edit
(`[[reviewer-tuning-is-prompts-not-thresholds]]`) — `reviewer-audit` never writes prompts.
A full recalibration **sweep** (every agent, live backend, eval-gated) is an operator op the
tooling enables, not an automated step.

## Half 2 — consumer BYO reviewers (opt-in, rookie-free)

A generated project can add its own reviewer with **no framework changes**, under
`.framework/reviewers/`:

```
.framework/reviewers/<name>.md      # domain prompt (same shape as agents/<name>.md)
.framework/reviewers/<name>.toml    # block_threshold / active_when / model / trigger_globs / [context]
.framework/reviewers/fixtures/<name>/{good,bad}/<case>/change.patch [+ expect.json]
```

`framework audit --target project` and `reviewer-audit --target project` discover these
(`register_project_reviewers`) and merge them into the project roster. To tune one:

```bash
uv run framework reviewer-audit --target project   # in the generated project
#   fixtures default → .framework/reviewers/fixtures when that dir exists (no flag needed)
```

Guarantees:

- **Rookie-free:** no `.framework/reviewers/` directory → identical behavior to today.
- **No silent shadowing:** a custom reviewer that reuses a built-in agent name is a loud
  error (exit 2), not an override.
- **Projects don't tune the built-ins:** a generated project ships no built-in fixtures, so
  `--target project` there meaningfully audits only the project's own reviewers. Built-in
  agents are calibrated upstream (Half 1); a project that finds a built-in agent mis-flagging
  its code files that upstream rather than forking the prompt locally
  (`2026-05-29-local-reviewers-design.md`: "projects don't own fixtures").

## The one pipeline both halves share

`run_audit(..., fixtures_root=…)` threads a chosen fixtures dir into `build_audit_brief`
(FWK118), and `reviewer-audit` selects the roster by `--target` and the fixtures by
`--fixtures-root` (defaulting to the project's BYO dir on `--target project`). `fixtures_root`
is part of the `--resume` provenance fingerprint (FWK47/118), so re-pointing the fixtures
invalidates a stale checkpoint rather than silently reusing it.
