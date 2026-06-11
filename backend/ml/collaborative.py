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


def train_svd(ratings, movie_order: list[int], n_factors: int = 50) -> np.ndarray:
    """Learn latent item factors by truncated SVD of the user-item matrix.

    Builds the sparse ``(users × items)`` rating matrix and factorizes it with
    scikit-learn's :class:`~sklearn.decomposition.TruncatedSVD` (the standard,
    NumPy-2-safe matrix-factorization path; scikit-surprise's compiled SVD is
    incompatible with NumPy 2). The item latent vectors are ``components_.T``,
    aligned to ``movie_order``. Items absent from the ratings get a (near-)zero
    factor — :func:`cf_scores` treats those as non-matches.

    Args:
        ratings: A DataFrame with columns ``userId, movieId, rating``.
        movie_order: MovieLens ``movieId`` values in catalog (row) order.
        n_factors: Latent dimension.

    Returns:
        An ``(len(movie_order), n_factors)`` float32 factor matrix.
    """
    import scipy.sparse as sp
    from sklearn.decomposition import TruncatedSVD

    col_of = {mid: i for i, mid in enumerate(movie_order)}
    df = ratings[ratings["movieId"].isin(col_of)]
    users = df["userId"].unique()
    row_of = {u: i for i, u in enumerate(users)}

    rows = df["userId"].map(row_of).to_numpy()
    cols = df["movieId"].map(col_of).to_numpy()
    vals = df["rating"].to_numpy(dtype=np.float32)
    matrix = sp.csr_matrix((vals, (rows, cols)), shape=(len(users), len(movie_order)))

    k = max(1, min(n_factors, min(matrix.shape) - 1))
    svd = TruncatedSVD(n_components=k, random_state=42)
    svd.fit(matrix)
    factors = svd.components_.T.astype(np.float32)  # (n_items, k)

    if factors.shape[1] < n_factors:  # pad to the requested width
        pad = np.zeros((factors.shape[0], n_factors - factors.shape[1]), dtype=np.float32)
        factors = np.hstack([factors, pad])
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

    # Fold in any supplemental rating sources (e.g. the Netflix Prize set built
    # by `data.ingest_netflix`). Same schema, disjoint user-id space; absent the
    # file this is a no-op so the default MovieLens-only training is unchanged.
    netflix_path = art / "netflix_ratings.parquet"
    if netflix_path.exists():
        extra = pd.read_parquet(netflix_path)
        print(f"  + {len(extra):,} supplemental ratings from {netflix_path.name}")
        ratings = pd.concat([ratings, extra[ratings.columns]], ignore_index=True)

    print(f"Training SVD on {len(ratings):,} ratings over {len(movie_order):,} movies...")
    factors = train_svd(ratings, movie_order)
    np.save(Path(art) / CF_FACTORS_FILE, factors)
    print(f"Saved {factors.shape} CF factors -> {art / CF_FACTORS_FILE}")


if __name__ == "__main__":
    _train_cli()
