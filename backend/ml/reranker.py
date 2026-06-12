"""Layer 1 adaptive signal: real-time session re-ranking from swipes.

After every swipe the session's preference vector is nudged toward (or away
from) the swiped title's embedding, and the remaining deck is re-sorted by
cosine similarity to that vector. This is pure numpy (~milliseconds) — no model
inference, no retraining. Retraining on accumulated swipes (Layer 3) happens
offline.

The signals are intentionally **asymmetric**: a dismiss is not the mirror image
of a like, and a fast dismiss counts for more than a hesitant one (the
``time_modifier``). Layer 2 (cross-session user profiles) needs accounts and is
deferred to Phase 3 — this module is fully anonymous, keyed only by an opaque
``session_id``.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

import numpy as np

from ml.artifacts import MovieRecord


def _unit_rows(matrix: np.ndarray) -> np.ndarray:
    """L2-normalize each row so dot product equals cosine. Zero rows stay zero."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return (matrix / np.where(norms == 0.0, 1.0, norms)).astype(np.float32)


# Share of the hybrid space's cosine energy carried by the semantic block; the
# rest is collaborative. Tuned by sweep in ``ml.evaluate`` (temporal holdout on
# MovieLens): the 50/50 split scored AUC 0.700, but the semantic signal alone is
# weak (AUC 0.57), so leaning the blend toward CF lifts AUC to ~0.737 with the
# optimum flat across 0.05-0.15. 0.15 keeps the most content-awareness for
# novel/sparsely-rated titles at no measured accuracy cost.
W_SEMANTIC_ENERGY = 0.15

# Additive popularity-prior weight used by taste ranking (see
# :func:`popularity_prior`). Originally swept to 0.6 against the 10%-sample
# factors; re-swept jointly with w_semantic after the Stage-3 retrain (full
# 25M + Kion factors): 0.75 wins AUC on all three holdout seeds
# (e.g. 0.8019 -> 0.8031 on seed 42) and degrades past ~1.0.
POP_BETA = 0.75

# Early-swipe taste shrinkage. The taste cosine is scaled by
# ``confidence / (confidence + TASTE_SHRINK)`` so a vector built from 1-2 noisy
# swipes can't override the strong popularity prior before it's trustworthy.
# Since ``confidence ~= 0.1 * signal_count``, 0.4 reproduces ``k / (k + 4)`` for
# a pure-like run. Swept on a held-out MovieLens user split (cross-seed): it
# removes the measured cold-start dip (P@10 at swipe 1: 0.856 -> 0.889, AUC
# 0.608 -> 0.635) and lifts swipe-3 P@10 0.875 -> 0.891, with the warm regime
# (swipe 12) preserved (P@10 0.916 -> 0.917, AUC 0.679 -> 0.685). A warm /
# persisted profile carries high confidence, so it is barely shrunk.
TASTE_SHRINK = 0.4


def build_taste_space(
    embeddings: np.ndarray, cf_factors: np.ndarray, w_semantic: float = W_SEMANTIC_ENERGY
) -> np.ndarray:
    """Build the item-vector space the session reranker ranks in.

    A weighted blend of the semantic plot embeddings and the collaborative-
    filtering item factors: each block is L2-normalized per row, scaled so the
    semantic block carries ``w_semantic`` of the final cosine energy (scale
    factors are square roots because cosine energy is quadratic in the block
    norm), then concatenated and re-normalized.

    Offline evaluation (``ml.evaluate``, temporal holdout on MovieLens) drove
    both moves away from the original bare semantic space: hybridizing with CF
    (ROC-AUC ~0.57 -> ~0.70) and then re-weighting the blend toward CF
    (~0.70 -> ~0.74 at ``w_semantic=0.15``), because like/dislike is driven by
    collaborative signal, not plot-summary similarity. Keeping a semantic share
    preserves content-awareness for novel / sparsely-rated titles. Both
    production and the evaluator call THIS function, so the shipped space is
    exactly the measured one.
    """
    s = float(np.sqrt(w_semantic))
    c = float(np.sqrt(1.0 - w_semantic))
    return _unit_rows(np.concatenate([s * _unit_rows(embeddings), c * _unit_rows(cf_factors)], axis=1))


def popularity_prior(catalog: list[MovieRecord]) -> np.ndarray:
    """Per-row popularity prior in ``[0, 1]``, aligned to the catalog ordering.

    ``log1p`` of each title's MovieLens rating count, min-max scaled. Added to
    the taste cosine as ``score = cosine + POP_BETA * prior`` wherever taste
    ranking happens, because a like is far more likely on a broadly-popular
    title than the cosine alone predicts (popularity alone scores AUC 0.59 vs
    0.5 chance on the holdout). Bundles without rating counts (the sample)
    yield all zeros, making the prior a no-op.
    """
    counts = np.array([max(0, rec.rating_count) for rec in catalog], dtype=np.float64)
    log_pop = np.log1p(counts)
    spread = float(log_pop.max() - log_pop.min())
    if spread == 0.0:
        return np.zeros(len(catalog), dtype=np.float32)
    return ((log_pop - log_pop.min()) / spread).astype(np.float32)


