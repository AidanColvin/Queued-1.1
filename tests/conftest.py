from __future__ import annotations
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]

@pytest.fixture(scope="session")
def training_dir(repo_root: Path) -> Path:
    return repo_root / "training"

@pytest.fixture(scope="session")
def app_module():
    from backend.app.main import app
    return app

@pytest.fixture()
def client(app_module):
    with TestClient(app_module) as c:
        yield c

@pytest.fixture(scope="session")
def model_summary(training_dir: Path):
    p = training_dir / "serve_model_summary.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}

@pytest.fixture(scope="session")
def ratings_df(training_dir: Path):
    import pandas as pd
    p = training_dir / "ratings_catalog.csv"
    if not p.exists():
        pytest.skip("ratings_catalog.csv not found; run training first")
    return pd.read_csv(p)

@pytest.fixture(scope="session")
def movies_df(training_dir: Path):
    import pandas as pd
    p = training_dir / "movies_catalog.csv"
    if not p.exists():
        pytest.skip("movies_catalog.csv not found; run training first")
    return pd.read_csv(p)
