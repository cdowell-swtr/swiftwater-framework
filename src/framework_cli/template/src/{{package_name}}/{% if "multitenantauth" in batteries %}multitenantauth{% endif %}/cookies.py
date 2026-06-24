"""The session-cookie helper — the ONE home for setting the auth cookie.

``set_session_cookie`` writes the opaque session token to an httpOnly cookie. The flags are
the security-load-bearing part:

- ``httponly=True`` — JS can never read the token (XSS can't exfiltrate the session).
- ``secure=settings.session_cookie_secure`` — never sent over plaintext HTTP (default True;
  override only for local dev, never in prod/staging — see the B-F9 note in settings).
- ``samesite="lax"`` — the cookie rides top-level navigations but NOT cross-site subrequests,
  the first line of CSRF defence (the CSRF middleware in routes is the second).
- ``domain=settings.session_cookie_domain`` — None = host-only (safe single-host default);
  set to a parent domain only for an intentional multi-subdomain deployment.

This is the sole writer of the session cookie: every route that issues a session (signup,
login) calls this, so the flag policy lives in exactly one place.
"""

from __future__ import annotations

from fastapi import Response

from ..config.settings import get_settings


def set_session_cookie(response: Response, raw: str) -> None:
    """Set the session cookie on *response* with the security flag policy above."""
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        raw,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        domain=settings.session_cookie_domain,
    )
