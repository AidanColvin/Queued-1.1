"""Backfill streaming availability from TMDB ``watch/providers`` (JustWatch).

Walks every title in the movie catalog (``movie_index.json``) and the TV
catalog (``tv_index.json``), asks TMDB which services stream it in ``--region``
(flatrate tiers only — rentals/purchases are not "on your service"), collapses
SKU variants onto the canonical provider set, and writes
``data/artifacts/providers.json``::

    {"region": "US", "generated_at": "...", "titles": {"<tmdb_id>": [8, 15]}}

The API loads this at startup (see ``providers.ProviderIndex``) and mirrors it
into the ``title_providers`` table. Requires ``TMDB_API_KEY``.

Resumable + nightly-friendly: by default already-fetched ids are skipped, so a
re-run only fills gaps; pass ``--refresh`` to re-fetch everything (the nightly
mode — availability changes as licensing windows move).

Usage:
    python -m data.enrich_providers              # fill gaps
    python -m data.enrich_providers --refresh    # full nightly re-sync
    python -m data.enrich_providers --region GB
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from providers import PROVIDERS_FILE, canonicalize  # noqa: E402

TMDB_BASE = "https://api.themoviedb.org/3"
# Stay politely under TMDB's ~50 req/s burst limit.
REQUEST_DELAY_S = 0.025


def _load_catalog_ids(artifacts_dir: Path) -> list[tuple[int, str]]:
    """Collect ``(tmdb_id, "movie"|"tv")`` pairs from both catalogs."""
    pairs: dict[int, str] = {}

    index_path = artifacts_dir / "movie_index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for movie in index.get("movies", []):
            tmdb_id = movie.get("tmdb_id")
            if tmdb_id:
                pairs[int(tmdb_id)] = "tv" if movie.get("type") == "tv" else "movie"

    tv_path = artifacts_dir / "tv_index.json"
    if tv_path.exists():
        tv_index = json.loads(tv_path.read_text(encoding="utf-8"))
        for series in tv_index.get("series", []):
            tmdb_id = series.get("tmdb_id")
            if tmdb_id:
                pairs[int(tmdb_id)] = "tv"

    return sorted(pairs.items())


def _fetch_providers(client: httpx.Client, api_key: str, tmdb_id: int, media: str, region: str) -> list[int] | None:
    """Return the canonical provider ids streaming a title, or ``None`` on error."""
    try:
        res = client.get(f"{TMDB_BASE}/{media}/{tmdb_id}/watch/providers", params={"api_key": api_key})
        if res.status_code == 404:
            return []
        res.raise_for_status()
    except httpx.HTTPError:
        return None
    offers = res.json().get("results", {}).get(region, {})
    raw_ids = [p["provider_id"] for tier in ("flatrate", "ads") for p in offers.get(tier, [])]
    return sorted(canonicalize(raw_ids))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="US", help="ISO country code for availability (default US).")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch every title (nightly mode).")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N titles (smoke testing).")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.tmdb_api_key:
        print("TMDB_API_KEY is required to fetch watch providers (free key: themoviedb.org).", file=sys.stderr)
        return 1

    artifacts_dir = settings.artifacts_dir
    out_path = artifacts_dir / PROVIDERS_FILE

    existing: dict[str, list[int]] = {}
    if out_path.exists() and not args.refresh:
        existing = json.loads(out_path.read_text(encoding="utf-8")).get("titles", {})

    pairs = _load_catalog_ids(artifacts_dir)
    todo = [(tid, media) for tid, media in pairs if args.refresh or str(tid) not in existing]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(pairs)} catalog titles; fetching {len(todo)} ({'refresh' if args.refresh else 'gaps only'})")

    titles: dict[str, list[int]] = {} if args.refresh else dict(existing)
    fetched = errors = 0
    with httpx.Client(timeout=15) as client:
        for tmdb_id, media in todo:
            ids = _fetch_providers(client, settings.tmdb_api_key, tmdb_id, media, args.region)
            if ids is None:
                errors += 1
            else:
                titles[str(tmdb_id)] = ids
                fetched += 1
            if fetched and fetched % 250 == 0:
                print(f"  …{fetched}/{len(todo)}")
            time.sleep(REQUEST_DELAY_S)

    payload = {
        "region": args.region,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "titles": titles,
    }
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    on_service = sum(1 for ids in titles.values() if ids)
    print(f"Wrote {out_path}: {len(titles)} titles, {on_service} with streaming offers, {errors} errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
