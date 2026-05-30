"""Preprocess the raw datasets into the artifact bundle (REAL pipeline).

Pipeline (mirrors the README's "ML pipeline" section):

1. Load ``ratings.csv``, ``movies.csv``, ``tags.csv``, ``links.csv``.
2. Keep movies with >= 50 ratings and users with >= 20 ratings.
3. Persist the filtered ratings to ``ratings.parquet`` for the SVD step.
4. Build the catalog: canonical title/year (IMDb), genres + top tags (MovieLens),
   and overview/poster (TMDB, rate-limited + cached).
5. Compute the TF-IDF content matrix and the semantic embedding matrix.
6. Save the artifact bundle (CF factors start as a zero placeholder and are
   filled in by ``python -m ml.collaborative``).

Run after :mod:`data.download`:

    pip install -r requirements-train.txt
    python -m data.preprocess --sample-frac 0.1   # fast dev (10% of users)
    python -m ml.collaborative                     # train CF factors

Needs ``TMDB_API_KEY`` in the environment for the overview/poster enrichment.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from tqdm import tqdm

from config import get_settings
from ml.artifacts import ArtifactBundle, MovieRecord, save_artifacts
from ml.collaborative import DEFAULT_N_FACTORS
from ml.content import TfidfBuilder
from ml.embeddings import get_embedder

RAW_DIR = Path(__file__).resolve().parent / "raw"
ML_DIR = RAW_DIR / "ml-25m"

MIN_RATINGS_PER_MOVIE = 50
MIN_RATINGS_PER_USER = 20
TOP_TAGS_PER_MOVIE = 6
TMDB_SLEEP = 0.25  # seconds between TMDB calls (free-tier courtesy)
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"


# --------------------------------------------------------------------------- #
# Ratings
# --------------------------------------------------------------------------- #
def load_and_filter_ratings(sample_frac: float = 1.0) -> pd.DataFrame:
    """Load ratings and apply the popularity/activity filters.

    Args:
        sample_frac: Fraction of users to keep (deterministic) for fast dev.

    Returns:
        Filtered ratings DataFrame (``userId, movieId, rating, timestamp``).
    """
    ratings = pd.read_csv(ML_DIR / "ratings.csv")

    if sample_frac < 1.0:
        users = ratings["userId"].drop_duplicates()
        keep = users.sample(frac=sample_frac, random_state=42)
        ratings = ratings[ratings["userId"].isin(keep)]

    movie_counts = ratings["movieId"].value_counts()
    good_movies = movie_counts[movie_counts >= MIN_RATINGS_PER_MOVIE].index
    ratings = ratings[ratings["movieId"].isin(good_movies)]

    user_counts = ratings["userId"].value_counts()
    good_users = user_counts[user_counts >= MIN_RATINGS_PER_USER].index
    ratings = ratings[ratings["userId"].isin(good_users)]

    print(
        f"Filtered ratings: {len(ratings):,} rows, "
        f"{ratings['userId'].nunique():,} users, {ratings['movieId'].nunique():,} movies"
    )
    return ratings.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Catalog metadata
# --------------------------------------------------------------------------- #
def _aggregate_tags(movie_ids: list[int]) -> dict[int, list[str]]:
    """Return the most frequent user tags per movie from ``tags.csv``."""
    tags_path = ML_DIR / "tags.csv"
    if not tags_path.exists():
        return {}
    tags = pd.read_csv(tags_path)
    tags = tags[tags["movieId"].isin(set(movie_ids))]
    out: dict[int, list[str]] = {}
    for movie_id, group in tags.groupby("movieId"):
        top = group["tag"].astype(str).str.lower().value_counts().head(TOP_TAGS_PER_MOVIE)
        out[int(movie_id)] = list(top.index)
    return out


class TMDBClient:
    """Minimal cached TMDB client for overview/genres/poster enrichment.

    Args:
        api_key: TMDB API key.
        cache_path: JSON file used to memoize responses across runs.
    """

    def __init__(self, api_key: str, cache_path: Path) -> None:
        self.api_key = api_key
        self.cache_path = cache_path
        self.cache: dict[str, dict] = (
            json.loads(cache_path.read_text()) if cache_path.exists() else {}
        )

    def fetch(self, tmdb_id: int) -> dict:
        """Fetch (and cache) a movie record from TMDB.

        Args:
            tmdb_id: TMDB movie id (from MovieLens ``links.csv``).

        Returns:
            ``{"overview", "genres", "poster_url"}`` (possibly empty on failure).
        """
        key = str(tmdb_id)
        if key in self.cache:
            return self.cache[key]

        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        try:
            resp = requests.get(url, params={"api_key": self.api_key}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            poster = data.get("poster_path")
            record = {
                "overview": data.get("overview", "") or "",
                "genres": [g["name"] for g in data.get("genres", [])],
                "poster_url": f"{TMDB_IMG_BASE}{poster}" if poster else None,
            }
        except requests.RequestException:
            record = {"overview": "", "genres": [], "poster_url": None}

        self.cache[key] = record
        time.sleep(TMDB_SLEEP)
        return record

    def flush(self) -> None:
        """Persist the cache to disk."""
        self.cache_path.write_text(json.dumps(self.cache))


def build_catalog(movie_ids: list[int]) -> list[MovieRecord]:
    """Assemble :class:`MovieRecord` entries for the kept movies.

    Joins MovieLens ``movies.csv`` (titles/genres) and ``links.csv`` (TMDB id),
    aggregates top user tags, and enriches with TMDB overview/genres/poster.

    Args:
        movie_ids: MovieLens movie ids to include, in catalog order.

    Returns:
        Aligned list of movie records.
    """
    movies = pd.read_csv(ML_DIR / "movies.csv").set_index("movieId")
    links = pd.read_csv(ML_DIR / "links.csv").set_index("movieId")
    tag_map = _aggregate_tags(movie_ids)

    settings = get_settings()
    if not settings.tmdb_api_key:
        raise RuntimeError("TMDB_API_KEY is required for the real preprocess step.")
    tmdb = TMDBClient(settings.tmdb_api_key, RAW_DIR / "tmdb_cache.json")

    year_re = r"\((\d{4})\)\s*$"
    catalog: list[MovieRecord] = []
    for idx, movie_id in enumerate(tqdm(movie_ids, desc="Building catalog")):
        row = movies.loc[movie_id]
        raw_title = str(row["title"])
        match = pd.Series([raw_title]).str.extract(year_re).iloc[0, 0]
        year = int(match) if pd.notna(match) else None
        title = pd.Series([raw_title]).str.replace(year_re, "", regex=True).iloc[0].strip()
        ml_genres = [g for g in str(row["genres"]).split("|") if g != "(no genres listed)"]

        tmdb_id = links.loc[movie_id, "tmdbId"] if movie_id in links.index else None
        tmdb_id = int(tmdb_id) if pd.notna(tmdb_id) else None
        meta = tmdb.fetch(tmdb_id) if tmdb_id else {"overview": "", "genres": [], "poster_url": None}

        genres = sorted({*ml_genres, *meta["genres"]})
        catalog.append(
            MovieRecord(
                idx=idx,
                movie_id=int(movie_id),
                tmdb_id=tmdb_id,
                title=title,
                year=year,
                type="movie",  # MovieLens 25M is films only
                genres=genres,
                mood_tags=tag_map.get(int(movie_id), []),
                overview=meta["overview"],
                poster_url=meta["poster_url"],
            )
        )

    tmdb.flush()
    return catalog


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def _content_document(rec: MovieRecord) -> str:
    """TF-IDF document for a record: weighted genres + tags + overview."""
    genres = " ".join(rec.genres) + " "
    tags = " ".join(rec.mood_tags) + " "
    return (genres * 3) + (tags * 2) + rec.overview


def preprocess(sample_frac: float = 1.0) -> ArtifactBundle:
    """Run the full preprocessing pipeline and save the artifact bundle.

    Args:
        sample_frac: Fraction of users to keep for fast local development.

    Returns:
        The saved bundle (CF factors are a zero placeholder until training).
    """
    settings = get_settings()
    art = settings.artifacts_dir
    art.mkdir(parents=True, exist_ok=True)

    ratings = load_and_filter_ratings(sample_frac=sample_frac)
    ratings.to_parquet(art / "ratings.parquet")  # consumed by ml.collaborative

    movie_ids = sorted(ratings["movieId"].unique().tolist())
    catalog = build_catalog(movie_ids)

    print("Building TF-IDF content matrix...")
    tfidf = TfidfBuilder(min_df=2).fit_transform([_content_document(r) for r in catalog])

    print("Computing semantic embeddings...")
    embedder = get_embedder(prefer_semantic=True)
    embeddings = embedder.encode([r.overview or r.title for r in catalog])

    cf_placeholder = np.zeros((len(catalog), DEFAULT_N_FACTORS), dtype=np.float32)
    bundle = ArtifactBundle(
        catalog=catalog,
        cf_factors=cf_placeholder,
        tfidf=tfidf,
        embeddings=embeddings,
        meta={
            "source": "movielens-25m",
            "sample_frac": sample_frac,
            "embed_dim": int(embeddings.shape[1]),
            "cf_trained": False,
        },
    )
    save_artifacts(bundle, art)
    print(
        f"\nSaved bundle: {bundle.size:,} movies -> {art}\n"
        "Next: python -m ml.collaborative   (trains CF factors)"
    )
    return bundle


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Preprocess MovieLens 25M into artifacts.")
    parser.add_argument(
        "--sample-frac",
        type=float,
        default=1.0,
        help="Fraction of users to keep (e.g. 0.1 for fast dev). Default: 1.0 (full).",
    )
    args = parser.parse_args()
    preprocess(sample_frac=args.sample_frac)


if __name__ == "__main__":
    main()
