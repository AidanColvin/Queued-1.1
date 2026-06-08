"""Bake YouTube trailer ids into the catalog — keyless, via Wikidata P1651.

Companion to :mod:`data.enrich_keyless` (which fills posters). Many film/TV
items on Wikidata carry a ``P1651`` ("YouTube video ID") statement pointing at
the official trailer. Resolving it lets the frontend embed and *play the
trailer inside the app* with **no API key** — the id is committed into
``movie_index.json`` and served like any other field.

    movie_id ──(links.csv)──▶ imdb_id ──(Wikidata P345)──▶ film item
    ──(P1651)──▶ YouTube video id

Run it (resumable — only fetches titles that still lack a ``trailer_key``)::

    cd backend
    .venv/bin/python -m data.enrich_trailers

Coverage is whatever Wikidata has (a subset of the catalog); titles without a
P1651 keep ``trailer_key=None`` and the player falls back to its other paths.
Only ``movie_index.json`` is rewritten — the aligned matrices are untouched.
Uses ``httpx`` only; no API key.
"""

from __future__ import annotations

import time

import httpx

from config import get_settings
from db.database import Movie, get_session_factory, init_db, seed_movies
from ml.artifacts import load_artifacts

# Reuse the IMDb map, retry/backoff, index writer and constants from the poster
# enrichment so the two scripts behave identically against Wikimedia services.
from data.enrich_keyless import (
    SPARQL_BATCH,
    SPARQL_SLEEP,
    USER_AGENT,
    WDQS_ENDPOINT,
    _imdb_map,
    _request_with_retry,
    _write_index,
)


def _wikidata_trailers(client: httpx.Client, imdb_ids: list[str]) -> dict[str, str]:
    """Resolve IMDb ids to a YouTube trailer id via Wikidata ``P1651``.

    One SPARQL query per :data:`SPARQL_BATCH` ids: match the film item by
    ``P345`` (IMDb id), then read its ``P1651`` (YouTube video ID). Items with
    no such statement are simply absent from the result.

    Args:
        client: An open httpx client.
        imdb_ids: Full ``tt``-prefixed IMDb ids.

    Returns:
        ``imdb_id`` → YouTube video id (only ids that have one).
    """
    resolved: dict[str, str] = {}
    for start in range(0, len(imdb_ids), SPARQL_BATCH):
        batch = imdb_ids[start : start + SPARQL_BATCH]
        values = " ".join(f'"{i}"' for i in batch)
        query = (
            "SELECT ?imdb ?yt WHERE {"
            f"  VALUES ?imdb {{ {values} }}"
            "  ?film wdt:P345 ?imdb ."
            "  ?film wdt:P1651 ?yt ."
            "}"
        )
        resp = _request_with_retry(
            client,
            "POST",
            WDQS_ENDPOINT,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
            timeout=60,
        )
        if resp is not None:
            try:
                for row in resp.json()["results"]["bindings"]:
                    resolved.setdefault(row["imdb"]["value"], row["yt"]["value"])
            except (ValueError, KeyError):
                pass
        done = min(start + SPARQL_BATCH, len(imdb_ids))
        print(f"  Wikidata: {done}/{len(imdb_ids)} ids → {len(resolved)} trailers", flush=True)
        time.sleep(SPARQL_SLEEP)
    return resolved


def enrich() -> None:
    """Fill ``trailer_key`` for every catalog title that still lacks one, then persist."""
    settings = get_settings()
    art = settings.artifacts_dir
    bundle = load_artifacts(art)
    imdb_map = _imdb_map()

    # Resumable: only work on titles that don't already have a trailer id.
    todo = [r for r in bundle.catalog if not r.trailer_key and r.movie_id in imdb_map]
    have = sum(1 for r in bundle.catalog if r.trailer_key)
    print(
        f"{have}/{len(bundle.catalog)} already have trailers; resolving {len(todo)} more (keyless)…",
        flush=True,
    )
    if not todo:
        print("Nothing to do.")
        return

    imdb_ids = sorted({imdb_map[r.movie_id] for r in todo})
    by_imdb: dict[str, list] = {}
    for rec in todo:
        by_imdb.setdefault(imdb_map[rec.movie_id], []).append(rec)

    with httpx.Client() as client:
        imdb_to_yt = _wikidata_trailers(client, imdb_ids)

    filled = 0
    for imdb, yt in imdb_to_yt.items():
        for rec in by_imdb.get(imdb, []):
            if not rec.trailer_key:
                rec.trailer_key = yt
                filled += 1

    bundle.meta["trailers_enriched"] = "wikidata-keyless"
    _write_index(bundle, art)

    # Refresh the SQLite catalog so any cached read sees the new ids too.
    init_db()
    with get_session_factory()() as session:
        session.query(Movie).delete()
        session.commit()
    seed_movies(bundle.catalog)

    total = have + filled
    pct = 100 * total / len(bundle.catalog) if bundle.catalog else 0
    print(f"\nDone. +{filled} this run → {total}/{len(bundle.catalog)} trailers ({pct:.0f}%).")
    print("Re-run to fill more (rate-limited ids retry); restart the API to serve them.")


if __name__ == "__main__":
    enrich()
