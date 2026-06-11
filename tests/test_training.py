import pytest
import os
import sys

# FORCE the path to the backend directory
# This ensures that 'from ml.train_from_logs' works because 'backend/' is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

# Now the import will work regardless of pytest configuration
from ml.train_from_logs import train_from_logs

def test_train_pipeline():
    # Only proceed if data exists
    log_path = "backend/data/simulation_logs.csv"
    if os.path.exists(log_path):
        train_from_logs()
        assert os.path.exists("backend/data/artifacts/weights.json")
    else:
        pytest.skip("Simulation logs missing, skipping training test.")