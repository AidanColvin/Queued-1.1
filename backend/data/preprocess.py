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
from ml.artifacts import ArtifactBundle, MovieRecord, normalize_title, save_artifacts
from ml.collaborative import DEFAULT_N_FACTORS
from ml.content import TfidfBuilder
from ml.embeddings import get_embedder

RAW_DIR = Path(__file__).resolve().parent / "raw"
ML_DIR = RAW_DIR / "ml-25m"
CMU_DIR = RAW_DIR / "MovieSummaries"

MIN_RATINGS_PER_MOVIE = 50
MIN_RATINGS_PER_USER = 20
TOP_TAGS_PER_MOVIE = 6
TOP_GENOME_TAGS = 15  # highest-relevance genome tags kept per movie
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


def load_genome_tags(movie_ids: list[int]) -> dict[int, list[str]]:
    """Top relevance-weighted genome tags per movie — the richest content signal.

    ``genome-scores.csv`` scores each of 1,128 tags per movie; we keep the
    highest-relevance ones as content keywords.

    Args:
        movie_ids: Movies to keep.

    Returns:
        ``{movieId: [tag, ...]}`` (empty if the genome files are absent).
    """
    scores_path = ML_DIR / "genome-scores.csv"
    tags_path = ML_DIR / "genome-tags.csv"
    if not scores_path.exists() or not tags_path.exists():
        return {}
    print("Loading genome-scores (richest content signal)...")
    tag_names = pd.read_csv(tags_path).set_index("tagId")["tag"].to_dict()
    scores = pd.read_csv(scores_path)
    scores = scores[scores["movieId"].isin(set(movie_ids))]
    out: dict[int, list[str]] = {}
    for movie_id, grp in scores.groupby("movieId"):
        top = grp.nlargest(TOP_GENOME_TAGS, "relevance")["tagId"].tolist()
        out[int(movie_id)] = [tag_names[t] for t in top if t in tag_names]
    return out


