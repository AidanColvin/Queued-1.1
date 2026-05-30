"""Tests for ``POST /swipe`` (Layer 1 adaptive re-ranking)."""

from __future__ import annotations

# TMDB ids from the sample catalog used to build coherent swipe scenarios.
BREAKING_BAD = 1396
THE_WIRE = 1438
THE_SOPRANOS = 1398
OZARK = 69740
THE_OFFICE = 2316
PARKS_AND_REC = 8592


def _swipe(client, session_id, tmdb_id, action, remaining=None, ms=2000):
    """POST a swipe and return the parsed JSON body."""
    resp = client.post(
        "/swipe",
        json={
            "session_id": session_id,
            "tmdb_id": tmdb_id,
            "action": action,
            "time_on_card_ms": ms,
            "remaining": remaining or [],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_swipe_records_and_returns_shape(client) -> None:
    """A swipe returns the documented response shape."""
    body = _swipe(client, "s-shape", BREAKING_BAD, "liked", remaining=[THE_WIRE, THE_OFFICE])
    assert set(body) == {"reranked_queue", "session_confidence", "applied"}
    assert body["applied"] is True
    assert sorted(body["reranked_queue"]) == sorted([THE_WIRE, THE_OFFICE])


def test_swipe_invalid_action_returns_422(client) -> None:
    """An action outside the four directions is rejected by validation."""
    resp = client.post(
        "/swipe",
        json={"session_id": "s-bad", "tmdb_id": BREAKING_BAD, "action": "love", "time_on_card_ms": 100},
    )
    assert resp.status_code == 422


def test_swipe_confidence_grows_with_signal(client) -> None:
    """Confidence accumulates across swipes within a session."""
    first = _swipe(client, "s-conf", BREAKING_BAD, "liked")
    second = _swipe(client, "s-conf", THE_WIRE, "liked")
    assert first["session_confidence"] < second["session_confidence"]


def test_swipe_below_threshold_keeps_order(client) -> None:
    """A single like (confidence 0.1 < 0.15) leaves the deck order untouched."""
    remaining = [THE_OFFICE, THE_SOPRANOS, PARKS_AND_REC]
    body = _swipe(client, "s-thresh", BREAKING_BAD, "liked", remaining=remaining)
    assert body["session_confidence"] < 0.15
    assert body["reranked_queue"] == remaining


def test_swipe_reranks_toward_liked_taste(client) -> None:
    """After liking two crime dramas, a crime drama outranks a sitcom."""
    session = "s-rerank"
    _swipe(client, session, BREAKING_BAD, "liked")
    body = _swipe(
        client,
        session,
        THE_WIRE,
        "liked",
        remaining=[THE_OFFICE, THE_SOPRANOS, PARKS_AND_REC],
    )
    assert body["session_confidence"] >= 0.15
    queue = body["reranked_queue"]
    # The Sopranos (crime drama) should now rank ahead of the sitcoms.
    assert queue.index(THE_SOPRANOS) < queue.index(THE_OFFICE)
    assert queue.index(THE_SOPRANOS) < queue.index(PARKS_AND_REC)


def test_swipe_unknown_card_is_noop_not_error(client) -> None:
    """An unknown tmdb_id is a graceful no-op (applied=False), not a 500."""
    body = _swipe(client, "s-unknown", 999_999_999, "liked", remaining=[THE_WIRE])
    assert body["applied"] is False
    assert body["reranked_queue"] == [THE_WIRE]


def test_swipe_persists_events(client) -> None:
    """Swipes are written to the swipe_events table for offline retraining."""
    from sqlalchemy import func, select

    from db.database import SwipeEvent, get_session_factory

    session = "s-persist"
    _swipe(client, session, BREAKING_BAD, "liked")
    _swipe(client, session, THE_OFFICE, "dismissed", ms=800)

    with get_session_factory()() as db:
        count = db.scalar(select(func.count()).select_from(SwipeEvent).where(SwipeEvent.session_id == session))
    assert count == 2
