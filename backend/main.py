"""NextWatch API — FastAPI application entry point.

Run locally with:

    uvicorn main:app --reload

The model + DB are loaded by :func:`load_state`, called both from the startup
lifespan (local/Render) and lazily on the first request (serverless platforms
like Vercel do not run lifespan events). ``create_app(api_prefix=...)`` lets the
same app be mounted under ``/api`` when it runs behind the static frontend.
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from db.database import init_db, seed_movies, seed_title_providers
from ml.artifacts import artifacts_exist, load_artifacts
from ml.recommender import HybridRecommender
from ml.reranker import SessionStore
from providers import ProviderIndex
from routers import auth, health, letterboxd, popular, providers, recommend, search, swipe, trailer, tv, user_data

logger = logging.getLogger("nextwatch")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

_load_lock = threading.Lock()


def _ensure_artifacts(artifacts_dir) -> None:
    """Generate the sample bundle if no artifacts are present and allowed to."""
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


def _load_tv_catalog(artifacts_dir) -> list[dict]:
    """Load the keyless popular-TV catalog (``data.build_tv`` output).

    TV is a standalone catalog with no ML model; returns an empty list when the
    file is absent so ``/tv`` simply serves nothing rather than erroring.
    """
    import json

    try:
        return json.loads((artifacts_dir / "tv_index.json").read_text(encoding="utf-8")).get("series", [])
    except (OSError, ValueError):
        return []


def load_state(app: FastAPI) -> None:
    """Load the model + seed the DB onto ``app.state`` (idempotent, thread-safe).

    Safe to call on every request: it returns immediately once loaded. This is
    what lets the app work on serverless platforms that never run lifespan.
    """
    if getattr(app.state, "recommender", None) is not None:
        return
    with _load_lock:
        if getattr(app.state, "recommender", None) is not None:
            return
        artifacts_dir = get_settings().artifacts_dir
        try:
            _ensure_artifacts(artifacts_dir)
            bundle = load_artifacts(artifacts_dir)
            init_db()
            seed_movies(bundle.catalog)
            app.state.session_store = SessionStore(bundle.embeddings, bundle.catalog)
            app.state.tv_catalog = _load_tv_catalog(artifacts_dir)
            # Streaming availability (optional artifact — empty index when the
            # enrich script hasn't been run; filters then degrade to "all").
            app.state.provider_index = ProviderIndex.load(artifacts_dir)
            if app.state.provider_index.has_data:
                seed_title_providers(app.state.provider_index)
            app.state.recommender = HybridRecommender(bundle)  # set last = "ready" flag
            logger.info("Loaded '%s' bundle: %d titles", app.state.recommender.source, app.state.recommender.size)
        except Exception:  # noqa: BLE001 — serve degraded so /health stays useful
            logger.exception("Failed to load recommendation model")
            app.state.recommender = None
            app.state.session_store = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Eagerly load on startup (local/Render); harmless if the platform skips it."""
    load_state(app)
    yield


def create_app(api_prefix: str = "") -> FastAPI:
    """Build and configure the FastAPI application.

    Args:
        api_prefix: Path prefix for all routes (``"/api"`` when served behind the
            static frontend on a single origin). Empty for local/uvicorn.

    Returns:
        The configured app (used by Uvicorn, the test suite, and the serverless
        entry point).
    """
    settings = get_settings()
    app = FastAPI(
        title="NextWatch API",
        version="1.0.0",
        summary="Hybrid movie & TV recommendation engine.",
        lifespan=lifespan,
        docs_url=f"{api_prefix}/docs",
        openapi_url=f"{api_prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _ensure_loaded(request: Request, call_next):
        """Lazy-load the model on the first request (serverless-safe)."""
        if getattr(request.app.state, "recommender", None) is None:
            load_state(request.app)
        return await call_next(request)

    for router in (health, search, recommend, swipe, popular, tv, trailer, auth, user_data, providers, letterboxd):
        app.include_router(router.router, prefix=api_prefix)

    @app.get(api_prefix or "/", tags=["meta"])
    def root() -> dict:
        """Tiny landing payload pointing at the interactive docs."""
        return {"name": "NextWatch API", "docs": f"{api_prefix}/docs", "health": f"{api_prefix}/health"}

    return app


app = create_app()
