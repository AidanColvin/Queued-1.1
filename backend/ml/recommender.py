"""Hybrid recommender: blends collaborative, content and semantic signals.

``hybrid_score = 0.45 * CF + 0.35 * content + 0.20 * semantic``

Each component returns a similarity vector over the whole catalog; the vectors
are rescaled to ``[0, 1]`` (cosines from ``[-1, 1]`` are mapped with
``(x + 1) / 2``), blended with the fixed weights, the seed titles are masked
out, and the top-N are returned with a generated explanation and an aggregate
taste profile.

The recommender is constructed once at startup from a loaded
:class:`~ml.artifacts.ArtifactBundle` and is read-only thereafter, so a single
instance is safely shared across requests.
"""

from __future__ import annotations

import difflib
from collections import Counter
from dataclasses import dataclass

import numpy as np

from ml.artifacts import ArtifactBundle, MovieRecord, normalize_title
from ml.collaborative import cf_scores
from ml.content import content_scores
from ml.embeddings import semantic_scores
from ml.reranker import POP_BETA, TASTE_SHRINK, popularity_prior
from schemas import Recommendation, RecommendResponse, TasteProfile

# Blend weights (must sum to 1.0). CF dominates because behavioral signal is the
# strongest predictor at MovieLens scale; semantic adds thematic diversity.
W_CF = 0.45
W_CONTENT = 0.35
W_SEMANTIC = 0.20

# Fuzzy-resolution cutoff for matching a free-text title to the catalog.
_RESOLVE_CUTOFF = 0.84


@dataclass(slots=True)
class ResolvedSeeds:
    """Outcome of mapping user titles to catalog rows."""

    indices: list[int]
    matched: list[str]
    unknown: list[str]


def _cosine_to_unit(scores: np.ndarray) -> np.ndarray:
    """Map cosine similarities in ``[-1, 1]`` to ``[0, 1]``."""
    return np.clip((scores + 1.0) / 2.0, 0.0, 1.0)


