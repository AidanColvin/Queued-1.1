"""Per-user saved state: merge guest data, history, and the single-save endpoint."""

from __future__ import annotations


def _rec(movie_id: int, title: str, tmdb_id: int) -> dict:
    return {
        "id": movie_id,
        "title": title,
        "year": 1999,
        "type": "movie",
        "score": 0.8,
        "genres": ["Drama"],
        "cast": [],
        "overview": "",
        "poster_url": None,
        "tmdb_id": tmdb_id,
        "trailer_key": None,
        "why": "x",
    }


def _signup(api, email: str) -> None:
    assert api.post("/auth/register", json={"email": email, "password": "hunter2pw"}).status_code == 200


def test_merge_then_history_returns_items(api) -> None:
    _signup(api, "merge1@example.com")
    liked = [_rec(1, "Heat", 949)]
    wishlist = [_rec(2, "Fargo", 275)]
    r = api.post("/account/merge", json={"liked": liked, "wishlist": wishlist, "seen": [1, 2, 3]})
    assert r.status_code == 200
    body = r.json()
    assert {x["id"] for x in body["liked"]} == {1}
    assert {x["id"] for x in body["wishlist"]} == {2}
    assert set(body["seen"]) == {1, 2, 3}

    hist = api.get("/account/history").json()
    assert hist["liked"][0]["title"] == "Heat"


def test_merge_is_idempotent(api) -> None:
    _signup(api, "merge2@example.com")
    payload = {"liked": [_rec(10, "Se7en", 807)], "wishlist": [], "seen": [10]}
    api.post("/account/merge", json=payload)
    second = api.post("/account/merge", json=payload).json()
    assert len(second["liked"]) == 1
    assert second["seen"] == [10]


def test_history_requires_auth(api) -> None:
    assert api.get("/account/history").status_code == 401


def test_saved_endpoint_adds_one_title(api) -> None:
    _signup(api, "saved@example.com")
    assert api.post("/account/saved", json={"rec": _rec(20, "Whiplash", 244786), "kind": "wishlist"}).status_code == 204
    hist = api.get("/account/history").json()
    assert hist["wishlist"][0]["id"] == 20
    assert 20 in hist["seen"]  # saving also marks it seen
