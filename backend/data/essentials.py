"""Curated "must-have" titles that the MovieLens-trained catalog can't contain.

MovieLens 25M's ratings end around November 2019, so films released after that
(plus a few classics that fell out of the 10% sample) are simply not in the
trained model. This list lets :mod:`data.add_essentials` splice them into the
catalog so the deck always carries these marquee titles.

Each entry names an ``anchor`` — a near-identical title already in the catalog
(a prequel, the same franchise, or a close tonal match). The supplement copies
the anchor's collaborative / content / semantic vectors, so the new title
behaves sensibly in ``/recommend`` (surfaces for fans of the anchor, and liking
it pulls similar films) instead of being a dead, unrecommendable row.
"""

from __future__ import annotations

# Pre-release MovieLens placeholders → their real release names + years.
RENAMES: dict[str, tuple[str, int]] = {
    # "Avengers: Infinity War - Part I" / "Part II" were the dataset's
    # placeholder names before the films were titled.
    "avengers infinity war part i": ("Avengers: Infinity War", 2018),
    "avengers infinity war part ii": ("Avengers: Endgame", 2019),
}

# Genuinely-absent titles to splice in. ``anchor`` must be an existing catalog
# title (matched article/case-insensitively) whose vectors we copy.
ESSENTIALS: list[dict] = [
    {
        "title": "Oldboy",
        "year": 2003,
        "genres": ["Drama", "Mystery", "Thriller"],
        "tmdb_id": 670,
        "anchor": "Seven (a.k.a. Se7en)",
        "overview": "After 15 years of inexplicable imprisonment, a man is freed and given days to find who took his life from him — and why.",
    },
    {
        "title": "Parasite",
        "year": 2019,
        "genres": ["Comedy", "Drama", "Thriller"],
        "tmdb_id": 496243,
        "anchor": "Seven (a.k.a. Se7en)",
        "overview": "A poor family schemes its way into the employ of a wealthy household, with consequences that spiral out of control.",
    },
    {
        "title": "Top Gun: Maverick",
        "year": 2022,
        "genres": ["Action", "Drama"],
        "tmdb_id": 361743,
        "anchor": "Top Gun",
        "overview": "After thirty years as a Navy aviator, Maverick trains a detachment of graduates for a near-impossible mission.",
    },
    {
        "title": "Spider-Man: No Way Home",
        "year": 2021,
        "genres": ["Action", "Adventure", "Sci-Fi"],
        "tmdb_id": 634649,
        "anchor": "Spider-Man: Far from Home",
        "overview": "With his identity exposed, Peter Parker asks Doctor Strange for help — and tears open the multiverse.",
    },
    {
        "title": "Star Wars: The Rise of Skywalker",
        "year": 2019,
        "genres": ["Action", "Adventure", "Sci-Fi"],
        "tmdb_id": 181812,
        "anchor": "Star Wars: Episode VII - The Force Awakens",
        "overview": "The surviving Resistance faces the First Order once more as the saga of the Skywalkers reaches its end.",
    },
    {
        "title": "Black Panther: Wakanda Forever",
        "year": 2022,
        "genres": ["Action", "Adventure", "Drama"],
        "tmdb_id": 505642,
        "anchor": "Black Panther",
        "overview": "The leaders of Wakanda fight to protect their nation in the wake of King T'Challa's death.",
    },
    {
        "title": "Doctor Strange in the Multiverse of Madness",
        "year": 2022,
        "genres": ["Action", "Adventure", "Fantasy"],
        "tmdb_id": 453395,
        "anchor": "Doctor Strange",
        "overview": "Doctor Strange traverses the multiverse, teaming with old and new allies to confront a mysterious adversary.",
    },
    {
        "title": "Venom: Let There Be Carnage",
        "year": 2021,
        "genres": ["Action", "Sci-Fi", "Thriller"],
        "tmdb_id": 580489,
        "anchor": "Venom",
        "overview": "Eddie Brock and the symbiote Venom square off against serial killer Cletus Kasady, host to Carnage.",
    },
    {
        "title": "Indiana Jones and the Dial of Destiny",
        "year": 2023,
        "genres": ["Action", "Adventure"],
        "tmdb_id": 335977,
        "anchor": "Indiana Jones and the Last Crusade",
        "overview": "An aging Indiana Jones races a former Nazi to recover a legendary, reality-bending artifact.",
    },
]
