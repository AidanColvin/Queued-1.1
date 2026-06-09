"""``GET /trailer/{tmdb_id}`` — resolve a title's YouTube trailer key.

The frontend embeds the returned key in an in-page player so the trailer plays
inside NextWatch instead of navigating the user away to youtube.com.

Resolution order:
1. **TMDB** ``videos`` when a ``TMDB_API_KEY`` is configured (most precise —
   official/marked trailers).
2. **Keyless YouTube search** fallback: when TMDB is unconfigured or has no
   trailer, scrape the first result for ``"<title> <year> trailer"`` directly
   from YouTube's search page. This needs no API key, so trailers play in-app
   even on the keyless deploy. The client passes ``title``/``year`` for this.

If neither resolves a key the endpoint returns ``youtube_key=None`` and
``source`` explains why; the client then degrades to an explicit "open on
YouTube" link rather than ever auto-navigating.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query

from config import get_settings
from schemas import MediaType, TrailerResponse

# Imported defensively: this router must never break app startup if the slim
# serverless runtime is missing httpx — the endpoint just degrades to an error
# response and every other route keeps working.
try:
    import httpx
except ImportError:  # pragma: no cover - httpx is a declared runtime dependency
    httpx = None  # type: ignore[assignment]

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


# Matches the 11-char YouTube video ids embedded throughout the search-results
# HTML (``"videoId":"dQw4w9WgXcQ"``); the first hit is the top search result.
_VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')

# MovieLens stores titles article-last ("Incredibles, The", "Matrix, The").
_ARTICLE_LAST_RE = re.compile(r"^(.*),\s+(the|a|an)$", re.IGNORECASE)


def _search_title(title: str) -> str:
    """Restore natural word order so the query reads like a real title.

    "Incredibles, The" → "The Incredibles" — without this the trailing article
    skews YouTube's results toward unrelated clips.
    """
    match = _ARTICLE_LAST_RE.match(title.strip())
    return f"{match.group(2)} {match.group(1)}" if match else title.strip()


# Per-result title in the search JSON: ``"title":{"runs":[{"text":"…"}``.
_RESULT_TITLE_RE = re.compile(r'"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"')

# Auto-generated promo clips (notably Peacock's "PKTV ……") rank high but aren't
# trailers — skip them in favour of a result whose title actually says trailer.
_JUNK_MARKERS = ("peacock", "pktv ")


def _looks_like_trailer(name: str) -> bool:
    low = name.lower()
    return "trailer" in low and not any(m in low for m in _JUNK_MARKERS)


def _youtube_search_key(title: str, year: int | None) -> str | None:
    """Resolve a trailer's YouTube id by scraping YouTube search — no API key.

    Fetches the results page for ``"<title> <year> official trailer"`` and walks
    the results, returning the first whose own title actually reads like a
    trailer (skipping auto-generated promo clips that otherwise rank first), and
    falling back to the very first result if none clearly match. ``hl``/``gl`` +
    a consent cookie and browser UA keep YouTube from serving a consent
    interstitial to server IPs. Returns ``None`` on any failure so the caller
    degrades gracefully.
    """
    if httpx is None:
        return None
    name = _search_title(title)
    query = f"{name} {year} official trailer" if year else f"{name} official trailer"
    try:
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            resp = client.get(
                "https://www.youtube.com/results",
                params={"search_query": query, "hl": "en", "gl": "US"},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                },
                cookies={"CONSENT": "YES+1"},
            )
            resp.raise_for_status()
    except httpx.HTTPError:
        return None

    # Each video result is a ``videoRenderer`` carrying its id and title; pick the
    # first whose title looks like a real trailer, else the top result.
    first_id: str | None = None
    for chunk in resp.text.split('"videoRenderer"')[1:]:
        id_match = _VIDEO_ID_RE.search(chunk)
        if not id_match:
            continue
        video_id = id_match.group(1)
        if first_id is None:
            first_id = video_id
        title_match = _RESULT_TITLE_RE.search(chunk)
        if title_match and _looks_like_trailer(title_match.group(1)):
            return video_id
    return first_id


@router.get("/trailer/{tmdb_id}", response_model=TrailerResponse)
def trailer(
    tmdb_id: int,
    type: MediaType = Query("movie", description="Whether the id is a movie or a TV show."),
    title: str | None = Query(None, description="Title, used for the keyless YouTube-search fallback."),
    year: int | None = Query(None, description="Release year, sharpens the YouTube-search fallback."),
) -> TrailerResponse:
    """Return the YouTube key of the best available trailer for a title.

    Tries TMDB first (when a key is configured), then falls back to a keyless
    YouTube search by ``title``/``year`` so trailers still play in-app on the
    keyless deploy.

    Args:
        tmdb_id: TMDB id of the title (``0`` when unknown — only the YouTube
            fallback is used).
        type: ``"movie"`` or ``"tv"`` — selects the TMDB endpoint.
        title: Title for the keyless YouTube-search fallback.
        year: Release year, to disambiguate the search.

    Returns:
        A :class:`~schemas.TrailerResponse`. ``youtube_key`` is ``None`` (never a
        500) only when no source resolves a trailer, so the client can always
        degrade gracefully.
    """
    settings = get_settings()

    # 1) TMDB — most precise, when a key is configured and the id is real.
    if settings.tmdb_api_key and httpx is not None and tmdb_id > 0:
        endpoint = "tv" if type == "tv" else "movie"
        url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/videos"
        try:
            with httpx.Client(timeout=8) as client:
                resp = client.get(url, params={"api_key": settings.tmdb_api_key})
                resp.raise_for_status()
                videos = resp.json().get("results", [])
            best = _best_trailer(videos)
            if best:
                return TrailerResponse(youtube_key=best["key"], name=best.get("name"), source="tmdb")
        except (httpx.HTTPError, ValueError):
            pass  # fall through to the keyless search

    # 2) Keyless YouTube search — works with no API key as long as we have a title.
    if title:
        key = _youtube_search_key(title, year)
        if key:
            return TrailerResponse(youtube_key=key, name=f"{title} — trailer", source="youtube")

    if not settings.tmdb_api_key and not title:
        return TrailerResponse(source="unconfigured")
    return TrailerResponse(source="none")
