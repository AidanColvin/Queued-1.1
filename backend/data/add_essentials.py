"""Splice the curated :mod:`data.essentials` titles into the catalog.

MovieLens 25M can't contain post-2019 films (its ratings stop there), so the
deck was missing marquee titles like *Top Gun: Maverick* and *Parasite*. This
script appends them — copying each one's ``anchor`` feature vectors so the
collaborative / content / semantic matrices stay aligned and the new title
recommends sensibly — and applies a couple of release-name fixes.

It is **offline and idempotent** (no network, no API key): re-running skips any
title already present. Run it after training/enrichment and commit the four
updated artifact files::

    cd backend
    python -m data.add_essentials
    git add data/artifacts/*.json data/artifacts/*.npy data/artifacts/*.npz
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from config import get_settings
from data.essentials import ESSENTIALS, RENAMES
from db.database import Movie, get_session_factory, init_db, seed_movies
from ml.artifacts import ArtifactBundle, MovieRecord, load_artifacts, normalize_title, save_artifacts

# Synthetic movie_ids for spliced titles — far above any real MovieLens id so
# they never collide (the frontend de-dupes on this id).
_SYNTHETIC_ID_BASE = 900_000_000


def add_essentials() -> None:
    """Apply renames and splice essential titles in — rebuilding from the base
    catalog each run so it stays idempotent and correctly row-aligned."""
    art = get_settings().artifacts_dir
    bundle = load_artifacts(art)

    # Strip any previously-spliced synthetic entries (always appended at the
    # tail) back to the trained base, then rebuild. This makes re-runs a stable
    # fixpoint and guarantees each record's idx equals its matrix-row position.
    base_n = sum(1 for r in bundle.catalog if r.movie_id < _SYNTHETIC_ID_BASE)
    catalog = bundle.catalog[:base_n]
    cf = bundle.cf_factors[:base_n]
    emb = bundle.embeddings[:base_n]
    tfidf = bundle.tfidf[:base_n].tocsr()
    for i, rec in enumerate(catalog):
        rec.idx = i  # defensive: keep idx == position

    by_norm = {normalize_title(r.title): r for r in catalog}

    # 1) Release-name fixes for the dataset's pre-release placeholders.
    renamed = 0
    for old_norm, (new_title, new_year) in RENAMES.items():
        rec = by_norm.get(old_norm)
        if rec and normalize_title(rec.title) != normalize_title(new_title):
            rec.title, rec.year = new_title, new_year
            by_norm[normalize_title(new_title)] = rec
            renamed += 1

    # 2) Splice in the essentials that aren't already present, copying each
    #    one's anchor (an existing base title) feature vectors.
    cf_rows, emb_rows, tfidf_rows = [], [], []
    for spec in ESSENTIALS:
        if normalize_title(spec["title"]) in by_norm:
            continue  # already present — idempotent
        anchor = by_norm.get(normalize_title(spec["anchor"]))
        if anchor is None or anchor.idx >= base_n:
            print(f"  ! skip {spec['title']!r}: anchor {spec['anchor']!r} not a base title")
            continue
        idx = len(catalog)  # the row this record will occupy
        rec = MovieRecord(
            idx=idx,
            movie_id=_SYNTHETIC_ID_BASE + idx,
            title=spec["title"],
            year=spec.get("year"),
            type="movie",
            genres=spec.get("genres", []),
            mood_tags=[],
            cast=[],
            overview=spec.get("overview", ""),
            tmdb_id=spec.get("tmdb_id"),
            poster_url=None,  # backfilled later by keyless enrichment
            trailer_key=None,
        )
        catalog.append(rec)
        by_norm[normalize_title(spec["title"])] = rec
        cf_rows.append(cf[anchor.idx])
        emb_rows.append(emb[anchor.idx])
        tfidf_rows.append(tfidf[anchor.idx])

    added = len(cf_rows)
    if added:
        cf = np.vstack([cf, np.array(cf_rows, dtype=cf.dtype)])
        emb = np.vstack([emb, np.array(emb_rows, dtype=emb.dtype)])
        tfidf = sp.vstack([tfidf, sp.vstack(tfidf_rows)]).tocsr()

    ids = [r.movie_id for r in catalog]
    if len(set(ids)) != len(ids):
        raise RuntimeError("Duplicate movie_id in catalog after merge — aborting to avoid a corrupt deck.")

    merged = ArtifactBundle(
        catalog=catalog,
        cf_factors=cf,
        tfidf=tfidf,
        embeddings=emb,
        meta={**bundle.meta, "essentials_added": added},
    )
    save_artifacts(merged, art)

    # Refresh the SQLite catalog so /search sees the new titles too.
    init_db()
    with get_session_factory()() as session:
        session.query(Movie).delete()
        session.commit()
    seed_movies(merged.catalog)

    print(f"Renamed {renamed}, added {added} essential titles → {merged.size} total.")


if __name__ == "__main__":
    add_essentials()
