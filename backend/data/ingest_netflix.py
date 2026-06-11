"""Fold the Netflix Prize dataset into the collaborative-filtering training set.

The Netflix Prize data uses its own movie ids (1..17770) and customer ids, so it
can't be concatenated with MovieLens directly. This module:

  1. reads ``movie_titles.csv`` (``netflixId,year,title``) and matches each
     Netflix film to a catalog row by normalized title + year (±1) — the same
     matcher the Letterboxd importer uses, so the ids land in the catalog's
     MovieLens ``movieId`` space;
  2. streams ``combined_data_*.txt`` (``N:`` movie header, then
     ``custId,rating,date`` rows), keeping only ratings for matched films;
  3. offsets the customer ids into a disjoint range so they never collide with
     MovieLens users;
  4. writes ``data/artifacts/netflix_ratings.parquet`` in the exact
     ``userId,movieId,rating,timestamp`` schema ``ml.collaborative`` consumes.

The CF trainer (``ml.collaborative``) automatically concatenates this supplement
when it exists, so retraining picks up the extra ~100M ratings with no code
change. Absent the raw files this module is a no-op.

Run from ``backend`` after placing the Kaggle download under
``data/raw/netflix/``::

    python -m data.ingest_netflix            # all combined_data_*.txt
    python -m data.ingest_netflix --part 1   # just combined_data_1.txt

Note: the Netflix Prize dataset is research/non-commercial only (it was withdrawn
by Netflix over re-identification concerns) — the same non-commercial constraint
that already governs this project's MovieLens/IMDb data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator

from ml.artifacts import normalize_title

DATA_DIR = Path(__file__).resolve().parent
RAW_DIR = DATA_DIR / "raw" / "netflix"
ARTIFACTS = DATA_DIR / "artifacts"

# Customer ids are shifted past any plausible MovieLens userId so the two rating
# sources occupy disjoint user spaces in the factorization.
NETFLIX_USER_OFFSET = 100_000_000


def load_movie_titles(raw_dir: Path = RAW_DIR) -> dict[int, tuple[int | None, str]]:
    """Parse ``movie_titles.csv`` -> ``{netflix_id: (year, title)}``.

    The file is Latin-1 and titles can contain commas, so each line is split
    into exactly three fields. ``year`` is ``None`` when the source has ``NULL``.
    """
    path = raw_dir / "movie_titles.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — place the Kaggle download under {raw_dir}/")
    out: dict[int, tuple[int | None, str]] = {}
    with open(path, encoding="latin-1") as fh:
        for line in fh:
            parts = line.rstrip("\n").split(",", 2)
            if len(parts) != 3:
                continue
            nid, year, title = parts
            try:
                out[int(nid)] = (int(year) if year not in ("", "NULL") else None, title)
            except ValueError:
                continue
    return out


def build_catalog_index(artifacts: Path = ARTIFACTS) -> dict[str, list[tuple[int | None, int]]]:
    """Catalog lookup ``{normalized_title: [(year, movieId), ...]}`` for matching."""
    movies = json.loads((artifacts / "movie_index.json").read_text())["movies"]
    index: dict[str, list[tuple[int | None, int]]] = {}
    for m in movies:
        index.setdefault(normalize_title(m["title"]), []).append((m.get("year"), m["movie_id"]))
    return index


def match_titles(
    movie_titles: dict[int, tuple[int | None, str]],
    catalog: dict[str, list[tuple[int | None, int]]],
) -> dict[int, int]:
    """Resolve ``{netflix_id: catalog_movieId}`` by normalized title + year (±1)."""
    matched: dict[int, int] = {}
    for nid, (year, title) in movie_titles.items():
        candidates = catalog.get(normalize_title(title))
        if not candidates:
            continue
        if year is None or len(candidates) == 1:
            matched[nid] = candidates[0][1]
            continue
        best = min(
            candidates,
            key=lambda c: abs((c[0] or 0) - year) if c[0] is not None else 99,
        )
        if best[0] is None or abs(best[0] - year) <= 1:
            matched[nid] = best[1]
    return matched


def iter_ratings(
    netflix_to_movie: dict[int, int], raw_dir: Path = RAW_DIR, parts: list[int] | None = None
) -> Iterator[tuple[int, int, float, str]]:
    """Stream ``(userId, movieId, rating, date)`` rows for matched films only.

    Parses the Netflix ``combined_data_*.txt`` layout: a ``N:`` line sets the
    current Netflix movie, following ``cust,rating,date`` lines are its ratings.
    """
    files = (
        [raw_dir / f"combined_data_{p}.txt" for p in parts]
        if parts
        else sorted(raw_dir.glob("combined_data_*.txt"))
    )
    for path in files:
        if not path.exists():
            continue
        current: int | None = None  # catalog movieId, or None to skip this block
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.endswith(":\n") or line.endswith(":"):
                    current = netflix_to_movie.get(int(line.split(":")[0]))
                elif current is not None:
                    cust, rating, date = line.rstrip("\n").split(",")
                    yield NETFLIX_USER_OFFSET + int(cust), current, float(rating), date


def ingest(parts: list[int] | None = None) -> int:
    """Match, stream, and write ``netflix_ratings.parquet``. Returns row count."""
    import pandas as pd

    titles = load_movie_titles()
    catalog = build_catalog_index()
    matched = match_titles(titles, catalog)
    print(f"matched {len(matched):,}/{len(titles):,} Netflix films to the catalog")

    rows = list(iter_ratings(matched, parts=parts))
    if not rows:
        print("no ratings produced (no matched films in the provided combined_data files)")
        return 0
    df = pd.DataFrame(rows, columns=["userId", "movieId", "rating", "date"])
    # Seconds since epoch, robust to pandas' datetime resolution (ns vs us): cast
    # to second precision first, then to int64 — `// 10**9` would be wrong unless
    # the dtype is exactly datetime64[ns].
    df["timestamp"] = pd.to_datetime(df["date"]).astype("datetime64[s]").astype("int64")
    df = df.drop(columns=["date"])
    out = ARTIFACTS / "netflix_ratings.parquet"
    df.to_parquet(out)
    print(
        f"wrote {len(df):,} ratings ({df.userId.nunique():,} users, "
        f"{df.movieId.nunique():,} films) -> {out}"
    )
    print("Re-run `python -m ml.collaborative` to retrain CF including this data.")
    return len(df)


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest Netflix Prize ratings into the CF training set.")
    ap.add_argument("--part", type=int, action="append", help="combined_data_N.txt to read (repeatable)")
    args = ap.parse_args()
    ingest(parts=args.part)


if __name__ == "__main__":
    main()
