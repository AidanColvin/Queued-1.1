"""Bake reliable trailer ids into the catalog — keyless, via YouTube search.

Wikidata's ``P1651`` (used by :mod:`data.enrich_trailers`) is too stale: even
iconic films resolve to deleted/unembeddable videos. YouTube *search* instead
returns the current, embeddable official trailer (Rotten Tomatoes / Movieclips /
studio channels) as its first video result — exactly what plays in the in-app
player. No API key: just the public results page.

    movie title + year ──(youtube.com/results, video filter)──▶ first videoId

Run (resumable — only fills titles still lacking a ``trailer_key``; processes
the most popular first so the cards users see get covered soonest)::

    cd backend && .venv/bin/python -m data.enrich_trailers_youtube --limit 2500

Rewrites ``movie_index.json`` and re-seeds the SQLite catalog. ``httpx`` only.
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.parse

import httpx

from config import get_settings
from data.enrich_keyless import _write_index
from db.database import Movie, get_session_factory, init_db, seed_movies
from ml.artifacts import load_artifacts

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
# YouTube "type: video" search filter (sp param) — skips channels/playlists.
_VIDEO_FILTER = "EgIQAQ%3D%3D"
_VIDEO_ID = re.compile(r'"videoId":"([\w-]{11})"')
_SLEEP = 0.4  # politeness between searches


def _first_video(client: httpx.Client, title: str, year: int | None) -> str | None:
    """Return the first video id YouTube returns for the title's trailer search."""
    q = f"{title} {year} trailer" if year else f"{title} trailer"
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode(
        {"search_query": q, "sp": _VIDEO_FILTER}, safe="%"
    )
    try:
        html = client.get(url, timeout=15).text
    except httpx.HTTPError:
        return None
    m = _VIDEO_ID.search(html)
    return m.group(1) if m else None


def enrich(limit: int) -> None:
    """Fill ``trailer_key`` (via YouTube search) for the top ``limit`` titles."""
    art = get_settings().artifacts_dir
    bundle = load_artifacts(art)
    # Catalog is popularity-ordered, so the first `limit` are the cards users
    # actually reach. Resumable: skip any that already have a key this run.
    targets = [r for r in bundle.catalog[:limit] if not r.trailer_key]
    print(f"Resolving trailers for {len(targets)} of the top {limit} titles (keyless YouTube search)…", flush=True)

    filled = misses = 0
    # Guard against YouTube serving a generic/consent page: the same video id
    # answering different queries is garbage, not 200 films sharing a trailer.
    # One id once nuked 1,251 records this way (see data.fix_collisions).
    seen_keys: set[str] = {r.trailer_key for r in bundle.catalog if r.trailer_key}
    with httpx.Client(headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}) as client:
        for i, rec in enumerate(targets, 1):
            key = _first_video(client, rec.title, rec.year)
            if key and key not in seen_keys:
                seen_keys.add(key)
                rec.trailer_key = key
                filled += 1
            else:
                misses += 1
            if i % 100 == 0:
                print(f"  {i}/{len(targets)} — {filled} found, {misses} missed", flush=True)
                _write_index(bundle, art)  # periodic checkpoint (resumable)
            time.sleep(_SLEEP)

    bundle.meta["trailers_source"] = "youtube-search-keyless"
    _write_index(bundle, art)
    init_db()
    with get_session_factory()() as session:
        session.query(Movie).delete()
        session.commit()
    seed_movies(bundle.catalog)

    total = sum(1 for r in bundle.catalog if r.trailer_key)
    print(f"\nDone. +{filled} this run → {total} catalog trailers. Restart the API to serve them.")


def _main() -> None:
    parser = argparse.ArgumentParser(description="Keyless trailer ids via YouTube search.")
    parser.add_argument("--limit", type=int, default=2500, help="How many top-popular titles to cover.")
    parser.add_argument("--reset", action="store_true", help="Clear existing (stale) trailer ids first.")
    args = parser.parse_args()

    if args.reset:
        art = get_settings().artifacts_dir
        bundle = load_artifacts(art)
        for r in bundle.catalog:
            r.trailer_key = None
        _write_index(bundle, art)
        print("Cleared existing trailer ids.")

    enrich(args.limit)


if __name__ == "__main__":
    _main()
