"""Tests for keyless trailer enrichment (Wikidata P1651) + trailer_key passthrough."""

from __future__ import annotations

import data.enrich_trailers as et


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_wikidata_trailers_parses_bindings(monkeypatch) -> None:
    """SPARQL bindings are flattened to an imdb_id → youtube_id map."""
    payload = {
        "results": {
            "bindings": [
                {"imdb": {"value": "tt0137523"}, "yt": {"value": "BdJKm16Co6M"}},
                {"imdb": {"value": "tt0133093"}, "yt": {"value": "vKQi3bBA1y8"}},
            ]
        }
    }
    monkeypatch.setattr(et, "_request_with_retry", lambda *a, **k: _FakeResp(payload))
    monkeypatch.setattr(et.time, "sleep", lambda *_: None)

    out = et._wikidata_trailers(object(), ["tt0137523", "tt0133093", "tt9999999"])
    assert out == {"tt0137523": "BdJKm16Co6M", "tt0133093": "vKQi3bBA1y8"}


def test_wikidata_trailers_handles_failed_request(monkeypatch) -> None:
    """A None response (exhausted retries) yields no ids, never an error."""
    monkeypatch.setattr(et, "_request_with_retry", lambda *a, **k: None)
    monkeypatch.setattr(et.time, "sleep", lambda *_: None)
    assert et._wikidata_trailers(object(), ["tt1", "tt2"]) == {}


def test_recommendations_expose_trailer_key(client) -> None:
    """The API surfaces trailer_key so the client can play trailers in-page."""
    first = client.get("/popular?count=3").json()["recommendations"][0]
    assert "trailer_key" in first
