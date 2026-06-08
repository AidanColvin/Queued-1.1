"""Tests for ``GET /trailer/{tmdb_id}`` (in-page trailer resolution)."""

from __future__ import annotations

from types import SimpleNamespace

import routers.trailer as trailer_mod

FIGHT_CLUB = 550


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # noqa: D102
        pass

    def json(self) -> dict:  # noqa: D102
        return self._payload


class _FakeClient:
    """Stand-in for ``httpx.Client`` that returns a canned ``videos`` payload."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def get(self, url: str, params: dict | None = None) -> _FakeResp:
        return _FakeResp(self._payload)


def test_trailer_unconfigured_returns_null_not_error(client) -> None:
    """With no TMDB key (the test env), the route is a graceful null, not a 500."""
    resp = client.get(f"/trailer/{FIGHT_CLUB}?type=movie")
    assert resp.status_code == 200
    assert resp.json() == {"youtube_key": None, "name": None, "source": "unconfigured"}


def test_trailer_returns_youtube_key_from_tmdb(client, monkeypatch) -> None:
    """When TMDB is configured, the best YouTube trailer key is returned."""
    monkeypatch.setattr(trailer_mod, "get_settings", lambda: SimpleNamespace(tmdb_api_key="test-key"))
    payload = {
        "results": [
            {"site": "YouTube", "key": "TEASERKEY", "type": "Teaser", "official": True},
            {"site": "YouTube", "key": "TRAILERKEY", "type": "Trailer", "official": True},
            {"site": "Vimeo", "key": "VIMEOKEY", "type": "Trailer", "official": True},
        ]
    }
    monkeypatch.setattr(trailer_mod.httpx, "Client", lambda **kw: _FakeClient(payload))

    body = client.get(f"/trailer/{FIGHT_CLUB}?type=movie").json()
    assert body["youtube_key"] == "TRAILERKEY"
    assert body["source"] == "tmdb"


def test_best_trailer_prefers_official_trailer() -> None:
    """Official trailers outrank teasers and fan uploads; non-YouTube is ignored."""
    videos = [
        {"site": "YouTube", "key": "teaser", "type": "Teaser", "official": True},
        {"site": "YouTube", "key": "fan", "type": "Trailer", "official": False},
        {"site": "YouTube", "key": "official", "type": "Trailer", "official": True},
        {"site": "Vimeo", "key": "vimeo", "type": "Trailer", "official": True},
    ]
    assert trailer_mod._best_trailer(videos)["key"] == "official"


def test_best_trailer_none_when_no_youtube_video() -> None:
    """No embeddable YouTube video → ``None`` (client falls back gracefully)."""
    assert trailer_mod._best_trailer([{"site": "Vimeo", "key": "x", "type": "Trailer"}]) is None
    assert trailer_mod._best_trailer([]) is None
