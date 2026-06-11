# Shared reviewer rubric (draft — Plan 21)

Every `review-*` agent prompt inherits these rules.

## Severity (consistent across all agents)
- **high** — blocks a builder: a concrete, demonstrable defect that will cause incorrect
  behavior, data loss, a security/privacy breach, or a broken contract in the changed code.
- **medium** — should fix before merge but does not block: a real issue with a plausible
  path to harm, or a clear violation of an established project convention.
- **low** — advisory: style, minor clarity, or a non-urgent improvement.
- **info** — observation only; never implies an action is required.

## Codebase-bar principle
Do not hold new code to a stricter standard than the surrounding codebase already meets.
Before flagging a pattern, check whether the template/baseline already does the same thing
unflagged; if it does, do not flag the new instance.

## Internal consistency within one review
Apply one standard to every instance of a pattern you see in the same diff. If you do not
flag instance A, do not flag an identical instance B (the `create_item`/bulk-insert lesson).

## Scope discipline
Stay within this agent's domain (stated per-agent). Do not flag issues another agent owns.

## Output
Return JSON ONLY — an array of {"path","line","severity","message","suggestion"}; [] if none.
