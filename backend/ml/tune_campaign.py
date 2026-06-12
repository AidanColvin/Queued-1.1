"""Large-scale tuning campaign for the predictive model (guess -> validate).

Evaluates a full grid over five model dimensions — each grid point is one
complete train/guess/check cycle against real user histories — then validates
the winner on an untouched user pool across multiple seeds, reporting accuracy
at multiple horizons (the next 5 / 10 / 20 cards), not just one card ahead.

Dimensions swept (all closed-form, so thousands of cycles cost minutes):
  * ``decay``     — per-swipe recency decay of the taste vector
                    (``v = decay * v + w * item``): recent swipes count more.
  * ``dislike``   — magnitude of the dismiss signal relative to a like.
  * ``w_sem``     — semantic share of the hybrid space's cosine energy.
  * ``beta``      — popularity-prior weight.
  * ``gamma``     — QUALITY-prior weight (per-item mean rating, a signal the
                    model previously ignored: popular-but-bad vs popular-and-
                    good titles scored identically).

Protocol (no leakage):
  1. Users are split into disjoint TUNE / TEST pools (fixed master seed).
  2. The quality prior is computed from TUNE users' ratings only, so TEST
     validation never sees its own data in the item statistics.
  3. Each user's earliest 70% of ratings trains their vector with the real
     production semantics; the held-out 30% (time-ordered) is what we guess.
  4. The best TUNE config must beat the shipped config on EVERY seed of the
     TEST pool to be declared an upgrade.

Horizons: metrics are also computed on just the FIRST 5 / 10 / 20 held-out
judgments per user (time order) — "if the model froze right now, how good are
its guesses for the next 5/10/20 cards the user will actually judge?"

Run:  ``python -m ml.tune_campaign``  (from ``backend``; needs
``data/artifacts/ratings.parquet`` — see ``ml.evaluate``).
Read-only: changes nothing by itself.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.artifacts import MovieRecord
from ml.evaluate import DISLIKE_AT, LIKE_AT, _auc
from ml.reranker import POP_BETA, W_SEMANTIC_ENERGY, _unit_rows, popularity_prior

ARTIFACTS = Path("data/artifacts")
HOLDOUT_FRAC = 0.3
HORIZONS = (5, 10, 20)

# The shipped configuration, expressed in this script's dimensions.
SHIPPED = {"decay": 1.0, "dislike": 0.55, "w_sem": W_SEMANTIC_ENERGY, "beta": POP_BETA, "gamma": 0.0}


def _load_arrays():
    semantic = _unit_rows(np.load(ARTIFACTS / "embeddings.npy").astype(np.float32)).astype(np.float64)
    cf = _unit_rows(np.load(ARTIFACTS / "cf_item_factors.npy").astype(np.float32)).astype(np.float64)
    movies = json.loads((ARTIFACTS / "movie_index.json").read_text())["movies"]
    movieid_to_idx = {m["movie_id"]: m["idx"] for m in movies}
    pop_prior = popularity_prior([MovieRecord.from_json(m) for m in movies]).astype(np.float64)
    return semantic, cf, movieid_to_idx, pop_prior


def quality_prior_from(ratings: pd.DataFrame, movieid_to_idx: dict[int, int], n_items: int,
                       shrink: float = 50.0) -> np.ndarray:
    """Per-item quality prior in ``[-1, 1]`` from a ratings frame.

    Mean rating mapped from the 1-5 scale to ``(mean - 3) / 2`` and shrunk
    toward 0 by evidence (``n / (n + shrink)``), so a 5.0 from three raters
    doesn't outrank a 4.4 from ten thousand. Items absent from the frame get 0
    (the prior is a no-op for them).
    """
    q = np.zeros(n_items, dtype=np.float64)
    stats = ratings.groupby("movieId")["rating"].agg(["mean", "size"])
    for mid, row in stats.iterrows():
        idx = movieid_to_idx.get(int(mid))
        if idx is not None:
            q[idx] = ((row["mean"] - 3.0) / 2.0) * (row["size"] / (row["size"] + shrink))
    return q


def _user_stats(rows, movieid_to_idx, semantic, cf, pop_prior, q_prior, decays):
    """Per-user sufficient statistics enabling a fully closed-form grid.

    The taste vector for any (decay, dislike) is ``P(decay) - dislike * N(decay)``
    per block, where P/N are decay-weighted sums of liked/disliked unit rows.
    Everything any grid point needs reduces to dot products against P and N.
    """
    cut = int(len(rows) * (1 - HOLDOUT_FRAC))
    train, held = rows[:cut], rows[cut:]

    judged = [(r["movieId"], 1 if r["rating"] >= LIKE_AT else 0)
              for r in held if r["rating"] >= LIKE_AT or r["rating"] <= DISLIKE_AT]
    labels = np.array([lab for _, lab in judged])
    if labels.size == 0 or labels.sum() in (0, labels.size):
        return None

    signed = [(movieid_to_idx[r["movieId"]], 1.0 if r["rating"] >= LIKE_AT else -1.0)
              for r in train if r["rating"] >= LIKE_AT or r["rating"] <= DISLIKE_AT]
    if not signed:
        return None
    idxs = np.array([movieid_to_idx[mid] for mid, _ in judged])
    held_sem, held_cf = semantic[idxs], cf[idxs]

    per_decay = {}
    n = len(signed)
    for decay in decays:
        # age = number of later training signals; most recent has age 0.
        ages = np.array([n - 1 - k for k in range(n)], dtype=np.float64)
        wts = decay ** ages
        pos = np.array([w if s > 0 else 0.0 for (_, s), w in zip(signed, wts)])
        neg = np.array([w if s < 0 else 0.0 for (_, s), w in zip(signed, wts)])
        rows_idx = np.array([i for i, _ in signed])
        sem_p = pos @ semantic[rows_idx]
        sem_n = neg @ semantic[rows_idx]
        cf_p = pos @ cf[rows_idx]
        cf_n = neg @ cf[rows_idx]
        per_decay[decay] = {
            "sp_dot": held_sem @ sem_p, "sn_dot": held_sem @ sem_n,
            "cp_dot": held_cf @ cf_p, "cn_dot": held_cf @ cf_n,
            "spp": sem_p @ sem_p, "spn": sem_p @ sem_n, "snn": sem_n @ sem_n,
            "cpp": cf_p @ cf_p, "cpn": cf_p @ cf_n, "cnn": cf_n @ cf_n,
        }
    return {"labels": labels, "pop": pop_prior[idxs], "q": q_prior[idxs], "per_decay": per_decay}


def _config_scores(st, decay, dislike, w, beta, gamma):
    d = st["per_decay"][decay]
    s_dot = d["sp_dot"] - dislike * d["sn_dot"]
    c_dot = d["cp_dot"] - dislike * d["cn_dot"]
    s_norm2 = d["spp"] - 2 * dislike * d["spn"] + dislike**2 * d["snn"]
    c_norm2 = d["cpp"] - 2 * dislike * d["cpn"] + dislike**2 * d["cnn"]
    denom = np.sqrt(w * s_norm2 + (1.0 - w) * c_norm2)
    if denom == 0.0:
        return None
    cosine = (w * s_dot + (1.0 - w) * c_dot) / denom
    return cosine + beta * st["pop"] + gamma * st["q"]


def _evaluate(stats, cfg) -> dict:
    """Pooled AUC + per-user P@5/P@10 + horizon AUCs for one configuration."""
    pooled_s, pooled_l = [], []
    p5, p10 = [], []
    hor = {h: ([], []) for h in HORIZONS}
    for st in stats:
        sc = _config_scores(st, cfg["decay"], cfg["dislike"], cfg["w_sem"], cfg["beta"], cfg["gamma"])
        if sc is None:
            continue
        labels = st["labels"]
        pooled_s.append(sc)
        pooled_l.append(labels)
        if labels.size >= 5:
            p5.append(labels[np.argsort(-sc)[:5]].mean())
        if labels.size >= 10:
            p10.append(labels[np.argsort(-sc)[:10]].mean())
        for h in HORIZONS:  # the next-h judged cards, in time order
            s_h, l_h = sc[:h], labels[:h]
            if l_h.size and 0 < l_h.sum() < l_h.size:
                hor[h][0].append(s_h)
                hor[h][1].append(l_h)
    out = {
        "auc": _auc(np.concatenate(pooled_s), np.concatenate(pooled_l)),
        "p@5": float(np.mean(p5)) if p5 else float("nan"),
        "p@10": float(np.mean(p10)) if p10 else float("nan"),
    }
    for h in HORIZONS:
        s, l = hor[h]
        out[f"auc@next{h}"] = _auc(np.concatenate(s), np.concatenate(l)) if s else float("nan")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Grid campaign over the predictive model dimensions.")
    ap.add_argument("--users", type=int, default=3000)
    ap.add_argument("--min-ratings", type=int, default=15)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 2026])
    args = ap.parse_args()

    semantic, cf, movieid_to_idx, pop_prior = _load_arrays()
    ratings = pd.read_parquet(ARTIFACTS / "ratings.parquet")
    ratings = ratings[ratings["movieId"].isin(movieid_to_idx)]
    counts = ratings.groupby("userId").size()
    eligible = counts[counts >= args.min_ratings].index.to_numpy().copy()
    rng = np.random.default_rng(1234)
    rng.shuffle(eligible)
    half = len(eligible) // 2
    tune_pool, test_pool = eligible[:half], eligible[half:]

    # Quality prior from TUNE users only — TEST validation never sees its own
    # ratings inside the item statistics.
    q_prior = quality_prior_from(ratings[ratings["userId"].isin(tune_pool)],
                                 movieid_to_idx, semantic.shape[0])

    grid = {
        "decay": [1.0, 0.995, 0.98, 0.95, 0.9, 0.8],
        "dislike": [0.25, 0.55, 0.8, 1.0],
        "w_sem": [0.10, 0.15, 0.20],
        "beta": [0.75, 1.0, 1.25, 1.5],
        "gamma": [0.0, 0.25, 0.5, 0.75, 1.0],
    }
    n_points = int(np.prod([len(v) for v in grid.values()]))

    def collect(pool, seed):
        r = np.random.default_rng(seed)
        chosen = r.choice(pool, size=min(args.users, len(pool)), replace=False)
        sub = ratings[ratings["userId"].isin(chosen)].sort_values(["userId", "timestamp"])
        stats = []
        for _uid, grp in sub.groupby("userId", sort=False):
            st = _user_stats(grp.to_dict("records"), movieid_to_idx, semantic, cf,
                             pop_prior, q_prior, grid["decay"])
            if st is not None:
                stats.append(st)
        return stats

    print(f"eligible users {len(eligible):,} (tune {len(tune_pool):,} / test {len(test_pool):,}); "
          f"grid points: {n_points:,}")
    tune_stats = collect(tune_pool, args.seeds[0])
    print(f"tune users evaluated: {len(tune_stats):,}; "
          f"running {n_points:,} train/guess/validate cycles...\n")

    results: dict[tuple, float] = {}
    for combo in itertools.product(*grid.values()):
        cfg = dict(zip(grid.keys(), combo))
        results[combo] = _evaluate(tune_stats, cfg)["auc"]

    ranked = sorted(results.items(), key=lambda kv: kv[1], reverse=True)
    print("top 10 on TUNE:")
    for combo, auc in ranked[:10]:
        print("  " + " ".join(f"{k}={v}" for k, v in zip(grid.keys(), combo)) + f"  AUC {auc:.4f}")

    shipped_combo = tuple(SHIPPED[k] for k in grid.keys())
    shipped_auc = results.get(shipped_combo) or _evaluate(tune_stats, SHIPPED)["auc"]
    best = dict(zip(grid.keys(), ranked[0][0]))
    print(f"\nshipped on TUNE: AUC {shipped_auc:.4f}  ({SHIPPED})")

    print("\nvalidation on untouched TEST users (full + horizon metrics):")
    wins = 0
    for seed in args.seeds:
        test_stats = collect(test_pool, seed + 1)
        m_best = _evaluate(test_stats, best)
        m_ship = _evaluate(test_stats, SHIPPED)
        wins += m_best["auc"] > m_ship["auc"]
        print(f"  seed {seed}: best AUC {m_best['auc']:.4f} vs shipped {m_ship['auc']:.4f}  "
              f"{'WIN' if m_best['auc'] > m_ship['auc'] else 'no win'}")
        for h in HORIZONS:
            print(f"    next-{h:<3} best {m_best[f'auc@next{h}']:.4f} vs shipped {m_ship[f'auc@next{h}']:.4f}"
                  f"   |  P@5 {m_best['p@5']:.3f} vs {m_ship['p@5']:.3f}")
    verdict = "ADOPT" if wins == len(args.seeds) else "KEEP SHIPPED"
    print(f"\nverdict: {verdict} ({wins}/{len(args.seeds)} seeds won)")
    print("winner:", best)


if __name__ == "__main__":
    main()
