"""NextWatch API — FastAPI application entry point.

Run locally with:

    uvicorn main:app --reload

On startup the app ensures an artifact bundle exists (generating the bundled
sample bundle if none is found and ``AUTO_SAMPLE`` is enabled), loads it into a
shared :class:`~ml.recommender.HybridRecommender`, and seeds the SQLite catalog
that backs ``/search``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from db.database import init_db, seed_movies
from ml.artifacts import artifacts_exist, load_artifacts
from ml.recommender import HybridRecommender
from ml.reranker import SessionStore
from routers import health, popular, recommend, search, swipe

logger = logging.getLogger("nextwatch")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _ensure_artifacts(artifacts_dir) -> None:
    """Generate the sample bundle if no artifacts are present and allowed to.

    Args:
        artifacts_dir: Directory the API loads artifacts from.

    Raises:
        FileNotFoundError: If artifacts are missing and ``AUTO_SAMPLE`` is off.
    """
    settings = get_settings()
    if artifacts_exist(artifacts_dir):
        return
    if not settings.auto_sample:
        raise FileNotFoundError(
            f"No artifacts in {artifacts_dir} and AUTO_SAMPLE is disabled. "
            "Run `python -m data.sample` (sample) or the real data pipeline."
        )
    from data.sample import write_sample_bundle  # local import: training-free

    logger.info("No artifacts found — generating bundled sample bundle...")
    write_sample_bundle(artifacts_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the model and seed the database on startup; tidy up on shutdown."""
    settings = get_settings()
    artifacts_dir = settings.artifacts_dir
    try:
        _ensure_artifacts(artifacts_dir)
        bundle = load_artifacts(artifacts_dir)
        app.state.recommender = HybridRecommender(bundle)
        app.state.session_store = SessionStore(bundle.embeddings, bundle.catalog)
        init_db()
        seeded = seed_movies(bundle.catalog)
        logger.info(
            "Loaded '%s' bundle: %d titles; catalog rows in DB: %d",
            app.state.recommender.source,
            app.state.recommender.size,
            seeded,
        )
    except Exception:  # noqa: BLE001 — log and serve degraded so /health is useful
        logger.exception("Failed to load recommendation model")
        app.state.recommender = None
        app.state.session_store = None
    yield
    app.state.recommender = None
    app.state.session_store = None


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        The configured app (used by Uvicorn and the test suite).
    """
    settings = get_settings()
    app = FastAPI(
        title="NextWatch API",
        version="1.0.0",
        summary="Hybrid movie & TV recommendation engine.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(search.router)
    app.include_router(recommend.router)
    app.include_router(swipe.router)
    app.include_router(popular.router)

    @app.get("/", tags=["meta"])
    def root() -> dict:
        """Tiny landing payload pointing at the interactive docs."""
        return {"name": "NextWatch API", "docs": "/docs", "health": "/health"}

    return app


app = create_app()
