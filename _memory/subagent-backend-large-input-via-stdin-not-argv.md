---
name: subagent-backend-large-input-via-stdin-not-argv
description: "SubagentBackend (claude -p) must pass large content (system prompt, diff) via stdin / --system-prompt-file, NOT argv — Linux per-arg MAX_ARG_STRLEN (~128KB) fails on a real audit even when every small-fixture test passes. The Phase-6 live smoke is the ONLY thing that catches this class."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 2d69c8e8-89d9-4fb3-b97e-d82adf436f70
---

**Hard-won in Plan 20b Phase 6 (2026-06-10).** `framework audit --target framework --backend
subagent` failed with `OSError: [Errno 7] Argument list too long: 'claude'`. Cause:
`SubagentBackend._SubagentMessages.create` passed `_join_system(system)` (the diff + context
bundle) as a `--system-prompt <value>` **argv element**. A bundle-agent's system content on a
real target exceeds Linux's **per-argument** limit `MAX_ARG_STRLEN` (~128 KB / 32 pages) — which
is NOT the total `ARG_MAX` (3.2 MB on this box; a single big arg fails long before the total does).

**Fix (now in `backend.py`):** write the system content to a temp file (mkstemp, 0o600,
finally-cleanup) → `--system-prompt-file <path>`; pass the user prompt via **stdin**
(`input_text=prompt`), not the argv positional. Both keep large strings out of argv.
`--system-prompt-file` replaces the system prompt identically to `--system-prompt`, so
single-turn / `--exclude-dynamic-system-prompt-sections` / JSON-output semantics are preserved.

**Why it hid for an entire build:** every hermetic test uses tiny prompts, and the 20a eval uses
tiny *fixture* diffs — both stay under 128 KB. ONLY a real audit (whole-framework bundle) crosses
it. **Lesson:** (1) any subprocess-shaped review backend must pass large content via stdin/file,
never argv; (2) the **Phase-6 live smoke — one real agent on a real target, BOTH backends — is
load-bearing**, not ceremony; it's the only validation that exercises large real inputs. Don't
skip it for "the hermetic tests pass."

**Adjacent content-size gotcha (same session):** a delta diff > ~200 K tokens (e.g. the 2.35 MB /
44 k-line diff produced by an *ancient* auto-discovered audit baseline `audit-2026-05-30-2446de8`)
trips `claude`'s **1M-context mode, which requires PAID usage credits** → fails on the subscription
on BOTH backends (`"API Error: Usage credits required for 1M context"`). That's a content-size
limit, NOT a path/parity bug — both api and subagent fail on a 2.35 MB diff. Re-derive stale audit
baselines (Plan 21) so audit deltas stay reasonable; or audit `--snapshot` / a recent `--since`.
Also: `_finalize_audit` used to DROP a failed agent's `error` field (silent `_(no findings)_`) —
now fixed to render `_(agent errored: …)_`, which is what made this diagnosable. See
[[reviewer-dev-prod-parity-gap]] (now resolved — one path, swappable backend).
