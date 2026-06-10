"""``GET /recommendations/personal`` — the "For You" page.

Builds seeds from **everything known about the caller** — saved likes, the
swipe log, imported Letterboxd ratings — and returns ranked shelves:

* ``Because you liked <title>`` (hybrid, one shelf per top seed),
* ``Loved by viewers like you`` (pure collaborative signal),
* ``On your services`` (hard-filtered to the user's streaming services).

Anonymous callers get the same shelves from client-supplied seed titles (their
local session likes) plus a sign-in nudge; with no seeds at all the page falls
back to the popular deck. Already-seen titles never appear, and a title is
never repeated across shelves.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_optional_user
from db.database import ExternalRating, Movie, SwipeEvent, User, UserSavedTitle, get_db
from dependencies import get_provider_index, get_recommender
from ml.recommender import HybridRecommender
from providers import ProviderIndex
from routers.providers import user_provider_ids
from schemas import PersonalResponse, PersonalSection, Recommendation

router = APIRouter(tags=["personal"])

_SECTION_SIZE = 10
_MAX_SEEDS = 12
_MAX_BECAUSE_SHELVES = 3
# Ranked lists shrink under the seen-exclusions + provider filter; over-fetch.
_OVERFETCH = 5


def _account_seed_titles(db: Session, user: User) -> list[str]:
    """Seed titles from the account: saved likes, high Letterboxd ratings, and
    recent liked swipes — newest first, deduped, capped."""
    titles: list[str] = []

    liked_rows = db.scalars(
        select(UserSavedTitle)
        .where(UserSavedTitle.user_id == user.id, UserSavedTitle.kind == "liked")
        .order_by(UserSavedTitle.id.desc())
    ).all()
    for row in liked_rows:
        if row.rec_json and row.rec_json.get("type") == "movie":
            titles.append(row.rec_json["title"])

    lb_rows = db.scalars(
        select(ExternalRating)
        .where(
            ExternalRating.user_id == user.id,
            ExternalRating.movie_id.is_not(None),
            ExternalRating.rating >= 3.5,
        )
        .order_by(ExternalRating.id.desc())
    ).all()
    titles.extend(row.title for row in lb_rows)

    swipe_tmdb = db.scalars(
        select(SwipeEvent.tmdb_id)
        .where(SwipeEvent.user_id == user.id, SwipeEvent.action.in_(("liked", "superliked")))
        .order_by(SwipeEvent.id.desc())
        .limit(_MAX_SEEDS)
    ).all()
    if swipe_tmdb:
        movies = db.scalars(select(Movie).where(Movie.tmdb_id.in_(swipe_tmdb), Movie.type == "movie")).all()
        titles.extend(m.title for m in movies)

    deduped: list[str] = []
    seen = set()
    for title in titles:
        key = title.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(title)
    return deduped[:_MAX_SEEDS]


def _account_seen_ids(db: Session, user: User) -> set[int]:
    """Every movie_id the account has interacted with (never re-recommended)."""
    return set(db.scalars(select(UserSavedTitle.movie_id).where(UserSavedTitle.user_id == user.id)))


def _parse_csv_ints(raw: str) -> list[int]:
    return [int(p) for p in raw.split(",") if p.strip().lstrip("-").isdigit()]


@router.get("/recommendations/personal", response_model=PersonalResponse)
def personal(
    seeds: str = Query("", description="Anonymous fallback: comma-separated liked titles from the session."),
    provider_filter: str = Query("all", pattern="^(all|only|prefer)$"),
    providers: str = Query("", description="Anonymous fallback: comma-separated provider ids."),
    recommender: HybridRecommender = Depends(get_recommender),
    index: ProviderIndex = Depends(get_provider_index),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> PersonalResponse:
    """Build the personalized shelves (see module docstring)."""
    if user is not None:
        seed_titles = _account_seed_titles(db, user)
        used: set[int] = _account_seen_ids(db, user)
        selected = user_provider_ids(db, user) or _parse_csv_ints(providers)
    else:
        seed_titles = [t.strip() for t in seeds.split(",") if t.strip()][:_MAX_SEEDS]
        used = set()
        selected = _parse_csv_ints(providers)

    resolved = recommender.resolve(seed_titles)
    sections: list[PersonalSection] = []

    def shelf(key: str, title: str, recs: list[Recommendation], mode: str) -> None:
        """Drop used titles, apply the provider filter, record + append."""
        fresh = [r for r in recs if r.id not in used]
        fresh = index.apply_filter(fresh, mode, selected, _SECTION_SIZE)
        if fresh:
            used.update(r.id for r in fresh)
            sections.append(PersonalSection(key=key, title=title, items=fresh))

    # 1. One shelf per top seed — "Because you liked X".
    for idx, matched_title in list(zip(resolved.indices, resolved.matched))[:_MAX_BECAUSE_SHELVES]:
        res = recommender.recommend(
            [idx], count=_SECTION_SIZE * _OVERFETCH, exclude_ids=list(used), exclude_seen=True
        )
        display = recommender.catalog()[idx].title  # canonical title, not the raw input
        shelf(f"because_you_liked:{idx}", f"Because you liked {display}", res.recommendations, provider_filter)

    # 2. Pure collaborative signal over every seed — "viewers like you".
    if resolved.indices:
        res = recommender.recommend(
            resolved.indices,
            count=_SECTION_SIZE * _OVERFETCH,
            exclude_ids=list(used),
            exclude_seen=True,
            weights=(1.0, 0.0, 0.0),
        )
        shelf("similar_users", "Loved by viewers like you", res.recommendations, provider_filter)

    # 3. Hard-filtered to the user's services (only when that adds information).
    if resolved.indices and selected and index.has_data and provider_filter != "only":
        res = recommender.recommend(
            resolved.indices, count=_SECTION_SIZE * _OVERFETCH, exclude_ids=list(used), exclude_seen=True
        )
        shelf("on_your_services", "On your services", res.recommendations, "only")

    # Fallback: nothing known about the caller yet → popular titles.
    if not sections:
        from routers.popular import _popular_deck

        res = _popular_deck(_SECTION_SIZE * _OVERFETCH, list(used), recommender, db)
        shelf("popular", "Popular right now", res.recommendations, provider_filter)

    return PersonalResponse(
        sections=sections,
        seeded_by=[recommender.catalog()[i].title for i in resolved.indices],
        signed_in=user is not None,
    )
