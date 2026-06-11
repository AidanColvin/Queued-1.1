"""Phase 5: bearer-token auth (Capacitor shell) + Sign in with Apple."""

from __future__ import annotations


def test_login_returns_access_token_and_bearer_works(api):
    reg = api.post("/auth/register", json={"email": "native@example.com", "password": "hunter2secret"})
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    assert token

    # A cookie-less client authenticates with the Authorization header alone.
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as bare:
        assert bare.get("/auth/me").status_code == 401
        res = bare.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["email"] == "native@example.com"
        # /me never echoes a token back.
        assert res.json()["access_token"] is None


def test_apple_unconfigured_returns_503(api):
    res = api.post("/auth/apple", json={"identity_token": "anything"})
    assert res.status_code == 503


def test_apple_sign_in_creates_links_and_rejects(api, monkeypatch):
    from auth import apple as apple_mod
    from config import get_settings

    monkeypatch.setenv("APPLE_CLIENT_IDS", "com.queued.app")
    get_settings.cache_clear()
    try:
        # Bad token → 401.
        monkeypatch.setattr(apple_mod, "verify_identity_token", lambda tok: None)
        assert api.post("/auth/apple", json={"identity_token": "junk"}).status_code == 401

        # First sign-in (Apple shares the email) → account created + verified.
        claims = {"sub": "apple-sub-1", "email": "Apple-User@example.com"}
        monkeypatch.setattr(apple_mod, "verify_identity_token", lambda tok: claims)
        res = api.post("/auth/apple", json={"identity_token": "ok", "display_name": "Apple User"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["email"] == "apple-user@example.com"
        assert body["email_verified"] is True
        assert body["access_token"]

        # Later sign-in: Apple omits the email; resolved by apple_sub.
        monkeypatch.setattr(apple_mod, "verify_identity_token", lambda tok: {"sub": "apple-sub-1"})
        res = api.post("/auth/apple", json={"identity_token": "ok"})
        assert res.status_code == 200
        assert res.json()["id"] == body["id"]

        # Unknown sub with no email → can't create an account.
        monkeypatch.setattr(apple_mod, "verify_identity_token", lambda tok: {"sub": "apple-sub-2"})
        assert api.post("/auth/apple", json={"identity_token": "ok"}).status_code == 401
    finally:
        monkeypatch.delenv("APPLE_CLIENT_IDS", raising=False)
        get_settings.cache_clear()


def test_apple_links_existing_email_account(api, monkeypatch):
    from auth import apple as apple_mod
    from config import get_settings

    api.post("/auth/register", json={"email": "linkme@example.com", "password": "hunter2secret"})
    api.cookies.clear()

    monkeypatch.setenv("APPLE_CLIENT_IDS", "com.queued.app")
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(
            apple_mod, "verify_identity_token", lambda tok: {"sub": "apple-sub-link", "email": "linkme@example.com"}
        )
        res = api.post("/auth/apple", json={"identity_token": "ok"})
        assert res.status_code == 200
        # Same account — the original password still works alongside Apple.
        api.cookies.clear()
        login = api.post("/auth/login", json={"email": "linkme@example.com", "password": "hunter2secret"})
        assert login.status_code == 200
        assert login.json()["id"] == res.json()["id"]
    finally:
        monkeypatch.delenv("APPLE_CLIENT_IDS", raising=False)
        get_settings.cache_clear()
