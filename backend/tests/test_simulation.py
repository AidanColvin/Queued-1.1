"""Robustness regression: the deck must adapt toward diverse simulated tastes.

Runs the ``ml.simulate`` harness (the exact production scoring) over the real
committed artifacts — skipped if they aren't present. Guards the core promise:
swiping teaches the engine, for users with very different tastes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ml.artifacts import MovieRecord
from ml.reranker import (
    POP_BETA,
    QUALITY_GAMMA,
    build_taste_space,
    load_quality_prior,
    popularity_prior,
)

ARTIFACTS = Path("data/artifacts")

pytestmark = pytest.mark.skipif(
    not (ARTIFACTS / "embeddings.npy").exists(), reason="real artifact bundle not present"
)


@pytest.fixture(scope="module")
def engine():
    """Production-config engine with an identity P(like) calibration."""
    from ml.simulate import Engine

    movies = json.loads((ARTIFACTS / "movie_index.json").read_text())["movies"]
    catalog = [MovieRecord.from_json(m) for m in movies]
    emb = np.load(ARTIFACTS / "embeddings.npy").astype(np.float32)
    cf = np.load(ARTIFACTS / "cf_item_factors.npy").astype(np.float32)
    # Production parity: popularity AND quality priors (the Engine multiplies
    # its prior by POP_BETA, so quality is folded in at gamma/beta scale).
    prior = popularity_prior(catalog) + (QUALITY_GAMMA / POP_BETA) * load_quality_prior(
        ARTIFACTS, len(catalog)
    )
    return Engine(
        catalog=catalog,
        space=build_taste_space(emb, cf),
        prior=prior,
        movieid_to_idx={r.movie_id: r.idx for r in catalog},
        calib_x=np.array([0.0, 1.0]),
        calib_y=np.array([0.0, 1.0]),
    )


def test_every_persona_deck_adapts(engine, capsys) -> None:
    """After 12 swipes, no persona's top-20 fits their taste worse than the
    cold-start deck — and most fit substantially better."""
    from ml.simulate import run_personas

    curves = run_personas(engine, swipes=12, noise=0.0, seed=7)
    capsys.readouterr()  # silence the debug log in test output

    improvements = {name: curve[-1] - curve[0] for name, curve in curves.items()}
    assert all(delta >= 0 for delta in improvements.values()), improvements
    strong = sum(delta >= 0.15 for delta in improvements.values())
    assert strong >= 4, f"expected most personas to improve >=3/20 cards: {improvements}"


def test_real_user_learning_curve_improves(engine, capsys) -> None:
    """Replaying real users' swipes raises held-out AUC and next-card hit rate."""
    pd = pytest.importorskip("pandas")
    from ml.simulate import run_batch

    if not (ARTIFACTS / "ratings.parquet").exists():
        pytest.skip("ratings.parquet not present (training-only artifact)")

    ratings = pd.read_parquet(ARTIFACTS / "ratings.parquet")
    ratings = ratings[ratings["movieId"].isin(engine.movieid_to_idx)]
    # 300 users: with the quality prior the cold deck is strong enough that ten
    # swipes move AUC by only ~+0.004 — real, but beneath a 60-user sample's
    # noise floor. Verified stable across seeds at n>=300.
    rows = run_batch(engine, ratings, n_users=300, max_swipes=10, seed=7)
    capsys.readouterr()

    cold, warm = rows[0], rows[-1]
    assert warm["auc"] > cold["auc"], (cold, warm)
    assert warm["p@20"] >= cold["p@20"], (cold, warm)
