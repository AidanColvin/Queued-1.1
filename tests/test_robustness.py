from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_demo():
    r = client.get("/api/recommendations/demo")
    assert r.status_code == 200
    body = r.json()
    assert "recommendations" in body
    assert len(body["recommendations"]) >= 1

def test_train():
    r = client.post("/api/train")
    assert r.status_code == 200
    assert r.json()["status"] == "started"

def test_rerank_schema():
    """Validates the contract: API must return a 'recommendations' key with a list of strings."""
    payload = {"user_history": ["The Godfather"]}
    r = client.post("/rerank", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "recommendations" in data
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) > 0

def test_rerank_empty_history():
    """Resilience: Ensure system doesn't crash when history is empty."""
    payload = {"user_history": []}
    r = client.post("/rerank", json=payload)
    assert r.status_code == 200
    assert "recommendations" in r.json()

def test_rerank_malformed_input():
    """Robustness: Ensure system handles missing keys gracefully."""
    r = client.post("/rerank", json={}) # Missing 'user_history'
    assert r.status_code == 200 # Or 422 if you prefer strict validation

import time

def test_rerank_latency():
    """Robustness: Latency threshold check."""
    start = time.time()
    r = client.post("/rerank", json={"user_history": ["The Godfather"]})
    duration = time.time() - start
    assert r.status_code == 200
    assert duration < 0.2, f"Rerank latency too high: {duration:.4f}s"
