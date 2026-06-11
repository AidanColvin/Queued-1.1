"""Prune un-embeddable trailer ids from the catalog — keyless validation.

Wikidata's ``P1651`` sometimes points at a YouTube video that is deleted,
private, or has embedding disabled — the in-app player would then show "Video
unavailable". This checks every baked-in ``trailer_key`` against YouTube's
**keyless** oEmbed endpoint and clears the ones that won't actually play, so the
player only ever embeds a working trailer (others fall back to the YouTube
search link). Companion to :mod:`data.enrich_trailers`.

    cd backend && .venv/bin/python -m data.validate_trailers

Uses ``httpx`` only; no API key.
"""

from __future__ import annotations

import concurrent.futures as cf

import httpx

from config import get_settings
from data.enrich_keyless import _write_index
from db.database import Movie, get_session_factory, init_db, seed_movies
from ml.artifacts import load_artifacts

OEMBED = "https://www.youtube.com/oembed"


def _playable(client: httpx.Client, key: str) -> bool:
    """Return True if a YouTube id is embeddable (oEmbed returns 200)."""
    try:
        r = client.get(OEMBED, params={"url": f"https://youtu.be/{key}", "format": "json"}, timeout=10)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def validate() -> None:
    """Drop every ``trailer_key`` whose video won't embed, then persist."""
    art = get_settings().artifacts_dir
    bundle = load_artifacts(art)
    keyed = [r for r in bundle.catalog if r.trailer_key]
    if not keyed:
        print("No trailer ids to validate.")
        return

    print(f"Validating {len(keyed)} trailer ids via YouTube oEmbed (keyless)…", flush=True)
    with httpx.Client(headers={"User-Agent": "Mozilla/5.0 Queued"}) as client:
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            verdicts = list(ex.map(lambda r: (r, _playable(client, r.trailer_key)), keyed))

    dropped = 0
    for rec, ok in verdicts:
        if not ok:
            rec.trailer_key = None
            dropped += 1
    kept = len(keyed) - dropped

    bundle.meta["trailers_validated"] = True
    _write_index(bundle, art)

    init_db()
    with get_session_factory()() as session:
        session.query(Movie).delete()
        session.commit()
    seed_movies(bundle.catalog)

    print(f"\nDone. {kept} playable kept, {dropped} dead dropped ({100 * kept // len(keyed)}% good). Restart the API.")


if __name__ == "__main__":
    validate()
