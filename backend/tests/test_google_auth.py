"""Google OAuth, with the network calls mocked (no real Google credentials).

Covers the state round-trip, account create + link-by-email, the CSRF state
check, and the not-configured guard."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from auth import google


@pytest.fixture
def google_mock(monkeypatch):
    """Make Google appear configured and stub the token/userinfo network calls.
    Returns a setter so a test can choose the profile the callback will see."""
    profile = {"sub": "g-sub-1", "email": "g@user.com", "name": "G User"}
    monkeypatch.setattr(google, "google_configured", lambda: True)
    monkeypatch.setattr(google, "exchange_code", lambda code: {"access_token": "tok"})
    monkeypatch.setattr(google, "fetch_userinfo", lambda tok: profile)
    return profile


def _login_and_state(api) -> str:
    r = api.get("/auth/google/login", follow_redirects=False)
    assert r.status_code == 302 and "accounts.google.com" in r.headers["location"]
    assert google.OAUTH_STATE_COOKIE in api.cookies
    return parse_qs(urlparse(r.headers["location"]).query)["state"][0]


def test_google_login_redirects_and_sets_state(api, google_mock) -> None:
    _login_and_state(api)


def test_google_callback_creates_account(api, google_mock) -> None:
    google_mock["sub"] = "g-sub-new"
    google_mock["email"] = "newgoogle@user.com"
    state = _login_and_state(api)
    cb = api.get(f"/auth/google/callback?state={state}&code=abc", follow_redirects=False)
    assert cb.status_code == 302 and cb.headers["location"].endswith("/?login=success")
    assert api.get("/auth/me").json()["email"] == "newgoogle@user.com"


def test_google_links_existing_email_account(api, google_mock) -> None:
    api.post("/auth/register", json={"email": "linkme@user.com", "password": "hunter2pw"})
    uid = api.get("/auth/me").json()["id"]
    api.post("/auth/logout")

    google_mock["sub"] = "g-sub-link"
    google_mock["email"] = "linkme@user.com"
    state = _login_and_state(api)
    api.get(f"/auth/google/callback?state={state}&code=abc", follow_redirects=False)
    # Same account (linked, not duplicated).
    assert api.get("/auth/me").json()["id"] == uid


def test_google_callback_rejects_bad_state(api, google_mock) -> None:
    _login_and_state(api)
    bad = api.get("/auth/google/callback?state=tampered&code=abc", follow_redirects=False)
    assert bad.status_code == 400


def test_google_not_configured_is_503(api) -> None:
    # No monkeypatch → no credentials in the test env.
    assert api.get("/auth/google/login", follow_redirects=False).status_code == 503
