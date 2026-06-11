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
    if improved and refresh_prior:
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


def stage2_netflix_prize() -> None:
    """Netflix Prize (100M ratings, 2005) mapped onto the catalog by title+year.

    Netflix users are offset to stay disjoint from MovieLens users; the model
    trains on the combined matrix but the holdout stays the pure-MovieLens
    ``ratings.parquet`` from Stage 1, so adoption is judged on the identical
    benchmark. Netflix popularity is 2005-era, so the prior is NOT refreshed.
    """
    from ml.artifacts import normalize_title

    movies, _ = _catalog()
    key_of: dict[tuple[str, int | None], int] = {}
    for m in movies:
        key_of.setdefault((normalize_title(m["title"]), m["year"]), m["movie_id"])

    nf_dir = RAW / "download"
    mapped: dict[int, int] = {}
    for line in (nf_dir / "movie_titles.txt").read_text(encoding="latin-1").splitlines():
        nf_id, year_s, title = line.split(",", 2)
        year = int(year_s) if year_s.isdigit() else None
        for y in (year, (year - 1) if year else None, (year + 1) if year else None):
            mid = key_of.get((normalize_title(title), y))
            if mid is not None:
                mapped[int(nf_id)] = mid
                break
    print(f"[Stage 2] mapped {len(mapped):,} of 17,770 Netflix movies onto the catalog")

    frames = []
    for i, (nf_id, mid) in enumerate(sorted(mapped.items())):
        f = nf_dir / "training_set" / f"mv_{nf_id:07d}.txt"
        if not f.exists():
            continue
        df = pd.read_csv(f, skiprows=1, header=None, names=["userId", "rating", "d"],
                         usecols=["userId", "rating"], dtype={"userId": np.int64, "rating": np.float32})
        df["movieId"] = mid
        frames.append(df)
        if i % 500 == 0:
            print(f"  parsed {i:,}/{len(mapped):,} movie files...")
    nf = pd.concat(frames, ignore_index=True)
    print(f"[Stage 2] Netflix ratings on catalog titles: {len(nf):,}")
    # Full Netflix (75.6M) outweighs modern MovieLens 3:1 and REGRESSED the
    # holdout (AUC 0.794 -> 0.764): 2005-era preferences swamp the signal.
    # Subsample Netflix users to rough parity with MovieLens instead.
    keep_users = nf["userId"] % 4 == 0  # deterministic ~25% of users
    nf = nf[keep_users]
    nf["userId"] = nf["userId"] + 1_000_000_000  # disjoint from MovieLens ids
    print(f"[Stage 2] after 25% user subsample: {len(nf):,} ratings")

    ml = pd.read_parquet(ARTIFACTS / "ratings.parquet")[["userId", "movieId", "rating"]]
    combined = pd.concat([ml, nf], ignore_index=True)
    _retrain_and_compare(
        combined,
        "Stage 2 — Netflix Prize pretrain (+ML25M, 25% user subsample)",
        [f"- {len(mapped):,}/17,770 Netflix titles mapped by normalized title+year (±1)",
         f"- full-Netflix variant (75.6M ratings) REGRESSED AUC 0.7936 -> 0.7643 (2005-era data swamps modern signal); retried at 25% user parity",
         f"- Netflix adds {len(nf):,} ratings on catalog titles ({nf['userId'].nunique():,} users)"],
        write_parquet=False,   # holdout stays pure MovieLens
        refresh_prior=False,   # 2005-era popularity must not leak into the prior
    )


