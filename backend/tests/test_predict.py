import pytest
from fastapi.testclient import TestClient
from ml.predictor import TrajectoryPredictor
from main import app

def test_trajectory_prediction_math():
    pr = TrajectoryPredictor()
    score = pr.predict_future_affinity([0.1]*384, [{"action":"liked","embedding":[0.2]*384}], [0.1]*384)
    assert isinstance(score, float)

def test_api_validation():
    client = TestClient(app)
    res = client.post("/predict/trajectory", json={
        "current_profile": [0.0]*384,
        "simulated_steps": [{"action":"liked","embedding":[0.1]*384}],
        "candidate_embedding": [0.1]*384
    })
    assert res.status_code == 200
    assert "predicted_affinity" in res.json()
