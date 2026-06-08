"""Artifact contract shared by the data pipeline and the recommender.

An *artifact bundle* is everything the API needs to serve recommendations
without touching the raw datasets or any external API. It is produced by either:

* ``data.sample``     — a small, curated, dependency-light bundle for dev/tests, or
* ``data.preprocess`` + ``ml.collaborative`` — the real MovieLens 25M bundle.

Both write the **same four files** so the runtime code path is identical:

================  ===================================================
File              Contents
================  ===================================================
movie_index.json  Ordered catalog + metadata + provenance (``meta``).
cf_item_factors.npy   ``(n_movies, n_factors)`` collaborative item vectors.
tfidf_matrix.npz  ``(n_movies, n_terms)`` sparse TF-IDF content matrix.
embeddings.npy    ``(n_movies, dim)`` dense semantic plot embeddings.
================  ===================================================

Row ``i`` of every matrix corresponds to ``catalog[i]`` — the ordering in
``movie_index.json`` is the alignment key for the whole system.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import scipy.sparse as sp

MOVIE_INDEX_FILE = "movie_index.json"
CF_FACTORS_FILE = "cf_item_factors.npy"
TFIDF_FILE = "tfidf_matrix.npz"
EMBEDDINGS_FILE = "embeddings.npy"

_PUNCT_RE = re.compile(r"[^a-z0-9]+")
_YEAR_SUFFIX_RE = re.compile(r"\s*\((\d{4})\)\s*$")


@dataclass(slots=True)
class MovieRecord:
    """One catalog entry, aligned by ``idx`` to every artifact matrix row.

    Attributes:
        idx: Row index into the artifact matrices.
        movie_id: Internal id (MovieLens ``movieId`` for the real bundle).
        tmdb_id: TMDB id, when known.
        title: Display title.
        year: Release year, when known.
        type: ``"movie"`` or ``"tv"``.
        genres: Genre labels.
        mood_tags: Short descriptive tags ("slow-burn", "prestige", ...).
        overview: Plot synopsis used for the semantic embedding.
        poster_url: Fully-qualified TMDB poster URL, when known.
        trailer_key: YouTube video id of the title's trailer, when known —
            baked in keylessly (Wikidata P1651) so the player embeds it in-page
            with no runtime API key. See ``data.enrich_trailers``.
    """

    idx: int
    movie_id: int
    title: str
    year: int | None
    type: str
    genres: list[str] = field(default_factory=list)
    mood_tags: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    overview: str = ""
    tmdb_id: int | None = None
    poster_url: str | None = None
    trailer_key: str | None = None

    def to_json(self) -> dict:
        """Serialize to a plain dict for ``movie_index.json``."""
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "MovieRecord":
        """Rebuild from a ``movie_index.json`` entry, ignoring unknown keys."""
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def normalize_title(title: str) -> str:
    """Return a lookup key for a title.

    Lowercases, drops a trailing ``(YYYY)``, removes punctuation and collapses
    whitespace so ``"The Wire (2002)"`` and ``"the  wire"`` resolve identically.

    Args:
        title: Raw user- or dataset-supplied title.

    Returns:
        A normalized key suitable for dictionary lookup.
    """
    title = _YEAR_SUFFIX_RE.sub("", title.strip().lower())
    cleaned = _PUNCT_RE.sub(" ", title).strip()
    # Drop leading/trailing articles so "The Matrix" and MovieLens's "Matrix,
    # The" resolve to the same key.
    tokens = [t for t in cleaned.split() if t not in {"the", "a", "an"}]
    return " ".join(tokens) if tokens else cleaned


@dataclass(slots=True)
class ArtifactBundle:
    """In-memory view of a saved artifact set.

    Attributes:
        catalog: Movie records ordered by ``idx``.
        cf_factors: Collaborative item-factor matrix ``(n, n_factors)``.
        tfidf: Sparse TF-IDF content matrix ``(n, n_terms)``.
        embeddings: Dense semantic matrix ``(n, dim)``.
        meta: Free-form provenance ("source", counts, hyperparameters).
    """

    catalog: list[MovieRecord]
    cf_factors: np.ndarray
    tfidf: sp.csr_matrix
    embeddings: np.ndarray
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = len(self.catalog)
        for name, arr in (
            ("cf_factors", self.cf_factors),
            ("tfidf", self.tfidf),
            ("embeddings", self.embeddings),
        ):
            if arr.shape[0] != n:
                raise ValueError(
                    f"{name} has {arr.shape[0]} rows but catalog has {n} entries; "
                    "artifact matrices must be aligned to the catalog ordering."
                )

    @property
    def size(self) -> int:
        """Number of titles in the catalog."""
        return len(self.catalog)


def save_artifacts(bundle: ArtifactBundle, out_dir: str | Path) -> None:
    """Write an :class:`ArtifactBundle` to ``out_dir`` as the four contract files.

    Args:
        bundle: The bundle to persist.
        out_dir: Destination directory; created if missing.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    index = {
        "meta": {**bundle.meta, "n_movies": bundle.size},
        "movies": [m.to_json() for m in bundle.catalog],
    }
    (out / MOVIE_INDEX_FILE).write_text(json.dumps(index, indent=2), encoding="utf-8")
    np.save(out / CF_FACTORS_FILE, bundle.cf_factors.astype(np.float32))
    sp.save_npz(out / TFIDF_FILE, bundle.tfidf.tocsr())
    np.save(out / EMBEDDINGS_FILE, bundle.embeddings.astype(np.float32))


def load_artifacts(in_dir: str | Path) -> ArtifactBundle:
    """Load an :class:`ArtifactBundle` previously written by :func:`save_artifacts`.

    Args:
        in_dir: Directory containing the four contract files.

    Returns:
        The reconstructed bundle.

    Raises:
        FileNotFoundError: If any required artifact file is missing.
    """
    src = Path(in_dir)
    index_path = src / MOVIE_INDEX_FILE
    if not index_path.exists():
        raise FileNotFoundError(f"Missing artifact: {index_path}")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    catalog = [MovieRecord.from_json(m) for m in index["movies"]]
    cf_factors = np.load(src / CF_FACTORS_FILE)
    tfidf = sp.load_npz(src / TFIDF_FILE).tocsr()
    embeddings = np.load(src / EMBEDDINGS_FILE)
    return ArtifactBundle(
        catalog=catalog,
        cf_factors=cf_factors,
        tfidf=tfidf,
        embeddings=embeddings,
        meta=index.get("meta", {}),
    )


def artifacts_exist(in_dir: str | Path) -> bool:
    """Return ``True`` if all four contract files are present in ``in_dir``."""
    src = Path(in_dir)
    return all(
        (src / name).exists()
        for name in (MOVIE_INDEX_FILE, CF_FACTORS_FILE, TFIDF_FILE, EMBEDDINGS_FILE)
    )
