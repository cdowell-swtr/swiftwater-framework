# FWK136 — Async `resource_grant` resolver — Layer-2 adversarial security matrix

**Date:** 2026-06-30  
**Branch:** `fwk136-layer2-review`  
**Subject:** post-merge security review of FWK136 async `multitenantauth` `resource_grant` support.

**Method:** full stance x focus producer panel, followed by triage and default-to-refuted verification.
The producer panel was batched because of agent concurrency limits, but all 25 cells completed:
stances `break-in / harden / destroy / disrupt / leak` x focuses `F1 awaitability/coercion /
F2 tenant boundary / F3 fail-closed semantics / F4 direct API/backcompat / F5 availability/observability`.
Raw cell findings were deduplicated into promoted hypotheses P1-P6. Each promoted finding then received
an independent verifier verdict with `refuted` and `mechanism_verified`.

**Gate rule:** count CONFIRMED findings (`refuted=false` and `mechanism_verified=true`) at Critical/High;
PASS iff that count is 0.

**Process note:** an earlier controller-written draft of this scorecard was superseded. It did not represent
the completed Layer-2 protocol because it skipped the explicit verifier/refutation stage.

## Gate Verdict: GREEN after fixes

Producer cells raised 6 promoted hypotheses. Verification confirmed 5 and refuted 1. Two confirmed Highs
were fixed in this branch before the gate was closed:

| ID | Verified finding | Sev | Refuted | Mechanism | Disposition |
|---|---|---:|---|---|---|
| P1 | Nested awaitable returned by async resolver grants after one await | High | no | yes | **FIXED** |
| P2 | Malformed truthy non-bool / async-generator resolver result grants | Medium | no | yes | **FIXED** |
| P3 | Async guard ran framework-owned sync SQLAlchemy / resolver work on event loop | High | no | yes | **FIXED** |
| P4 | Unbounded async resolver can hang request and starve later `ANY` fallback | Medium | no | yes | **CARRY-OVER** |
| P5 | Resolver/factory exception detail leaked through `exc_info=True` logs | Medium | no | yes | **FIXED** |
| P6 | `asyncio.CancelledError` escapes the local deny path | N/A | **yes** | yes | NO-ACTION |

Confirmed Critical/High after fixes: **0**.

## Verifier Dispositions

### P1 — nested awaitable fail-open — FIXED

Verifier verdict: `refuted=false`, `mechanism_verified=true`, High.

Mechanism: `_adapt_resource_grant()` and `_await_bool()` awaited one layer, then called `bool(...)`.
A resolver shaped like `async def grant(...): return inner_false()` returned a truthy inner coroutine,
granting both route guard and direct async evaluator paths. Sync `evaluate()` was already fail-closed after
the local `_sync_bool()` draft.

Fix: async and sync result coercion now accepts only actual `bool`; a second-layer awaitable denies and is
closed when possible. Regression coverage: direct async evaluator nested-awaitable false and route-level
nested-awaitable false both deny.

### P2 — malformed truthy result fail-open — FIXED

Verifier verdict: `refuted=false`, `mechanism_verified=true`, Medium.

Mechanism: the documented resolver contract is `bool | Awaitable[bool]`, but previous code accepted arbitrary
truthy results (`object()`, non-empty string/list/dict, async-generator object). This was consumer-misuse-gated,
not request-input-only, but still a fail-open on protected resource leaves.

Fix: route adapter and direct evaluators now require `isinstance(result, bool)` after await handling; any other
shape denies. Regression coverage: truthy non-bool and async-generator returns deny in direct and route paths.

### P3 — sync work on event loop — FIXED

Verifier verdict: `refuted=false`, `mechanism_verified=true`, High.

Mechanism: FWK136 changed `guard()` to `async def`; FastAPI executes coroutine dependencies on the event loop.
The guard still did framework-owned sync SQLAlchemy/control-plane reads and invoked sync resolver/factory code
directly. Verifier confirmed prior sync dependencies ran in a worker thread while the new async guard ran on the
route/event-loop thread.

Fix: framework-owned sync control-plane reads, default resource-grant SQL, resolver factory construction, and
consumer resolver invocation are now executed via `run_in_threadpool(...)`. Regression coverage: a sync registered
resolver records a different thread than an async handler after the guard completes.

### P4 — unbounded async resolver / sequential fallback — CARRY-OVER

Verifier verdict: `refuted=false`, `mechanism_verified=true`, Medium availability.

Mechanism: supported async resolvers have no framework timeout/budget. A never-completing resource resolver can
hold a guarded request, prevent a later `ANY` fallback such as `tenant:manage-members` from being evaluated, and
avoid final authz decision metrics. This is not an auth bypass.

Disposition: recorded carry-over. A timeout policy is a behavior/design decision: fail closed immediately on
resolver timeout versus continue to later `ANY` fallbacks. This should be designed as a separate multitenantauth
availability hardening slice.

### P5 — exception detail in logs — FIXED

Verifier verdict: `refuted=false`, `mechanism_verified=true`, Medium.

Mechanism: resolver/factory failures denied HTTP access, but `logger.warning(..., exc_info=True)` copied consumer
exception text into shared logs. The framework did not inject tenant/resource/token values itself; the leak was
consumer-originated exception content.

Fix: resolver/factory failure logs are now generic and omit traceback/exception text. Regression coverage: a resolver
raising `tenant=acme resource=widget-1 token=secret123` still denies 403 and none of those strings, nor the exception
type, appears in captured logs.

### P6 — cancellation escaping deny path — REFUTED

Verifier verdict: `refuted=true`, `mechanism_verified=true`.

Mechanism observed: `asyncio.CancelledError` is a `BaseException`, so it is not caught by `except Exception`.
Refutation: this is correct cancellation propagation, not an ordinary resolver failure. Catching `BaseException`
would swallow request cancellation. It is not an auth allow or data leak. No code change.

## Fix Evidence

RED evidence:

- P1/P2/P5 focused rendered run: 13 expected failures over `test_expr_resource.py` and `test_auth_deps.py`
  (nested awaitables, truthy non-bools, async generator, custom close, and log redaction).
- P3 focused rendered run: `test_registered_sync_resolver_runs_off_event_loop_thread` failed with identical
  resolver and async-handler thread ids.

GREEN evidence:

- Rendered multitenantauth focused suite at `/tmp/fwk136-l2-green3`:
  `uv run pytest -q tests/unit/test_expr_resource.py tests/functional/test_auth_deps.py`
  -> **48 passed, 1 warning**.

## Net

Layer-2 gate is **GREEN after fixes**: confirmed High P1 and P3 are closed, confirmed Medium P2/P5 are closed,
confirmed Medium P4 remains documented as an availability carry-over, and P6 is refuted. The scorecard is based on
actual producer panel output plus verifier/refutation verdicts, not the superseded controller draft.
