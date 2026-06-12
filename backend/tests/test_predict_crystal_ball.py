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


def test_forecast_never_names_already_swiped_titles(client) -> None:
    """Predicting a title the user just liked is recall, not a forecast."""
    session = "cb-no-echo"
    swiped = [1396, 1438]  # Breaking Bad, The Wire
    for tmdb_id in swiped:
        _swipe(client, session, tmdb_id, "liked")
    body = client.get(f"/predict/crystal-ball?session_id={session}").json()
    assert body["personalized"] is True
    forecast_ids = {m["id"] for m in body["loves"]} | {m["id"] for m in body["hates"]}
    assert not forecast_ids & set(swiped), "forecast echoed an already-swiped title"
