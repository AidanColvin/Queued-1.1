import os
import sys

import pytest

# Root on path so 'backend' resolves as a (namespace) package.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# The log-trainer module is optional local tooling (never shipped to the repo);
# skip cleanly when absent instead of erroring the whole collection.
train_mod = pytest.importorskip(
    "backend.ml.train_from_logs", reason="train_from_logs module not present"
)


def test_train_pipeline():
    log_path = os.path.join("backend", "data", "simulation_logs.csv")
    artifact_path = os.path.join("backend", "data", "artifacts", "weights.json")

    if os.path.exists(log_path):
        train_mod.train_from_logs()
        assert os.path.exists(artifact_path)
    else:
        pytest.skip("Simulation logs missing, skipping training test.")
