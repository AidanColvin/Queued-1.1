"""Email/password account lifecycle: register, login, /me, logout."""

from __future__ import annotations


def test_register_signs_in_and_me_returns_user(api) -> None:
    r = api.post("/auth/register", json={"email": "ada@example.com", "password": "hunter2pw", "display_name": "Ada"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "ada@example.com" and body["display_name"] == "Ada"

    me = api.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"


def test_anonymous_me_is_401(api) -> None:
    assert api.get("/auth/me").status_code == 401


def test_duplicate_email_is_409(api) -> None:
    api.post("/auth/register", json={"email": "dup@example.com", "password": "hunter2pw"})
    again = api.post("/auth/register", json={"email": "DUP@example.com", "password": "otherpass"})
    assert again.status_code == 409


def test_login_good_and_bad_credentials(api) -> None:
    api.post("/auth/register", json={"email": "li@example.com", "password": "correctpw1"})
    api.post("/auth/logout")

    assert api.post("/auth/login", json={"email": "li@example.com", "password": "wrongpass"}).status_code == 401
    assert api.post("/auth/login", json={"email": "nobody@example.com", "password": "correctpw1"}).status_code == 401

    good = api.post("/auth/login", json={"email": "li@example.com", "password": "correctpw1"})
    assert good.status_code == 200
    assert api.get("/auth/me").status_code == 200


def test_logout_clears_session(api) -> None:
    api.post("/auth/register", json={"email": "out@example.com", "password": "hunter2pw"})
    assert api.get("/auth/me").status_code == 200
    assert api.post("/auth/logout").status_code == 204
    assert api.get("/auth/me").status_code == 401
