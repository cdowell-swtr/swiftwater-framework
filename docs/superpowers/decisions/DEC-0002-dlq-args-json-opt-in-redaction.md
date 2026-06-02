---
id: DEC-0002
status: deferred
agents: [compliance]
concern: "DLQ args_json default stores task args unredacted (opt-in redaction seam)"
premise: >
  The BaseTask.dlq_args_json override seam exists and is documented. This is tracked
  debt pending the DLQ-PII compliance-posture follow-up; the default-redact question is
  decided there, not here.
date: 2026-06-01
---

Deferred (NOT accepted-forever): the redaction default is intentionally opt-in for now.
Tracked by the DLQ-PII compliance-posture slice (see the memory note / meta-plan
"DLQ-PII compliance posture"). Re-raise if that slice closes without a decision, or if
the `BaseTask.dlq_args_json` seam is removed.
