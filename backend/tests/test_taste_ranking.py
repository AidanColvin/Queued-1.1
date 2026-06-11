"""Unit tests for the tuned taste space and popularity prior (``ml.reranker``)."""

from __future__ import annotations

import numpy as np

from ml.artifacts import MovieRecord
from ml.reranker import POP_BETA, SessionReranker, build_taste_space, popularity_prior


def _record(idx: int, rating_count: int = 0) -> MovieRecord:
    return MovieRecord(
        idx=idx, movie_id=idx, title=f"t{idx}", year=2000, type="movie", rating_count=rating_count
    )


def test_taste_space_rows_unit_norm() -> None:
    """Every row of the hybrid space is unit-norm regardless of the weight."""
    rng = np.random.default_rng(0)
    emb, cf = rng.normal(size=(6, 8)).astype(np.float32), rng.normal(size=(6, 4)).astype(np.float32)
    for w in (0.0, 0.15, 0.5, 1.0):
        space = build_taste_space(emb, cf, w_semantic=w)
        assert np.allclose(np.linalg.norm(space, axis=1), 1.0, atol=1e-6)


def test_taste_space_weight_controls_block_energy() -> None:
    """``w_semantic`` is the share of squared norm in the semantic block."""
    rng = np.random.default_rng(1)
    emb, cf = rng.normal(size=(5, 8)).astype(np.float32), rng.normal(size=(5, 4)).astype(np.float32)
    space = build_taste_space(emb, cf, w_semantic=0.15)
    semantic_energy = (space[:, :8] ** 2).sum(axis=1)
    assert np.allclose(semantic_energy, 0.15, atol=1e-5)


def test_popularity_prior_scaled_and_monotone() -> None:
    """The prior is min-max scaled log counts: [0, 1], order-preserving."""
    prior = popularity_prior([_record(0, 0), _record(1, 10), _record(2, 10_000)])
    assert prior[0] == 0.0
    assert prior[2] == 1.0
    assert 0.0 < prior[1] < prior[2]


def test_popularity_prior_no_counts_is_zero() -> None:
    """A bundle without rating counts (the sample) yields an all-zero prior."""
    prior = popularity_prior([_record(0), _record(1)])
    assert not prior.any()


def test_rerank_blends_popularity_prior() -> None:
    """A slightly-worse cosine with a big popularity edge overtakes — but only
    when the reranker carries a prior."""
    rt2 = np.sqrt(2.0) / 2.0
    # 200 matches the liked direction exactly; 300 is 45 degrees off but popular.
    embeddings = np.array([[1.0, 0.0], [1.0, 0.0], [rt2, rt2]], dtype=np.float32)
    tmdb_to_idx = {100: 0, 200: 1, 300: 2}
    prior = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    without = SessionReranker(embeddings, tmdb_to_idx)
    without.update(100, "liked", 2000)
    assert without.rerank([300, 200])[0] == 200  # pure cosine: exact match wins

    with_prior = SessionReranker(embeddings, tmdb_to_idx, prior=prior)
    with_prior.update(100, "liked", 2000)
    # cosine gap (1.0 - rt2 ~ 0.29) < POP_BETA * 1.0 -> popular title overtakes.
    assert with_prior.rerank([300, 200])[0] == 300


def test_prior_does_not_override_strong_taste_signal() -> None:
    """A clear taste match beats max popularity: cosine spread (2.0 across
    opposite directions) outweighs ``POP_BETA`` (< 1) by design."""
    embeddings = np.array([[1.0, 0.0], [1.0, 0.0], [-1.0, 0.0]], dtype=np.float32)
    tmdb_to_idx = {100: 0, 200: 1, 300: 2}
    prior = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    assert POP_BETA < 2.0

    rr = SessionReranker(embeddings, tmdb_to_idx, prior=prior)
    rr.update(100, "liked", 2000)
    # 200 matches taste exactly (cos 1.0); 300 is opposite (cos -1.0) but popular.
    assert rr.rerank([300, 200])[0] == 200
