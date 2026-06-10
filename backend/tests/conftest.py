"""Pytest fixtures.

The suite runs entirely on the bundled **sample** bundle — no MovieLens
download, no TMDB key, no torch. A throwaway temp directory holds both the
artifacts and the SQLite database, and ``AUTO_SAMPLE`` lets the app's startup
generate the sample artifacts automatically, so the fixtures exercise the real
startup path end-to-end.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator

import pytest

# Make the backend package importable regardless of pytest's CWD.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(scope="session")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator:
    """A ``TestClient`` wired to an isolated sample bundle + SQLite database.

    Session-scoped: the model loads and the catalog is seeded once. All tests
    are read-only, so sharing the instance is safe and keeps the suite fast.
    """
    tmp = tmp_path_factory.mktemp("nextwatch")
    os.environ["MODEL_ARTIFACTS_PATH"] = str(tmp / "artifacts")
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp / 'test.db'}"
    os.environ["AUTO_SAMPLE"] = "true"
    os.environ["CORS_ORIGINS"] = "http://localhost:3000"
    # Accounts/auth (Phase 3): deterministic JWT secret, no Secure flag over the
    # test client's plain HTTP, and a frontend origin for OAuth redirects.
    os.environ["JWT_SECRET"] = "test-secret"
    os.environ["COOKIE_SECURE"] = "false"
    os.environ["FRONTEND_URL"] = "http://localhost:3000"

    # Clear cached settings/engine so the env above takes effect, then import
    # the app fresh (first import in the process happens here, post-env).
    from config import get_settings

    get_settings.cache_clear()
    import db.database as database

    database.get_engine.cache_clear()
    database.get_session_factory.cache_clear()

    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def api(client) -> Iterator:
    """A fresh ``TestClient`` over the already-loaded app, with its own cookie
    jar — so each auth test starts signed out and can't leak a session into the
    next. Depends on ``client`` only to guarantee the model/DB are loaded."""
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as isolated:
        yield isolated
