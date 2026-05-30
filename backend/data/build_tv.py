"""Build a popular-TV catalog — keyless, via Wikidata + Wikipedia.

MovieLens (and therefore the trained recommender) is movies-only, so the TV
stack is a separate, self-contained catalog with no ML model behind it: the
top ~300 television series by global Wikipedia presence, served in popularity
order. It reuses the exact keyless chain the movie posters use:

    Wikidata (television series, ranked by wikibase:sitelinks) ──▶ imdb_id,
    English Wikipedia article, year, genres ──(pageimages + extracts)──▶
    poster thumbnail + 2-sentence synopsis

Writes ``tv_index.json`` next to the model artifacts (catalog only — TV has no
aligned ML matrices). The ``/tv`` endpoint serves it. Run::

    cd backend
    .venv/bin/python -m data.build_tv

Resumable and rate-limit-aware (it shares the retry/backoff helper used for
movie posters). Uses ``httpx`` only; no API key.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

from config import get_settings
from data.enrich_keyless import (
    USER_AGENT,
    WDQS_ENDPOINT,
    WIKIPEDIA_API,
    _norm,
    _request_with_retry,
)

TV_INDEX_FILE = "tv_index.json"
TARGET = 300            # number of series to keep
EXTRACT_BATCH = 20      # MediaWiki extracts cap exlimit at 20
GENRE_BATCH = 150       # imdb ids per genre query
ID_OFFSET = 8_000_000   # keep TV ids clear of MovieLens movie_ids

# Strips a trailing Wikipedia disambiguation suffix like "(TV series)",
# "(American TV series)" or "(2004 TV series)" from the display title.
_DISAMBIG = re.compile(r"\s*\((?:[^()]*\bTV\b[^()]*|\d{4}[^()]*)\)\s*$")


def _clean_title(title: str) -> str:
    """Drop a trailing ``(… TV series)`` / ``(YYYY …)`` disambiguation suffix."""
    return _DISAMBIG.sub("", title).strip()


def _popular_series(client: httpx.Client) -> list[dict]:
    """Return the most-linked television series from Wikidata.

    Ranks by ``wikibase:sitelinks`` — a precomputed per-item count of language
    editions, a reliable popularity proxy that needs no aggregation (so the
    query stays fast). Each result has an IMDb id and an English Wikipedia
    article.

    Args:
        client: An open httpx client.

    Returns:
        Dicts with ``imdb``, ``article`` (title), ``year`` and ``links``,
        de-duplicated and ordered most-popular first.
    """
    query = (
        "SELECT ?imdb ?name ?year ?links WHERE {"
        "  ?item wdt:P31 wd:Q5398426 ;"          # instance of: television series
        "        wdt:P345 ?imdb ;"
        "        wikibase:sitelinks ?links ."
        "  ?article schema:about ?item ;"
        "           schema:isPartOf <https://en.wikipedia.org/> ;"
        "           schema:name ?name ."
        "  OPTIONAL { ?item wdt:P580 ?start. BIND(YEAR(?start) AS ?year) }"
        "}"
        f" ORDER BY DESC(?links) LIMIT {TARGET * 2}"
    )
    resp = _request_with_retry(
        client, "POST", WDQS_ENDPOINT,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        timeout=90,
    )
    out: list[dict] = []
    seen: set[str] = set()
    if resp is not None:
        for row in resp.json()["results"]["bindings"]:
            imdb = row["imdb"]["value"]
            if imdb in seen:
                continue
            seen.add(imdb)
            year = row.get("year", {}).get("value")
            out.append({
                "imdb": imdb,
                "article": row["name"]["value"],
                "year": int(year) if year else None,
                "links": int(row["links"]["value"]),
            })
            if len(out) >= TARGET:
                break
    return out


def _genres(client: httpx.Client, imdb_ids: list[str]) -> dict[str, list[str]]:
    """Map IMDb id → genre labels (Wikidata P136), batched."""
    genres: dict[str, list[str]] = {}
    for start in range(0, len(imdb_ids), GENRE_BATCH):
        batch = imdb_ids[start : start + GENRE_BATCH]
        values = " ".join(f'"{i}"' for i in batch)
        query = (
            "SELECT ?imdb ?g WHERE {"
            f"  VALUES ?imdb {{ {values} }}"
            "  ?item wdt:P345 ?imdb ; wdt:P136 ?genre ."
            '  ?genre rdfs:label ?g FILTER(LANG(?g)="en") .'
            "}"
        )
        resp = _request_with_retry(
            client, "POST", WDQS_ENDPOINT,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
            timeout=90,
        )
        if resp is not None:
            for row in resp.json()["results"]["bindings"]:
                raw = row["g"]["value"].lower().replace(" film", "").replace(" series", "").replace(" television", "")
                label = " ".join(w.capitalize() for w in raw.split())  # word-case, keeps "Children's"
                bucket = genres.setdefault(row["imdb"]["value"], [])
                if label and label not in bucket and len(bucket) < 3:
                    bucket.append(label)
        time.sleep(1.0)
    return genres


def _posters_and_overviews(client: httpx.Client, titles: list[str]) -> dict[str, dict]:
    """Fetch poster thumbnail + 2-sentence intro for each article, batched."""
    out: dict[str, dict] = {}
    unique = sorted(set(titles))
    for start in range(0, len(unique), EXTRACT_BATCH):
        batch = unique[start : start + EXTRACT_BATCH]
        resp = _request_with_retry(
            client, "GET", WIKIPEDIA_API,
            params={
                "action": "query", "format": "json", "formatversion": "2",
                "prop": "pageimages|extracts",
                "piprop": "thumbnail", "pithumbsize": "500", "pilicense": "any",
                "exintro": "1", "explaintext": "1", "exsentences": "2",
                "titles": "|".join(batch),
            },
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        if resp is not None:
            for page in resp.json().get("query", {}).get("pages", []):
                if not page.get("title"):
                    continue
                out[_norm(page["title"])] = {
                    "poster_url": page.get("thumbnail", {}).get("source"),
                    "overview": (page.get("extract") or "").strip(),
                }
        print(f"  Wikipedia: {min(start + EXTRACT_BATCH, len(unique))}/{len(unique)} series", flush=True)
        time.sleep(1.5)
    return out


def build() -> None:
    """Fetch the popular-TV catalog and write ``tv_index.json``."""
    out_path = get_settings().artifacts_dir / TV_INDEX_FILE
    with httpx.Client() as client:
        print("Querying Wikidata for the most-linked television series…", flush=True)
        series = _popular_series(client)
        print(f"  {len(series)} series. Fetching genres + posters + synopses (keyless)…", flush=True)
        imdb_ids = [s["imdb"] for s in series]
        genres = _genres(client, imdb_ids)
        media = _posters_and_overviews(client, [s["article"] for s in series])

    catalog: list[dict] = []
    for i, s in enumerate(series):
        m = media.get(_norm(s["article"]), {})
        if not m.get("poster_url"):
            continue  # no poster → skip (keeps the TV deck clean)
        catalog.append({
            "id": ID_OFFSET + i,
            "title": _clean_title(s["article"]),
            "year": s["year"],
            "type": "tv",
            "genres": genres.get(s["imdb"], []),
            "cast": [],
            "overview": m.get("overview", ""),
            "poster_url": m["poster_url"],
            "tmdb_id": None,
        })

    out_path.write_text(
        json.dumps({"meta": {"source": "wikidata-keyless", "n_series": len(catalog)}, "series": catalog}, indent=2),
        encoding="utf-8",
    )
    print(f"\nDone. Wrote {len(catalog)} TV series with posters to {out_path.name}. Restart the API to serve /tv.")


if __name__ == "__main__":
    build()
