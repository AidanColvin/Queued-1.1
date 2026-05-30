"""Tests for ``GET /search``."""

from __future__ import annotations


def test_search_returns_results_for_known_title(client) -> None:
    """A known title resolves and ranks first."""
    resp = client.get("/search", params={"q": "succession"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) >= 1
    assert results[0]["title"] == "Succession"
    assert results[0]["type"] == "tv"


def test_search_empty_query_returns_400(client) -> None:
    """A blank query is rejected with 400."""
    resp = client.get("/search", params={"q": "   "})
    assert resp.status_code == 400


def test_search_fuzzy_match_works(client) -> None:
    """A misspelled query still surfaces the intended title via fuzzy fallback."""
    resp = client.get("/search", params={"q": "succesion"})  # missing an 's'
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()["results"]]
    assert "Succession" in titles


def test_search_type_filter_restricts_media(client) -> None:
    """The type filter restricts results to a single media kind."""
    resp = client.get("/search", params={"q": "the", "type": "movie", "limit": 25})
    assert resp.status_code == 200
    assert all(r["type"] == "movie" for r in resp.json()["results"])
