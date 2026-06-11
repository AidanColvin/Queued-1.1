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

def test_superlike_steers_harder_than_like():
    """The predictor must share the live reranker's signal weights."""
    pr = TrajectoryPredictor()
    profile, target = [0.0] * 8, [1.0] + [0.0] * 7
    step = lambda action: [{"action": action, "embedding": target}]
    liked = pr.predict_future_affinity(profile, step("liked"), target)
    superliked = pr.predict_future_affinity(profile, step("superliked"), target)
    disliked = pr.predict_future_affinity(profile, step("dismissed"), target)
    assert liked == superliked == 1.0  # same direction -> same cosine
    assert disliked == -1.0            # dismissal points away
    assert pr.w["superliked"] > pr.w["liked"] > pr.w["dismissed"]

def test_dimension_mismatch_is_rejected():
    client = TestClient(app)
    res = client.post("/predict/trajectory", json={
        "current_profile": [0.1] * 384,
        "simulated_steps": [],
        "candidate_embedding": [0.1] * 434,
    })
    assert res.status_code == 400

def test_taste_space_dims_accepted():
    """434-dim production taste-space vectors must work, not just 384."""
    client = TestClient(app)
    res = client.post("/predict/trajectory", json={
        "current_profile": [0.1] * 434,
        "simulated_steps": [{"action": "superliked", "embedding": [0.2] * 434}],
        "candidate_embedding": [0.1] * 434,
    })
    assert res.status_code == 200
    assert res.json()["predicted_affinity"] > 0.9
