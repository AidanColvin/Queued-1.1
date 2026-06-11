from __future__ import annotations
import pytest

def test_recommendations_status_code(client):
    r = client.get("/api/recommendations/1?top_n=5")
    assert r.status_code == 200

def test_recommendations_payload_shape(client):
    r = client.get("/api/recommendations/1?top_n=5")
    data = r.json()
    assert "user_id" in data
    assert "count" in data
    assert "recommendations" in data
    assert isinstance(data["recommendations"], list)

@pytest.mark.parametrize("top_n", [1, 3, 5, 10])
def test_recommendations_top_n_limit(client, top_n):
    r = client.get(f"/api/recommendations/1?top_n={top_n}")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] <= top_n

def test_recommendations_item_keys(client):
    r = client.get("/api/recommendations/1?top_n=5")
    data = r.json()
    if data["recommendations"]:
        item = data["recommendations"][0]
        assert "movieId" in item
        assert "title" in item
        assert "predicted_rating" in item

def test_recommendations_unknown_user(client):
    r = client.get("/api/recommendations/999999?top_n=5")
    assert r.status_code == 200

def test_recommendations_zero_top_n(client):
    r = client.get("/api/recommendations/1?top_n=0")
    assert r.status_code == 200
    data = r.json()
    assert data["recommendations"] == []

def test_recommendations_negative_user_rejected_or_safe(client):
    r = client.get("/api/recommendations/-1?top_n=5")
    assert r.status_code in {200, 422, 500}

def test_recommendations_bad_top_n_rejected_or_safe(client):
    r = client.get("/api/recommendations/1?top_n=abc")
    assert r.status_code in {422}

def test_recommendations_large_top_n(client):
    r = client.get("/api/recommendations/1?top_n=200")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["recommendations"], list)