# Per-action base weights. Positive pulls the session vector toward the title;
# negative pushes it away. Not symmetric — see the module docstring.
SIGNAL_WEIGHTS: dict[str, float] = {
    "superliked": 1.8,  # emphatic positive — a double-tap "exactly this, more of it".
                       # Weighted well above an ordinary like so a single super
                       # like steers the deck harder than a normal swipe-right.
    "liked": 1.0,      # strong positive — "more exactly like this"
    "saved": 0.65,     # moderate positive — "interested, lower urgency"
    "skip": 0.0,       # neutral — "haven't seen it": unfamiliarity, not taste.
                       # Still recorded to swipe_events (offline training), but
                       # never nudges the live taste vector — a discovery app
                       # must not learn *away* from titles you simply haven't met.
    "dismissed": -0.55,  # moderate negative — "not this vibe at all" (dislike)
}

# Re-rank once the session carries a little signal — low so the deck visibly
# adapts within the first couple of swipes (~one like or two dislikes).
CONFIDENCE_THRESHOLD = 0.1
# Cap on concurrently tracked anonymous sessions (oldest evicted past this).
MAX_SESSIONS = 10_000


def time_modifier(time_on_card_ms: int, action: str) -> float:
    """Scale a negative signal by how long the user deliberated.

    Hesitation is only informative for negatives: a fast dismiss is a confident
    "no" (amplify), a long pause before dismissing is an uncertain "maybe"
    (soften). Positives are unaffected.

    Args:
        time_on_card_ms: Milliseconds from card appearing to swipe commit.
        action: The swipe action.

    Returns:
        A multiplier applied to the base weight before accumulation.
    """
    if action in ("liked", "saved", "superliked"):
        return 1.0
    if time_on_card_ms < 1500:
        return 1.2
    if time_on_card_ms > 6000:
        return 0.6
    return 1.0


class SessionReranker:
    """A single session's evolving taste vector over the embedding space.

    Args:
        embeddings: L2-normalized embedding matrix ``(n_movies, dim)``.
        tmdb_to_idx: Map from TMDB id to embedding row index.
        init_vector: Optional warm-start vector (Phase 3 user-profile blend).
        init_confidence: Optional warm-start confidence.
        prior: Optional per-row popularity prior (see :func:`popularity_prior`);
            ``None`` disables the prior term in :meth:`rerank`.
    """

    def __init__(
        self,
        embeddings: np.ndarray,
        tmdb_to_idx: dict[int, int],
        init_vector: np.ndarray | None = None,
        init_confidence: float = 0.0,
        prior: np.ndarray | None = None,
    ) -> None:
        self._embeddings = embeddings
        self._tmdb_to_idx = tmdb_to_idx
        self._prior = prior
        dim = embeddings.shape[1]
        self.session_vector = (
            init_vector.astype(np.float32).copy()
            if init_vector is not None
            else np.zeros(dim, dtype=np.float32)
        )
        self.confidence = init_confidence

    def update(self, tmdb_id: int, action: str, time_on_card_ms: int) -> bool:
        """Fold one swipe into the session vector.

        Args:
            tmdb_id: TMDB id of the swiped card.
            action: One of :data:`SIGNAL_WEIGHTS`.
            time_on_card_ms: Deliberation time in milliseconds.

        Returns:
            ``True`` if the swipe moved the session vector, ``False`` if the
            card/action was unknown or carries no signal (e.g. a neutral
            "haven't seen it"). Either way it is not an error.
        """
        idx = self._tmdb_to_idx.get(tmdb_id)
        weight = SIGNAL_WEIGHTS.get(action)
        if idx is None or weight is None or weight == 0.0:
            return False
        self.session_vector += weight * time_modifier(time_on_card_ms, action) * self._embeddings[idx]
        self.confidence = min(self.confidence + abs(weight) * 0.1, 1.0)
        return True

    def rerank(self, candidate_ids: list[int], boost_ids: set[int] | None = None, boost: float = 0.12) -> list[int]:
        """Return ``candidate_ids`` re-sorted by similarity to the session vector.

        Below the confidence threshold the original order is preserved (not
        enough signal yet). Candidates not in the embedding index are kept,
        appended at the end in their original order.

        Args:
            candidate_ids: Remaining deck as TMDB ids.
            boost_ids: Optional ids to nudge upward (the "prefer my services"
                soft boost) — added to the cosine score, so taste still
                dominates and off-service titles are never excluded.
            boost: Additive score bonus for ``boost_ids``.

        Returns:
            The re-ordered TMDB ids.
        """
        if self.confidence < CONFIDENCE_THRESHOLD:
            return list(candidate_ids)

        norm = float(np.linalg.norm(self.session_vector))
        if norm == 0:
            return list(candidate_ids)

        known = [c for c in candidate_ids if c in self._tmdb_to_idx]
        unknown = [c for c in candidate_ids if c not in self._tmdb_to_idx]
        if not known:
            return list(candidate_ids)

        unit = self.session_vector / norm
        known_idxs = [self._tmdb_to_idx[c] for c in known]
        scores = self._embeddings[known_idxs] @ unit  # rows are unit-norm -> dot == cosine
        # Shrink the taste signal toward the prior while evidence is thin (see
        # TASTE_SHRINK): full trust only once the session vector has matured.
        scores = (self.confidence / (self.confidence + TASTE_SHRINK)) * scores
        if self._prior is not None:
            scores = scores + POP_BETA * self._prior[known_idxs]
        if boost_ids:
            scores = scores + np.array([boost if c in boost_ids else 0.0 for c in known], dtype=scores.dtype)
        order = np.argsort(scores)[::-1]
        return [known[i] for i in order] + unknown


