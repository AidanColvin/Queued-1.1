"""Offline evaluation of the swipe-prediction accuracy of the Layer-1 reranker.

Question answered: *given a user's past behaviour, how well does the taste
vector predict whether they'll like or dislike the next titles?*

Method (temporal holdout, ground truth = MovieLens ratings):
  1. For each sampled user, take their catalog ratings sorted by time.
  2. Feed the earliest ``1 - holdout_frac`` into the **real** ``SessionReranker``
     (rating >= LIKE_AT -> "liked", <= DISLIKE_AT -> "dismissed"; middling
     ratings are neutral and skipped, mirroring production weights).
  3. On the held-out (most recent) ratings, score each title by the reranker's
     own cosine(session_vector, item_vector) and compare to the true label.

The same holdout is scored in several configurations so improvements are
apples-to-apples, plus a non-personalized popularity baseline and random:
  * ``semantic``  — MiniLM plot-summary embeddings alone.
  * ``cf``        — collaborative-filtering item factors (SVD on ratings).
  * ``hybrid50``  — the original 50/50 semantic/CF blend.
  * ``hybrid``    — the tuned blend (``W_SEMANTIC_ENERGY`` of cosine energy
                    from semantic, the rest CF).
  * ``shipped``   — ``hybrid`` plus the popularity prior
                    (``cosine + POP_BETA * prior``) — what production runs.

Reported metrics:
  * ROC-AUC  — P(a liked title outranks a disliked one). 0.5 = chance.
  * Precision@k — of the top-k titles we'd surface, the fraction actually liked.

Run:  ``python -m ml.evaluate``  (from ``backend``, inside .venv).
Read-only: loads committed artifacts + raw ratings, touches no database.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from ml.artifacts import MovieRecord
from ml.reranker import POP_BETA, SessionReranker, _unit_rows, build_taste_space, popularity_prior

LIKE_AT = 4.0
DISLIKE_AT = 2.0
NEUTRAL_MS = 3000  # ~neutral deliberation -> time_modifier == 1.0
SPACES = ("semantic", "cf", "hybrid50", "hybrid")

ARTIFACTS = Path("data/artifacts")


def _load() -> tuple[dict[str, np.ndarray], dict[int, int], pd.DataFrame, np.ndarray]:
    """Return ({space: item-matrix}, movie_id->idx, catalog ratings, prior)."""
    raw_emb = np.load(ARTIFACTS / "embeddings.npy").astype(np.float32)
    raw_cf = np.load(ARTIFACTS / "cf_item_factors.npy").astype(np.float32)
    semantic = _unit_rows(raw_emb)
    cf = _unit_rows(raw_cf)
    # `hybrid` uses the SAME builder production ships (tuned default weight), so
    # the measured number is exactly what runs live; `hybrid50` is the original
    # 50/50 blend kept as a reference point.
    matrices = {
        "semantic": semantic,
        "cf": cf,
        "hybrid50": build_taste_space(raw_emb, raw_cf, w_semantic=0.5),
        "hybrid": build_taste_space(raw_emb, raw_cf),
    }

    movies = json.loads((ARTIFACTS / "movie_index.json").read_text())["movies"]
    movieid_to_idx = {m["movie_id"]: m["idx"] for m in movies}
    # Same prior production blends in (zeros if the bundle has no rating counts).
    prior = popularity_prior([MovieRecord.from_json(m) for m in movies])
    ratings = pd.read_parquet(ARTIFACTS / "ratings.parquet")
    ratings = ratings[ratings["movieId"].isin(movieid_to_idx)]
    return matrices, movieid_to_idx, ratings, prior


def _auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """ROC-AUC via the rank-sum (Mann-Whitney) identity; handles ties."""
    pos = labels == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = rankdata(scores)
    return (ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def _action(rating: float) -> str | None:
    if rating >= LIKE_AT:
        return "liked"
    if rating <= DISLIKE_AT:
        return "dismissed"
    return None


def evaluate(n_users: int, min_ratings: int, holdout_frac: float, seed: int) -> dict:
    matrices, movieid_to_idx, ratings, prior = _load()
    popularity = ratings.groupby("movieId").size().to_dict()

    counts = ratings.groupby("userId").size()
    eligible = counts[counts >= min_ratings].index.to_numpy()
    rng = np.random.default_rng(seed)
    if len(eligible) > n_users:
        eligible = rng.choice(eligible, size=n_users, replace=False)
    sample = ratings[ratings["userId"].isin(eligible)].sort_values(["userId", "timestamp"])

    # Pooled (score, label) per config, plus popularity; per-user precision@k.
    configs = (*SPACES, "shipped", "popularity")
    pooled = {c: [] for c in configs}
    labels_all: list[int] = []
    p_at = {c: {5: [], 10: []} for c in configs}
    n_eval_users = 0

    for _uid, grp in sample.groupby("userId", sort=False):
        rows = grp.to_dict("records")
        cut = int(len(rows) * (1 - holdout_frac))
        train, held = rows[:cut], rows[cut:]

        judged = [
            (r["movieId"], 1 if r["rating"] >= LIKE_AT else 0)
            for r in held
            if r["rating"] >= LIKE_AT or r["rating"] <= DISLIKE_AT
        ]
        labels = np.array([lab for _, lab in judged])
        if labels.size == 0 or labels.sum() in (0, labels.size):
            continue  # need both a like and a dislike held out
        idxs = np.array([movieid_to_idx[mid] for mid, _ in judged])

        # Score the held-out items in each space with the real reranker logic.
        space_scores = {}
        usable = False
        for space, matrix in matrices.items():
            rr = SessionReranker(matrix, movieid_to_idx)
            for r in train:
                act = _action(r["rating"])
                if act:
                    rr.update(r["movieId"], act, NEUTRAL_MS)
            norm = float(np.linalg.norm(rr.session_vector))
            if norm == 0.0:
                space_scores[space] = None
            else:
                space_scores[space] = matrix[idxs] @ (rr.session_vector / norm)
                usable = True
        if not usable:
            continue
        # The shipped config: tuned hybrid cosine + the popularity prior.
        hybrid_sc = space_scores["hybrid"]
        space_scores["shipped"] = (
            hybrid_sc + POP_BETA * prior[idxs] if hybrid_sc is not None else None
        )
        pop = np.array([float(popularity.get(mid, 0.0)) for mid, _ in judged])

        labels_all.extend(labels.tolist())
        for col in (*SPACES, "shipped"):
            sc = space_scores[col]
            pooled[col].extend((sc if sc is not None else np.zeros(labels.size)).tolist())
        pooled["popularity"].extend(pop.tolist())
        n_eval_users += 1

        for k in (5, 10):
            if labels.size >= k:
                for col in (*SPACES, "shipped"):
                    sc = space_scores[col]
                    if sc is not None:
                        p_at[col][k].append(labels[np.argsort(-sc)[:k]].mean())
                p_at["popularity"][k].append(labels[np.argsort(-pop)[:k]].mean())

    label = np.array(labels_all)
    out = {"users_evaluated": n_eval_users, "holdout_judgments": int(label.size),
           "like_rate": float(label.mean()), "rows": {}}
    for col in configs:
        sc = np.array(pooled[col])
        out["rows"][col] = {
            "auc": _auc(sc, label),
            "p@5": float(np.mean(p_at[col][5])) if p_at[col][5] else float("nan"),
            "p@10": float(np.mean(p_at[col][10])) if p_at[col][10] else float("nan"),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate swipe-prediction accuracy.")
    ap.add_argument("--users", type=int, default=4000)
    ap.add_argument("--min-ratings", type=int, default=15)
    ap.add_argument("--holdout", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    r = evaluate(args.users, args.min_ratings, args.holdout, args.seed)
    base = r["like_rate"]
    print("\n=== NextWatch swipe-prediction accuracy (offline, temporal holdout) ===")
    print(f"users evaluated    : {r['users_evaluated']:,}")
    print(f"held-out judgments : {r['holdout_judgments']:,}  (like rate {base:.1%})\n")
    print(f"{'configuration':<14}{'ROC-AUC':>10}{'P@5':>9}{'P@10':>9}")
    print("-" * 42)
    label_for = {
        "semantic": "semantic",
        "cf": "cf",
        "hybrid50": "hybrid50",
        "hybrid": "hybrid",
        "shipped": "shipped*",
        "popularity": "popularity",
    }
    for col in (*SPACES, "shipped", "popularity"):
        m = r["rows"][col]
        print(f"{label_for[col]:<14}{m['auc']:>10.3f}{m['p@5']:>9.3f}{m['p@10']:>9.3f}")
    print(f"{'random':<14}{0.5:>10.3f}{base:>9.3f}{base:>9.3f}")
    print("\n* = what production uses (tuned hybrid + popularity prior). "
          "AUC = P(liked title outranks disliked); 0.5 = chance, 1.0 = perfect.\n")


if __name__ == "__main__":
    main()
