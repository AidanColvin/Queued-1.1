"""``GET /health`` — liveness + model-readiness probe."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ml.recommender import HybridRecommender
from schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Report service status, whether the model loaded, and the index size.

    Returns ``200`` regardless so orchestrators can scrape it; the ``status``
    field is ``"ok"`` only when the recommender is loaded.

    Args:
        request: The incoming request (carries ``app.state``).

    Returns:
        A :class:`~schemas.HealthResponse`.
    """
    recommender: HybridRecommender | None = getattr(request.app.state, "recommender", None)
    loaded = recommender is not None
    return HealthResponse(
        status="ok" if loaded else "degraded",
        model_loaded=loaded,
        index_size=recommender.size if recommender else 0,
    )
