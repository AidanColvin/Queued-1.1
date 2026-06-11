"""The crystal ball must forecast from the caller's REAL taste vector."""

from __future__ import annotations


def _swipe(client, session_id, tmdb_id, action):
    return client.post(
        "/swipe",
        json={"session_id": session_id, "tmdb_id": tmdb_id, "action": action,
              "time_on_card_ms": 2000, "remaining": []},
    )


def test_cold_session_gets_crowd_fallback(client) -> None:
    body = client.get("/predict/crystal-ball?session_id=cb-cold").json()
    assert body["personalized"] is False
    assert len(body["loves"]) > 0  # popularity fallback, never empty
    assert body["hates"] == []


def test_swipes_personalize_the_forecast(client) -> None:
    session = "cb-warm"
    _swipe(client, session, 1396, "liked")   # Breaking Bad
    _swipe(client, session, 1438, "liked")   # The Wire
    body = client.get(f"/predict/crystal-ball?session_id={session}").json()
    assert body["personalized"] is True
    assert len(body["loves"]) > 0
    titles = {m["title"] for m in body["loves"]}
    assert titles, "personalized loves must not be empty"
    # forecast entries carry usable fields for the widget
    first = body["loves"][0]
    assert {"id", "title", "score"} <= set(first)
