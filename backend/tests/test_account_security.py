"""Phase 1 hardening: password reset, email verification, account deletion,
rate limiting, and durable anonymous session profiles."""

from __future__ import annotations

import pytest


def _register(api, email: str, password: str = "hunter2secret") -> dict:
    res = api.post("/auth/register", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# Password reset
# --------------------------------------------------------------------------- #
def test_password_reset_flow(api, caplog):
    _register(api, "reset@example.com", "originalpass1")
    api.cookies.clear()

    with caplog.at_level("INFO", logger="queued"):
        res = api.post("/auth/request-password-reset", json={"email": "reset@example.com"})
    assert res.status_code == 204

    # Console-fallback email carries the link; pull the token out of the log.
    body = "\n".join(r.getMessage() for r in caplog.records if "reset-password" in r.getMessage())
    token = body.split("token=")[1].split()[0]

    res = api.post("/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"})
    assert res.status_code == 204

    # Old password dead, new password works.
    assert api.post("/auth/login", json={"email": "reset@example.com", "password": "originalpass1"}).status_code == 401
    login = api.post("/auth/login", json={"email": "reset@example.com", "password": "brandnewpass1"})
    assert login.status_code == 200
    # Completing a reset proves inbox control.
    assert login.json()["email_verified"] is True

    # The token is single-use: replaying it after the hash changed fails.
    res = api.post("/auth/reset-password", json={"token": token, "new_password": "anotherpass99"})
    assert res.status_code == 400


def test_password_reset_unknown_email_does_not_leak(api):
    res = api.post("/auth/request-password-reset", json={"email": "nobody@example.com"})
    assert res.status_code == 204  # same response as a real account


def test_reset_password_rejects_garbage_token(api):
    res = api.post("/auth/reset-password", json={"token": "not-a-token", "new_password": "whatever123"})
    assert res.status_code == 400


# --------------------------------------------------------------------------- #
# Email verification
# --------------------------------------------------------------------------- #
def test_register_sends_verification_and_token_verifies(api, caplog):
    with caplog.at_level("INFO", logger="queued"):
        user = _register(api, "verify@example.com")
    assert user["email_verified"] is False

    body = "\n".join(r.getMessage() for r in caplog.records if "verify-email" in r.getMessage())
    token = body.split("token=")[1].split()[0]

    assert api.post("/auth/verify-email", json={"token": token}).status_code == 204
    assert api.get("/auth/me").json()["email_verified"] is True


def test_verify_email_rejects_session_jwt(api):
    """A session cookie JWT must not double as a verification token."""
    _register(api, "purpose@example.com")
    session_jwt = api.cookies.get("queued_auth")
    assert session_jwt
    res = api.post("/auth/verify-email", json={"token": session_jwt})
    assert res.status_code == 400


# --------------------------------------------------------------------------- #
# Account deletion
# --------------------------------------------------------------------------- #
def test_delete_account_removes_everything(api):
    _register(api, "deleteme@example.com")
    # Leave some data behind: a swipe and a saved title.
    api.post(
        "/swipe",
        json={"session_id": "del-sess", "tmdb_id": 1396, "action": "liked", "time_on_card_ms": 900, "remaining": []},
    )

    res = api.delete("/account")
    assert res.status_code == 204

    # Session is gone and the credentials no longer exist.
    assert api.get("/auth/me").status_code == 401
    assert (
        api.post("/auth/login", json={"email": "deleteme@example.com", "password": "hunter2secret"}).status_code == 401
    )
    # The email is free to register again (row really deleted, not soft-flagged).
    assert api.post("/auth/register", json={"email": "deleteme@example.com", "password": "hunter2secret"}).status_code == 200


def test_delete_account_requires_auth(api):
    assert api.delete("/account").status_code == 401


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
def test_login_rate_limited(api, monkeypatch):
    from auth import ratelimit
    from config import get_settings

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    get_settings.cache_clear()
    ratelimit.reset()
    try:
        statuses = [
            api.post("/auth/login", json={"email": "rl@example.com", "password": "wrongpass1"}).status_code
            for _ in range(20)
        ]
        assert 429 in statuses
        assert statuses[0] == 401  # first attempts pass through the limiter
    finally:
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
        get_settings.cache_clear()
        ratelimit.reset()


# --------------------------------------------------------------------------- #
# Durable anonymous sessions
# --------------------------------------------------------------------------- #
def test_anon_session_survives_store_restart(api, client):
    """The taste vector persists to the DB, so a swipe stream keeps its signal
    across a process restart (simulated by wiping the in-memory store)."""
    import main

    session_id = "durable-sess"
    for _ in range(3):  # enough liked signal to cross the confidence threshold
        res = api.post(
            "/swipe",
            json={"session_id": session_id, "tmdb_id": 1396, "action": "liked", "time_on_card_ms": 800, "remaining": []},
        )
        assert res.status_code == 200
    confidence_before = res.json()["session_confidence"]
    assert confidence_before > 0

    # Simulate a restart: drop the in-memory session.
    main.app.state.session_store.reset(session_id)

    res = api.post(
        "/swipe",
        json={"session_id": session_id, "tmdb_id": 1396, "action": "skip", "time_on_card_ms": 500, "remaining": []},
    )
    assert res.status_code == 200
    # A neutral "skip" adds nothing, so any confidence here was warm-started
    # from the persisted row rather than starting over at zero.
    assert res.json()["session_confidence"] == pytest.approx(confidence_before, abs=1e-6)
