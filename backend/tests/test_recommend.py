"""Tests for ``POST /recommend``."""

from __future__ import annotations


def test_empty_input_returns_400(client) -> None:
    """An empty title list is rejected with 400."""
    resp = client.post("/recommend", json={"titles": []})
    assert resp.status_code == 400


def test_single_title_returns_results(client) -> None:
    """A single seed produces a well-formed, non-trivial result set."""
    resp = client.post("/recommend", json={"titles": ["Breaking Bad"]})
    assert resp.status_code == 200
    body = resp.json()
    recs = body["recommendations"]
    assert len(recs) >= 5
    first = recs[0]
    assert {"title", "year", "type", "score", "genres", "poster_url", "tmdb_id", "why"} <= first.keys()
    assert 0.0 <= first["score"] <= 1.0
    assert first["why"]
    assert body["taste_profile"]["top_genres"]


def test_done_criteria_breaking_bad_the_wire(client) -> None:
    """DONE CRITERIA: two seeds return at least five recommendations."""
    resp = client.post("/recommend", json={"titles": ["Breaking Bad", "The Wire"]})
    assert resp.status_code == 200
    assert len(resp.json()["recommendations"]) >= 5


def test_multiple_titles_blend_correctly(client) -> None:
    """Multiple seeds blend into a ranked list with a coherent taste profile."""
    resp = client.post(
        "/recommend",
        json={"titles": ["The Wire", "Succession", "Severance"], "count": 8},
    )
    assert resp.status_code == 200
    body = resp.json()
    recs = body["recommendations"]
    assert 1 <= len(recs) <= 8
    # Scores are sorted descending.
    scores = [r["score"] for r in recs]
    assert scores == sorted(scores, reverse=True)
    assert "Drama" in body["taste_profile"]["top_genres"]


def test_exclude_seen_removes_inputs(client) -> None:
    """With exclude_seen, none of the seed titles appear in the results."""
    seeds = ["Breaking Bad", "Better Call Saul"]
    resp = client.post("/recommend", json={"titles": seeds, "exclude_seen": True})
    assert resp.status_code == 200
    titles = {r["title"] for r in resp.json()["recommendations"]}
    assert titles.isdisjoint(set(seeds))


def test_count_is_respected(client) -> None:
    """The result count never exceeds the requested ``count``."""
    resp = client.post("/recommend", json={"titles": ["Inception"], "count": 3})
    assert resp.status_code == 200
    assert len(resp.json()["recommendations"]) == 3


def test_unknown_title_returns_graceful_error(client) -> None:
    """When no seed resolves, a clean 422 explains the problem (not a 500)."""
    resp = client.post("/recommend", json={"titles": ["Zzxqwv Not A Real Title"]})
    assert resp.status_code == 422
    assert "matched" in resp.json()["detail"].lower()


def test_unknown_title_is_skipped_when_others_resolve(client) -> None:
    """A single bad title does not sink a request that has a valid seed."""
    resp = client.post(
        "/recommend", json={"titles": ["Breaking Bad", "Zzxqwv Not A Real Title"]}
    )
    assert resp.status_code == 200
    assert len(resp.json()["recommendations"]) >= 5
