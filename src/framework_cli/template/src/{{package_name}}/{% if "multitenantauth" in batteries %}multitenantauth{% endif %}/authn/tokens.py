"""Opaque session / invite tokens.

Mint a high-entropy random token, hand the raw value to the client exactly once, and persist only
its ``HMAC-SHA256(token, session_pepper)``. The token is opaque (carries no meaning); the DB lookup
of its hash IS the integrity check, so tokens are never signed. Storing the hash (not the token)
means a DB-only read leak yields no usable sessions, and the pepper (in settings, not the DB) means
the hash can't be reconstructed offline without the app secret.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from ...config.settings import get_settings


def mint() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)``. Hand ``raw_token`` to the client; persist ``token_hash``."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    """``HMAC-SHA256(raw, session_pepper)`` as hex — the stored/looked-up form of a token."""
    pepper = get_settings().session_pepper.get_secret_value().encode()
    return hmac.new(pepper, raw.encode(), hashlib.sha256).hexdigest()
