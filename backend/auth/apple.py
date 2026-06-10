"""Sign in with Apple — server-side identity-token verification.

The native app runs Apple's authorization UI and receives an ``identityToken``
(a JWT signed by Apple). The backend verifies it against Apple's published
JWKS, checks the audience (our bundle id / Services ID from
``APPLE_CLIENT_IDS``) and issuer, and only then trusts the ``sub``/``email``
claims. No Apple secret is needed for this flow — verification is pure JWKS.

Apple requires offering this whenever third-party sign-in (Google) is offered
in an iOS app (App Store Review Guideline 4.8).
"""

from __future__ import annotations

import jwt
from jwt import PyJWKClient

from config import get_settings

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"

# Lazily constructed so importing this module never touches the network.
_jwks_client: PyJWKClient | None = None


def apple_configured() -> bool:
    """Whether Sign in with Apple is configured on this deployment."""
    return bool(get_settings().apple_client_ids)


def verify_identity_token(identity_token: str) -> dict | None:
    """Verify an Apple identity token and return its claims, or ``None``.

    Checks signature (Apple JWKS), issuer, expiry, and that the audience is
    one of our configured client ids. Patchable in tests.
    """
    global _jwks_client
    try:
        if _jwks_client is None:
            _jwks_client = PyJWKClient(APPLE_JWKS_URL, lifespan=3600)
        signing_key = _jwks_client.get_signing_key_from_jwt(identity_token)
        return jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=get_settings().apple_client_ids,
            issuer=APPLE_ISSUER,
        )
    except Exception:  # noqa: BLE001 — any failure means "not authenticated"
        return None
