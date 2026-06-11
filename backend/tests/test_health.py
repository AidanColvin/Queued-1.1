from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "nextwatch-backend"

def test_demo_recommendations():
    r = client.get("/api/recommendations/demo")
    assert r.status_code == 200
    body = r.json()
    assert "recommendations" in body
    assert len(body["recommendations"]) >= 1
