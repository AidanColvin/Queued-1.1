"""Trajectory prediction: will this user like a candidate after N more swipes?

Folds a hypothetical sequence of future swipes into a preference vector using
the SAME per-action signal weights the live session reranker trains with
(``ml.reranker.SIGNAL_WEIGHTS`` — superlikes steer hardest, skips are neutral,
dislikes push away), then scores a candidate by cosine. Dimension-agnostic:
works on raw 384-dim plot embeddings or rows of the 434-dim production taste
space, as long as profile and candidate agree.
"""

from __future__ import annotations

import numpy as np

from ml.reranker import SIGNAL_WEIGHTS


class TrajectoryPredictor:
    """Stateless affinity forecaster over any shared embedding space."""

    def __init__(self) -> None:
        # Single source of truth — a drifted copy of these weights once made
        # /predict disagree with what swipes actually train.
        self.w = SIGNAL_WEIGHTS

    def predict_future_affinity(self, c, s, cand) -> float:
        """Cosine between the trajectory-adjusted profile and a candidate.

        Args:
            c: Current preference vector.
            s: Simulated swipes: ``[{"action": ..., "embedding": [...]}]``.
            cand: Candidate item vector (same dimension as ``c``).

        Returns:
            Cosine in ``[-1, 1]``; 0.0 when either side carries no signal.
        """
        v_pref = np.asarray(c, dtype=np.float64)
        v_cand = np.asarray(cand, dtype=np.float64)
        for swipe in s:
            v_pref = v_pref + self.w.get(swipe["action"], 0.0) * np.asarray(
                swipe["embedding"], dtype=np.float64
            )
        np_norm = np.linalg.norm(v_pref)
        nc_norm = np.linalg.norm(v_cand)
        if not np_norm or not nc_norm:
            return 0.0
        return float(np.dot(v_pref, v_cand) / (np_norm * nc_norm))
