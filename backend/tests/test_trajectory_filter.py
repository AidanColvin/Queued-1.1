"""The doom filter must trust the taste vector exactly as much as the rankers do."""

from __future__ import annotations

import numpy as np

from ml.reranker import TASTE_SHRINK
from ml.trajectory_filter import DOOM_THRESHOLD, filter_doomed_titles


def _space() -> dict[int, np.ndarray]:
    # id 1 aligns with the profile, id 2 directly opposes it (cosine -1).
    return {1: np.array([1.0, 0.0], dtype=np.float32), 2: np.array([-1.0, 0.0], dtype=np.float32)}


def _fetch(space):
    return lambda tmdb_id: space.get(tmdb_id)


def test_mature_profile_dooms_opposed_titles() -> None:
    """At full confidence a strongly-opposed card is dropped (old behaviour)."""
    out = filter_doomed_titles([1, 2], [1.0, 0.0], [], _fetch(_space()), confidence=1.0)
    assert out == [1]


def test_thin_evidence_cannot_doom() -> None:
    """One swipe (~0.1 confidence) shrinks the cosine inside the threshold,
    so the filter never drops cards on evidence the ranker doesn't trust."""
    confidence = 0.1
    assert (confidence / (confidence + TASTE_SHRINK)) * -1.0 > DOOM_THRESHOLD  # sanity
    out = filter_doomed_titles([1, 2], [1.0, 0.0], [], _fetch(_space()), confidence=confidence)
    assert out == [1, 2]


def test_default_confidence_preserves_prior_behaviour() -> None:
    """Callers that don't pass confidence get the original raw-cosine filter."""
    assert filter_doomed_titles([1, 2], [1.0, 0.0], [], _fetch(_space())) == [1]


def test_no_signal_passes_everything_through() -> None:
    assert filter_doomed_titles([1, 2], [0.0, 0.0], [], _fetch(_space()), confidence=0.0) == [1, 2]


def test_unknown_ids_pass_through() -> None:
    out = filter_doomed_titles([7, 2], [1.0, 0.0], [], _fetch(_space()), confidence=1.0)
    assert out == [7]
