"""``GET /popular`` — the seedless cold-start deck.

Ranks the catalog by what the crowd has been swiping on (weighted ``swipe_events``
counts), falling back to catalog order when there is no signal yet. This powers
the landing deck and any refill before the user has liked anything.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.database import SwipeEvent, get_db
from dependencies import get_recommender
from ml.recommender import HybridRecommender
from schemas import RecommendResponse

router = APIRouter(tags=["popular"])

# How much each action contributes to a title's popularity.
_ACTION_WEIGHT = {"liked": 1.0, "saved": 0.7, "skip": -0.2, "dismissed": -0.5}


def _parse_exclude(exclude: str | None) -> list[int]:
    """Parse a comma-separated id list, ignoring junk."""
    if not exclude:
        return []
    out: list[int] = []
    for part in exclude.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


@router.get("/popular", response_model=RecommendResponse)
def popular(
    count: int = Query(20, ge=1, le=60),
    exclude: str | None = Query(None, description="Comma-separated recommendation ids (movie_id) to skip."),
    recommender: HybridRecommender = Depends(get_recommender),
    db: Session = Depends(get_db),
) -> RecommendResponse:
    """Return a popularity-ranked deck.

    Args:
        count: Number of cards to return.
        exclude: TMDB ids already shown (kept out of the result).
        recommender: Injected recommender (owns the catalog).
        db: Injected database session (holds the swipe log).

    Returns:
        A :class:`~schemas.RecommendResponse`.
    """
    rows = db.execute(
        select(SwipeEvent.tmdb_id, SwipeEvent.action, func.count())
        .group_by(SwipeEvent.tmdb_id, SwipeEvent.action)
    ).all()
    popularity: dict[int, float] = {}
    for tmdb_id, action, n in rows:
        popularity[tmdb_id] = popularity.get(tmdb_id, 0.0) + _ACTION_WEIGHT.get(action, 0.0) * n

    return recommender.popular(
        popularity=popularity,
        count=count,
        exclude_ids=_parse_exclude(exclude),
    )
