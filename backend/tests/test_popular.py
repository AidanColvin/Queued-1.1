"""Tests for ``GET /popular`` and the endless-deck exclude behavior."""

from __future__ import annotations


def test_popular_returns_full_deck(client) -> None:
    """The cold-start deck returns the requested number of cards with metadata."""
    resp = client.get("/popular", params={"count": 12})
    assert resp.status_code == 200
    recs = resp.json()["recommendations"]
    assert len(recs) == 12
    first = recs[0]
    assert {"title", "genres", "cast", "overview", "poster_url", "score"} <= first.keys()


def test_popular_excludes_ids(client) -> None:
    """Ids passed to exclude never appear in the popular deck."""
    first = client.get("/popular", params={"count": 5}).json()["recommendations"]
    drop = first[0]["id"]
    again = client.get("/popular", params={"count": 5, "exclude": str(drop)}).json()["recommendations"]
    assert all(r["id"] != drop for r in again)


def test_recommend_excludes_ids(client) -> None:
    """exclude_ids keeps already-seen titles out of refills (no repeats)."""
    base = client.post("/recommend", json={"titles": ["Breaking Bad"], "count": 5}).json()
    seen = [r["id"] for r in base["recommendations"]]
    refill = client.post(
        "/recommend",
        json={"titles": ["Breaking Bad"], "count": 5, "exclude_ids": seen},
    ).json()
    assert all(r["id"] not in seen for r in refill["recommendations"])


def test_popular_post_excludes_ids(client) -> None:
    """POST /popular takes the exclude list in the body (no URL-length ceiling)."""
    first = client.get("/popular", params={"count": 5}).json()["recommendations"]
    drop = [r["id"] for r in first]
    again = client.post("/popular", json={"count": 5, "exclude_ids": drop}).json()["recommendations"]
    assert all(r["id"] not in drop for r in again)


def test_tv_post_excludes_ids(client) -> None:
    """POST /tv mirrors GET /tv but with a body exclude list."""
    first = client.get("/tv", params={"count": 5}).json()["recommendations"]
    if not first:  # TV catalog may be empty on the sample bundle
        return
    drop = [r["id"] for r in first]
    again = client.post("/tv", json={"count": 5, "exclude_ids": drop}).json()["recommendations"]
    assert all(r["id"] not in drop for r in again)


def test_recommend_includes_cast_and_overview(client) -> None:
    """Recommendations now carry cast + synopsis for the card."""
    resp = client.post("/recommend", json={"titles": ["The Godfather"], "count": 5})
    recs = resp.json()["recommendations"]
    assert any(r["cast"] for r in recs)
    assert any(r["overview"] for r in recs)
