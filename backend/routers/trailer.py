"""``GET /trailer/{tmdb_id}`` — resolve a title's YouTube trailer key via TMDB.

The frontend embeds the returned key in an in-page player so the trailer plays
inside NextWatch instead of navigating the user away to youtube.com.

This needs a ``TMDB_API_KEY`` (the same key that powers posters + cast). Without
one — or when a title has no trailer — the endpoint returns ``youtube_key=None``
and ``source`` explains why; the client then degrades to an explicit "open on
YouTube" link rather than ever auto-navigating.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Query

from config import get_settings
from schemas import MediaType, TrailerResponse

router = APIRouter(tags=["trailer"])

# TMDB ``videos`` results, ranked best-first: official trailers, then any
# trailer, then teasers, then anything else hosted on YouTube.
_TYPE_RANK = {"Trailer": 0, "Teaser": 1, "Clip": 2, "Featurette": 3}


def _best_trailer(videos: list[dict]) -> dict | None:
    """Pick the most trailer-like YouTube video from a TMDB ``videos`` list."""
    youtube = [v for v in videos if v.get("site") == "YouTube" and v.get("key")]
    if not youtube:
        return None

    def rank(v: dict) -> tuple:
        return (
            _TYPE_RANK.get(v.get("type", ""), 9),  # trailers before teasers/clips
            not v.get("official", False),          # official before fan uploads
        )

    return min(youtube, key=rank)


@router.get("/trailer/{tmdb_id}", response_model=TrailerResponse)
def trailer(
    tmdb_id: int,
    type: MediaType = Query("movie", description="Whether the id is a movie or a TV show."),
) -> TrailerResponse:
    """Return the YouTube key of the best available trailer for ``tmdb_id``.

    Args:
        tmdb_id: TMDB id of the title.
        type: ``"movie"`` or ``"tv"`` — selects the TMDB endpoint.

    Returns:
        A :class:`~schemas.TrailerResponse`. ``youtube_key`` is ``None`` (never a
        500) when TMDB is not configured, the request fails, or no trailer
        exists, so the client can always degrade gracefully.
    """
    settings = get_settings()
    if not settings.tmdb_api_key:
        return TrailerResponse(source="unconfigured")

    endpoint = "tv" if type == "tv" else "movie"
    url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/videos"
    try:
        with httpx.Client(timeout=8) as client:
            resp = client.get(url, params={"api_key": settings.tmdb_api_key})
            resp.raise_for_status()
            videos = resp.json().get("results", [])
    except (httpx.HTTPError, ValueError):
        return TrailerResponse(source="error")

    best = _best_trailer(videos)
    if not best:
        return TrailerResponse(source="none")
    return TrailerResponse(youtube_key=best["key"], name=best.get("name"), source="tmdb")
