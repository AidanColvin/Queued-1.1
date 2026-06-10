"""Streaming-provider registry + per-title availability index.

NextWatch tracks a small canonical set of US streaming services. Availability
("which of my services has this title?") comes from TMDB's ``watch/providers``
endpoint (data licensed from JustWatch — attribution required in the UI) via
``data.enrich_providers``, which writes ``providers.json`` next to the model
artifacts. At startup the file is loaded into a :class:`ProviderIndex` on
``app.state`` and mirrored into the ``title_providers`` table.

The app degrades gracefully without the file: filtering is skipped (treated as
"All titles") and ``GET /providers`` reports ``availability_loaded: false`` so
the UI can explain why.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("nextwatch")

PROVIDERS_FILE = "providers.json"


@dataclass(frozen=True, slots=True)
class Provider:
    """One canonical streaming service (id = TMDB watch-provider id)."""

    id: int
    slug: str
    name: str
    color: str  # brand color for the UI chips


# The selectable services, in onboarding display order.
CANONICAL_PROVIDERS: list[Provider] = [
    Provider(8, "netflix", "Netflix", "#E50914"),
    Provider(15, "hulu", "Hulu", "#1CE783"),
    Provider(1899, "max", "Max", "#0026FF"),
    Provider(337, "disney_plus", "Disney+", "#113CCF"),
    Provider(9, "prime_video", "Prime Video", "#00A8E1"),
    Provider(350, "apple_tv_plus", "Apple TV+", "#555555"),
    Provider(531, "paramount_plus", "Paramount+", "#0064FF"),
    Provider(386, "peacock", "Peacock", "#05AC3F"),
]

CANONICAL_IDS = {p.id for p in CANONICAL_PROVIDERS}

# TMDB lists several SKUs of the same service (ad-supported tiers, channel
# bundles, legacy ids). Collapse them onto the canonical id so "Netflix
# Standard with Ads" counts as Netflix.
PROVIDER_ALIASES: dict[int, int] = {
    1796: 8,    # Netflix Standard with Ads
    2100: 9,    # Amazon Prime Video with Ads
    119: 9,     # Amazon Prime Video (regional listing)
    384: 1899,  # HBO Max (pre-rebrand id)
    616: 1899,  # HBO Max Amazon Channel
    1825: 1899, # Max Amazon Channel
    2077: 531,  # Paramount+ with Showtime
    582: 531,   # Paramount+ Amazon Channel
    387: 386,   # Peacock Premium Plus
    2207: 15,   # Hulu (ads) variant
}


def canonicalize(provider_ids: list[int]) -> set[int]:
    """Map raw TMDB provider ids onto the canonical set (dropping unknowns)."""
    mapped = {PROVIDER_ALIASES.get(pid, pid) for pid in provider_ids}
    return mapped & CANONICAL_IDS


class ProviderIndex:
    """Read-only ``tmdb_id → {canonical provider ids}`` availability map."""

    def __init__(self, titles: dict[int, frozenset[int]], region: str = "US") -> None:
        self._titles = titles
        self.region = region

    @classmethod
    def load(cls, artifacts_dir: str | Path) -> "ProviderIndex":
        """Load ``providers.json`` from the artifacts dir, or an empty index."""
        path = Path(artifacts_dir) / PROVIDERS_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls({}, "US")
        titles = {
            int(tmdb_id): frozenset(canonicalize(pids))
            for tmdb_id, pids in data.get("titles", {}).items()
        }
        index = cls({k: v for k, v in titles.items() if v}, str(data.get("region", "US")))
        logger.info("Loaded provider availability for %d titles (%s)", len(index._titles), index.region)
        return index

    @property
    def has_data(self) -> bool:
        """Whether any availability data is loaded."""
        return bool(self._titles)

    def __len__(self) -> int:
        return len(self._titles)

    def items(self):
        """Iterate ``(tmdb_id, provider_ids)`` pairs (used for the DB mirror)."""
        return self._titles.items()

    def available(self, tmdb_id: int | None) -> frozenset[int]:
        """Canonical provider ids carrying the title (empty when unknown)."""
        if tmdb_id is None:
            return frozenset()
        return self._titles.get(tmdb_id, frozenset())

    # ------------------------------------------------------------------ #
    # Filtering
    # ------------------------------------------------------------------ #
    def annotate(self, recs: list) -> None:
        """Stamp each ``Recommendation.providers`` with the title's services."""
        for rec in recs:
            rec.providers = sorted(self.available(rec.tmdb_id))

    def apply_filter(self, recs: list, mode: str, selected: list[int], count: int) -> list:
        """Apply the deck's provider filter to ranked recommendations.

        Args:
            recs: Ranked recommendations (already annotated or not — this
                annotates them as a side effect).
            mode: ``"all"`` (no-op), ``"only"`` (hard filter), or ``"prefer"``
                (on-service titles float to the front; nothing is dropped).
            selected: The user's provider ids.
            count: Final number of cards to return.

        Returns:
            The filtered/boosted list, trimmed to ``count``. With no selection
            or no availability data the filter degrades to "all".
        """
        self.annotate(recs)
        sel = set(selected) & CANONICAL_IDS
        if mode == "all" or not sel or not self.has_data:
            return recs[:count]

        def on_service(rec) -> bool:
            return bool(self.available(rec.tmdb_id) & sel)

        if mode == "only":
            return [r for r in recs if on_service(r)][:count]
        # "prefer": stable boost — on-service titles first, original ranked
        # order preserved within each group, nothing excluded.
        return sorted(recs, key=lambda r: not on_service(r))[:count]


# Over-fetch multiplier for the hard filter: the ranked list shrinks when
# off-service titles are dropped, so routes ask the recommender for extra.
ONLY_FILTER_OVERFETCH = 5
