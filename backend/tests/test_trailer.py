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


# --- Keyless YouTube-search fallback ------------------------------------------


def test_search_title_restores_article_order() -> None:
    """MovieLens' article-last titles are reflowed for a natural search query."""
    assert trailer_mod._search_title("Incredibles, The") == "The Incredibles"
    assert trailer_mod._search_title("Matrix, The") == "The Matrix"
    assert trailer_mod._search_title("Fargo") == "Fargo"
    assert trailer_mod._search_title("Godfather: Part II, The") == "The Godfather: Part II"


def test_looks_like_trailer_filters_promo_clips() -> None:
    """A real trailer passes; auto-generated Peacock/PKTV promos are rejected."""
    assert trailer_mod._looks_like_trailer("The Matrix (1999) Official Trailer")
    assert not trailer_mod._looks_like_trailer("PKTV 000118000 000306042 | Peacock")
    assert not trailer_mod._looks_like_trailer("The Matrix — full movie clip")  # no "trailer"


class _FakeSearchResp:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:  # noqa: D102
        pass


class _FakeSearchClient:
    """Stand-in for ``httpx.Client`` returning canned YouTube search HTML."""

    def __init__(self, text: str) -> None:
        self._text = text

    def __enter__(self) -> "_FakeSearchClient":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def get(self, url: str, params=None, headers=None, cookies=None) -> _FakeSearchResp:
        return _FakeSearchResp(self._text)


# A promo clip ranks first, the real trailer second; the parser must skip the promo.
_SEARCH_HTML = (
    '"videoRenderer":{"videoId":"PROMOCLIP01","title":{"runs":[{"text":"PKTV 0001 | Peacock"}]}}'
    '"videoRenderer":{"videoId":"REALTRAILER","title":{"runs":[{"text":"The Matrix (1999) Official Trailer"}]}}'
)


def test_youtube_search_skips_promo_and_returns_trailer(monkeypatch) -> None:
    """The scraper returns the first result whose title actually reads as a trailer."""
    monkeypatch.setattr(trailer_mod.httpx, "Client", lambda **kw: _FakeSearchClient(_SEARCH_HTML))
    assert trailer_mod._youtube_search_key("The Matrix", 1999) == "REALTRAILER"


def test_youtube_search_falls_back_to_first_result(monkeypatch) -> None:
    """When nothing clearly reads as a trailer, the top result is used."""
    html = '"videoRenderer":{"videoId":"FIRSTVIDEO1","title":{"runs":[{"text":"Some Movie Scene"}]}}'
    monkeypatch.setattr(trailer_mod.httpx, "Client", lambda **kw: _FakeSearchClient(html))
    assert trailer_mod._youtube_search_key("Some Movie", None) == "FIRSTVIDEO1"


def test_trailer_keyless_fallback_uses_youtube_search(client, monkeypatch) -> None:
    """No TMDB key but a title → endpoint resolves a key via YouTube search."""
    monkeypatch.setattr(trailer_mod.httpx, "Client", lambda **kw: _FakeSearchClient(_SEARCH_HTML))
    body = client.get("/trailer/0?type=movie&title=The+Matrix&year=1999").json()
    assert body["youtube_key"] == "REALTRAILER"
    assert body["source"] == "youtube"