def stage3_kion_implicit() -> None:
    """MTS Kion implicit watch events (2021 streaming) as pseudo-ratings.

    The closest dataset to real streaming behavior: completion percentage is
    the signal (finish it = like, bail early = dislike). 1,788 of the English-
    translated items map onto the catalog via title_orig/title + year (±1).
    Watch events become pseudo-ratings (>=70% watched -> 4.5, <=20% -> 1.5,
    middle = ambiguous, dropped) and join the MovieLens matrix with offset
    user ids. Holdout stays pure MovieLens; prior untouched.
    """
    from ml.artifacts import normalize_title

    movies, _ = _catalog()
    key_of: dict[tuple[str, int | None], int] = {}
    for m in movies:
        key_of.setdefault((normalize_title(m["title"]), m["year"]), m["movie_id"])

    kion = Path("../experiments/kion/data_en")
    items = pd.read_csv(kion / "items_en.csv", usecols=["item_id", "content_type", "title", "title_orig", "release_year"])
    films = items[items["content_type"] == "film"]
    mapped: dict[int, int] = {}
    for _, r in films.iterrows():
        year = int(r["release_year"]) if pd.notna(r["release_year"]) else None
        for t in (r["title_orig"], r["title"]):
            if pd.isna(t):
                continue
            k = normalize_title(str(t))
            hit = None
            for y in (year, (year - 1) if year else None, (year + 1) if year else None):
                hit = key_of.get((k, y))
                if hit:
                    break
            if hit:
                mapped[int(r["item_id"])] = hit
                break
    print(f"[Stage 3] mapped {len(mapped):,} Kion films onto the catalog")

    inter = pd.read_csv(kion / "interactions.csv", usecols=["user_id", "item_id", "watched_pct"])
    inter = inter[inter["item_id"].isin(mapped)].dropna(subset=["watched_pct"])
    finished = inter["watched_pct"] >= 70
    bailed = inter["watched_pct"] <= 20
    inter = inter[finished | bailed].copy()
    inter["rating"] = np.where(inter["watched_pct"] >= 70, 4.5, 1.5).astype(np.float32)
    kion_df = pd.DataFrame({
        "userId": inter["user_id"].astype(np.int64) + 2_000_000_000,
        "movieId": inter["item_id"].map(mapped),
        "rating": inter["rating"],
    })
    print(f"[Stage 3] Kion pseudo-ratings: {len(kion_df):,} ({kion_df['userId'].nunique():,} users)")

    ml = pd.read_parquet(ARTIFACTS / "ratings.parquet")[["userId", "movieId", "rating"]]
    combined = pd.concat([ml, kion_df], ignore_index=True)
    _retrain_and_compare(
        combined,
        "Stage 3 — MTS Kion implicit watch events (+ML25M)",
        [f"- {len(mapped):,}/12,002 Kion films mapped via title_orig/title + year (±1)",
         f"- completion-as-signal: >=70% watched -> 4.5, <=20% -> 1.5 (middle dropped)",
         f"- adds {len(kion_df):,} pseudo-ratings from {kion_df['userId'].nunique():,} real streaming users"],
        write_parquet=False,
        refresh_prior=False,
    )


def stage4_recent_ratings() -> None:
    """Recency finetune: train only on 2015+ MovieLens ratings.

    The HF ``pinecone/movielens-recent-ratings`` dataset is a loader script
    that downloads ml-25m.zip (already local) and slices recent ratings — so
    the experiment it enables is run directly from the raw data: do factors
    trained only on RECENT preferences predict the (recent-leaning) holdout
    better than factors trained on all 25 years?
    """
    _, movie_order = _catalog()
    keep = set(movie_order)
    cutoff = 1_420_070_400  # 2015-01-01 UTC
    print("Loading full ml-25m/ratings.csv and slicing >= 2015...")
    ratings = pd.read_csv(RAW / "ml-25m" / "ratings.csv")
    ratings = ratings[ratings["movieId"].isin(keep) & (ratings["timestamp"] >= cutoff)]
    active = ratings.groupby("userId").size()
    ratings = ratings[ratings["userId"].isin(active[active >= MIN_USER_RATINGS].index)]
    _retrain_and_compare(
        ratings,
        "Stage 4 — recent ratings only (2015+, HF recent-ratings equivalent)",
        ["- HF pinecone/movielens-recent-ratings is a loader over ml-25m.zip; the slice is reproduced locally",
         "- hypothesis: dropping pre-2015 preferences sharpens modern like/dislike prediction"],
        write_parquet=False,   # keep the established full-history holdout
        refresh_prior=False,
    )


STAGES = {
    1: stage1_movielens_full,
    2: stage2_netflix_prize,
    3: stage3_kion_implicit,
    4: stage4_recent_ratings,
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a CF training stage.")
    ap.add_argument("--stage", type=int, required=True, choices=sorted(STAGES))
    args = ap.parse_args()
    STAGES[args.stage]()


if __name__ == "__main__":
    main()
