"""HMAC-SHA256 signature verification for inbound webhooks."""

from __future__ import annotations

import hashlib
import hmac


def verify(raw_body: bytes, signature: str, secret: str) -> bool:
    """True iff `signature` is the hex HMAC-SHA256 of `raw_body` under `secret`.

    An empty secret (unconfigured) rejects everything. Comparison is constant-time.
    """
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), signature.encode())
