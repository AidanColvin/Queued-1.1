"""Trajectory pre-filter for the live deck: silently drop "doomed" titles.

After the session reranker orders the remaining deck, this peeks at each
candidate's affinity to the user's (trajectory-adjusted) preference vector and
removes titles scoring below ``DOOM_THRESHOLD`` — cards the model is confident
the user would dislike. One vectorized pass (a single matrix-vector product)
over the whole queue; candidates with no known embedding pass through
untouched.
"""

from __future__ import annotations

import numpy as np

from ml.predictor import TrajectoryPredictor

# Cosine below which a candidate is "destined to hate" and silently dropped.
DOOM_THRESHOLD = -0.3

predictor = TrajectoryPredictor()


def filter_doomed_titles(reranked_queue: list, current_profile: list, recent_swipes: list, get_embedding_fn) -> list:
    """Return ``reranked_queue`` minus titles predicted to be disliked.

    Args:
        reranked_queue: Deck order (bare ids or dicts with an ``id``).
        current_profile: The session taste vector.
        recent_swipes: Hypothetical next swipes (``{action, embedding}``) folded
            into the profile before scoring — the "trajectory" part.
        get_embedding_fn: id -> embedding row (or ``None`` for unknown ids).
    """
    v_pref = np.asarray(current_profile, dtype=np.float32)
    for swipe in recent_swipes:
        v_pref = v_pref + predictor.w.get(swipe["action"], 0.0) * np.asarray(
            swipe["embedding"], dtype=np.float32
        )
    norm = float(np.linalg.norm(v_pref))
    if norm == 0.0:
        return list(reranked_queue)  # no signal -> nothing is doomed
    unit = v_pref / norm

    ids = [item if isinstance(item, int) else item.get("id") for item in reranked_queue]
    embs = [get_embedding_fn(i) for i in ids]
    known = [k for k, e in enumerate(embs) if e is not None]
    if not known:
        return list(reranked_queue)

    # One matrix-vector product scores every known candidate at once. Rows are
    # unit-norm (the taste space), so the dot product is the cosine.
    matrix = np.stack([embs[k] for k in known]).astype(np.float32)
    scores = matrix @ unit
    doomed = {known[j] for j, s in enumerate(scores) if float(s) < DOOM_THRESHOLD}
    return [item for k, item in enumerate(reranked_queue) if k not in doomed]
