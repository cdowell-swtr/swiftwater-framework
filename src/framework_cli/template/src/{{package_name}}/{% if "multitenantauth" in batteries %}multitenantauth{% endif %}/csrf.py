"""CSRF defence for cookie-authenticated state-changing requests (Origin/Referer check).

The CSRF vector is a browser auto-attaching the session cookie to a cross-site state-changing
request — and browsers always send ``Origin`` (or at least ``Referer``) on such requests. So for
a mutating method authenticated via the session COOKIE (not a Bearer token), a cross-origin
Origin/Referer is rejected.

Exemptions: Bearer-authenticated requests without a session cookie are exempt (an attacker
can't forge the Authorization header cross-site). Unauthenticated requests (no session cookie)
are also exempt. A cookie-authenticated mutating request with NEITHER Origin nor Referer is
REJECTED (fail-closed) — a real browser always sends Origin on a cross-origin mutating request,
so an absent pair implies a non-browser / header-stripping client. The full double-submit-token
flow lands with the browser UI (MDN38).

§5.1 security invariants (B-F3/B-F4):
  - A parent-domain ``session_cookie_domain`` discloses the raw session token to every subdomain's
    server — only enable it where every subdomain in the domain is equally trusted.
  - ``SameSite=Lax`` gives no cross-tenant protection between sibling subdomains (the cookie
    rides top-level navigations across sibling origins). Therefore the exact-match
    ``csrf_allowed_origins`` allowlist is the **only** cross-tenant CSRF defence when a parent
    domain cookie is in use.
  - The allowlist is EXACT-MATCH against bare netlocs (e.g. ``"app.example.com"``). Wildcards
    (``"*"``, ``"*.example.com"``) are inert: they are never treated as patterns, so a wildcard
    entry can never grant access. Forbidden by design (B-F4).
  - Default (empty allowlist): only same-host requests pass.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..config.settings import get_settings

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in _MUTATING:
            settings = get_settings()
            # Auth prefers the cookie over a Bearer header (deps.current_user), so ANY request
            # carrying the session cookie is cookie-authenticated and must be CSRF-checked — a
            # junk ``Authorization: Bearer …`` header must NOT exempt it. Pure-Bearer clients
            # (no session cookie) are exempt (an attacker can't set that header cross-site).
            if settings.session_cookie_name in request.cookies:
                source = request.headers.get("origin") or request.headers.get("referer")
                if not source:
                    # B-F3 fail-closed: a cookie-authenticated mutating request with NEITHER
                    # Origin nor Referer is rejected. A real browser always sends Origin on a
                    # cross-origin mutating request, so an absent pair implies a non-browser /
                    # header-stripping client — deny rather than allow. (Layer-2 F: the prior
                    # lenient pass relied on browsers always sending Origin; the full
                    # double-submit-token flow is MDN38.)
                    return JSONResponse(
                        {"detail": "CSRF check failed"}, status_code=403
                    )
                host = request.headers.get("host", "")
                netloc = urlsplit(source).netloc
                # EXACT-MATCH ONLY (B-F4): csrf_allowed_origins holds exact netlocs;
                # NO wildcards/patterns — a "*" entry is never treated as a glob.
                allowed = (netloc == host) or (netloc in settings.csrf_allowed_origins)
                if not allowed:
                    return JSONResponse(
                        {"detail": "CSRF check failed"}, status_code=403
                    )
        return await call_next(request)
