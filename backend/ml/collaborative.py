"""Collaborative-filtering signal: latent item factors from matrix factorization.

The recommender never needs the rating matrix or scikit-surprise at runtime — it
loads the precomputed item-factor matrix ``cf_item_factors.npy`` and ranks by
cosine to the seed centroid. This module provides three things:

* :func:`cf_scores`            — the inference-time ranking (numpy only).
* :func:`train_svd`            — real SVD training via scikit-surprise.
* :func:`synthesize_item_factors` — a behaviorally-plausible factor space for the
  sample bundle, derived from genre/mood features so similar titles cluster.

Run ``python -m ml.collaborative`` (after ``data.preprocess``) to train the real
factors and overwrite the placeholder in the artifacts directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DEFAULT_N_FACTORS = 32


def cf_scores(cf_factors: np.ndarray, seed_indices: list[int]) -> np.ndarray:
    """Cosine similarity of every item factor to the seed centroid.

    Args:
        cf_factors: Item-factor matrix ``(n, n_factors)``.
        seed_indices: Rows of the seed titles.

    Returns:
        A length-``n`` array of similarities in ``[-1, 1]``. Items with a
        zero factor vector (cold items) score 0.
    """
    if not seed_indices:
        return np.zeros(cf_factors.shape[0], dtype=np.float64)

    # Normalize all rows once so the dot product is a true cosine.
    norms = np.linalg.norm(cf_factors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = cf_factors / norms

    centroid = unit[seed_indices].mean(axis=0)
    cnorm = np.linalg.norm(centroid)
    if cnorm == 0:
        return np.zeros(cf_factors.shape[0], dtype=np.float64)
    return unit @ (centroid / cnorm)


def synthesize_item_factors(
    feature_matrix: np.ndarray, n_factors: int = DEFAULT_N_FACTORS, seed: int = 7
) -> np.ndarray:
    """Project genre/mood features into a latent factor space for the sample.

    Real MovieLens factors come from SVD over millions of ratings. For the
    curated sample there are no ratings, so we approximate a behavioral space:
    a fixed random Gaussian projection of the content features plus a little
    deterministic noise. Titles with similar genres/moods land near each other,
    which is exactly the structure CF would learn, while the projection mixes
    dimensions so it is not a pure copy of the content signal.

    Args:
        feature_matrix: Dense ``(n, n_features)`` genre/mood indicator matrix.
        n_factors: Output factor dimension.
        seed: RNG seed for reproducibility.

    Returns:
        An ``(n, n_factors)`` float32 factor matrix.
    """
    rng = np.random.default_rng(seed)
    n_features = feature_matrix.shape[1]
    projection = rng.normal(0.0, 1.0, size=(n_features, n_factors))
    factors = feature_matrix @ projection
    factors += rng.normal(0.0, 0.05, size=factors.shape)
    return factors.astype(np.float32)


def train_svd(
    ratings,
    movie_order: list[int],
    n_factors: int = 50,
    n_epochs: int = 20,
    lr_all: float = 0.005,
    reg_all: float = 0.02,
) -> np.ndarray:
    """Train SVD on explicit ratings and return factors aligned to ``movie_order``.

    Uses scikit-surprise (a training-only dependency). Items absent from the
    ratings get a zero factor vector (cold start), which :func:`cf_scores`
    treats as a non-match.

    Args:
        ratings: A pandas DataFrame with columns ``userId, movieId, rating``.
        movie_order: MovieLens ``movieId`` values in catalog (row) order.
        n_factors: Latent dimension.
        n_epochs: SGD epochs.
        lr_all: Learning rate.
        reg_all: L2 regularization.

    Returns:
        An ``(len(movie_order), n_factors)`` factor matrix in catalog order.
    """
    from surprise import SVD, Dataset, Reader  # lazy, training-only

    reader = Reader(rating_scale=(0.5, 5.0))
    data = Dataset.load_from_df(ratings[["userId", "movieId", "rating"]], reader)
    trainset = data.build_full_trainset()

    algo = SVD(n_factors=n_factors, n_epochs=n_epochs, lr_all=lr_all, reg_all=reg_all)
    algo.fit(trainset)

    factors = np.zeros((len(movie_order), n_factors), dtype=np.float32)
    for row, movie_id in enumerate(movie_order):
        try:
            inner_iid = trainset.to_inner_iid(movie_id)
        except ValueError:
            continue  # movie had no ratings in the training split → cold start
        factors[row] = algo.qi[inner_iid]
    return factors


def _train_cli() -> None:
    """Entry point: train real CF factors and overwrite the artifact placeholder.

    Expects ``data.preprocess`` to have written:
        - ``<artifacts>/movie_index.json`` (catalog / movie order)
        - ``<artifacts>/ratings.parquet``  (filtered userId, movieId, rating)
    """
    import pandas as pd  # training-only

    from config import get_settings
    from ml.artifacts import CF_FACTORS_FILE

    settings = get_settings()
    art = settings.artifacts_dir
    index = json.loads((art / "movie_index.json").read_text(encoding="utf-8"))
    movie_order = [m["movie_id"] for m in index["movies"]]

    ratings_path = art / "ratings.parquet"
    if not ratings_path.exists():
        raise FileNotFoundError(
            f"{ratings_path} not found. Run `python -m data.preprocess` first."
        )
    ratings = pd.read_parquet(ratings_path)

    print(f"Training SVD on {len(ratings):,} ratings over {len(movie_order):,} movies...")
    factors = train_svd(ratings, movie_order)
    np.save(Path(art) / CF_FACTORS_FILE, factors)
    print(f"Saved {factors.shape} CF factors -> {art / CF_FACTORS_FILE}")


if __name__ == "__main__":
    _train_cli()
