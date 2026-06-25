"""Process-wide multi-tenant auth metrics — hand-rolled Prometheus exposition (no client lib).

Mirrors the house pattern: thread-safe module-level singleton, label-light, bounded enum labels.

Covered surfaces:
- ``app_auth_logins_total``   counter  outcome∈{success,failure}
- ``app_auth_sessions_total`` counter  (session-create events; active-session gauge is DB-side)
- ``app_authz_decisions_total`` counter  decision∈{allow,deny} × domain∈{tenant,platform,resource}
- ``app_authz_grants_total``  counter  action∈{grant,revoke} × domain∈{tenant,platform,resource}

Labels are bounded enums — never user-supplied strings (no cardinality explosion).
``active_sessions`` is deliberately omitted from this singleton: in-process inc/dec is wrong
for a multi-worker process where sessions expire passively (no decrement event fires on TTL
expiry). A scrape-time DB count is emitted from the /metrics route instead (see health.py).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

LOGIN_OUTCOMES = ("success", "failure")
AUTHZ_DECISIONS = ("allow", "deny")
AUTHZ_DOMAINS = ("tenant", "platform", "resource")
GRANT_ACTIONS = ("grant", "revoke")


class AuthMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Pre-seed all bounded combos so series appear at zero with no traffic.
        self._logins: dict[str, int] = {o: 0 for o in LOGIN_OUTCOMES}
        self._sessions: int = 0
        self._authz: dict[tuple[str, str], int] = {
            (d, dm): 0 for d in AUTHZ_DECISIONS for dm in AUTHZ_DOMAINS
        }
        self._grants: dict[tuple[str, str], int] = {
            (a, dm): 0 for a in GRANT_ACTIONS for dm in AUTHZ_DOMAINS
        }

    # ── recorders ───────────────────────────────────────────────────────────────

    def record_login(self, outcome: str) -> None:
        """Increment the login counter. ``outcome`` must be 'success' or 'failure'."""
        if outcome not in self._logins:
            return
        with self._lock:
            self._logins[outcome] += 1

    def record_session_create(self) -> None:
        """Increment the session-create counter (a fresh session was minted)."""
        with self._lock:
            self._sessions += 1

    def record_authz(self, decision: str, domain: str) -> None:
        """Record an authz allow/deny event.

        ``decision`` ∈ {allow, deny}; ``domain`` ∈ {tenant, platform, resource}.
        Unknown values are silently ignored (never crash the request).
        """
        key = (decision, domain)
        if key not in self._authz:
            return
        with self._lock:
            self._authz[key] += 1

    def record_grant(self, action: str, domain: str) -> None:
        """Record a role grant/revoke event.

        ``action`` ∈ {grant, revoke}; ``domain`` ∈ {tenant, platform, resource}.
        """
        key = (action, domain)
        if key not in self._grants:
            return
        with self._lock:
            self._grants[key] += 1

    # ── exposition ──────────────────────────────────────────────────────────────

    def render_prometheus(self) -> str:
        with self._lock:
            logins = "".join(
                f'app_auth_logins_total{{outcome="{o}"}} {self._logins[o]}\n'
                for o in LOGIN_OUTCOMES
            )
            sessions = f"app_auth_sessions_total {self._sessions}\n"
            authz = "".join(
                f'app_authz_decisions_total{{decision="{d}",domain="{dm}"}} {self._authz[(d, dm)]}\n'
                for d in AUTHZ_DECISIONS
                for dm in AUTHZ_DOMAINS
            )
            grants = "".join(
                f'app_authz_grants_total{{action="{a}",domain="{dm}"}} {self._grants[(a, dm)]}\n'
                for a in GRANT_ACTIONS
                for dm in AUTHZ_DOMAINS
            )
        return (
            "# HELP app_auth_logins_total Login attempts by outcome\n"
            "# TYPE app_auth_logins_total counter\n"
            f"{logins}"
            "# HELP app_auth_sessions_total Sessions created (minted) by the app\n"
            "# TYPE app_auth_sessions_total counter\n"
            f"{sessions}"
            "# HELP app_authz_decisions_total AuthZ decisions by outcome and domain\n"
            "# TYPE app_authz_decisions_total counter\n"
            f"{authz}"
            "# HELP app_authz_grants_total Role grant/revoke events by action and domain\n"
            "# TYPE app_authz_grants_total counter\n"
            f"{grants}"
        )

    def reset(self) -> None:
        with self._lock:
            self._logins = {o: 0 for o in LOGIN_OUTCOMES}
            self._sessions = 0
            self._authz = {(d, dm): 0 for d in AUTHZ_DECISIONS for dm in AUTHZ_DOMAINS}
            self._grants = {(a, dm): 0 for a in GRANT_ACTIONS for dm in AUTHZ_DOMAINS}


auth_metrics = AuthMetrics()
"""Process-wide singleton imported by auth routes, deps, and authz/service."""


def render_active_sessions_gauge(cs: "Session") -> str:  # type: ignore[name-defined]
    """Return Prometheus text for the live-session gauge (DB-authoritative count).

    Called at scrape-time from the /metrics route with a short-lived control session.
    Counts only unexpired rows — sessions that have been issued but not yet expired or
    explicitly deleted. This is the accurate multi-worker view: in-process inc/dec would
    under-count (restarts reset to zero) and never decrement on TTL expiry.

    The ``Session`` import is inline to keep this module importable without the DB stack
    (used in unit tests that mock the DB).
    """
    from datetime import datetime, timezone

    from sqlalchemy import func, select

    from ..db.control import models as m

    count = (
        cs.scalar(
            select(func.count())
            .select_from(m.Session)
            .where(m.Session.expires_at > datetime.now(timezone.utc))
        )
        or 0
    )
    return (
        "# HELP app_auth_active_sessions Active (unexpired) auth sessions\n"
        "# TYPE app_auth_active_sessions gauge\n"
        f"app_auth_active_sessions {count}\n"
    )
