# FWK158 Reserved Tenant Slugs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable reserved tenant-slug seam to the `multitenantauth` battery without changing default slug claimability.

**Architecture:** Keep slug policy centralized in `multitenantauth.tenancy.registry`. Add a module-level registration API whose configured slug set is checked by `_assert_slug_claimable()` before the existing live-slug and cooling-history checks; all routes and provisioning helpers inherit the behavior because they already call `register_tenant()` or `rename_slug()`.

**Tech Stack:** Python, FastAPI generated template, SQLAlchemy, pytest generated-project tests.

---

### Task 1: Registry Seam And Tests

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/{% if "multitenantauth" in batteries %}multitenantauth{% endif %}/tenancy/registry.py`
- Test: `src/framework_cli/template/tests/unit/{{ 'test_tenancy_registry.py' if 'multitenantauth' in batteries else '' }}.jinja`
- Test: `src/framework_cli/template/tests/functional/{{ 'test_tenant_role_routes.py' if 'multitenantauth' in batteries else '' }}.jinja`

- [ ] **Step 1: Write failing registry tests**

Add tests that import `register_reserved_tenant_slugs`, reset it in the autouse fixture, then prove `register_tenant()` and `rename_slug()` reject configured reserved slugs while ordinary slugs still pass.

- [ ] **Step 2: Verify registry tests fail**

Render a `multitenantauth` project and run:

```bash
uv run pytest -q tests/unit/test_tenancy_registry.py -k reserved
```

Expected: fail because `register_reserved_tenant_slugs` does not exist.

- [ ] **Step 3: Implement the seam**

Add `register_reserved_tenant_slugs(slugs: Iterable[str] | None) -> None`, normalize configured values to lowercase strings, reset to empty on `None`, and make `_assert_slug_claimable()` raise `ValueError` when `slug` is configured as reserved. Do not change `_validate_slug()`, live slug checks, cooling-history checks, or default behavior.

- [ ] **Step 4: Verify registry tests pass**

Run:

```bash
uv run pytest -q tests/unit/test_tenancy_registry.py -k reserved
```

Expected: pass.

- [ ] **Step 5: Add route inheritance test**

Add a tenant provisioning route test that registers a reserved slug and proves `POST /tenants` returns the existing generic slug-unavailable response without writing a tenant row.

- [ ] **Step 6: Verify focused route test passes**

Run:

```bash
uv run pytest -q tests/functional/test_tenant_role_routes.py -k reserved
```

Expected: pass.

- [ ] **Step 7: Run focused and framework verification**

Run the generated focused suites plus framework render checks, formatting, linting, typing, and affected tests:

```bash
uv run pytest -q tests/unit/test_tenancy_registry.py tests/functional/test_tenant_role_routes.py
uv run ruff check .
uv run ruff format --check .
uv run mypy src
task test:affected
```

Expected: all pass.
