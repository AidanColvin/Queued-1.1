"""Tests for ``GET /health`` and the root metadata route."""

from __future__ import annotations


def test_health_reports_loaded_model(client) -> None:
    """Health returns 200 with a loaded model and a non-empty index."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["index_size"] > 0


def test_root_points_at_docs(client) -> None:
    """The root route returns a small JSON pointer to the docs."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["docs"] == "/docs"
