"""``POST /recommend`` — the hybrid recommendation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_recommender
from ml.recommender import HybridRecommender
from schemas import RecommendRequest, RecommendResponse

router = APIRouter(tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
def recommend(
    payload: RecommendRequest,
    recommender: HybridRecommender = Depends(get_recommender),
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

    return recommender.recommend(
        seed_indices=resolved.indices,
        count=payload.count,
        exclude_seen=payload.exclude_seen,
        exclude_ids=payload.exclude_ids,
    )
