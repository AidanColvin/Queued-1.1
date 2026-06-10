"""Tests for ``POST /recommend/adaptive`` — the taste-driven movie deck."""

from __future__ import annotations

# TMDB ids from the sample catalog (see test_swipe).
BREAKING_BAD = 1396
THE_WIRE = 1438
THE_SOPRANOS = 1398


def _swipe(client, session_id, tmdb_id, action):
    r = client.post(
        "/swipe",
        json={"session_id": session_id, "tmdb_id": tmdb_id, "action": action, "time_on_card_ms": 2000, "remaining": []},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _adaptive(client, session_id, exclude=None):
    r = client.post(
        "/recommend/adaptive",
        json={"session_id": session_id, "count": 8, "exclude_ids": exclude or []},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_adaptive_falls_back_to_popular_without_signal(client) -> None:
    """A brand-new session has no taste yet → still returns a (popular) deck."""
    body = _adaptive(client, "adapt-cold")
    assert len(body["recommendations"]) > 0


def test_adaptive_personalizes_after_swipes(client) -> None:
    """Once a session has signal, the deck returns taste-ranked candidates (not
    the popular fallback), tagged with the personalized explanation."""
    sid = "adapt-warm"
    for tmdb in (BREAKING_BAD, THE_WIRE):  # two likes → confidence >= 0.1
        _swipe(client, sid, tmdb, "liked")
    body = _adaptive(client, sid)
    recs = body["recommendations"]
    assert len(recs) > 0
    # The taste path tags its picks; the popular fallback uses a different why.
    assert any(r["why"] == "Tuned to your taste." for r in recs)


def test_adaptive_excludes_are_respected(client) -> None:
    """Explicit exclude_ids never come back (the dedup guarantee)."""
    sid = "adapt-exclude"
    _swipe(client, sid, BREAKING_BAD, "liked")
    _swipe(client, sid, THE_WIRE, "liked")
    first = _adaptive(client, sid)
    seen = [r["id"] for r in first["recommendations"]]
    second = _adaptive(client, sid, exclude=seen)
    assert all(r["id"] not in seen for r in second["recommendations"])
