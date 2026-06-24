"""Conservative email canonicalization for the uniqueness key.

A speed-bump against casual multi-account abuse, NOT a wall — provider ``+tag``/dot semantics are
provider-specific, and a custom-domain owner controls their own aliasing. The robust proof of inbox
control is the email-validation flow. Display/delivery uses the as-entered address; uniqueness uses
this canonical form.

To avoid *merging distinct inboxes*, ``+tag`` stripping is applied ONLY for a known-provider
allowlist (providers documented to treat ``+tag`` as the same mailbox), and dot-stripping only for
Gmail. Unknown domains are lowercased + trimmed but otherwise left intact.
"""

from __future__ import annotations

# Providers known to treat `local+tag@domain` as the same mailbox as `local@domain`.
_PLUS_PROVIDERS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "fastmail.com",
        "proton.me",
        "protonmail.com",
        "icloud.com",
    }
)
# Providers that also ignore dots in the local part.
_DOT_PROVIDERS = frozenset({"gmail.com", "googlemail.com"})


def canonicalize(raw: str) -> str:
    """Return the canonical (uniqueness-key) form of *raw*. Raises ValueError if malformed."""
    email = raw.strip().lower()
    if email.count("@") != 1 or email.startswith("@") or email.endswith("@"):
        raise ValueError(f"malformed email: {raw!r}")
    local, domain = email.split("@")
    if domain in _PLUS_PROVIDERS:
        local = local.split("+", 1)[0]
    if domain in _DOT_PROVIDERS:
        local = local.replace(".", "")
    if not local:
        raise ValueError(f"malformed email local part: {raw!r}")
    return f"{local}@{domain}"
