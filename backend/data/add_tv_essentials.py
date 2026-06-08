"""Merge :mod:`data.tv_essentials` into the keyless ``tv_index.json``.

The TV deck has no ML model, so this just appends any missing series (matched
article/case-insensitively) to the catalog the ``/tv`` endpoint serves. Offline
and idempotent — re-running skips series already present. Commit the updated
``tv_index.json`` afterwards.

    cd backend
    python -m data.add_tv_essentials
"""

from __future__ import annotations

import json

from config import get_settings
from data.tv_essentials import TV_ESSENTIALS
from ml.artifacts import normalize_title

TV_INDEX_FILE = "tv_index.json"
# TV ids live in their own range (existing entries start at 8_000_000); keep the
# spliced ones well clear so they never collide with a built-catalog id.
_TV_ID_BASE = 8_900_000


def add_tv_essentials() -> None:
    """Append any missing curated series to ``tv_index.json``."""
    path = get_settings().artifacts_dir / TV_INDEX_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    series: list[dict] = data.get("series", [])

    have = {normalize_title(s["title"]) for s in series}
    added = 0
    for spec in TV_ESSENTIALS:
        if normalize_title(spec["title"]) in have:
            continue
        series.append(
            {
                "id": _TV_ID_BASE + added,
                "title": spec["title"],
                "year": spec.get("year"),
                "type": "tv",
                "genres": spec.get("genres", []),
                "cast": [],
                "overview": spec.get("overview", ""),
                "poster_url": None,
                "tmdb_id": spec.get("tmdb_id"),
                "trailer_key": None,
            }
        )
        have.add(normalize_title(spec["title"]))
        added += 1

    if not added:
        print("Nothing to do — all curated series already present.")
        return

    data["series"] = series
    data.setdefault("meta", {})["tv_essentials_added"] = added
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Added {added} series → {len(series)} total in {TV_INDEX_FILE}.")


if __name__ == "__main__":
    add_tv_essentials()
