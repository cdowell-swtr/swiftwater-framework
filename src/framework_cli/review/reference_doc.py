"""Generates documentation/reference/review-agents.md — mechanical facts live from the
registry, prose from _BLURBS. Regenerate via scripts/gen_reviewer_reference.py; a test guards it."""

from __future__ import annotations

from framework_cli.review.registry import agent_names, get_agent

# 2-3 sentence operator-facing blurb per agent: the lens, what it flags, and what it deliberately
# will NOT flag (its scope boundary / codebase-bar). Keyed by agent_names() (short keys). The
# mechanical facts (scope/threshold/tier) are read live from the registry — do NOT repeat them here.
_BLURBS: dict[str, str] = {
    "accessibility": (
        "React/TSX accessibility (WCAG-class) review: non-semantic interactive elements (a div "
        "acting as a button with no role), missing accessible names (img without alt, icon-only "
        "buttons without aria-label), keyboard traps, and ARIA/contrast smells on changed lines. "
        "Does not flag backend/Python changes or stylistic CSS with no a11y impact."
    ),
    "api-design": (
        "GraphQL schema and resolver design (Strawberry, code-first) — exclusively: N+1 "
        "resolvers, uncompensated breaking schema changes, unbounded list fields without "
        "pagination, nullability mistakes, and mutation error design. REST/OpenAPI is out of "
        "scope (defers to contracts); raw query cost defers to performance."
    ),
    "application-logic": (
        "Correctness review of changed lines only: unhandled edge cases "
        "(empty/null/boundary/concurrent), wrong conditionals, missing or swallowed error "
        "handling, and recovery paths that don't actually recover. Not style; structural concerns "
        "defer to architecture, query cost to performance."
    ),
    "architecture": (
        "Module boundaries and the handler/worker seam: layering violations (a route bypassing "
        "the repository layer, duplicate data-access modules), circular dependencies, and heavy "
        "synchronous work (external HTTP, large DB writes, loops over remote I/O) run inline in a "
        "request handler. Defers edge-case correctness to application-logic, query cost to "
        "performance."
    ),
    "compliance": (
        "Audit / retention / right-to-erasure obligations: privileged or destructive record "
        "operations (delete, purge, export, bulk-modify) that emit no structured audit entry, "
        "personal data persisted with no retention or deletion path, and uncovered erasure "
        "obligations. Does not flag PII logging or over-collection (privacy) or write atomicity "
        "(data-integrity)."
    ),
    "contracts": (
        "Consumer-driven contract testing via Pact: a provider change that breaks a committed "
        "consumer pact, incompatible response changes, weakened consumer assertions, and hard "
        "reads of undeclared fields (KeyError risk). Additive backward-compatible changes and "
        "optional `.get()` reads are not flagged; GraphQL design defers to api-design."
    ),
    "coverage-gap": (
        "Framework-native, agentic: whether a newly provisioned operational surface in the "
        "template is exercised by a test that drives it on its real runtime path (not just "
        "render-checked or mock-patched). Flags surfaces of a kind `enumerate.py` doesn't "
        "recognize, and in-app lifecycle/route/worker paths the change adds but no test drives "
        "live. Diff-anchored; "
        "defers to anything already classified in the FWK29 `registry.py` "
        "(EXERCISED/EXEMPT/KNOWN_GAP)."
    ),
    "data-integrity": (
        "Atomicity and store-invariant review: non-atomic writes (e.g. per-row commits that break "
        "batch atomicity), nullability/constraint mistakes that corrupt the model, and "
        "data-losing or backward-incompatible migrations. Doesn't flag optional safeguards the "
        "codebase already omits; PII → privacy, audit/retention → compliance, unbounded scans → "
        "performance."
    ),
    "data-lineage": (
        "Data-flow tracing: PII reaching an undocumented sink, an erasure path that clears one "
        "store but misses another (index, cache, second table), stale derived/denormalized fields "
        "whose write path updates only one side, and cross-store writes with no consistency "
        "strategy. Atomicity defers to data-integrity; PII-logging severity to privacy."
    ),
    "dependency": (
        "Manifest-only review (pyproject / uv.lock / package*.json): unjustified or redundant "
        "dependencies, maintenance/supply-chain health, pin floors below the project's `>=` "
        "convention, and concrete supply-chain compromise (malicious/typosquatted/yanked — not "
        "speculative). Does not reason about runtime behavior or call sites."
    ),
    "documentation": (
        "Docs accuracy: missing docstrings only where sibling public interfaces in the same diff "
        "are documented, new config vars absent from `.env.example`, READMEs/specs that now "
        "contradict the change, and genuinely uncommented complex logic. Not correctness, "
        "typing/schema shape, or performance."
    ),
    "env-parity": (
        "Dev→CI→staging→prod parity: tracing how each environment composes its overlays, it flags "
        "services added only to dev-scoped overlays that won't reach staging/prod, env vars "
        "consumed in `settings.py` but absent from `.env.example`, and compose interpolations with "
        "no `.env.example` declaration. Biased to over-flag service parity; excludes observability "
        "wiring, secret/PII content, and per-env value divergence (expected)."
    ),
    "observability": (
        "App-layer instrumentation on changed business logic and routes: state-changing "
        "operations that emit no structured log, paths that bypass the FastAPI auto-instrumented "
        "seam (raw ASGI, background tasks outside the request lifecycle), and active signal "
        "suppression. Auto-instrumented routes are the clean baseline; the data-access seam is "
        "observability-db."
    ),
    "observability-db": (
        "Datastore-seam instrumentation in db/, cache/, vectors/, mongo/, timeseries/, graph/, "
        "migrations/: queries through a second engine or raw DBAPI connection that bypass "
        "SQLAlchemyInstrumentor, new datastore clients with no `/health` signal, and data-layer "
        "errors swallowed off the structlog path. Ordinary queries through the app's instrumented "
        "engine are auto-observed and not flagged."
    ),
    "observability-fe": (
        "Frontend observability in the React/TS SPA against the RUM beacon (`POST "
        "/internal/rum`): local handlers that swallow exceptions before the global "
        "window error/unhandledrejection handler, and unbounded/high-cardinality labels on "
        "promoted beacon fields. New components aren't flagged merely for lacking their own RUM; "
        "beacon PII defers to privacy."
    ),
    "observability-infra": (
        "Monitoring wiring in Compose overlays, Prometheus, Grafana, and Alertmanager: scrape "
        "jobs with no backing exporter (and exporters never scraped), prod-reaching services with "
        "no alert rule or dashboard, and obs wiring confined to dev.yml that never reaches prod. "
        "App-level auto-instrumentation belongs to observability."
    ),
    "performance": (
        "Query efficiency and algorithmic cost on changed lines: unbounded scans, N+1 queries, "
        "connection-pool exhaustion, hot-path allocation, and accidentally super-linear work. "
        "Bounded reads capped by `MAX_PAGE_SIZE` and full ORM-row hydration matching the repo "
        "idiom are not flagged; correctness defers to application-logic."
    ),
    "privacy": (
        "PII exposure: personal data logged or echoed back in a response, collection of PII not "
        "needed for the stated purpose, and retention beyond purpose — on changed lines. Security "
        "defects defer to security; audit/retention obligations to compliance."
    ),
    "security": (
        "Application-security review: injection, broken authn/z, hardcoded secret values, verified "
        "CVEs, and OWASP-Top-10 failures on changed lines. Flags concrete, demonstrable defects — "
        "not absent hardening the template baseline itself omits. PII handling defers to privacy; "
        "audit/retention to compliance."
    ),
    "test-quality": (
        "Tests that cannot fail regardless of behavior: assertions only against mocks, "
        "tautologies, missing assertions, mocks that don't match the real interface, and unhappy "
        "paths that don't assert the failure behavior. Scoped to the test diff."
    ),
    "usability": (
        "React/TSX UX review: unhandled async states (no loading/error/empty handling), mutations "
        "with no user feedback, and destructive actions without a confirmation step. Wiring "
        "completeness (unimported components) and accessibility defer to their own agents."
    ),
}

