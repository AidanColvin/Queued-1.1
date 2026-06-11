"""Social taste-match endpoint: swipe -> anon profile -> /social/match.

Regression guard. This router was once defined but **never registered** (404 in
production) and imported a schema that didn't exist (crash on registration).
These tests prove it's wired into the app and the match math is sane.
"""

from __future__ import annotations


def _popular_tmdb_ids(client, n: int) -> list[int]:
    r = client.get("/popular", params={"count": n})
    assert r.status_code == 200
    return [rec["tmdb_id"] for rec in r.json()["recommendations"] if rec.get("tmdb_id")][:n]


def _swipe(client, session: str, tmdb: int, action: str):
    return client.post(
        "/swipe",
        json={
            "session_id": session,
            "tmdb_id": tmdb,
            "action": action,
            "time_on_card_ms": 1500,
            "remaining": [],
        },
    )


def test_social_match_identical_beats_opposing(client):
    ids = _popular_tmdb_ids(client, 8)
    assert len(ids) >= 6, "sample bundle should expose enough postered titles"

    # alice and bob like the same films; carol likes the opposite set.
    for t in ids[:4]:
        assert _swipe(client, "soc_alice", t, "liked").status_code == 200
        assert _swipe(client, "soc_bob", t, "liked").status_code == 200
    for t in ids[:4]:
        _swipe(client, "soc_carol", t, "dismissed")
    for t in ids[4:8]:
        _swipe(client, "soc_carol", t, "liked")

    same = client.get("/social/match", params={"user_a": "soc_alice", "user_b": "soc_bob"})
    opp = client.get("/social/match", params={"user_a": "soc_alice", "user_b": "soc_carol"})
    assert same.status_code == 200 and opp.status_code == 200

    same_pct = same.json()["match_percentage"]
    assert 0 <= same_pct <= 100
    assert same_pct > opp.json()["match_percentage"], "identical tastes must match higher than opposing"


def test_social_match_unknown_session_is_404(client):
    r = client.get("/social/match", params={"user_a": "no-such-a", "user_b": "no-such-b"})
    assert r.status_code == 404
