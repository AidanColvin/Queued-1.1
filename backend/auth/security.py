"""Password hashing, the session JWT, and the auth cookie.

All three are deliberately small and stateless. The JWT is the only session
artifact — there is no server-side session store, which is what lets auth work
on serverless (Vercel) where nothing is shared between invocations. The token
rides in an httpOnly cookie; because the SPA and the API are the same origin,
``SameSite=Lax`` is enough and no CSRF token is needed for the JSON endpoints.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Response

from config import get_settings

# bcrypt only hashes the first 72 bytes of a password and rejects longer input,
# so encode-and-truncate before hashing/verifying. The register schema also caps
# the length, but truncating here keeps a long password from ever 500-ing.
_BCRYPT_MAX_BYTES = 72

# The httpOnly cookie the browser sends on every same-origin call.
AUTH_COOKIE = "nextwatch_auth"
# Path "/" (not "/api") so the same cookie works whether the API is root-mounted
# (local uvicorn / tests) or served under the "/api" prefix in production. The
# routes' mount prefix isn't known here, and "/" is correct in both.
_COOKIE_PATH = "/"
_JWT_ALG = "HS256"


def hash_password(password: str) -> str:
    """Return a bcrypt hash for ``password``."""
    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return whether ``password`` matches the stored ``hashed`` value."""
    try:
        pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed/legacy hash — treat as a failed login, not a 500.
        return False


def create_access_token(user_id: int, email: str) -> str:
    """Mint a signed session JWT for a user.

    Args:
        user_id: The user's primary key (stored as the ``sub`` claim).
        email: The user's email (carried for convenience; identity is ``sub``).

    Returns:
        The encoded HS256 token.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALG)


def create_action_token(user_id: int, purpose: str, expires_minutes: int, fingerprint: str = "") -> str:
    """Mint a single-purpose token (email verification / password reset).

    Stateless like the session JWT, but scoped by a ``purpose`` claim so a
    session token can never be replayed as a reset token (or vice versa).

    Args:
        user_id: The user the action applies to.
        purpose: e.g. ``"verify_email"`` or ``"reset_password"``.
        expires_minutes: Token lifetime.
        fingerprint: Optional state fingerprint baked into the token. For
            password resets this is a slice of the *current* password hash, so
            the token self-invalidates once the password changes (single use
            without a server-side token table).
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "purpose": purpose,
        "fp": fingerprint,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=_JWT_ALG)


def decode_action_token(token: str, purpose: str) -> dict | None:
    """Decode an action token, returning its claims only if valid *and* minted
    for ``purpose`` — otherwise ``None``."""
    claims = decode_token(token)
    if not claims or claims.get("purpose") != purpose:
        return None
    return claims


def password_fingerprint(hashed_password: str | None) -> str:
    """A short, non-reversible fingerprint of the current password hash, baked
    into reset tokens so they stop working the moment the password changes."""
    return (hashed_password or "")[-12:]


def decode_token(token: str) -> dict | None:
    """Decode and verify a session JWT.

    Returns:
        The claims dict, or ``None`` if the token is missing, expired, or has a
        bad signature (so callers can branch without catching exceptions).
    """
    if not token:
        return None
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=[_JWT_ALG])
    except jwt.PyJWTError:
        return None


def set_auth_cookie(response: Response, token: str) -> None:
    """Attach the session JWT to ``response`` as the auth cookie."""
    settings = get_settings()
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        max_age=settings.jwt_expire_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=_COOKIE_PATH,
    )


def clear_auth_cookie(response: Response) -> None:
    """Clear the auth cookie (logout). Flags must match ``set_auth_cookie`` so
    the browser actually drops it."""
    response.delete_cookie(
        key=AUTH_COOKIE,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path=_COOKIE_PATH,
    )
