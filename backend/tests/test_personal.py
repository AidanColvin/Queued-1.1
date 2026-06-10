"""Phase 4: the /recommendations/personal ("For You") endpoint."""

from __future__ import annotations

import pytest


def _register(api, email: str) -> dict:
    res = api.post("/auth/register", json={"email": email, "password": "hunter2secret"})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def some_movies(client) -> list[dict]:
    recs = client.post("/popular", json={"count": 50}).json()["recommendations"]
    movies = [r for r in recs if r["type"] == "movie"]
    assert len(movies) >= 2
    return movies


def test_anonymous_with_seeds_gets_shelves(api, some_movies):
    seed = some_movies[0]
    res = api.get("/recommendations/personal", params={"seeds": seed["title"]})
    assert res.status_code == 200
    body = res.json()
    assert body["signed_in"] is False
    assert body["seeded_by"]  # the seed resolved
    keys = [s["key"] for s in body["sections"]]
    assert any(k.startswith("because_you_liked") for k in keys)
    assert "similar_users" in keys
    # The shelf heading names the seed.
    because = next(s for s in body["sections"] if s["key"].startswith("because_you_liked"))
    assert because["title"].startswith("Because you liked ")
    assert because["items"]
    # The seed itself is never recommended back.
    all_ids = [r["id"] for s in body["sections"] for r in s["items"]]
    assert seed["id"] not in all_ids
    # No title is repeated across shelves.
    assert len(all_ids) == len(set(all_ids))


def test_anonymous_without_seeds_falls_back_to_popular(api):
    res = api.get("/recommendations/personal")
    assert res.status_code == 200
    body = res.json()
    assert body["signed_in"] is False
    assert [s["key"] for s in body["sections"]] == ["popular"]
    assert body["sections"][0]["items"]


def test_signed_in_uses_account_likes_and_excludes_seen(api, some_movies):
    _register(api, "foryou@example.com")
    loved, seen_only = some_movies[0], some_movies[1]
    # Save a like + mark another title merely seen.
    assert api.post("/account/saved", json={"rec": loved, "kind": "liked"}).status_code == 204
    api.post("/account/merge", json={"liked": [], "wishlist": [], "seen": [seen_only["id"]]})

    res = api.get("/recommendations/personal")
    assert res.status_code == 200
    body = res.json()
    assert body["signed_in"] is True
    assert loved["title"] in body["seeded_by"]
    all_ids = [r["id"] for s in body["sections"] for r in s["items"]]
    assert loved["id"] not in all_ids  # seeds excluded
    assert seen_only["id"] not in all_ids  # seen-set excluded


def test_on_your_services_shelf_appears_with_data(api, client, some_movies):
    import main

    from providers import ProviderIndex

    _register(api, "foryou-prov@example.com")
    api.post("/account/saved", json={"rec": some_movies[0], "kind": "liked"})
    api.put("/account/providers", json={"providers": [8]})

    # Everything is on Netflix → the services shelf must materialize.
    catalog = main.app.state.recommender.catalog()
    titles = {rec.tmdb_id: frozenset({8}) for rec in catalog if rec.tmdb_id is not None}
    previous = getattr(main.app.state, "provider_index", None)
    main.app.state.provider_index = ProviderIndex(titles)
    try:
        body = api.get("/recommendations/personal").json()
        keys = [s["key"] for s in body["sections"]]
        assert "on_your_services" in keys
        services = next(s for s in body["sections"] if s["key"] == "on_your_services")
        assert all(8 in r["providers"] for r in services["items"])
    finally:
        main.app.state.provider_index = previous
