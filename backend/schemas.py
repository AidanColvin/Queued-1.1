"""Pydantic v2 request/response models — the typed API contract.

These models are the single source of truth for the shapes documented in the
README and consumed by the frontend's ``lib/api.ts``. FastAPI uses them to
validate inputs and to generate the OpenAPI schema served at ``/docs``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# A title is either a film or a show. ``all`` is a search-only filter meaning
# "either kind".
MediaType = Literal["movie", "tv"]
SearchType = Literal["movie", "tv", "all"]

# The four swipe directions, stored verbatim in ``swipe_events``.
SwipeAction = Literal["liked", "saved", "dismissed", "skip"]


# --------------------------------------------------------------------------- #
# /recommend
# --------------------------------------------------------------------------- #
class RecommendRequest(BaseModel):
    """Payload for ``POST /recommend``.

    Attributes:
        titles: Seed titles the user has liked. Must contain at least one entry
            (enforced in the route so the error is a clean ``400``).
        count: Number of recommendations to return (1–50).
        exclude_seen: When true, the seed titles are removed from the results.
    """

    titles: list[str] = Field(default_factory=list, examples=[["The Wire", "Severance"]])
    count: int = Field(default=10, ge=1, le=50)
    exclude_seen: bool = True


class Recommendation(BaseModel):
    """A single ranked recommendation."""

    title: str
    year: int | None
    type: MediaType
    score: float = Field(ge=0.0, le=1.0, description="Blended hybrid confidence in [0, 1].")
    genres: list[str]
    poster_url: str | None
    tmdb_id: int | None
    why: str = Field(description="Human-readable explanation of why this title was matched.")


class TasteProfile(BaseModel):
    """Aggregate read of the seed titles."""

    top_genres: list[str]
    mood_tags: list[str]
    era_bias: str


class RecommendResponse(BaseModel):
    """Response body for ``POST /recommend``."""

    recommendations: list[Recommendation]
    taste_profile: TasteProfile


# --------------------------------------------------------------------------- #
# /search
# --------------------------------------------------------------------------- #
class SearchResult(BaseModel):
    """A single autocomplete match."""

    tmdb_id: int | None
    title: str
    year: int | None
    type: MediaType
    poster_url: str | None


class SearchResponse(BaseModel):
    """Response body for ``GET /search``."""

    results: list[SearchResult]


# --------------------------------------------------------------------------- #
# /swipe  (Layer 1 adaptive re-ranking)
# --------------------------------------------------------------------------- #
class SwipeRequest(BaseModel):
    """Payload for ``POST /swipe``.

    Attributes:
        session_id: Opaque, anonymous session key (the frontend generates it).
        tmdb_id: TMDB id of the card that was swiped.
        action: The swipe direction.
        time_on_card_ms: Deliberation time, measured client-side — the backend
            cannot compute it. Used as a hesitation signal for negatives.
        remaining: The deck's still-pending TMDB ids. The frontend owns the
            deck, so it sends what is left and receives it re-ordered; this
            keeps the server free of per-deck state.
    """

    session_id: str = Field(min_length=1)
    tmdb_id: int
    action: SwipeAction
    time_on_card_ms: int = Field(default=0, ge=0)
    remaining: list[int] = Field(default_factory=list)


class SwipeResponse(BaseModel):
    """Response body for ``POST /swipe``."""

    reranked_queue: list[int] = Field(description="Remaining TMDB ids in updated order.")
    session_confidence: float = Field(ge=0.0, le=1.0, description="How much signal the session carries (0–1).")
    applied: bool = Field(description="Whether the swipe affected the session vector.")


# --------------------------------------------------------------------------- #
# /health
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    """Response body for ``GET /health``."""

    status: Literal["ok", "degraded"]
    model_loaded: bool
    index_size: int
