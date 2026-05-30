"""``GET /search`` — autocomplete over the local catalog (SQLite).

Substring matches are pulled with SQL; if there are too few, a conservative
fuzzy pass (``difflib``) fills the rest so minor typos still surface results.
When a ``TMDB_API_KEY`` is configured the local results can be augmented with a
live TMDB search, but the local index always works offline.
"""

from __future__ import annotations

import difflib

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.database import Movie, get_db
from ml.artifacts import normalize_title
from schemas import MediaType, SearchResponse, SearchResult, SearchType

router = APIRouter(tags=["search"])


def _to_result(movie: Movie) -> SearchResult:
    """Map a :class:`~db.database.Movie` row to a :class:`~schemas.SearchResult`."""
    media_type: MediaType = movie.type if movie.type in ("movie", "tv") else "movie"
    return SearchResult(
        tmdb_id=movie.tmdb_id,
        title=movie.title,
        year=movie.year,
        type=media_type,
        poster_url=movie.poster_url,
    )


def _rank_key(movie: Movie, q_norm: str):
    """Sort key: exact, then prefix, then shorter titles, then alphabetical."""
    title_norm = normalize_title(movie.title)
    return (
        title_norm != q_norm,          # exact match first
        not title_norm.startswith(q_norm),  # then prefix matches
        len(title_norm),               # then shorter titles
        title_norm,
    )


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., description="Search query (title fragment)."),
    type: SearchType = Query("all", description="Filter by media type."),
    limit: int = Query(8, ge=1, le=25),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """Return up to ``limit`` autocomplete matches for ``q``.

    Args:
        q: The query string. Empty/blank queries return ``400``.
        type: ``movie``, ``tv`` or ``all``.
        limit: Maximum number of results.
        db: Injected database session.

    Returns:
        A :class:`~schemas.SearchResponse`.

    Raises:
        HTTPException: ``400`` if the query is empty.
    """
    q_norm = normalize_title(q)
    if not q_norm:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    base = select(Movie)
    if type != "all":
        base = base.where(Movie.type == type)

    # 1) Substring matches via SQL.
    matches = list(db.scalars(base.where(Movie.title_norm.like(f"%{q_norm}%"))).all())
    matches.sort(key=lambda m: _rank_key(m, q_norm))

    # 2) Fuzzy fallback if substring matching did not fill the page.
    if len(matches) < limit:
        seen_ids = {m.idx for m in matches}
        candidates = list(db.scalars(base).all())
        by_norm = {normalize_title(m.title): m for m in candidates}
        close = difflib.get_close_matches(q_norm, list(by_norm), n=limit, cutoff=0.6)
        for key in close:
            movie = by_norm[key]
            if movie.idx not in seen_ids:
                matches.append(movie)
                seen_ids.add(movie.idx)

    return SearchResponse(results=[_to_result(m) for m in matches[:limit]])
