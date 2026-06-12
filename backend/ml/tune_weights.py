"""Determine the production blend weights from a large public ratings dataset.

The two scalars that shape every prediction — ``W_SEMANTIC_ENERGY`` (how much
of the taste space's cosine energy is semantic vs collaborative) and
``POP_BETA`` (the popularity-prior weight) — are swept against real user
histories with a train/test protocol:

  1. Eligible users (>= ``min_ratings`` catalog ratings) are split into
     disjoint TUNE and TEST sets.
  2. For each user, the earliest 70% of ratings build their taste vector with
     the real production weights (``SessionReranker`` semantics); the held-out
     30% are scored and compared to what the user actually rated.
  3. The (w_semantic, pop_beta) grid is evaluated on TUNE users; the winner is
     then validated on the untouched TEST users across multiple seeds and is
     only reported as an upgrade if it beats the shipped config on EVERY seed.

The sweep is closed-form: a user's hybrid-space vector is the concatenation of
their (scaled) semantic and CF block sums, so for any ``w``::

    cosine = (w * S + (1 - w) * C) / sqrt(w * |A|^2 + (1 - w) * |B|^2)

where ``S``/``C`` are the per-item dot products against the user's semantic /
CF block sums — computed once per user, reused for every grid point. A full
grid over ~6,000 users costs seconds instead of hours.

Run:  ``python -m ml.tune_weights``  (from ``backend``; needs
``data/artifacts/ratings.parquet`` — see ``ml.evaluate`` for the schema).
Read-only: touches no database and changes nothing by itself.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.artifacts import MovieRecord
from ml.evaluate import DISLIKE_AT, LIKE_AT, _auc
from ml.reranker import POP_BETA, SIGNAL_WEIGHTS, W_SEMANTIC_ENERGY, _unit_rows, popularity_prior

ARTIFACTS = Path("data/artifacts")
HOLDOUT_FRAC = 0.3


def _signal(rating: float) -> float | None:
    """Map a rating to the production swipe weight (None = neutral, skipped)."""
    if rating >= LIKE_AT:
        return SIGNAL_WEIGHTS["liked"]
    if rating <= DISLIKE_AT:
        return SIGNAL_WEIGHTS["dismissed"]
    return None


def _user_stats(rows, movieid_to_idx, semantic, cf, prior):
    """Per-user sufficient statistics for the closed-form sweep.

    Returns ``None`` when the user has no usable signal or a one-sided holdout.
    """
    cut = int(len(rows) * (1 - HOLDOUT_FRAC))
    train, held = rows[:cut], rows[cut:]

    judged = [(r["movieId"], 1 if r["rating"] >= LIKE_AT else 0)
              for r in held if r["rating"] >= LIKE_AT or r["rating"] <= DISLIKE_AT]
    labels = np.array([lab for _, lab in judged])
    if labels.size == 0 or labels.sum() in (0, labels.size):
        return None

    sem_sum = np.zeros(semantic.shape[1], dtype=np.float64)
    cf_sum = np.zeros(cf.shape[1], dtype=np.float64)
    any_signal = False
    for r in train:
        w = _signal(r["rating"])
        if w is None:
            continue
        idx = movieid_to_idx[r["movieId"]]
        sem_sum += w * semantic[idx]
        cf_sum += w * cf[idx]
        any_signal = True
    if not any_signal:
        return None

    idxs = np.array([movieid_to_idx[mid] for mid, _ in judged])
    return {
        "labels": labels,
        "s_dot": semantic[idxs] @ sem_sum,   # semantic block dots
        "c_dot": cf[idxs] @ cf_sum,          # CF block dots
        "s_norm2": float(sem_sum @ sem_sum),
        "c_norm2": float(cf_sum @ cf_sum),
        "prior": prior[idxs],
    }


def _score_grid(stats: list[dict], w: float, beta: float) -> float:
    """Pooled ROC-AUC of ``shrunk-free`` production scoring at one grid point."""
    scores, labels = [], []
    for st in stats:
        denom = np.sqrt(w * st["s_norm2"] + (1.0 - w) * st["c_norm2"])
        if denom == 0.0:
            continue
        cosine = (w * st["s_dot"] + (1.0 - w) * st["c_dot"]) / denom
        scores.append(cosine + beta * st["prior"])
        labels.append(st["labels"])
    return _auc(np.concatenate(scores), np.concatenate(labels))


def _collect(sample: pd.DataFrame, movieid_to_idx, semantic, cf, prior) -> list[dict]:
    stats = []
    for _uid, grp in sample.groupby("userId", sort=False):
        st = _user_stats(grp.to_dict("records"), movieid_to_idx, semantic, cf, prior)
        if st is not None:
            stats.append(st)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Determine blend weights from public ratings data.")
    ap.add_argument("--users", type=int, default=3000, help="users per split")
    ap.add_argument("--min-ratings", type=int, default=15)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 2026])
    args = ap.parse_args()

    semantic = _unit_rows(np.load(ARTIFACTS / "embeddings.npy").astype(np.float32))
    cf = _unit_rows(np.load(ARTIFACTS / "cf_item_factors.npy").astype(np.float32))
    movies = json.loads((ARTIFACTS / "movie_index.json").read_text())["movies"]
    movieid_to_idx = {m["movie_id"]: m["idx"] for m in movies}
    prior = popularity_prior([MovieRecord.from_json(m) for m in movies])

    ratings = pd.read_parquet(ARTIFACTS / "ratings.parquet")
    ratings = ratings[ratings["movieId"].isin(movieid_to_idx)]
    counts = ratings.groupby("userId").size()
    eligible = counts[counts >= args.min_ratings].index.to_numpy().copy()

    # Disjoint TUNE / TEST user pools (fixed master seed so the split is stable).
    rng = np.random.default_rng(1234)
    rng.shuffle(eligible)
    half = len(eligible) // 2
    tune_pool, test_pool = eligible[:half], eligible[half:]

    w_grid = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
    beta_grid = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5]

    def sample_stats(pool, seed):
        r = np.random.default_rng(seed)
        chosen = r.choice(pool, size=min(args.users, len(pool)), replace=False)
        sub = ratings[ratings["userId"].isin(chosen)].sort_values(["userId", "timestamp"])
        return _collect(sub, movieid_to_idx, semantic, cf, prior)

    print(f"eligible users: {len(eligible):,} (tune {len(tune_pool):,} / test {len(test_pool):,})")
    tune_stats = sample_stats(tune_pool, args.seeds[0])
    print(f"tune users evaluated: {len(tune_stats):,}\n")

    print(f"{'w_sem':>6} {'beta':>6} {'AUC':>8}")
    results = {}
    for w in w_grid:
        for beta in beta_grid:
            auc = _score_grid(tune_stats, w, beta)
            results[(w, beta)] = auc
            print(f"{w:>6.2f} {beta:>6.2f} {auc:>8.4f}")

    best = max(results, key=results.get)
    shipped = (W_SEMANTIC_ENERGY, POP_BETA)
    print(f"\nbest on TUNE : w_sem={best[0]:.2f} beta={best[1]:.2f} (AUC {results[best]:.4f})")
    print(f"shipped      : w_sem={shipped[0]:.2f} beta={shipped[1]:.2f} (AUC {results.get(shipped, float('nan')):.4f})")

    print("\nvalidation on untouched TEST users:")
    wins = 0
    for seed in args.seeds:
        test_stats = sample_stats(test_pool, seed + 1)
        a_best = _score_grid(test_stats, *best)
        a_ship = _score_grid(test_stats, *shipped)
        wins += a_best > a_ship
        print(f"  seed {seed:<6} best {a_best:.4f}  vs shipped {a_ship:.4f}  "
              f"{'WIN' if a_best > a_ship else 'no win'}")
    verdict = "ADOPT" if wins == len(args.seeds) and best != shipped else "KEEP SHIPPED"
    print(f"\nverdict: {verdict} ({wins}/{len(args.seeds)} seeds won)")


if __name__ == "__main__":
    main()
