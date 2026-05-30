"""Build the bundled **sample** artifact bundle (no downloads, no TMDB key).

Turns :data:`~data.catalog_seed.SEED_CATALOG` into the same four artifact files
the real pipeline produces, so the API serves recognizable recommendations out
of the box:

    python -m data.sample          # writes to MODEL_ARTIFACTS_PATH

The content (TF-IDF) and semantic (hashing) signals are computed from the real
text; the collaborative factors are synthesized from genre/mood structure (see
:func:`~ml.collaborative.synthesize_item_factors`) since the sample has no
ratings. ``meta.source`` is set to ``"sample"`` so provenance is explicit.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from data.catalog_seed import SEED_CATALOG
from data.sample_enrichment import CAST
from ml.artifacts import ArtifactBundle, MovieRecord, save_artifacts
from ml.collaborative import DEFAULT_N_FACTORS, synthesize_item_factors
from ml.content import TfidfBuilder
from ml.embeddings import EMBED_DIM, HashingEmbedder


def _content_document(entry: dict) -> str:
    """Compose the TF-IDF document for an entry (genres + moods + overview).

    Genres and moods are weighted by repetition so they count more than any
    single overview word — they are the strongest content signal.
    """
    genres = " ".join(entry["genres"]) + " "
    moods = " ".join(entry["mood_tags"]) + " "
    return (genres * 3) + (moods * 2) + entry["overview"]


def _feature_matrix(catalog: list[MovieRecord]) -> np.ndarray:
    """Build a dense genre+mood multi-hot matrix to seed the CF factor space."""
    vocab = sorted({tag for rec in catalog for tag in (*rec.genres, *rec.mood_tags)})
    col = {tag: i for i, tag in enumerate(vocab)}
    mat = np.zeros((len(catalog), len(vocab)), dtype=np.float32)
    for row, rec in enumerate(catalog):
        for tag in (*rec.genres, *rec.mood_tags):
            mat[row, col[tag]] = 1.0
    return mat


def build_sample_bundle(seed: int = 7) -> ArtifactBundle:
    """Construct the in-memory sample :class:`ArtifactBundle`.

    Args:
        seed: RNG seed for the synthesized collaborative factors.

    Returns:
        A fully-populated, aligned artifact bundle.
    """
    catalog = [
        MovieRecord(
            idx=i,
            movie_id=i + 1,
            tmdb_id=entry.get("tmdb_id"),
            title=entry["title"],
            year=entry["year"],
            type=entry["type"],
            genres=entry["genres"],
            mood_tags=entry["mood_tags"],
            cast=CAST.get(entry["title"], []),
            overview=entry["overview"],
            poster_url=None,  # real posters arrive with TMDB enrichment
        )
        for i, entry in enumerate(SEED_CATALOG)
    ]

    tfidf = TfidfBuilder(min_df=1).fit_transform([_content_document(e) for e in SEED_CATALOG])
    embeddings = HashingEmbedder(dim=EMBED_DIM).encode(
        [f"{r.title}. {' '.join(r.genres)}. {' '.join(r.mood_tags)}. {r.overview}" for r in catalog]
    )
    cf_factors = synthesize_item_factors(
        _feature_matrix(catalog), n_factors=DEFAULT_N_FACTORS, seed=seed
    )

    return ArtifactBundle(
        catalog=catalog,
        cf_factors=cf_factors,
        tfidf=tfidf,
        embeddings=embeddings,
        meta={
            "source": "sample",
            "description": "Curated dependency-free sample bundle.",
            "n_factors": DEFAULT_N_FACTORS,
            "embed_dim": EMBED_DIM,
        },
    )


def write_sample_bundle(out_dir: str | Path, seed: int = 7) -> ArtifactBundle:
    """Build and persist the sample bundle to ``out_dir``.

    Args:
        out_dir: Destination artifacts directory.
        seed: RNG seed for reproducibility.

    Returns:
        The bundle that was written.
    """
    bundle = build_sample_bundle(seed=seed)
    save_artifacts(bundle, out_dir)
    return bundle


def _main() -> None:
    """CLI: write the sample bundle to ``MODEL_ARTIFACTS_PATH``."""
    from config import get_settings

    out = get_settings().artifacts_dir
    bundle = write_sample_bundle(out)
    print(f"Wrote sample bundle: {bundle.size} titles -> {out}")


if __name__ == "__main__":
    _main()
