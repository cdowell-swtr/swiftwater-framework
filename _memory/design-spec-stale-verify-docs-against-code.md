---
name: design-spec-stale-verify-docs-against-code
description: "The framework design spec (docs/superpowers/specs/2026-05-20-framework-design.md) is the ORIGINAL plan and is STALE on specifics (battery list, CLI flags, pre-commit tools, compose profiles) — the code/template evolved past it. Use it for concepts/intent only; verify every concrete claim against the actual code/template. Doc-authoring subagents fabricate plausible-but-wrong specifics — use a capable model + a controller fact-check."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: e7e23a67-9817-4ea6-8b0e-fbf0bba32de0
---

`docs/superpowers/specs/2026-05-20-framework-design.md` (21 sections) is the framework's
original design plan. After Plans 1–17 it is **stale on specifics**: e.g. its battery list
(`rest`, a `database` paradigm-wizard) does NOT match the implemented `batteries.py`
(`webhooks, websockets, workers, graphql, pgvector, mongodb, timescaledb, age, redis, react,
consumers`); some CLI flags and the "observability battery" framing also drifted. **Use the
spec for concepts/why/intent only; the authoritative source for any concrete claim is the
code/template** — `batteries.py`, `cli.py`, and `src/framework_cli/template/` (Taskfile,
`.pre-commit-config.yaml`, compose overlays, routes, `settings.py.jinja`).

**Doc-authoring lesson (Plan 22a):** a Sonnet doc-implementer fabricated plausible-but-wrong
specifics — invented pre-commit hooks (taplo/yamllint/hadolint/prettier), a non-existent
`task ci` AI-review step, overstated compose profiles, a stale 15-agent table — all of which
*read* correct. The Opus doc-quality review caught them with code citations. **How to apply:**
for docs/feature work, author with a capable model under an explicit "verify every claim
against the real file, do not infer/fabricate" instruction, then controller-fact-check the
concrete claims (commands, flags, tokens, thresholds, env vars) against the cited sources
before committing. This same drift produced a real template bug the docs review surfaced
(GraphQL introspection on in prod — `settings.py.jinja` `!= "production"` vs env `prod`).
