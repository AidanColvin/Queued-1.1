"""``POST /recommend`` — the hybrid recommendation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.deps import get_optional_user
from db.database import User, get_db
from dependencies import get_provider_index, get_recommender
from ml.recommender import HybridRecommender
from providers import ONLY_FILTER_OVERFETCH, ProviderIndex
from routers.providers import user_provider_ids
from schemas import RecommendRequest, RecommendResponse

router = APIRouter(tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
def recommend(
    payload: RecommendRequest,
    recommender: HybridRecommender = Depends(get_recommender),
    index: ProviderIndex = Depends(get_provider_index),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> RecommendResponse:
    """Return ranked recommendations for the seed titles.

    Unknown titles are skipped: if at least one seed resolves, recommendations
    are produced from the resolved set. Only when *none* resolve is an error
    returned, so a single typo never sinks the whole request.

    Args:
        payload: The request body (titles, count, exclude_seen).
        recommender: The injected hybrid recommender.

    Returns:
        A :class:`~schemas.RecommendResponse`.

    Raises:
        HTTPException: ``400`` if no non-blank titles are supplied; ``422`` if
            none of the supplied titles match the catalog.
    """
    titles = [t.strip() for t in payload.titles if t and t.strip()]
    if not titles:
        raise HTTPException(status_code=400, detail="At least one title is required.")

    resolved = recommender.resolve(titles)
    if not resolved.indices:
        raise HTTPException(
            status_code=422,
            detail=f"None of the provided titles matched the catalog: {resolved.unknown}",
        )

    # A signed-in user's saved services override the request's provider list.
    selected = user_provider_ids(db, user) or payload.providers
    # The hard filter drops off-service titles after ranking, so over-fetch.
    fetch = payload.count * ONLY_FILTER_OVERFETCH if payload.provider_filter == "only" else payload.count

    response = recommender.recommend(
        seed_indices=resolved.indices,
        count=fetch,
        exclude_seen=payload.exclude_seen,
        exclude_ids=payload.exclude_ids,
    )
    response.recommendations = index.apply_filter(
        response.recommendations, payload.provider_filter, selected, payload.count
    )
    return response
