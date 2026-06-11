from __future__ import annotations

def test_health_status_code(client):
    r = client.get("/health")
    assert r.status_code == 200

def test_health_payload(client):
    r = client.get("/health")
    data = r.json()
    assert data["status"] == "ok"
    assert data["model_loaded"] is True
