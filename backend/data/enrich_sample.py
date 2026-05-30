"""Enrich the SAMPLE bundle with real TMDB posters + cast (needs a TMDB key).

The keyless sample ships with no posters and a curated cast. Once you have a free
[TMDB key](https://www.themoviedb.org/settings/api):

    # backend/.env  ->  TMDB_API_KEY=...
    python -m data.sample          # build the keyless bundle (if not already)
    python -m data.enrich_sample   # fetch real posters + cast into it
    # then restart the API

It updates ``movie_index.json`` in place (so ``/recommend`` serves posters after
a restart) and re-seeds the SQLite catalog (so ``/search`` serves them now). Uses
``httpx`` only — no heavy training deps. Handles both movie and TV ids.
"""

from __future__ import annotations

import time

import httpx

from config import get_settings
from db.database import Movie, get_session_factory, init_db, seed_movies
from ml.artifacts import load_artifacts, save_artifacts

TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"
SLEEP = 0.25  # free-tier courtesy
TOP_CAST = 3


def _fetch(client: httpx.Client, media_type: str, tmdb_id: int, api_key: str) -> dict:
    """Fetch poster_path + top cast for one title from TMDB.

    Args:
        client: An open httpx client.
        media_type: ``"movie"`` or ``"tv"`` (selects the endpoint).
        tmdb_id: TMDB id.
        api_key: TMDB API key.

    Returns:
        ``{"poster_url": str | None, "cast": list[str]}`` (empty on failure).
    """
    endpoint = "tv" if media_type == "tv" else "movie"
    extra = "aggregate_credits,credits" if endpoint == "tv" else "credits"
    url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}"
    try:
        resp = client.get(url, params={"api_key": api_key, "append_to_response": extra}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return {"poster_url": None, "cast": []}

    poster = data.get("poster_path")
    credits = data.get("aggregate_credits") or data.get("credits") or {}
    cast = [c["name"] for c in (credits.get("cast") or [])[:TOP_CAST] if c.get("name")]
    return {"poster_url": f"{TMDB_IMG_BASE}{poster}" if poster else None, "cast": cast}


def enrich() -> None:
    """Fetch posters + cast for every sample title and persist the result."""
    settings = get_settings()
    if not settings.tmdb_api_key:
        raise RuntimeError("TMDB_API_KEY is not set. Add it to backend/.env first.")

    art = settings.artifacts_dir
    bundle = load_artifacts(art)
    total = sum(1 for r in bundle.catalog if r.tmdb_id)
    print(f"Enriching {total} titles from TMDB (≈{total * SLEEP:.0f}s)...")

    with httpx.Client() as client:
        done = 0
        for rec in bundle.catalog:
            if not rec.tmdb_id:
                continue
            meta = _fetch(client, rec.type, rec.tmdb_id, settings.tmdb_api_key)
            if meta["poster_url"]:
                rec.poster_url = meta["poster_url"]
            if meta["cast"]:
                rec.cast = meta["cast"]
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{total}")
            time.sleep(SLEEP)

    bundle.meta["enriched"] = True
    save_artifacts(bundle, art)

    # Refresh the SQLite catalog so /search returns the new posters immediately.
    init_db()
    with get_session_factory()() as session:
        session.query(Movie).delete()
        session.commit()
    seed_movies(bundle.catalog)

    print(f"\nDone. Enriched {done} titles. Restart the API to serve posters via /recommend.")


if __name__ == "__main__":
    enrich()
