"""``POST /recommend/adaptive`` — the taste-driven movie deck.

Unlike ``/popular`` (crowd ranking) and ``/recommend`` (ranks from seed *titles*),
this generates fresh candidates from the visitor's accumulated **taste vector** —
the same vector the swipe reranker builds, which encodes everything they've liked
AND disliked and lives in the hybrid CF+semantic space. So the deck predicts new,
unique titles that fit the user (and, via the CF half, what similar users liked),
and a dislike immediately steers what's fetched next — not just the on-screen order.

Falls back to the popularity deck when there isn't enough signal yet (a brand-new
visitor), so the first load still works. Seen ids are excluded so cards never repeat.
"""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth.deps import get_optional_user
from db.database import AnonSessionProfile, User, UserProfile, get_db
from dependencies import get_provider_index, get_recommender
from ml.recommender import HybridRecommender
from providers import ONLY_FILTER_OVERFETCH, ProviderIndex
from routers.popular import _popular_deck
from routers.providers import user_provider_ids
from schemas import AdaptiveRequest, RecommendResponse

router = APIRouter(tags=["recommend"])

# Minimum session confidence before taste-driven candidates kick in. Low on
# purpose: ~one like or ~two dislikes is enough to start personalizing, so the
# deck visibly adapts within the first few swipes. (Reranker weights add ~0.1
# confidence per like, ~0.055 per dislike.)
ADAPTIVE_MIN_CONFIDENCE = 0.1


def _load_taste(db: Session, user: User | None, session_id: str) -> tuple[list | None, float]:
    """Return (taste_vector, confidence) for the signed-in user or anon session."""
    if user is not None:
        profile = db.get(UserProfile, user.id)
        return (profile.taste_vector, profile.confidence) if profile else (None, 0.0)
    if session_id:
        state = db.get(AnonSessionProfile, session_id)
        return (state.taste_vector, state.confidence) if state else (None, 0.0)
    return (None, 0.0)


@router.post("/recommend/adaptive", response_model=RecommendResponse)
def adaptive(
    payload: AdaptiveRequest,
    recommender: HybridRecommender = Depends(get_recommender),
    index: ProviderIndex = Depends(get_provider_index),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> RecommendResponse:
    """Return taste-ranked candidates (or the popular deck if there's no signal yet)."""
    vector, confidence = _load_taste(db, user, payload.session_id)
    # Over-fetch for a hard "only my services" filter so enough survive it.
    fetch = payload.count * ONLY_FILTER_OVERFETCH if payload.provider_filter == "only" else payload.count

    response: RecommendResponse | None = None
    if vector and confidence >= ADAPTIVE_MIN_CONFIDENCE:
        response = recommender.recommend_by_taste(
            np.asarray(vector, dtype=np.float32), count=fetch, exclude_ids=payload.exclude_ids
        )
    # No signal / stale vector / drained → crowd-popularity fallback.
    if response is None or not response.recommendations:
        response = _popular_deck(fetch, payload.exclude_ids, recommender, db)

    selected = user_provider_ids(db, user) or payload.providers
    response.recommendations = index.apply_filter(
        response.recommendations, payload.provider_filter, selected, payload.count
    )
    return response
