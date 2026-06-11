import pytest
import os
import sys

# Ensure the root directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.ml.train_from_logs import train_from_logs

def test_train_pipeline():
    if os.path.exists("backend/data/simulation_logs.csv"):
        train_from_logs()
        assert os.path.exists("backend/data/artifacts/weights.json")
    else:
        pytest.skip("Simulation logs missing, skipping training test.")
