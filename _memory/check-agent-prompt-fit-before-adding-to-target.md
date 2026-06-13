---
name: check-agent-prompt-fit-before-adding-to-target
description: "Read an agent's prompt file before adding it to a target's active-agents set (e.g. FRAMEWORK_AGENTS); agent names mislead — domain scoping lives in the prompt, not the name."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0576f127-c936-4be4-8ea0-a38356f39443
---

Before adding any review agent to a target's active set (e.g. `FRAMEWORK_AGENTS` in `src/framework_cli/review/context.py`), read its prompt at `src/framework_cli/review/agents/<name>.md`. Names are short and abstract; prompts are scoped to specific domains.

**Why:** On 2026-05-31 I tried to add `api-design`, `contracts`, `performance` to `FRAMEWORK_AGENTS` based on names (sounded CLI-applicable). The gate's architecture reviewer caught (2× HIGH + 1× MEDIUM) that the prompts are scoped to generated-project app domains:

- `api-design` reviews GraphQL/Strawberry schemas.
- `contracts` reviews Pact consumer contracts.
- `performance` targets web-app SLOs with `src/*/routes/*.py` + `src/*/db/*.py` context globs that don't exist in `framework_cli`.

Adding them produces false negatives (intended CLI-surface coverage doesn't actually happen) and wastes subagent quota. The original 6-agent FRAMEWORK_AGENTS was correct *for prompt-alignment reasons*, not just naming. Reverted on the `framework-agents-expand` branch; the comment in `context.py` now records the finding so future readers don't re-attempt.

**How to apply:** When proposing a new agent for `FRAMEWORK_AGENTS` (or any target's active set in [[offload-architecture-not-delegate]]-style scaffolding), read `src/framework_cli/review/agents/<name>.md` and confirm the prompt's domain matches the target's surface. If it doesn't, the right move is a new CLI-scoped agent prompt (e.g. `cli-api-design`), not membership change.
