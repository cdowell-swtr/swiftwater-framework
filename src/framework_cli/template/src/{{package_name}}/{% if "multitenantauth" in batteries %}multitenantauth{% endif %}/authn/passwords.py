"""Argon2id password hashing with an application pepper.

argon2-cffi's high-level ``PasswordHasher`` does not expose argon2's native K-secret (the
"pepper"); that field is only reachable via the raw ``argon2_ctx`` CFFI call, which we avoid as
fragile hand-rolled crypto glue in a security-critical path. Instead the pepper is applied as an
**HMAC-SHA256 pre-hash** of the password (a standard, audited peppering pattern), and the result is
argon2id-hashed with a per-row salt (embedded in the encoded PHC string). The pepper lives in
settings, never the DB, so a DB-only leak cannot begin cracking.

Version columns are forward-compat seams ONLY (B-F8): ``pepper_version`` in Settings and
``hash_version`` on AppUser reserve the rotation seam; Phase 1 ships no live rotation logic.
``needs_rehash`` returns True when argon2 cost params change; the login flow rehashes-on-login
after a successful verify.
"""

from __future__ import annotations

import hashlib
import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from ...config.settings import get_settings


def _hasher() -> PasswordHasher:
    s = get_settings()
    return PasswordHasher(
        time_cost=s.argon2_time_cost,
        memory_cost=s.argon2_memory_cost,
        parallelism=s.argon2_parallelism,
    )


def _peppered(password: str) -> str:
    """HMAC-SHA256(password, pepper) → hex. Collapses the password to 256 bits before argon2."""
    pepper = get_settings().password_pepper.get_secret_value().encode()
    return hmac.new(pepper, password.encode(), hashlib.sha256).hexdigest()


def hash_password(password: str) -> str:
    """Return an argon2id PHC-encoded hash (per-row salt embedded) of the peppered password."""
    return _hasher().hash(_peppered(password))


def verify_password(password: str, encoded: str) -> bool:
    """True iff *password* (+ current pepper) matches *encoded*. All failure modes → False."""
    try:
        return _hasher().verify(encoded, _peppered(password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(encoded: str) -> bool:
    """True when *encoded* was produced with different argon2 cost params (→ rehash on login)."""
    try:
        return _hasher().check_needs_rehash(encoded)
    except InvalidHashError:
        return True
