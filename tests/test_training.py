import pytest
import os
# We use absolute imports starting from the root 'backend' package
from backend.ml.train_from_logs import train_from_logs

def test_train_pipeline():
    # Only proceed if data exists to prevent false negatives
    if os.path.exists("backend/data/simulation_logs.csv"):
        train_from_logs()
        assert os.path.exists("backend/data/artifacts/weights.json")
    else:
        pytest.skip("Simulation logs missing, skipping training test.")
