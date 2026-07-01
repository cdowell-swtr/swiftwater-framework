# FWK152 AuthZ Resource Resolver Timeout Design

## Goal

Bound supported async `resource_grant` resolvers so a hung consumer resolver cannot hold a guarded
request indefinitely or starve later `ANY` leaves.

## Decisions

- Timeout policy is fail-closed for the resource leaf. A timed-out resolver returns `False`; it does
  not grant and does not receive special fallback behavior that would rescue the request through a
  later `ANY` branch.
- Timeout applies to awaitable resolver results. Sync resolvers continue to run in the threadpool path
  established by FWK136; this slice does not try to cancel blocking sync code.
- Timeout is configurable through `APP_AUTHZ_RESOURCE_GRANT_TIMEOUT_MS`, default `250`, with a positive
  integer settings floor.
- Timeout logs include a static developer-authored `resource_type` and timeout value, but not tenant id,
  resource id, exception text, or traceback. `guard(expr, resource_type="product")` is the route-level
  opt-in; default is `"resource"`.
- Metrics reuse the existing bounded auth metrics surface. Any expression containing a resource-scoped
  leaf records final decisions under `domain="resource"` in `app_authz_decisions_total`; no new metric
  label is introduced for `resource_type`.

## Test Shape

- A rendered `multitenantauth` functional test sets a tiny timeout, registers a sleeping async resolver,
  and asserts the request returns `403` quickly.
- The timeout log contains the configured resource type and timeout value, and omits the resource id.
- The existing authz decision counter records the timeout denial as `decision="deny",domain="resource"`.
- Existing async-grant, async-deny, malformed-result, and sync-thread tests continue to pass.
