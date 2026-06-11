"""Google OAuth (authorization-code flow) over plain ``httpx``.

We use the token + userinfo endpoints directly rather than an OAuth library:
it's a few lines, adds no dependency, and avoids server-side session state —
which matters because serverless instances share nothing between requests. CSRF
is covered by a random ``state`` echoed through a short-lived httpOnly cookie
(an attacker can neither read nor set it cross-site), so no signing lib is
needed.

The token exchange and userinfo fetch are module-level functions so tests can
monkeypatch them without real Google credentials.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from config import get_settings

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# Short-lived httpOnly cookie holding the CSRF ``state`` between /login and
# /callback. Path "/" so it survives the round-trip through Google.
OAUTH_STATE_COOKIE = "queued_oauth_state"
OAUTH_SCOPE = "openid email profile"


def google_configured() -> bool:
    """Whether Google sign-in is set up (all three credentials present)."""
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret and s.google_redirect_uri)


def build_authorize_url(state: str) -> str:
    """Build the Google consent-screen URL to redirect the browser to."""
    s = get_settings()
    params = {
        "client_id": s.google_client_id,
        "redirect_uri": s.google_redirect_uri,
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """Exchange an authorization ``code`` for tokens. Raises on HTTP error."""
    s = get_settings()
    resp = httpx.post(
        _GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "redirect_uri": s.google_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_userinfo(access_token: str) -> dict:
    """Fetch the OpenID userinfo (``sub``, ``email``, ``name``). Raises on error."""
    resp = httpx.get(
        _GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()
