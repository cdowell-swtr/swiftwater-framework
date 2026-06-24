"""Recursive resource-bound permission expressions — the authorization decision core.

`Perm`/`ALL`/`ANY` nest arbitrarily. A `Perm` leaf is satisfied iff the user holds the permission ON a
matching resource scope, and the scopes are NEVER crossed:

- ``on="platform"``             → checks the request's GLOBAL platform grants
- ``on="tenant:{tenant_id}"``   → checks the request's TENANT grants (for the URL-selected tenant)
- ``on=".../resource:*"``       → a wildcard subtree → an existence query (inert in Phase 1)

So a platform grant can never satisfy a tenant leaf and vice-versa (a name/scope mismatch simply
denies). The expression is a PURE boolean over precomputed grant sets — no DB access, cacheable per
request, and read by the T1–T4 fitness tests. It is NEVER serialized to a client (T3).

Two construction-time guards close known footguns:
- empty ``ALL()``/``ANY()`` raise (``all([])`` is True — a silent allow-all);
- a wildcard ``Perm`` as a direct child of ``ALL`` raises (it is inert → unconditional deny today, and
  would silently flip to a grant when the subtree resolver lights up).

There is intentionally NO ``require`` here — the FastAPI route-guard builder (``guard``) lives in
``multitenantauth/deps.py``; this module is pure and dependency-free.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_PARAM = re.compile(r"\{(\w+)\}")


def _is_wildcard(pattern: str) -> bool:
    return pattern.rstrip().endswith("*")


def _is_resource_scoped(pattern: str) -> bool:
    """A concrete resource-scoped pattern (authored, not bound) — routes through the
    resource-aware resource_grant resolver instead of the flat tenant_perms membership check."""
    return "/resource:" in pattern


@dataclass(frozen=True)
class Perm:
    """A permission required ON a resource. `on` is a resource pattern: ``platform``,
    ``tenant:{tenant_id}``, or ``tenant:{tenant_id}/resource:*``."""

    name: str
    on: str


def _has_wildcard_leaf(node: Any) -> bool:
    """True if a wildcard `Perm` leaf appears ANYWHERE in `node`'s subtree (not just as a direct
    child) — the ALL guard must be recursive, else `ALL(ANY(Perm(wild)))` slips a gating wildcard past
    it (inert deny today, silent grant later)."""
    if isinstance(node, Perm):
        return _is_wildcard(node.on)
    return any(_has_wildcard_leaf(c) for c in node.children)


@dataclass(frozen=True)
class ALL:
    """n-ary AND. Rejects empty children and a wildcard `Perm` leaf anywhere in the subtree."""

    children: tuple[Any, ...]

    def __init__(self, *children: Any) -> None:
        if not children:
            raise ValueError(
                "ALL() requires at least one child (all([]) is True — a silent allow-all)"
            )
        for c in children:
            if _has_wildcard_leaf(c):
                raise ValueError(
                    f"wildcard Perm leaf is not allowed anywhere under ALL: {c!r} "
                    "(inert → unconditional deny today; would silently become a grant later)"
                )
        object.__setattr__(self, "children", tuple(children))


@dataclass(frozen=True)
class ANY:
    """n-ary OR. Rejects empty children."""

    children: tuple[Any, ...]

    def __init__(self, *children: Any) -> None:
        if not children:
            raise ValueError("ANY() requires at least one child")
        object.__setattr__(self, "children", tuple(children))


Expr = Perm | ALL | ANY


def bind_resource(pattern: str, path: dict[str, Any]) -> str | None:
    """Substitute ``{param}`` from `path`. Returns None if any referenced param is absent — the
    caller treats that as DENY (a missing path param must never raise a 500)."""
    missing: list[str] = []

    def _sub(mo: re.Match[str]) -> str:
        key = mo.group(1)
        if key not in path:
            missing.append(key)
            return ""
        return str(path[key])

    result = _PARAM.sub(_sub, pattern)
    return None if missing else result


def perm_leaves(node: Expr) -> list[Perm]:
    """Every `Perm` leaf in the tree, in order (used by the T2 resource-binding fitness test)."""
    if isinstance(node, Perm):
        return [node]
    leaves: list[Perm] = []
    for c in node.children:
        leaves.extend(perm_leaves(c))
    return leaves


def resource_params(node: Expr) -> set[str]:
    """Every ``{param}`` referenced by any leaf's resource pattern."""
    return {p for leaf in perm_leaves(node) for p in _PARAM.findall(leaf.on)}


def evaluate(node: Expr, ctx: dict[str, Any]) -> bool:
    """Evaluate `node` against `ctx` = {tenant_perms, platform_perms, path, subtree_exists,
    resource_grant}.

    `tenant_perms`/`platform_perms` are precomputed sets (domain-split, from `multitenantauth.authz.resolution`);
    `path` is the request path params; `subtree_exists(name, resource)` resolves a wildcard subtree
    (inert/empty in Phase 1); `resource_grant(name, resource)` resolves a concrete resource-scoped
    grant. Short-circuits.
    """
    if isinstance(node, Perm):
        if node.on == "platform":
            return node.name in ctx["platform_perms"]
        # Wildcard-ness is a property of the authored PATTERN, never the bound value — otherwise an
        # attacker-controlled path segment of "*" would flip a concrete leaf into the subtree branch.
        is_wildcard = _is_wildcard(node.on)
        resource = bind_resource(node.on, ctx["path"])
        if resource is None:
            return False  # missing path param → deny (never a 500)
        if is_wildcard:
            subtree_exists: Callable[[str, str], bool] = ctx["subtree_exists"]
            return subtree_exists(node.name, resource)
        if _is_resource_scoped(node.on):
            resource_grant: Callable[[str, str], bool] = ctx["resource_grant"]
            return resource_grant(node.name, resource)
        return node.name in ctx["tenant_perms"]
    if isinstance(node, ALL):
        # `bool(node.children)` backstops an empty-children ALL (only constructable by bypassing
        # __init__) — all([]) is True, a silent allow-all; treat as deny.
        return bool(node.children) and all(evaluate(c, ctx) for c in node.children)
    if isinstance(node, ANY):
        return any(evaluate(c, ctx) for c in node.children)
    raise TypeError(f"not an Expr node: {node!r}")


class Authorized:
    """Wraps an expression for use as a route guard. Carries `expr` for the T1–T4 fitness tests; it is
    NEVER serialized to a client (enforced structurally by T3). `multitenantauth/deps.py:guard` builds
    these."""

    def __init__(self, expr: Expr) -> None:
        self.expr = expr

    def resource_params(self) -> set[str]:
        return resource_params(self.expr)

    def perm_leaves(self) -> list[Perm]:
        return perm_leaves(self.expr)

    def satisfied(self, ctx: dict[str, Any]) -> bool:
        return evaluate(self.expr, ctx)
