"""Phase 2: streaming-service registry, onboarding selection, and deck filters."""

from __future__ import annotations

import pytest

from providers import CANONICAL_PROVIDERS, ProviderIndex


def _register(api, email: str) -> dict:
    res = api.post("/auth/register", json={"email": email, "password": "hunter2secret"})
    assert res.status_code == 200, res.text
    return res.json()


def _install_index(app, titles: dict[int, frozenset[int]]):
    """Swap a synthetic availability index onto the app for a test."""
    previous = getattr(app.state, "provider_index", None)
    app.state.provider_index = ProviderIndex(titles)
    return previous


@pytest.fixture
def deck_ids(client) -> list[int]:
    """tmdb_ids of the popular deck, so tests can build availability for them."""
    res = client.post("/popular", json={"count": 10})
    assert res.status_code == 200
    return [r["tmdb_id"] for r in res.json()["recommendations"] if r["tmdb_id"] is not None]


# --------------------------------------------------------------------------- #
# Registry + onboarding selection
# --------------------------------------------------------------------------- #
def test_providers_registry(api):
    res = api.get("/providers")
    assert res.status_code == 200
    body = res.json()
    names = [p["name"] for p in body["providers"]]
    assert "Netflix" in names and "Hulu" in names and "Max" in names
    assert len(body["providers"]) == len(CANONICAL_PROVIDERS)


def test_onboarding_flow_sets_flag_and_saves_selection(api):
    user = _register(api, "onboard@example.com")
    assert user["onboarding_completed"] is False

    res = api.put("/account/providers", json={"providers": [8, 15, 99999], "complete": True})
    assert res.status_code == 200
    body = res.json()
    assert body["providers"] == [8, 15]  # unknown ids dropped
    assert body["onboarding_completed"] is True

    # The flag sticks on /auth/me, and the selection round-trips.
    assert api.get("/auth/me").json()["onboarding_completed"] is True
    assert api.get("/account/providers").json()["providers"] == [8, 15]

    # Replacing the selection replaces, not appends.
    api.put("/account/providers", json={"providers": [337]})
    assert api.get("/account/providers").json()["providers"] == [337]


def test_account_providers_requires_auth(api):
    assert api.get("/account/providers").status_code == 401
    assert api.put("/account/providers", json={"providers": [8]}).status_code == 401


# --------------------------------------------------------------------------- #
# Deck filtering
# --------------------------------------------------------------------------- #
def test_only_filter_hard_filters_deck(api, client, deck_ids):
    import main

    on_netflix = set(deck_ids[:3])
    titles = {tid: frozenset({8}) for tid in on_netflix}
    titles.update({tid: frozenset({15}) for tid in deck_ids[3:]})
    previous = _install_index(main.app, titles)
    try:
        res = api.post("/popular", json={"count": 10, "provider_filter": "only", "providers": [8]})
        assert res.status_code == 200
        recs = res.json()["recommendations"]
        assert recs, "expected at least one on-service card"
        for rec in recs:
            assert 8 in rec["providers"], rec["title"]
            assert rec["tmdb_id"] in on_netflix
    finally:
        main.app.state.provider_index = previous


def test_prefer_filter_floats_services_without_dropping(api, client, deck_ids):
    import main

    last = deck_ids[-1]  # bottom-ranked card is the boost target
    previous = _install_index(main.app, {last: frozenset({1899})})
    try:
        baseline = api.post("/popular", json={"count": 10}).json()["recommendations"]
        boosted = api.post(
            "/popular", json={"count": 10, "provider_filter": "prefer", "providers": [1899]}
        ).json()["recommendations"]
        # Nothing dropped, and the on-service title moved to the front.
        assert {r["id"] for r in boosted} == {r["id"] for r in baseline}
        assert boosted[0]["tmdb_id"] == last
    finally:
        main.app.state.provider_index = previous


def test_filter_degrades_to_all_without_data(api):
    """No availability artifact loaded → 'only' behaves like 'all' (never an
    empty deck because enrichment hasn't run)."""
    res = api.post("/popular", json={"count": 5, "provider_filter": "only", "providers": [8]})
    assert res.status_code == 200
    assert len(res.json()["recommendations"]) == 5


def test_signed_in_selection_overrides_request_providers(api, client, deck_ids):
    import main

    target = deck_ids[0]
    previous = _install_index(main.app, {target: frozenset({531})})
    try:
        _register(api, "override@example.com")
        api.put("/account/providers", json={"providers": [531]})
        # The request lies and says Netflix; the account's Paramount+ wins.
        res = api.post("/popular", json={"count": 10, "provider_filter": "only", "providers": [8]})
        recs = res.json()["recommendations"]
        assert [r["tmdb_id"] for r in recs] == [target]
    finally:
        main.app.state.provider_index = previous
