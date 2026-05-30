"""Enrich the catalog with movie posters — keyless, via Wikidata + Wikipedia.

The bundled catalog ships with ``tmdb_id`` for nearly every title but no poster
image (real TMDB posters need an API key). This script fills ``poster_url``
*without any API key* by walking a fully public chain:

    movie_id ──(links.csv)──▶ imdb_id ──(Wikidata P345)──▶ English Wikipedia
    article ──(pageimages)──▶ poster thumbnail on upload.wikimedia.org

English Wikipedia hosts film posters under fair-use (Wikimedia *Commons* does
not, which is why ``P18`` is unreliable for posters), so the article's lead
image is almost always the poster. ``pilicense=any`` is required to include
those non-free images.

Run it to bake poster URLs into ``movie_index.json`` (committed, so the deployed
API serves them with no runtime dependency on Wikipedia)::

    cd backend
    .venv/bin/python -m data.enrich_keyless

The run is **resumable**: it only fetches titles that don't already have a
poster, so Wikimedia's aggressive rate-limiting of datacenter IPs (HTTP 429) is
handled by simply re-running until coverage plateaus. Each request retries with
exponential backoff that honors ``Retry-After``, and progress is checkpointed to
``movie_index.json`` every few batches. Only the catalog JSON is rewritten — the
aligned model matrices are untouched. Uses ``httpx`` only; no API key.
"""

from __future__ import annotations

import csv
import json
import random
import time
from pathlib import Path

import httpx

from config import get_settings
from db.database import Movie, get_session_factory, init_db, seed_movies
from ml.artifacts import MOVIE_INDEX_FILE, ArtifactBundle, load_artifacts

# A descriptive User-Agent is mandatory: the Wikidata Query Service and the
# MediaWiki API both reject generic/blank agents.
USER_AGENT = "NextWatch/1.0 (portfolio recommender; keyless poster enrichment)"
WDQS_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

LINKS_CSV = Path(__file__).resolve().parent / "raw" / "ml-25m" / "links.csv"

# Batch sizes — kept at each service's limits to minimise request count.
SPARQL_BATCH = 200      # imdb ids per Wikidata query
PAGEIMAGES_BATCH = 50   # titles per MediaWiki query (the API hard cap)
THUMB_SIZE = 500        # poster width in px — crisp on the 420px-wide cards
SPARQL_SLEEP = 1.0      # base pause between Wikidata queries
WIKI_SLEEP = 1.5        # base pause between MediaWiki queries
CHECKPOINT_EVERY = 15   # flush posters to disk every N Wikipedia batches
MAX_RETRIES = 5


def _imdb_map() -> dict[int, str]:
    """Map MovieLens ``movieId`` to a full IMDb id (``tt0109830``).

    Returns:
        ``movie_id`` → ``"tt"``-prefixed IMDb id, read from MovieLens
        ``links.csv``. Rows without an IMDb id are skipped.
    """
    out: dict[int, str] = {}
    with LINKS_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            imdb = (row.get("imdbId") or "").strip()
            if imdb:
                out[int(row["movieId"])] = f"tt{imdb}"
    return out


