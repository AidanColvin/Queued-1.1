"""Multi-dataset CF training stages for the like/dislike predictor.

Each stage retrains the collaborative item factors from a bigger or different
ratings source, WITHOUT touching the catalog: the 5,462 rows of
``movie_index.json`` (and their aligned embeddings/posters/trailers the
frontend depends on) are the fixed item vocabulary; external datasets are
mapped onto it. After every stage the same offline holdout (``ml.evaluate``)
judges old vs new factors apples-to-apples, and the result is appended to
``docs/TRAINING_LOG.md``.

Stages:
  1  Full MovieLens 25M (we previously trained on a 10% user sample).
  2  Netflix Prize pretrain (title+year mapped onto the catalog).
  3  MTS Kion feasibility (implicit RU-streaming events).
  4  Hugging Face movielens-recent-ratings recency slice.
  5  Kaggle 20M ratings+tags (redundancy check vs 25M).

Run from ``backend``: ``python -m ml.train_stages --stage 1``
Raw datasets stay in ``data/raw`` (gitignored); only the small retrained
``cf_item_factors.npy`` + refreshed ``rating_count`` prior are committed.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from ml.collaborative import train_svd

ARTIFACTS = Path("data/artifacts")
RAW = Path("data/raw")
LOG = Path("../docs/TRAINING_LOG.md")

# Same activity floor the original preprocess used: casual raters add noise.
MIN_USER_RATINGS = 5


def _catalog() -> tuple[list[dict], list[int]]:
    index = json.loads((ARTIFACTS / "movie_index.json").read_text())
    movies = index["movies"]
    return movies, [m["movie_id"] for m in movies]


def _evaluate_factors(tag: str) -> dict:
    """Run the standard holdout eval against whatever artifacts are on disk."""
    from ml.evaluate import evaluate

    r = evaluate(n_users=4000, min_ratings=15, holdout_frac=0.3, seed=42)
    rows = r["rows"]
    return {
        "tag": tag,
        "users": r["users_evaluated"],
        "judgments": r["holdout_judgments"],
        "cf_auc": rows["cf"]["auc"],
        "shipped_auc": rows["shipped"]["auc"],
        "shipped_p5": rows["shipped"]["p@5"],
        "shipped_p10": rows["shipped"]["p@10"],
    }


def _append_log(stage: str, lines: list[str]) -> None:
    LOG.parent.mkdir(exist_ok=True)
    header = "# Training log\n\nOne entry per dataset stage. Metric = ml.evaluate temporal holdout (AUC / P@k), same protocol every stage.\n"
    text = LOG.read_text() if LOG.exists() else header
    text += f"\n## {stage}\n\n" + "\n".join(lines) + "\n"
    LOG.write_text(text)


def _retrain_and_compare(
    ratings: pd.DataFrame,
    stage_name: str,
    extra_notes: list[str],
    write_parquet: bool = True,
    refresh_prior: bool = True,
) -> None:
    """Shared tail of every stage: eval old factors, train, eval new, log.

    ``ratings`` is the TRAINING matrix (userId / movieId / rating, movieId in
    catalog vocabulary). The EVAL holdout always comes from
    ``artifacts/ratings.parquet``; pass ``write_parquet=False`` when training
    on an augmented corpus (e.g. +Netflix) so the benchmark stays the pure
    MovieLens holdout and stages remain comparable. ``refresh_prior=False``
    keeps the MovieLens rating counts as the popularity prior when the extra
    corpus's popularity is stale (e.g. 2005-era Netflix).
    """
    movies, movie_order = _catalog()
    factors_path = ARTIFACTS / "cf_item_factors.npy"
    backup = ARTIFACTS / "cf_item_factors.prev.npy"

    print(f"[{stage_name}] ratings: {len(ratings):,} rows, "
          f"{ratings['userId'].nunique():,} users, {ratings['movieId'].nunique():,} movies")
    if write_parquet:
        ratings.to_parquet(ARTIFACTS / "ratings.parquet")

    # Baseline: OLD factors scored on the NEW holdout (same data both runs).
    before = _evaluate_factors("old-factors")
    print(f"[{stage_name}] baseline (old factors): shipped AUC {before['shipped_auc']:.4f} "
          f"P@5 {before['shipped_p5']:.4f}")

    shutil.copy(factors_path, backup)
    factors = train_svd(ratings, movie_order, n_factors=50)
    np.save(factors_path, factors)

    after = _evaluate_factors("new-factors")
    print(f"[{stage_name}] retrained:             shipped AUC {after['shipped_auc']:.4f} "
          f"P@5 {after['shipped_p5']:.4f}")

    improved = after["shipped_auc"] >= before["shipped_auc"]
    if not improved:
        shutil.copy(backup, factors_path)
        print(f"[{stage_name}] REGRESSION — old factors restored.")

    # Refresh the popularity prior from this (larger) ratings source.
    if improved:
        counts = ratings.groupby("movieId").size().to_dict()
        for m in movies:
            m["rating_count"] = int(counts.get(m["movie_id"], 0))
        index = json.loads((ARTIFACTS / "movie_index.json").read_text())
        index["movies"] = movies
        index["meta"]["cf_trained"] = True
        index["meta"]["cf_source"] = stage_name
        (ARTIFACTS / "movie_index.json").write_text(json.dumps(index, indent=2))

    _append_log(stage_name, [
        *extra_notes,
        f"- ratings: {len(ratings):,} rows / {ratings['userId'].nunique():,} users "
        f"({before['judgments']:,} holdout judgments, {before['users']:,} eval users)",
        f"- old factors: shipped AUC {before['shipped_auc']:.4f}, P@5 {before['shipped_p5']:.4f}, P@10 {before['shipped_p10']:.4f} (cf-only AUC {before['cf_auc']:.4f})",
        f"- new factors: shipped AUC {after['shipped_auc']:.4f}, P@5 {after['shipped_p5']:.4f}, P@10 {after['shipped_p10']:.4f} (cf-only AUC {after['cf_auc']:.4f})",
        f"- verdict: {'ADOPTED' if improved else 'REJECTED (regression — old factors kept)'}",
    ])
    backup.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
def stage1_movielens_full() -> None:
    """Full 25M ratings (prior model used a 10% user sample) on the catalog."""
    _, movie_order = _catalog()
    keep = set(movie_order)
    print("Loading full ml-25m/ratings.csv (25M rows)...")
    ratings = pd.read_csv(RAW / "ml-25m" / "ratings.csv")
    ratings = ratings[ratings["movieId"].isin(keep)]
    active = ratings.groupby("userId").size()
    ratings = ratings[ratings["userId"].isin(active[active >= MIN_USER_RATINGS].index)]
    _retrain_and_compare(
        ratings,
        "Stage 1 — MovieLens 25M (full)",
        ["- previous factors were trained on a 10% user sample (2.33M ratings)"],
    )


STAGES = {1: stage1_movielens_full}


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a CF training stage.")
    ap.add_argument("--stage", type=int, required=True, choices=sorted(STAGES))
    args = ap.parse_args()
    STAGES[args.stage]()


if __name__ == "__main__":
    main()
