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

# Per-action base weights. Positive pulls the session vector toward the title;
# negative pushes it away. Not symmetric — see the module docstring.
SIGNAL_WEIGHTS: dict[str, float] = {
    "liked": 1.0,      # strong positive — "more exactly like this"
    "saved": 0.65,     # moderate positive — "interested, lower urgency"
    "skip": -0.25,     # weak negative — "not appealing right now"
    "dismissed": -0.55,  # moderate negative — "not this vibe at all"
}

# Re-rank only once the session carries enough signal to be meaningful.
CONFIDENCE_THRESHOLD = 0.15
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
    if action in ("liked", "saved"):
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
    """

    def __init__(
        self,
        embeddings: np.ndarray,
        tmdb_to_idx: dict[int, int],
        init_vector: np.ndarray | None = None,
        init_confidence: float = 0.0,
    ) -> None:
        self._embeddings = embeddings
        self._tmdb_to_idx = tmdb_to_idx
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
            ``True`` if the swipe was applied, ``False`` if the card or action
            was unknown (the request is then a no-op, not an error).
        """
        idx = self._tmdb_to_idx.get(tmdb_id)
        weight = SIGNAL_WEIGHTS.get(action)
        if idx is None or weight is None:
            return False
        self.session_vector += weight * time_modifier(time_on_card_ms, action) * self._embeddings[idx]
        self.confidence = min(self.confidence + abs(weight) * 0.1, 1.0)
        return True

    def rerank(self, candidate_ids: list[int]) -> list[int]:
        """Return ``candidate_ids`` re-sorted by similarity to the session vector.

        Below the confidence threshold the original order is preserved (not
        enough signal yet). Candidates not in the embedding index are kept,
        appended at the end in their original order.

        Args:
            candidate_ids: Remaining deck as TMDB ids.

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
        rows = self._embeddings[[self._tmdb_to_idx[c] for c in known]]
        scores = rows @ unit  # embedding rows are unit-norm -> dot == cosine
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
        self._sessions: OrderedDict[str, SessionReranker] = OrderedDict()
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> SessionReranker:
        """Return the session's reranker, creating it on first use."""
        with self._lock:
            reranker = self._sessions.get(session_id)
            if reranker is None:
                reranker = SessionReranker(self._embeddings, self._tmdb_to_idx)
                self._sessions[session_id] = reranker
                if len(self._sessions) > MAX_SESSIONS:
                    self._sessions.popitem(last=False)  # evict oldest
            else:
                self._sessions.move_to_end(session_id)
            return reranker

    def reset(self, session_id: str) -> None:
        """Forget a session (e.g. when the user starts a fresh deck)."""
        with self._lock:
            self._sessions.pop(session_id, None)
