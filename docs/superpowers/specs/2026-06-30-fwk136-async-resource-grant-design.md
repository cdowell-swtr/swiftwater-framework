# FWK136 Async Resource Grant Design

## Context

`multitenantauth` exposes `register_authz_resolver_factory()` so consumers can replace the default flat `resource_grant` check with product-specific resource visibility logic. The shipped seam is documented as synchronous, but generated apps can include async surfaces such as workers, webhooks, and websockets, and a consumer can naturally write `async def resource_grant(...)`.

Today `_adapt_resource_grant()` calls the resolver and wraps the result in `bool(...)`. A coroutine object is truthy, so an async resolver fails open: every resource leaf it reaches is granted before the coroutine is awaited.

## Decision

FWK136 makes resource-grant resolution async-capable end to end while preserving the existing synchronous resolver contract.

The permission expression module keeps its current synchronous evaluator for existing direct unit tests and adds an async evaluator sibling. The async evaluator awaits awaitable results from `subtree_exists` or `resource_grant`, preserves short-circuit behavior, and otherwise mirrors the existing boolean semantics.

`Authorized` gains `satisfied_async(ctx)` while retaining `satisfied(ctx)`. `guard()` becomes an async FastAPI dependency and calls `await authorized.satisfied_async(ctx)`. Sync resolvers continue to work without consumer changes. Async resolvers are awaited before truth conversion. If a resolver or awaited result raises, `_adapt_resource_grant()` still fails closed and logs, matching the existing exception contract.

## Scope

In scope:

- `resource_grant` may be sync or async.
- The guard dependency may await the expression evaluator.
- Tests prove async grant, async deny, and async raise behavior through the real route guard.
- Existing sync resource-grant tests remain valid.

Out of scope:

- Making factories async. The factory runs during guard setup after membership resolution and remains synchronous for this patch.
- Enabling consumer override of `subtree_exists`.
- Changing route permission semantics, resource-id binding, or membership 404-before-403 behavior.

## Testing

The primary tests live in the generated multitenantauth `test_auth_deps.py` suite:

- async resolver returning `True` grants a resource leaf that the flat default denies
- async resolver returning `False` denies even when the flat default would grant
- async resolver raising fails closed with 403, not 500

Framework verification renders the multitenantauth project and runs the affected generated tests, then the framework fast tier.