_HEADER = """# Review agents — reference

> Generated from `src/framework_cli/review/registry.py` by
> `scripts/gen_reviewer_reference.py`. Do not edit by hand — change the registry (mechanical
> facts) or `reference_doc._BLURBS` (prose) and regenerate
> (`uv run python scripts/gen_reviewer_reference.py`); a test keeps this page in sync.

The review system runs a panel of single-concern AI agents over a change — see
[The review system](../working/review-system.md) for the architecture and why. Each agent below
owns one lens. **Blocks** is the severity at/above which a finding fails the gate (*advisory*
agents surface findings but never block). **Context** is how the agent sees the change (`diff` /
`bundle` / `agentic` tool-loop) and its model tier."""


def _tier(model: str) -> str:
    # "claude-sonnet-4-6" -> "sonnet", "claude-opus-4-8" -> "opus"
    parts = model.split("-")
    return parts[1] if len(parts) > 1 else model


def _row(key: str) -> str:
    a = get_agent(key)
    blocks = a.block_threshold or "advisory"
    triggers = (
        ", ".join(f"`{g}`" for g in a.trigger_globs)
        if a.trigger_globs
        else "all changed files"
    )
    context = f"{a.context.strategy} · {_tier(a.model)}"
    if a.framework_only:
        scope = "framework self-review"
    elif a.reviews_template:
        scope = "project + framework (template-incl.)"
    else:
        scope = "project + framework"
    return f"| `{a.name}` | {blocks} | {triggers} | {context} | {scope} |"


def render_reference() -> str:
    names = sorted(agent_names())
    missing = [n for n in names if n not in _BLURBS]
    if missing:
        raise ValueError(f"reference_doc._BLURBS is missing blurbs for: {missing}")
    orphans = [k for k in _BLURBS if k not in names]
    if orphans:
        raise ValueError(
            f"reference_doc._BLURBS has entries not in the registry: {orphans}"
        )
    out = [_HEADER, "", "## At a glance", ""]
    out += ["| Agent | Blocks | Triggers on | Context | Review scope |"]
    out += ["| --- | --- | --- | --- | --- |"]
    out += [_row(n) for n in names]
    out += ["", "## Agents", ""]
    for n in names:
        out += [f"### `{get_agent(n).name}`", "", _BLURBS[n], ""]
    return "\n".join(out).rstrip() + "\n"
