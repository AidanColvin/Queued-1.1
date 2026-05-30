"""Tests for ``GET /tv`` — the keyless, popularity-ranked television deck.

The sample bundle ships no ``tv_index.json``, so a small fake catalog is
injected onto ``app.state`` to exercise the ranking, shape and exclude logic.
"""

from __future__ import annotations

import pytest

FAKE_TV = [
    {
        "id": 8_000_000 + i,
        "title": f"Show {i}",
        "year": 2000 + i,
        "type": "tv",
        "genres": ["Drama"],
        "cast": [],
        "overview": f"About show {i}.",
        "poster_url": f"https://example.com/{i}.jpg",
        "tmdb_id": None,
    }
    for i in range(10)
]


@pytest.fixture(autouse=True)
def _seed_tv(client):
    """Inject a small TV catalog onto ``app.state`` for these tests."""
    client.app.state.tv_catalog = FAKE_TV
    yield
    client.app.state.tv_catalog = []


def test_tv_returns_ranked_deck(client) -> None:
    """The TV deck returns the requested number of TV cards in stored order."""
    resp = client.get("/tv", params={"count": 5})
    assert resp.status_code == 200
    recs = resp.json()["recommendations"]
    assert len(recs) == 5
    assert all(r["type"] == "tv" for r in recs)
    assert recs[0]["id"] == 8_000_000  # popularity order preserved
    assert {"title", "genres", "overview", "poster_url", "score"} <= recs[0].keys()


def test_tv_excludes_ids(client) -> None:
    """Ids passed to exclude never appear in the TV deck (no repeats)."""
    drop = 8_000_000
    recs = client.get("/tv", params={"count": 5, "exclude": str(drop)}).json()["recommendations"]
    assert all(r["id"] != drop for r in recs)


def test_tv_empty_without_catalog(client) -> None:
    """With no TV catalog loaded, the endpoint degrades to an empty deck."""
    client.app.state.tv_catalog = []
    body = client.get("/tv").json()
    assert body["recommendations"] == []
    assert "taste_profile" in body
