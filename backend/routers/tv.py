"""``GET /tv`` — the popularity-ranked television deck.

The trained recommender is movies-only (MovieLens has no TV), so TV is a
separate, self-contained catalog with no ML model behind it: the popular series
built keylessly by ``data.build_tv`` and loaded onto ``app.state.tv_catalog`` at
startup. This endpoint serves them in their stored popularity order, returning
the same :class:`~schemas.RecommendResponse` shape as ``/popular`` so the
frontend deck can consume it without any special-casing.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from auth.deps import get_optional_user
from db.database import User, get_db
from dependencies import get_provider_index
from providers import ONLY_FILTER_OVERFETCH, ProviderIndex
from routers.popular import _parse_exclude
from routers.providers import user_provider_ids
from schemas import PopularRequest, Recommendation, RecommendResponse, TasteProfile

router = APIRouter(tags=["tv"])


def _era_label(years: list[int]) -> str:
    """Return the dominant decade label (e.g. ``"2010s"``) for a set of years."""
    if not years:
        return "mixed"
    decade, _ = Counter((y // 10) * 10 for y in years).most_common(1)[0]
    return f"{decade}s"


def _tv_deck(request: Request, count: int, exclude_ids: list[int]) -> RecommendResponse:
    """Build the popularity-ranked TV deck, excluding ``exclude_ids``."""
    catalog: list[dict] = getattr(request.app.state, "tv_catalog", None) or []
    excluded = set(exclude_ids)
    chosen = [r for r in catalog if r["id"] not in excluded][:count]

    recs = [
        Recommendation(
            id=r["id"],
            title=r["title"],
            year=r.get("year"),
            type="tv",
            score=round(min(0.95, 0.70 + 0.02 * i), 2),
            genres=r.get("genres", []),
            cast=r.get("cast", []),
            overview=r.get("overview", ""),
            poster_url=r.get("poster_url"),
            tmdb_id=r.get("tmdb_id"),
            trailer_key=r.get("trailer_key"),
            why="Popular series right now.",
        )
        for i, r in enumerate(chosen)
    ]
    genres = Counter(g for r in chosen for g in r.get("genres", []))
    return RecommendResponse(
        recommendations=recs,
        taste_profile=TasteProfile(
            top_genres=[g for g, _ in genres.most_common(3)],
            mood_tags=[],
            era_bias=_era_label([r["year"] for r in chosen if r.get("year")]),
        ),
    )


@router.get("/tv", response_model=RecommendResponse)
def tv(
    request: Request,
    count: int = Query(20, ge=1, le=60),
    exclude: str | None = Query(None, description="TV ids already shown (kept out of the result)."),
) -> RecommendResponse:
    """Return a popularity-ranked deck of television series (query-string exclude).

    Args:
        request: The request (carries the loaded TV catalog on ``app.state``).
        count: Number of cards to return.
        exclude: Comma-separated TV ids already shown.

    Returns:
        A :class:`~schemas.RecommendResponse`.
    """
    return _tv_deck(request, count, _parse_exclude(exclude))


@router.post("/tv", response_model=RecommendResponse)
def tv_post(
    request: Request,
    payload: PopularRequest,
    index: ProviderIndex = Depends(get_provider_index),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> RecommendResponse:
    """Same as ``GET /tv`` but takes the exclude list in the body (so the shared,
    ever-growing "seen" set never bumps into URL-length limits) and honors the
    streaming-service filter."""
    selected = user_provider_ids(db, user) or payload.providers
    fetch = payload.count * ONLY_FILTER_OVERFETCH if payload.provider_filter == "only" else payload.count
    response = _tv_deck(request, fetch, payload.exclude_ids)
    response.recommendations = index.apply_filter(
        response.recommendations, payload.provider_filter, selected, payload.count
    )
    return response