def load_cmu_summaries() -> dict[tuple[str, int | None], str]:
    """Map (normalized title, year) → plot summary from the CMU corpus.

    CMU plot summaries are richer than TMDB overviews for many films and need no
    API key, so they back the semantic embedding layer.

    Returns:
        Lookup keyed by ``(title_norm, year)`` and ``(title_norm, None)``.
    """
    meta_path = CMU_DIR / "movie.metadata.tsv"
    plot_path = CMU_DIR / "plot_summaries.txt"
    if not meta_path.exists() or not plot_path.exists():
        return {}
    print("Loading CMU plot summaries (semantic layer)...")
    meta = pd.read_csv(
        meta_path, sep="\t", header=None, usecols=[0, 2, 3], names=["wikiId", "name", "release"]
    )
    plots = pd.read_csv(plot_path, sep="\t", header=None, names=["wikiId", "summary"])
    merged = meta.merge(plots, on="wikiId")

    out: dict[tuple[str, int | None], str] = {}
    for name, release, summary in zip(merged["name"], merged["release"], merged["summary"]):
        title_norm = normalize_title(str(name))
        rel = str(release)
        year = int(rel[:4]) if len(rel) >= 4 and rel[:4].isdigit() else None
        out[(title_norm, year)] = summary
        out.setdefault((title_norm, None), summary)
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
            resp = requests.get(
                url, params={"api_key": self.api_key, "append_to_response": "credits"}, timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            poster = data.get("poster_path")
            cast = [c["name"] for c in (data.get("credits", {}).get("cast") or [])[:3] if c.get("name")]
            record = {
                "overview": data.get("overview", "") or "",
                "genres": [g["name"] for g in data.get("genres", [])],
                "poster_url": f"{TMDB_IMG_BASE}{poster}" if poster else None,
                "cast": cast,
            }
        except requests.RequestException:
            record = {"overview": "", "genres": [], "poster_url": None, "cast": []}

        self.cache[key] = record
        time.sleep(TMDB_SLEEP)
        return record

    def flush(self) -> None:
        """Persist the cache to disk."""
        self.cache_path.write_text(json.dumps(self.cache))


def build_catalog(
    movie_ids: list[int],
    genome_map: dict[int, list[str]],
    cmu_map: dict[tuple[str, int | None], str],
) -> list[MovieRecord]:
    """Assemble :class:`MovieRecord` entries by fusing every data source.

    Per movie: MovieLens genres + user tags, the top genome tags (richest content
    signal), a CMU plot summary (semantic), and — when a ``TMDB_API_KEY`` is set —
    TMDB overview/genres/poster/cast. TMDB is **optional**: without a key the
    model still trains fully on MovieLens + genome + CMU + IMDb; posters are
    added later by ``data.enrich_sample``-style enrichment.

    Args:
        movie_ids: MovieLens movie ids to include, in catalog order.
        genome_map: ``{movieId: [genome tags]}``.
        cmu_map: CMU summary lookup keyed by ``(title_norm, year)``.

    Returns:
        Aligned list of movie records.
    """
    movies = pd.read_csv(ML_DIR / "movies.csv").set_index("movieId")
    links = pd.read_csv(ML_DIR / "links.csv").set_index("movieId")
    tag_map = _aggregate_tags(movie_ids)

    settings = get_settings()
    tmdb = TMDBClient(settings.tmdb_api_key, RAW_DIR / "tmdb_cache.json") if settings.tmdb_api_key else None
    if tmdb is None:
        print("No TMDB_API_KEY — training on MovieLens + genome + CMU + IMDb (posters added later).")

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
        meta = tmdb.fetch(tmdb_id) if (tmdb and tmdb_id) else {"overview": "", "genres": [], "poster_url": None, "cast": []}

        title_norm = normalize_title(title)
        cmu_summary = cmu_map.get((title_norm, year)) or cmu_map.get((title_norm, None)) or ""
        # Prefer TMDB overview for display; fall back to the (richer) CMU summary.
        overview = meta["overview"] or cmu_summary[:400]

        genres = sorted({*ml_genres, *meta["genres"]})
        # Content keywords = user tags + the high-relevance genome tags.
        mood_tags = list(dict.fromkeys([*tag_map.get(int(movie_id), []), *genome_map.get(int(movie_id), [])]))
        catalog.append(
            MovieRecord(
                idx=idx,
                movie_id=int(movie_id),
                tmdb_id=tmdb_id,
                title=title,
                year=year,
                type="movie",  # MovieLens 25M is films only
                genres=genres,
                mood_tags=mood_tags,
                cast=meta["cast"],
                overview=overview,
                poster_url=meta["poster_url"],
                # Full CMU text drives the semantic embedding (see preprocess()).
            )
        )

    if tmdb:
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

    # Order the catalog by MovieLens rating count (most-rated first) so the
    # cold-start /popular deck opens on a genuinely popular title.
    rating_counts = ratings["movieId"].value_counts()
    movie_ids = rating_counts.index.tolist()
    genome_map = load_genome_tags(movie_ids)
    cmu_map = load_cmu_summaries()
    catalog = build_catalog(movie_ids, genome_map, cmu_map)
    for rec in catalog:  # popularity prior consumed by ml.reranker
        rec.rating_count = int(rating_counts.get(rec.movie_id, 0))

    print("Building TF-IDF content matrix (genres + tags + genome + overview)...")
    tfidf = TfidfBuilder(min_df=2).fit_transform([_content_document(r) for r in catalog])

    print("Computing semantic embeddings (CMU plot summaries)...")
    embedder = get_embedder(prefer_semantic=True)

    def _semantic_text(rec: MovieRecord) -> str:
        key = normalize_title(rec.title)
        cmu = cmu_map.get((key, rec.year)) or cmu_map.get((key, None))
        return (cmu or rec.overview or rec.title)[:1000]

    embeddings = embedder.encode([_semantic_text(r) for r in catalog])

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
