"""Guess-then-check: swipes log the model's pre-swipe prediction, and
/predict/accuracy scores those guesses against what users actually did."""

from __future__ import annotations


def _swipe(client, session_id, tmdb_id, action, ms=2000):
    return client.post(
        "/swipe",
        json={"session_id": session_id, "tmdb_id": tmdb_id, "action": action,
              "time_on_card_ms": ms, "remaining": []},
    )


def test_first_swipe_has_no_guess_then_guesses_appear(client) -> None:
    """No taste signal -> no guess (null); once signal exists, swipes carry one."""
    from sqlalchemy import select

    import db.database as database
    from db.database import SwipeEvent

    session = "acc-log"
    _swipe(client, session, 1396, "liked")    # cold: model had nothing to go on
    _swipe(client, session, 1438, "liked")    # now there is a vector to guess from

    with database.get_session_factory()() as s:
        rows = s.execute(
            select(SwipeEvent.tmdb_id, SwipeEvent.predicted_score)
            .where(SwipeEvent.session_id == session)
            .order_by(SwipeEvent.id)
        ).all()
    assert len(rows) == 2
    assert rows[0][1] is None, "a cold model must not pretend it guessed"
    assert rows[1][1] is not None, "a warmed model must log its guess"


def test_accuracy_endpoint_scores_the_guesses(client) -> None:
    session = "acc-score"
    _swipe(client, session, 1396, "liked")
    _swipe(client, session, 1438, "liked")
    _swipe(client, session, 4087, "dismissed")  # judged outcomes with guesses

    body = client.get("/predict/accuracy").json()
    assert body["judged_predictions"] >= 2
    assert set(body) >= {"auc", "likes", "dislikes", "mean_score_liked", "mean_score_dismissed"}
    if body["auc"] is not None:
        assert 0.0 <= body["auc"] <= 1.0


def test_accuracy_endpoint_handles_no_data(api) -> None:
    """A deployment with no judged predictions reports counts, not a 500."""
    body = api.get("/predict/accuracy").json()
    assert body["judged_predictions"] >= 0
    assert "auc" in body