class SessionStore:
    """Thread-safe, size-bounded registry of per-session rerankers.

    In-memory for Phase 1 — swap for Redis (keyed by ``session_id``) in
    production. Oldest sessions are evicted past :data:`MAX_SESSIONS`.

    Args:
        embeddings: The bundle's embedding matrix.
        catalog: The bundle's catalog (for the TMDB-id index).
    """

    def __init__(self, embeddings: np.ndarray, catalog: list[MovieRecord]) -> None:
        self._embeddings = embeddings
        self._tmdb_to_idx = {rec.tmdb_id: rec.idx for rec in catalog if rec.tmdb_id is not None}
        self._prior = popularity_prior(catalog)
        self._sessions: OrderedDict[str, SessionReranker] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def dim(self) -> int:
        """Embedding dimensionality — used to validate a persisted user vector
        still matches the current model before warm-starting from it."""
        return int(self._embeddings.shape[1])

    def embedding_for(self, tmdb_id: int) -> np.ndarray | None:
        """The item vector for a TMDB id, or ``None`` when it isn't indexed.

        The public read path for callers (e.g. the trajectory doom filter) that
        need per-title vectors without reaching into private attributes.
        """
        idx = self._tmdb_to_idx.get(tmdb_id)
        return self._embeddings[idx] if idx is not None else None

    def reranker_for_user(
        self, init_vector: np.ndarray | None = None, init_confidence: float = 0.0
    ) -> SessionReranker:
        """Build a transient reranker warm-started from a user's persisted taste
        (Layer 2). Not cached in ``_sessions``: for a signed-in user the DB
        ``UserProfile`` row is the source of truth — the caller loads the vector,
        applies the swipe, and persists it back. This stays correct across
        serverless cold starts where any in-memory copy would be lost anyway.
        """
        return SessionReranker(
            self._embeddings,
            self._tmdb_to_idx,
            init_vector=init_vector,
            init_confidence=init_confidence,
            prior=self._prior,
        )

    def get_or_create(
        self,
        session_id: str,
        init_vector: np.ndarray | None = None,
        init_confidence: float = 0.0,
    ) -> SessionReranker:
        """Return the session's reranker, creating it on first use.

        ``init_vector``/``init_confidence`` warm-start a *newly created*
        reranker from the session's persisted ``AnonSessionProfile`` row, so a
        session survives process restarts; they are ignored when the session is
        already cached (the in-memory copy is at least as fresh).
        """
        with self._lock:
            reranker = self._sessions.get(session_id)
            if reranker is None:
                reranker = SessionReranker(
                    self._embeddings,
                    self._tmdb_to_idx,
                    init_vector=init_vector,
                    init_confidence=init_confidence,
                    prior=self._prior,
                )
                self._sessions[session_id] = reranker
                if len(self._sessions) > MAX_SESSIONS:
                    self._sessions.popitem(last=False)  # evict oldest
            else:
                self._sessions.move_to_end(session_id)
            return reranker

    def peek(self, session_id: str) -> SessionReranker | None:
        """Return the cached reranker without creating one (or ``None``)."""
        with self._lock:
            return self._sessions.get(session_id)

    def reset(self, session_id: str) -> None:
        """Forget a session (e.g. when the user starts a fresh deck)."""
        with self._lock:
            self._sessions.pop(session_id, None)
