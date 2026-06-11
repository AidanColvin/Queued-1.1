"""Netflix Prize ingestion: title matching, user-id offset, rating streaming.

Exercises the pure parse/match/stream logic on synthetic fixtures (no pandas,
no real download), so it runs in CI and guards the ID-mapping contract.
"""

import json

from data.ingest_netflix import (
    NETFLIX_USER_OFFSET,
    build_catalog_index,
    iter_ratings,
    load_movie_titles,
    match_titles,
)


def test_titles_match_catalog_by_title_and_year(tmp_path):
    raw, art = tmp_path / "raw", tmp_path / "art"
    raw.mkdir()
    art.mkdir()
    # netflixId,year,title  (Latin-1; NULL year is allowed)
    (raw / "movie_titles.csv").write_text(
        "1,2003,Lost in Translation\n"
        "2,1994,Forrest Gump\n"
        "3,1900,Some Unknown Film\n"
        "4,NULL,Pulp Fiction\n",
        encoding="latin-1",
    )
    (art / "movie_index.json").write_text(
        json.dumps(
            {
                "movies": [
                    {"movie_id": 356, "title": "Forrest Gump", "year": 1994},
                    {"movie_id": 296, "title": "Pulp Fiction", "year": 1994},
                    {"movie_id": 999, "title": "Lost in Translation", "year": 2004},
                ]
            }
        )
    )

    titles = load_movie_titles(raw)
    assert titles[1] == (2003, "Lost in Translation")
    assert titles[4][0] is None  # NULL year preserved

    matched = match_titles(titles, build_catalog_index(art))
    assert matched[2] == 356  # exact title + year
    assert matched[1] == 999  # year within ±1 (2003 vs 2004)
    assert matched[4] == 296  # NULL year -> unique normalized-title match
    assert 3 not in matched  # not in catalog -> dropped


def test_iter_ratings_offsets_users_and_skips_unmatched(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "combined_data_1.txt").write_text(
        "2:\n"
        "1488844,4,2005-09-06\n"
        "822109,5,2005-05-13\n"
        "3:\n"  # movie 3 is unmatched -> its ratings are skipped
        "100,1,2004-01-01\n",
        encoding="utf-8",
    )
    matched = {2: 356}  # only Netflix movie 2 maps to a catalog film
    rows = list(iter_ratings(matched, raw_dir=raw, parts=[1]))

    assert len(rows) == 2
    assert rows[0] == (NETFLIX_USER_OFFSET + 1488844, 356, 4.0, "2005-09-06")
    assert all(user >= NETFLIX_USER_OFFSET for user, *_ in rows)  # disjoint from MovieLens
