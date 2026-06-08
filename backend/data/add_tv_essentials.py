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


def _interleave(base: list[dict], extra: list[dict]) -> list[dict]:
    """Spread ``extra`` evenly through ``base`` so the additions aren't buried.

    The ``/tv`` deck plays the list in order with no reranker, so appending would
    leave these marquee series unreachable until ~all 200+ originals were swiped.
    Inserting one addition every few originals surfaces them early and throughout.
    """
    if not extra:
        return base
    step = max(1, len(base) // len(extra))
    out: list[dict] = []
    ei = 0
    for i, item in enumerate(base):
        out.append(item)
        if ei < len(extra) and (i + 1) % step == 0:
            out.append(extra[ei])
            ei += 1
    out.extend(extra[ei:])  # any leftover additions
    return out


def add_tv_essentials() -> None:
    """Interleave the curated series into ``tv_index.json`` (idempotent)."""
    path = get_settings().artifacts_dir / TV_INDEX_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    series: list[dict] = data.get("series", [])

    # Rebuild each run: strip any previously-spliced essentials (their reserved
    # id range), then re-interleave — so re-running is a no-op-shaped fixpoint.
    base = [s for s in series if s.get("id", 0) < _TV_ID_BASE]
    base_titles = {normalize_title(s["title"]) for s in base}

    extra = [
        {
            "id": _TV_ID_BASE + i,
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
        for i, spec in enumerate(spec for spec in TV_ESSENTIALS if normalize_title(spec["title"]) not in base_titles)
    ]

    merged = _interleave(base, extra)
    data["series"] = merged
    data.setdefault("meta", {})["tv_essentials_added"] = len(extra)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Interleaved {len(extra)} curated series → {len(merged)} total in {TV_INDEX_FILE}.")


if __name__ == "__main__":
    add_tv_essentials()
