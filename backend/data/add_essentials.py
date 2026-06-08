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
    """Apply renames and splice any missing essential titles into the bundle."""
    art = get_settings().artifacts_dir
    bundle = load_artifacts(art)

    by_norm = {normalize_title(r.title): r for r in bundle.catalog}

    # 1) Release-name fixes for the dataset's pre-release placeholders.
    renamed = 0
    for old_norm, (new_title, new_year) in RENAMES.items():
        rec = by_norm.get(old_norm)
        if rec and normalize_title(rec.title) != normalize_title(new_title):
            rec.title, rec.year = new_title, new_year
            by_norm[normalize_title(new_title)] = rec
            renamed += 1

    # 2) Splice in the essentials that aren't already present.
    cf_rows, emb_rows, tfidf_rows = [], [], []
    added = 0
    for spec in ESSENTIALS:
        if normalize_title(spec["title"]) in by_norm:
            continue  # already present — idempotent
        anchor = by_norm.get(normalize_title(spec["anchor"]))
        if anchor is None:
            print(f"  ! skip {spec['title']!r}: anchor {spec['anchor']!r} not in catalog")
            continue
        idx = len(bundle.catalog) + added
        bundle.catalog.append(
            MovieRecord(
                idx=idx,
                movie_id=_SYNTHETIC_ID_BASE + added,
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
        )
        cf_rows.append(bundle.cf_factors[anchor.idx])
        emb_rows.append(bundle.embeddings[anchor.idx])
        tfidf_rows.append(bundle.tfidf[anchor.idx])
        added += 1

    if not added and not renamed:
        print("Nothing to do — all essentials already present.")
        return

    if added:
        cf = np.vstack([bundle.cf_factors, np.array(cf_rows, dtype=bundle.cf_factors.dtype)])
        emb = np.vstack([bundle.embeddings, np.array(emb_rows, dtype=bundle.embeddings.dtype)])
        tfidf = sp.vstack([bundle.tfidf, sp.vstack(tfidf_rows)]).tocsr()
    else:
        cf, emb, tfidf = bundle.cf_factors, bundle.embeddings, bundle.tfidf

    merged = ArtifactBundle(
        catalog=bundle.catalog,
        cf_factors=cf,
        tfidf=tfidf,
        embeddings=emb,
        meta={**bundle.meta, "essentials_added": added + bundle.meta.get("essentials_added", 0)},
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
