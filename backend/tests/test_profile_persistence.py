"""Layer 2: a user's taste survives a cold start.

The in-memory SessionStore is per-process and ephemeral on serverless, so the
DB UserProfile row is the source of truth. After reloading app state (simulating
a fresh serverless instance) a signed-in user's next swipe must warm-start from
the persisted vector, not from zero."""

from __future__ import annotations


def _popular_tmdb_ids(api, n: int = 3) -> list[int]:
    recs = api.post("/popular", json={"count": 10, "exclude_ids": []}).json()["recommendations"]
    return [r["tmdb_id"] for r in recs if r["tmdb_id"]][:n]


def test_confidence_accumulates_across_swipes(api) -> None:
    api.post("/auth/register", json={"email": "accum@example.com", "password": "hunter2pw"})
    ids = _popular_tmdb_ids(api)
    confidences = []
    for tmdb_id in ids:
        r = api.post(
            "/swipe",
            json={"session_id": "s", "tmdb_id": tmdb_id, "action": "liked", "time_on_card_ms": 400, "remaining": ids},
        )
        confidences.append(r.json()["session_confidence"])
    assert confidences == sorted(confidences) and confidences[-1] > confidences[0]


def test_warm_start_after_cold_restart(api) -> None:
    import main

    api.post("/auth/register", json={"email": "warm@example.com", "password": "hunter2pw"})
    ids = _popular_tmdb_ids(api)
    last = 0.0
    for tmdb_id in ids:
        last = api.post(
            "/swipe",
            json={"session_id": "s", "tmdb_id": tmdb_id, "action": "liked", "time_on_card_ms": 400, "remaining": ids},
        ).json()["session_confidence"]
    assert last > 0

    # Simulate a fresh serverless instance: drop the loaded state and reload,
    # which rebuilds an empty in-memory SessionStore.
    main.app.state.recommender = None
    main.load_state(main.app)

    after = api.post(
        "/swipe",
        json={"session_id": "s-new", "tmdb_id": ids[0], "action": "liked", "time_on_card_ms": 400, "remaining": ids},
    ).json()["session_confidence"]
    # Warm-started from the persisted vector → strictly greater than the first swipe.
    assert after > last
