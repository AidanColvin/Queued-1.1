"""Signed-in swipes: SwipeEvent.user_id is filled and the taste vector persists.
Anonymous swipes keep working with a null user_id."""

from __future__ import annotations

from sqlalchemy import select


def _popular_tmdb_ids(api, n: int = 3) -> list[int]:
    recs = api.post("/popular", json={"count": 10, "exclude_ids": []}).json()["recommendations"]
    return [r["tmdb_id"] for r in recs if r["tmdb_id"]][:n]


def test_signed_in_swipe_sets_user_id_and_persists_profile(api) -> None:
    import db.database as database

    api.post("/auth/register", json={"email": "swiper@example.com", "password": "hunter2pw"})
    uid = api.get("/auth/me").json()["id"]
    ids = _popular_tmdb_ids(api)
    assert ids, "sample catalog should yield tmdb ids"

    sid = "swiper-session"
    for tmdb_id in ids:
        r = api.post(
            "/swipe",
            json={"session_id": sid, "tmdb_id": tmdb_id, "action": "liked", "time_on_card_ms": 400, "remaining": ids},
        )
        assert r.status_code == 200

    session = database.get_session_factory()()
    try:
        rows = session.execute(
            select(database.SwipeEvent.user_id).where(database.SwipeEvent.session_id == sid)
        ).all()
        assert rows and all(uid == row[0] for row in rows)
        profile = session.get(database.UserProfile, uid)
        assert profile is not None and profile.taste_vector and profile.confidence > 0
    finally:
        session.close()


def test_anonymous_swipe_still_works_with_null_user(api) -> None:
    import db.database as database

    ids = _popular_tmdb_ids(api, 1)
    r = api.post(
        "/swipe",
        json={"session_id": "anon-1", "tmdb_id": ids[0], "action": "liked", "time_on_card_ms": 400, "remaining": ids},
    )
    assert r.status_code == 200

    session = database.get_session_factory()()
    try:
        anon = session.execute(
            select(database.SwipeEvent).where(database.SwipeEvent.session_id == "anon-1")
        ).scalars().all()
        assert anon and all(ev.user_id is None for ev in anon)
    finally:
        session.close()