def _request_with_retry(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response | None:
    """Issue a request, retrying through rate-limits and transient errors.

    Wikimedia throttles datacenter IPs hard (HTTP 429) and occasionally returns
    502/503. On any of those this backs off exponentially — honoring a
    ``Retry-After`` header when present — and retries up to :data:`MAX_RETRIES`
    times. Returns ``None`` when every attempt is exhausted so the caller can
    leave those titles for the next resumable run.

    Args:
        client: An open httpx client.
        method: HTTP verb (``"GET"`` / ``"POST"``).
        url: Target URL.
        **kwargs: Passed through to ``client.request`` (params, data, headers…).

    Returns:
        A successful :class:`httpx.Response`, or ``None`` if it never succeeded.
    """
    delay = 10.0
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.request(method, url, **kwargs)
            if resp.status_code in (429, 502, 503):
                if attempt == MAX_RETRIES:
                    return None
                header = resp.headers.get("Retry-After", "")
                wait = float(header) if header.isdigit() else delay
                time.sleep(min(wait, 60.0) + random.uniform(0, 1.5))
                delay = min(delay * 2, 60.0)
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPError:
            if attempt == MAX_RETRIES:
                return None
            time.sleep(delay + random.uniform(0, 1.5))
            delay = min(delay * 2, 60.0)
    return None


def _wikidata_articles(client: httpx.Client, imdb_ids: list[str]) -> dict[str, str]:
    """Resolve IMDb ids to English Wikipedia article titles via Wikidata.

    Uses one SPARQL query per :data:`SPARQL_BATCH` ids: each id is matched to
    its film item by ``P345`` (IMDb id), then to the item's English Wikipedia
    sitelink. The sitelink name is the canonical article title (never a
    redirect), so it can be fed straight to the pageimages API.

    Args:
        client: An open httpx client.
        imdb_ids: Full ``tt``-prefixed IMDb ids.

    Returns:
        ``imdb_id`` → English Wikipedia article title (only resolved ids).
    """
    resolved: dict[str, str] = {}
    for start in range(0, len(imdb_ids), SPARQL_BATCH):
        batch = imdb_ids[start : start + SPARQL_BATCH]
        values = " ".join(f'"{i}"' for i in batch)
        query = (
            "SELECT ?imdb ?name WHERE {"
            f"  VALUES ?imdb {{ {values} }}"
            "  ?film wdt:P345 ?imdb ."
            "  ?article schema:about ?film ;"
            "           schema:isPartOf <https://en.wikipedia.org/> ;"
            "           schema:name ?name ."
            "}"
        )
        resp = _request_with_retry(
            client,
            "POST",
            WDQS_ENDPOINT,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
            timeout=60,
        )
        if resp is not None:
            try:
                for row in resp.json()["results"]["bindings"]:
                    resolved.setdefault(row["imdb"]["value"], row["name"]["value"])
            except (ValueError, KeyError):
                pass
        done = min(start + SPARQL_BATCH, len(imdb_ids))
        print(f"  Wikidata: {done}/{len(imdb_ids)} ids → {len(resolved)} articles", flush=True)
        time.sleep(SPARQL_SLEEP)
    return resolved


def _norm(title: str) -> str:
    """Normalize an article title for matching (case- and underscore-insensitive)."""
    return title.replace("_", " ").strip().casefold()


def enrich() -> None:
    """Fill ``poster_url`` for every catalog title that still lacks one, then persist."""
    settings = get_settings()
    art = settings.artifacts_dir
    bundle = load_artifacts(art)
    imdb_map = _imdb_map()

    # Resumable: only work on titles that don't already have a poster.
    todo = [r for r in bundle.catalog if not r.poster_url and r.movie_id in imdb_map]
    have = sum(1 for r in bundle.catalog if r.poster_url)
    print(f"{have}/{len(bundle.catalog)} already have posters; resolving {len(todo)} more (keyless)…", flush=True)
    if not todo:
        print("Nothing to do.")
        return

    imdb_ids = sorted({imdb_map[r.movie_id] for r in todo})
    article_to_recs: dict[str, list] = {}

    with httpx.Client() as client:
        imdb_to_article = _wikidata_articles(client, imdb_ids)
        for rec in todo:
            article = imdb_to_article.get(imdb_map[rec.movie_id])
            if article:
                article_to_recs.setdefault(_norm(article), []).append(rec)

        titles = sorted({a for a in imdb_to_article.values()})
        print(f"Fetching posters for {len(titles)} resolved articles…", flush=True)
        filled = 0
        for bi, start in enumerate(range(0, len(titles), PAGEIMAGES_BATCH)):
            batch = titles[start : start + PAGEIMAGES_BATCH]
            resp = _request_with_retry(
                client,
                "GET",
                WIKIPEDIA_API,
                params={
                    "action": "query",
                    "format": "json",
                    "formatversion": "2",
                    "prop": "pageimages",
                    "piprop": "thumbnail",
                    "pithumbsize": str(THUMB_SIZE),
                    "pilicense": "any",
                    "titles": "|".join(batch),
                },
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            if resp is not None:
                try:
                    pages = resp.json().get("query", {}).get("pages", [])
                except ValueError:
                    pages = []
                for page in pages:
                    thumb = page.get("thumbnail", {}).get("source")
                    if thumb and page.get("title"):
                        for rec in article_to_recs.get(_norm(page["title"]), []):
                            if not rec.poster_url:
                                rec.poster_url = thumb
                                filled += 1
            done = min(start + PAGEIMAGES_BATCH, len(titles))
            print(f"  Wikipedia: {done}/{len(titles)} titles → {filled} new posters", flush=True)
            if (bi + 1) % CHECKPOINT_EVERY == 0:
                _write_index(bundle, art)
                print(f"  …checkpointed ({have + filled} total)", flush=True)
            time.sleep(WIKI_SLEEP + random.uniform(0, 0.6))

    bundle.meta["enriched"] = "wikipedia-keyless"
    _write_index(bundle, art)

    # Refresh the SQLite catalog so /search returns the new posters too.
    init_db()
    with get_session_factory()() as session:
        session.query(Movie).delete()
        session.commit()
    seed_movies(bundle.catalog)

    total = have + filled
    pct = 100 * total / len(bundle.catalog) if bundle.catalog else 0
    print(f"\nDone. +{filled} this run → {total}/{len(bundle.catalog)} posters ({pct:.0f}%).")
    print("Re-run to fill more (rate-limited titles retry); restart the API to serve them.")


def _write_index(bundle: ArtifactBundle, out_dir: Path) -> None:
    """Rewrite only ``movie_index.json`` (the matrices are unchanged by enrichment)."""
    index = {
        "meta": {**bundle.meta, "n_movies": bundle.size},
        "movies": [m.to_json() for m in bundle.catalog],
    }
    (Path(out_dir) / MOVIE_INDEX_FILE).write_text(json.dumps(index, indent=2), encoding="utf-8")


if __name__ == "__main__":
    enrich()