class HybridRecommender:
    """Read-only recommender over a single artifact bundle.

    Args:
        bundle: The loaded artifact bundle (catalog + aligned matrices).
    """

    def __init__(self, bundle: ArtifactBundle) -> None:
        self._bundle = bundle
        self._catalog: list[MovieRecord] = bundle.catalog
        # The hybrid CF+semantic item space the session reranker scores in,
        # attached at startup (see main.load_state). Lets us generate *new*
        # candidates directly from a user's live taste vector — not just reorder.
        self._taste_space: np.ndarray | None = None
        # Popularity prior blended into taste ranking (zeros for the sample
        # bundle, where it is a no-op). Same prior the session reranker uses.
        self._pop_prior = popularity_prior(self._catalog)
        # Lookup maps. Later entries do not overwrite earlier ones, so the first
        # occurrence of a normalized title wins (stable, order-preserving).
        self._by_title: dict[str, int] = {}
        for rec in self._catalog:
            self._by_title.setdefault(normalize_title(rec.title), rec.idx)
        self._titles_norm = list(self._by_title.keys())

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def size(self) -> int:
        """Number of titles in the index."""
        return self._bundle.size

    @property
    def source(self) -> str:
        """Provenance of the loaded bundle (``"sample"`` or a dataset name)."""
        return str(self._bundle.meta.get("source", "unknown"))

    def catalog(self) -> list[MovieRecord]:
        """Return the underlying catalog (read-only use)."""
        return self._catalog

    # ------------------------------------------------------------------ #
    # Resolution
    # ------------------------------------------------------------------ #
    def resolve(self, titles: list[str]) -> ResolvedSeeds:
        """Map free-text titles to catalog indices.

        Exact (normalized) matches are tried first, then a conservative fuzzy
        match so minor typos still resolve. Duplicate resolutions are removed
        while preserving order.

        Args:
            titles: Raw seed titles from the request.

        Returns:
            A :class:`ResolvedSeeds` with matched indices and any unknown titles.
        """
        indices: list[int] = []
        matched: list[str] = []
        unknown: list[str] = []
        seen: set[int] = set()

        for raw in titles:
            key = normalize_title(raw)
            idx = self._by_title.get(key)
            if idx is None and key:
                close = difflib.get_close_matches(key, self._titles_norm, n=1, cutoff=_RESOLVE_CUTOFF)
                idx = self._by_title[close[0]] if close else None
            if idx is None:
                unknown.append(raw)
            elif idx not in seen:
                seen.add(idx)
                indices.append(idx)
                matched.append(raw)

        return ResolvedSeeds(indices=indices, matched=matched, unknown=unknown)

    # ------------------------------------------------------------------ #
    # Recommendation
    # ------------------------------------------------------------------ #
    def recommend(
        self,
        seed_indices: list[int],
        count: int = 10,
        exclude_seen: bool = True,
        exclude_ids: list[int] | None = None,
        weights: tuple[float, float, float] | None = None,
    ) -> RecommendResponse:
        """Produce ranked recommendations for resolved seed indices.

        Args:
            seed_indices: Catalog rows of the seed titles (already resolved).
            count: Maximum number of recommendations.
            exclude_seen: Drop the seed titles from the results when true.
            exclude_ids: Recommendation ids (``movie_id``) already shown — never
                returned again, so the endless deck never repeats a card.
            weights: Optional ``(cf, content, semantic)`` blend override. The
                default is the tuned hybrid; ``(1, 0, 0)`` gives the pure
                "viewers like you" collaborative ranking used by /for-you.

        Returns:
            A :class:`~schemas.RecommendResponse`.
        """
        w_cf, w_content, w_semantic = weights if weights is not None else (W_CF, W_CONTENT, W_SEMANTIC)
        cf = _cosine_to_unit(cf_scores(self._bundle.cf_factors, seed_indices))
        content = content_scores(self._bundle.tfidf, seed_indices)  # already [0, 1]
        semantic = _cosine_to_unit(semantic_scores(self._bundle.embeddings, seed_indices))

        blended = w_cf * cf + w_content * content + w_semantic * semantic

        order = np.argsort(blended)[::-1]
        seed_set = set(seed_indices) if exclude_seen else set()
        excluded = set(exclude_ids or [])

        recs: list[Recommendation] = []
        for idx in order:
            idx = int(idx)
            rec = self._catalog[idx]
            if idx in seed_set or rec.movie_id in excluded:
                continue
            recs.append(
                self._to_recommendation(
                    rec,
                    score=round(float(blended[idx]), 2),
                    why=self._explain(rec, seed_indices, cf[idx], content[idx], semantic[idx]),
                )
            )
            if len(recs) >= count:
                break

        return RecommendResponse(
            recommendations=recs,
            taste_profile=self._taste_profile(seed_indices),
        )

    def attach_taste_space(self, taste_space: np.ndarray) -> None:
        """Give the recommender the hybrid item-vector space used for taste-based
        candidate generation (the same matrix the session reranker ranks in)."""
        self._taste_space = taste_space

    def recommend_by_taste(
        self,
        vector: np.ndarray,
        count: int = 20,
        exclude_ids: list[int] | None = None,
        confidence: float = 1.0,
    ) -> RecommendResponse:
        """Generate fresh candidates nearest a live taste vector (Layer 2).

        Ranks the WHOLE catalog by cosine to the user's accumulated taste vector
        in the hybrid space — so results reflect everything they've liked AND
        disliked (dislikes pushed the vector away) and lean on collaborative
        signal (the CF half of the space) — plus the popularity prior
        (``cosine + POP_BETA * prior``), the configuration the offline holdout
        measured as most predictive (see ``ml.evaluate``). This is what lets the
        deck *predict new, unique titles* rather than only re-order a popularity
        pool. Already seen ids are excluded so a card never repeats.

        Returns an empty list (caller should fall back to popularity) when there
        is no taste space, no signal, or a stale-dimension vector.
        """
        space = self._taste_space
        norm = float(np.linalg.norm(vector)) if vector is not None else 0.0
        if space is None or norm == 0.0 or vector.shape[0] != space.shape[1]:
            return RecommendResponse(recommendations=[], taste_profile=self._taste_profile([]))

        cosine = space @ (vector / norm)  # space rows are unit-norm -> dot == cosine
        # Early-swipe shrinkage (see reranker.TASTE_SHRINK): trust the taste
        # vector in proportion to its confidence so a thin profile leans on the
        # popularity prior. A persisted/mature profile (high confidence) is
        # barely shrunk; the default 1.0 keeps callers that omit it unchanged.
        cosine = (confidence / (confidence + TASTE_SHRINK)) * cosine
        scores = cosine + POP_BETA * self._pop_prior
        order = np.argsort(scores)[::-1]
        excluded = set(exclude_ids or [])

        recs: list[Recommendation] = []
        chosen: list[int] = []
        for idx in order:
            idx = int(idx)
            rec = self._catalog[idx]
            if rec.movie_id in excluded:
                continue
            # Display score: map the blended score from [-1, 1 + POP_BETA] to [0, 1].
            display = (float(scores[idx]) + 1.0) / (2.0 + POP_BETA)
            recs.append(
                self._to_recommendation(rec, score=round(display, 2), why="Tuned to your taste.")
            )
            chosen.append(idx)
            if len(recs) >= count:
                break

        return RecommendResponse(recommendations=recs, taste_profile=self._taste_profile(chosen[:8]))

    def predict_extremes(self, vector, count: int = 5) -> tuple[list[dict], list[dict]]:
        """The crystal ball: titles the model predicts this taste will LOVE and HATE.

        Loves = the production blended ranking (cosine + popularity prior) —
        identical scoring to the adaptive deck, so the forecast IS the model's
        actual next picks. Hates = the most NEGATIVE raw cosines (no prior:
        "you'll dislike this" is about taste opposition, not obscurity).
        Returns ([], []) when there is no usable signal.
        """
        import numpy as np

        space = self._taste_space
        norm = float(np.linalg.norm(vector)) if vector is not None else 0.0
        if space is None or norm == 0.0 or vector.shape[0] != space.shape[1]:
            return [], []

        cosine = space @ (vector / norm)
        blended = cosine + POP_BETA * self._pop_prior

        def pack(idx: int, score: float) -> dict:
            rec = self._catalog[idx]
            return {"id": rec.movie_id, "title": rec.title, "year": rec.year,
                    "score": round(float(score), 2)}

        love_order = np.argsort(blended)[::-1][:count]
        # Only popular-enough titles qualify as predicted hates — "you'll hate
        # this obscure film you've never heard of" is noise, not a forecast.
        hate_mask = self._pop_prior >= 0.5
        hate_pool = np.where(hate_mask)[0]
        hate_order = hate_pool[np.argsort(cosine[hate_pool])[:count]] if hate_pool.size else []

        loves = [pack(int(i), blended[int(i)]) for i in love_order]
        hates = [pack(int(i), cosine[int(i)]) for i in hate_order]
        return loves, hates

    def popular(
        self,
        popularity: dict[int, float],
        count: int = 20,
        exclude_ids: list[int] | None = None,
    ) -> RecommendResponse:
        """Cold-start deck ranked by crowd popularity (no seeds needed).

        Used for the landing deck and for refills before the user has liked
        anything. ``popularity`` maps a recommendation id (``movie_id``) to a
        swipe-derived score; titles absent from it fall back to their catalog
        order so the deck is always full.

        Args:
            popularity: ``tmdb_id`` → popularity score (weighted swipe counts).
            count: How many cards to return.
            exclude_ids: Recommendation ids (``movie_id``) already shown.

        Returns:
            A :class:`~schemas.RecommendResponse`.
        """
        excluded = set(exclude_ids or [])
        ranked = sorted(
            (r for r in self._catalog if r.movie_id not in excluded),
            key=lambda r: (popularity.get(r.tmdb_id or -1, 0.0), -r.idx),
            reverse=True,
        )
        recs = [
            self._to_recommendation(
                rec,
                score=round(min(0.95, 0.7 + 0.02 * i), 2),
                why="Popular with viewers right now.",
            )
            for i, rec in enumerate(ranked[:count])
        ]
        chosen = [self._index_of(r) for r in ranked[:count]]
        return RecommendResponse(
            recommendations=recs,
            taste_profile=self._taste_profile(chosen),
        )

    def _index_of(self, rec: MovieRecord) -> int:
        """Return the catalog index of a record."""
        return rec.idx

    def _to_recommendation(self, rec: MovieRecord, score: float, why: str) -> Recommendation:
        """Build a :class:`~schemas.Recommendation` from a catalog record."""
        return Recommendation(
            id=rec.movie_id,
            title=rec.title,
            year=rec.year,
            type=rec.type if rec.type in ("movie", "tv") else "movie",
            score=score,
            genres=rec.genres,
            cast=rec.cast,
            overview=rec.overview,
            poster_url=rec.poster_url,
            tmdb_id=rec.tmdb_id,
            trailer_key=rec.trailer_key,
            why=why,
        )

    # ------------------------------------------------------------------ #
    # Explanation + profile
    # ------------------------------------------------------------------ #
    def _explain(
        self,
        rec: MovieRecord,
        seed_indices: list[int],
        cf: float,
        content: float,
        semantic: float,
    ) -> str:
        """Build the per-recommendation ``why`` string.

        Combines the genres/moods this title shares with the seeds and the
        component that contributed most to its (weighted) score.
        """
        seed_genres = Counter(g for i in seed_indices for g in self._catalog[i].genres)
        seed_moods = Counter(m for i in seed_indices for m in self._catalog[i].mood_tags)

        shared_genres = [g for g in rec.genres if g in seed_genres][:2]
        shared_moods = [m for m in rec.mood_tags if m in seed_moods][:2]

        signal = max(
            (W_CF * cf, "shared-audience (collaborative) signal"),
            (W_CONTENT * content, "genre & keyword overlap"),
            (W_SEMANTIC * semantic, "thematic plot similarity"),
            key=lambda pair: pair[0],
        )[1]

        parts: list[str] = []
        if shared_genres:
            parts.append("Shares " + " & ".join(shared_genres) + " with your picks")
        if shared_moods:
            parts.append(", ".join(shared_moods) + " tone")
        parts.append(f"strong {signal}")
        return "; ".join(parts) + "."

    def _taste_profile(self, seed_indices: list[int]) -> TasteProfile:
        """Aggregate the seed titles into a taste profile."""
        genres = Counter(g for i in seed_indices for g in self._catalog[i].genres)
        moods = Counter(m for i in seed_indices for m in self._catalog[i].mood_tags)
        years = [self._catalog[i].year for i in seed_indices if self._catalog[i].year]

        return TasteProfile(
            top_genres=[g for g, _ in genres.most_common(3)],
            mood_tags=[m for m, _ in moods.most_common(5)],
            era_bias=_era_label(years),
        )


def _era_label(years: list[int]) -> str:
    """Return the dominant decade label (e.g. ``"2010s"``) for a set of years."""
    if not years:
        return "mixed"
    decades = Counter((y // 10) * 10 for y in years)
    top_decade, _ = decades.most_common(1)[0]
    return f"{top_decade}s"
