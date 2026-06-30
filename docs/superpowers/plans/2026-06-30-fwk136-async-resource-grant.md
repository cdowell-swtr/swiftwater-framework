# FWK136 Async Resource Grant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the multitenantauth `resource_grant` seam safely support async resolvers instead of failing open on coroutine objects.

**Architecture:** Keep the existing synchronous expression evaluator for direct sync callers, add an async evaluator sibling, and have FastAPI route guards call the async path. The adapter accepts sync or async per-call resource resolvers and converts raised exceptions into fail-closed denies.

**Tech Stack:** Python 3.12, FastAPI dependencies, inspect awaitable detection, pytest generated-template tests.

---

## File Structure

- Modify `src/framework_cli/template/src/{{package_name}}/{% if "multitenantauth" in batteries %}multitenantauth{% endif %}/authz/expr.py`: add async evaluator and `Authorized.satisfied_async()`.
- Modify `src/framework_cli/template/src/{{package_name}}/{% if "multitenantauth" in batteries %}multitenantauth{% endif %}/deps.py`: import awaitable detection, make adapted grants async-capable, and make `guard()` dependency async.
- Modify `src/framework_cli/template/tests/functional/{{ 'test_auth_deps.py' if 'multitenantauth' in batteries else '' }}.jinja`: add route-level async resolver tests.
- Update `PLAN.md` and `ACTION_LOG.md`: record completion and verification.

## Task 1: Async Resolver Tests

- [ ] **Step 1: Add failing tests**

Add three tests after `test_registered_factory_grants_a_resource_leaf_through_the_guard` in `test_auth_deps.py.jinja`:

```python
def test_async_registered_factory_grants_a_resource_leaf_through_the_guard(probe_app, control_engine):  # type: ignore[no-untyped-def]
    with Session(control_engine) as s:
        token = _seed_acme_member(s, "async-factory-grant@x.com")
    assert _status(probe_app, token, "/t/acme/resource/widget-1/view") == 403

    def factory(cs, user, active_tenant_id):  # type: ignore[no-untyped-def]
        async def grant(name, resource_id):  # type: ignore[no-untyped-def]
            return name == "resource:view" and resource_id == "widget-1"

        return {"resource_grant": grant}

    register_authz_resolver_factory(factory)
    assert _status(probe_app, token, "/t/acme/resource/widget-1/view") == 200
```

Also add an async deny test where the member has `resource_role=True` but the async resolver returns `False`, expecting 403, and an async raise test expecting 403.

- [ ] **Step 2: Verify RED**

Run the rendered multitenantauth test target and confirm the async grant test fails because the current sync guard returns a truthy coroutine without awaiting it:

```bash
uv run pytest tests/test_copier_runner.py::test_render_multitenantauth_test_file_is_created -q
```

Then render a temporary multitenantauth project and run:

```bash
uv run pytest tests/functional/test_auth_deps.py -q
```

Expected before implementation: the async deny/raise tests fail by granting or leaking coroutine behavior.

## Task 2: Async Evaluator

- [ ] **Step 1: Implement async expression evaluation**

In `authz/expr.py`, import `inspect`, add `_maybe_await_bool(value)`, add `async def evaluate_async(node, ctx) -> bool`, and add `Authorized.satisfied_async()`. Preserve sync `evaluate()` unchanged for existing unit tests.

- [ ] **Step 2: Run focused expression tests**

Run:

```bash
uv run pytest tests/test_copier_runner.py::test_render_multitenantauth_test_file_is_created -q
```

Expected: PASS; rendering still includes the auth test file.

## Task 3: Async Guard Path

- [ ] **Step 1: Implement async resource-grant adapter and guard dependency**

In `deps.py`, make `_adapt_resource_grant()` return an async callable that awaits awaitable resolver results before applying `bool(...)`. Keep exception logging and fail-closed return `False`. Change `guard()`'s `_dep` to `async def` and call `await authorized.satisfied_async(ctx)`.

- [ ] **Step 2: Verify GREEN on generated auth tests**

Render a multitenantauth project and run:

```bash
uv run pytest tests/functional/test_auth_deps.py -q
```

Expected: PASS.

## Task 4: Framework Verification and Bookkeeping

- [ ] **Step 1: Run framework-side render/integrity checks affected by the locked mechanism**

Run:

```bash
uv run pytest tests/test_copier_runner.py::test_render_with_multitenantauth_battery_creates_package tests/integrity/test_auth_mechanism_lock.py -q
```

Expected: PASS.

- [ ] **Step 2: Run quality checks**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
task test:fast
```

Expected: all pass.

- [ ] **Step 3: Update planning records and commit**

Tick FWK136 in `PLAN.md`, append an `ACTION_LOG.md` completion entry with test evidence, then commit:

```bash
git add PLAN.md ACTION_LOG.md src/framework_cli/template/src src/framework_cli/template/tests docs/superpowers/specs/2026-06-30-fwk136-async-resource-grant-design.md docs/superpowers/plans/2026-06-30-fwk136-async-resource-grant.md
git commit -m "fix(FWK136): await async resource grant resolvers"
```
