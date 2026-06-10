"""Pydantic v2 request/response models — the typed API contract.

These models are the single source of truth for the shapes documented in the
README and consumed by the frontend's ``lib/api.ts``. FastAPI uses them to
validate inputs and to generate the OpenAPI schema served at ``/docs``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# A title is either a film or a show. ``all`` is a search-only filter meaning
# "either kind".
MediaType = Literal["movie", "tv"]
SearchType = Literal["movie", "tv", "all"]

# The four swipe directions plus the double-tap "super like", stored verbatim
# in ``swipe_events``.
SwipeAction = Literal["liked", "saved", "dismissed", "skip", "superliked"]

# Deck filtering by the user's streaming services: show everything, only titles
# on their services (hard filter), or float their services up (soft boost).
ProviderFilter = Literal["all", "only", "prefer"]


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
    count: int = Field(default=10, ge=1, le=60)
    exclude_seen: bool = True
    exclude_ids: list[int] = Field(
        default_factory=list,
        description="Recommendation ids already shown — never returned again (keeps the endless deck unique).",
    )
    provider_filter: ProviderFilter = Field(
        default="all", description="Filter/boost the deck by the user's streaming services."
    )
    providers: list[int] = Field(
        default_factory=list,
        description="The caller's provider ids (anonymous users). Signed-in users' saved services take precedence.",
    )


class Recommendation(BaseModel):
    """A single ranked recommendation."""

    id: int = Field(description="Stable unique id (MovieLens movie_id) — used to de-duplicate the deck.")
    title: str
    year: int | None
    type: MediaType
    score: float = Field(ge=0.0, le=1.0, description="Blended hybrid confidence in [0, 1].")
    genres: list[str]
    cast: list[str] = Field(default_factory=list, description="Top-billed cast.")
    overview: str = Field(default="", description="One- or two-sentence synopsis.")
    poster_url: str | None
    tmdb_id: int | None
    trailer_key: str | None = Field(
        default=None,
        description="YouTube video id for the trailer, baked in keylessly — lets the client play it in-page with no API key.",
    )
    providers: list[int] = Field(
        default_factory=list,
        description="Canonical streaming-provider ids carrying this title (empty when availability is unknown).",
    )
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


class PopularRequest(BaseModel):
    """Body for ``POST /popular`` and ``POST /tv``.

    The endless deck's "already seen" set grows without bound over a long
    session; sending it in a POST body (rather than a ``GET`` query string)
    keeps the request well clear of URL-length limits.

    Attributes:
        count: Number of cards to return.
        exclude_ids: Recommendation ids (``movie_id`` / TV id) already shown —
            kept out of the deck so a card is never served twice.
    """

    count: int = Field(default=20, ge=1, le=60)
    exclude_ids: list[int] = Field(default_factory=list)
    provider_filter: ProviderFilter = "all"
    providers: list[int] = Field(default_factory=list)


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
    provider_filter: ProviderFilter = Field(
        default="all",
        description='Deck filter in effect. With "prefer", the re-rank softly boosts on-service titles.',
    )
    providers: list[int] = Field(default_factory=list)


class SwipeResponse(BaseModel):
    """Response body for ``POST /swipe``."""

    reranked_queue: list[int] = Field(description="Remaining TMDB ids in updated order.")
    session_confidence: float = Field(ge=0.0, le=1.0, description="How much signal the session carries (0–1).")
    applied: bool = Field(description="Whether the swipe affected the session vector.")


# --------------------------------------------------------------------------- #
# /trailer
# --------------------------------------------------------------------------- #
class TrailerResponse(BaseModel):
    """Response body for ``GET /trailer/{tmdb_id}``.

    Attributes:
        youtube_key: The YouTube video id to embed and play in-page, or ``None``
            when no trailer could be resolved (keyless deploy, network error, or
            the title simply has no trailer on TMDB).
        name: The trailer's display name, when known.
        source: Why we got (or didn't get) a key — useful for the client's
            fallback messaging and for debugging a deployment's TMDB setup.
    """

    youtube_key: str | None = None
    name: str | None = None
    source: Literal["tmdb", "youtube", "none", "unconfigured", "error"] = "none"


# --------------------------------------------------------------------------- #
# /auth  +  /account  (Phase 3 — accounts, history, cross-session taste)
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    """Body for ``POST /auth/register`` (email/password sign-up)."""

    email: str = Field(min_length=3, max_length=320)
    # Capped at 72 chars because bcrypt only hashes the first 72 bytes.
    password: str = Field(min_length=8, max_length=72)
    display_name: str | None = Field(default=None, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        """Lowercase/trim and require an ``@`` (keeps a real email-validator
        dependency out of the runtime image)."""
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("A valid email address is required.")
        return value


class LoginRequest(BaseModel):
    """Body for ``POST /auth/login``."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserOut(BaseModel):
    """Public view of an account — what ``/auth/me`` and login/register return."""

    id: int
    email: str
    display_name: str | None = None
    email_verified: bool = False
    onboarding_completed: bool = False


class PasswordResetRequest(BaseModel):
    """Body for ``POST /auth/request-password-reset``."""

    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class PasswordResetConfirm(BaseModel):
    """Body for ``POST /auth/reset-password``."""

    token: str = Field(min_length=1)
    # Same bcrypt-driven cap as registration.
    new_password: str = Field(min_length=8, max_length=72)


class VerifyEmailRequest(BaseModel):
    """Body for ``POST /auth/verify-email``."""

    token: str = Field(min_length=1)


class HistoryResponse(BaseModel):
    """A user's saved state, used to hydrate the SPA on sign-in."""

    liked: list[Recommendation] = Field(default_factory=list)
    wishlist: list[Recommendation] = Field(default_factory=list)
    seen: list[int] = Field(default_factory=list, description="movie_ids ever shown.")


class MergeRequest(BaseModel):
    """Guest localStorage state POSTed to ``/account/merge`` on first sign-in.

    Upserted into the account (deduped) so a user who built a watchlist before
    creating an account keeps it.
    """

    liked: list[Recommendation] = Field(default_factory=list)
    wishlist: list[Recommendation] = Field(default_factory=list)
    seen: list[int] = Field(default_factory=list)


class SaveTitleRequest(BaseModel):
    """A single liked/watch-listed card POSTed to ``/account/saved`` while signed
    in, so the server copy stays current without a full merge. The full
    ``Recommendation`` is sent because the watchlist renders the card verbatim.
    """

    rec: Recommendation
    kind: Literal["liked", "wishlist"]


# --------------------------------------------------------------------------- #
# /recommendations/personal  (the "For You" page)
# --------------------------------------------------------------------------- #
class PersonalSection(BaseModel):
    """One ranked shelf on the For You page."""

    key: str = Field(description='Stable section id ("because_you_liked", "similar_users", "on_your_services", "popular").')
    title: str = Field(description="Display heading.")
    items: list[Recommendation]


class PersonalResponse(BaseModel):
    """Response for ``GET /recommendations/personal``."""

    sections: list[PersonalSection]
    seeded_by: list[str] = Field(
        default_factory=list, description="The titles the recommendations were built from."
    )
    signed_in: bool = Field(description="False → the UI shows a sign-in nudge (session-only seeds).")


# --------------------------------------------------------------------------- #
# /account/letterboxd
# --------------------------------------------------------------------------- #
class LetterboxdSyncRequest(BaseModel):
    """Body for ``POST /account/letterboxd/sync`` (public RSS import)."""

    username: str = Field(min_length=2, max_length=32)

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        return value.strip().lstrip("@").lower()


class LetterboxdSummary(BaseModel):
    """Outcome of an import: what landed in the account."""

    total: int = Field(description="Films parsed from the feed/export.")
    matched: int = Field(description="Films matched to the catalog.")
    liked: int = Field(description="Newly added likes (rated ≥ 3.5★).")
    seen: int = Field(description="Newly added seen-set entries.")
    unmatched: list[str] = Field(default_factory=list, description="Titles that didn't match (first 50).")


class LetterboxdStatus(BaseModel):
    """``GET /account/letterboxd`` — connection state for the settings UI."""

    username: str | None = None
    imported: int = Field(default=0, description="Total external ratings stored.")
    matched: int = Field(default=0, description="How many matched the catalog.")


# --------------------------------------------------------------------------- #
# /providers  (streaming services)
# --------------------------------------------------------------------------- #
class ProviderInfo(BaseModel):
    """One selectable streaming service."""

    id: int = Field(description="Canonical TMDB watch-provider id.")
    slug: str
    name: str
    color: str = Field(description="Brand color for UI chips.")


class ProvidersResponse(BaseModel):
    """Response for ``GET /providers`` — the selectable services + data status."""

    providers: list[ProviderInfo]
    availability_loaded: bool = Field(
        description="Whether per-title availability data is loaded (filters are no-ops when false)."
    )
    region: str = "US"


class UserProvidersResponse(BaseModel):
    """The signed-in user's saved services (``GET /account/providers``)."""

    providers: list[int] = Field(default_factory=list)
    onboarding_completed: bool = False


class UserProvidersUpdate(BaseModel):
    """Body for ``PUT /account/providers``."""

    providers: list[int] = Field(default_factory=list, max_length=32)
    # Saving (or skipping) the onboarding screen marks it done; edits from the
    # account menu leave it true.
    complete: bool = True


# --------------------------------------------------------------------------- #
# /health
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    """Response body for ``GET /health``."""

    status: Literal["ok", "degraded"]
    model_loaded: bool
    index_size: int
