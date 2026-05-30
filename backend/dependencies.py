"""Shared FastAPI dependencies.

The recommender is a heavy, read-only singleton built once at startup and stored
on ``app.state``; these helpers expose it (and the model-loaded flag) to routes.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from ml.recommender import HybridRecommender
from ml.reranker import SessionStore


def get_recommender(request: Request) -> HybridRecommender:
    """Return the loaded recommender or raise ``503`` if it is unavailable.

    Args:
        request: The incoming request (carries ``app.state``).

    Returns:
        The shared :class:`~ml.recommender.HybridRecommender`.

    Raises:
        HTTPException: ``503`` if the model failed to load at startup.
    """
    recommender: HybridRecommender | None = getattr(request.app.state, "recommender", None)
    if recommender is None:
        raise HTTPException(status_code=503, detail="Recommendation model is not loaded.")
    return recommender


def get_session_store(request: Request) -> SessionStore:
    """Return the per-session reranker store or raise ``503`` if unavailable.

    Args:
        request: The incoming request (carries ``app.state``).

    Returns:
        The shared :class:`~ml.reranker.SessionStore`.

    Raises:
        HTTPException: ``503`` if the model (and thus the store) failed to load.
    """
    store: SessionStore | None = getattr(request.app.state, "session_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Session store is not loaded.")
    return store
