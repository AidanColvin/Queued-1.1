"""One-shot repair of title-collision enrichment bugs in the catalog.

Two classes of corruption (see docs/TRAINING_LOG.md and git history):

1. **Wrong-film overviews.** ``build_catalog``/``_semantic_text`` fell back to
   the CMU summary keyed by ``(title, None)`` whenever the exact year missed —
   so any post-CMU film (corpus ends ~2012) sharing a title with an older film
   inherited the OLD film's plot (Inside Out 2015 got the 2011 crime film;
   Ex Machina got Appleseed Ex Machina). Detection replays the CMU lookup:
   a record whose overview matches the year-less fallback while the year-keyed
   lookup misses is provably wrong. Repair fetches the correct plot from
   Wikipedia REST summaries, trying ``Title (YEAR film)`` then ``Title (film)``
   (accepted only if the extract mentions the year) — else the overview is
   cleared (no text beats wrong text).

2. **Mass-duplicated trailer keys.** A YouTube-search enrichment pass scraped
   the first video id off search HTML; consent/generic pages made one id fan
   out over hundreds of films (19 keys covered 1,251 records). Any key shared
   by more than one film is wrong for at least all-but-one and untrustworthy
   for all — they are nulled; the trailer router's keyless runtime search
   takes over per request.

Rows whose overview changed are re-embedded (sentence-transformers if
available, else the hashing fallback) so the semantic space stops carrying the
wrong film's plot.

Run from ``backend``: ``python -m data.fix_collisions``
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path

import httpx
import numpy as np

from data.preprocess import load_cmu_summaries
from ml.artifacts import normalize_title

ARTIFACTS = Path("data/artifacts")
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
SLEEP = 0.2  # politeness; Wikimedia throttles datacenter IPs hard


def _wiki_extract(client: httpx.Client, article: str) -> str | None:
    try:
        r = client.get(WIKI_SUMMARY + article.replace(" ", "_"), timeout=20)
        if r.status_code != 200:
            return None
        extract = r.json().get("extract") or ""
        return extract.strip() or None
    except httpx.HTTPError:
        return None


def _display_title(title: str) -> str:
    """MovieLens catalog style -> Wikipedia article style.

    ``"Double, The"`` -> ``"The Double"``; trailing a.k.a. parentheticals are
    dropped. Without this, article guesses miss for every comma-article title.
    """
    title = re.sub(r"\s*\(a\.k\.a\..*\)$", "", title).strip()
    m = re.match(r"^(.*), (The|A|An)$", title)
    return f"{m.group(2)} {m.group(1)}" if m else title


def correct_overview(client: httpx.Client, title: str, year: int | None) -> str | None:
    """Year-disambiguated Wikipedia plot summary, or None if not confident."""
    title = _display_title(title)
    candidates = [f"{title} ({year} film)"] if year else []
    candidates += [f"{title} (film)", title]
    for i, article in enumerate(candidates):
        extract = _wiki_extract(client, article)
        time.sleep(SLEEP)
        if not extract:
            continue
        # Pages without the year qualifier are only trusted if they clearly
        # concern OUR film: the year must appear, and the bare-title article
        # must at least be about a film at all.
        if i > 0 and year and str(year) not in extract[:400]:
            continue
        if i == len(candidates) - 1 and "film" not in extract[:300].lower():
            continue
        return extract[:600]
    return None


def main() -> None:
    idx = json.loads((ARTIFACTS / "movie_index.json").read_text())
    movies = idx["movies"]
    cmu = load_cmu_summaries()

    # --- 1) overviews that provably came from the year-less CMU fallback ---
    wrong: list[dict] = []
    for m in movies:
        ov = m.get("overview") or ""
        if not ov:
            continue
        key = normalize_title(m["title"])
        year = m.get("year")
        exact = cmu.get((key, year)) or (year and (cmu.get((key, year - 1)) or cmu.get((key, year + 1))))
        fallback = cmu.get((key, None))
        if not exact and fallback and ov[:80] == str(fallback)[:80]:
            wrong.append(m)
    print(f"wrong-film overviews detected: {len(wrong)}")

    changed_rows: list[int] = []
    with httpx.Client(headers={"User-Agent": "queued-catalog-repair/1.0"}, follow_redirects=True) as client:
        for n, m in enumerate(wrong, 1):
            fixed = correct_overview(client, m["title"], m.get("year"))
            print(f"  [{n}/{len(wrong)}] {m['title']} ({m['year']}): "
                  f"{'fixed' if fixed else 'cleared (no confident source)'}")
            m["overview"] = fixed or ""
            changed_rows.append(m["idx"])

    # --- 2) trailer keys shared by >1 film are garbage: null them all ---
    counts = Counter(m["trailer_key"] for m in movies if m.get("trailer_key"))
    dup_keys = {k for k, c in counts.items() if c > 1}
    nulled = 0
    for m in movies:
        if m.get("trailer_key") in dup_keys:
            m["trailer_key"] = None
            nulled += 1
    print(f"nulled {nulled} duplicated trailer keys ({len(dup_keys)} distinct ids); "
          f"runtime YouTube-search fallback serves those titles")

    idx["meta"]["collision_repair"] = {
        "overviews_fixed": len(changed_rows),
        "trailer_keys_nulled": nulled,
    }
    (ARTIFACTS / "movie_index.json").write_text(json.dumps(idx, indent=2))

    # --- 3) re-embed rows whose overview changed ---
    if changed_rows:
        from ml.embeddings import get_embedder

        emb = np.load(ARTIFACTS / "embeddings.npy").astype(np.float32)
        embedder = get_embedder(prefer_semantic=True)
        texts = [
            (movies[i]["overview"] or movies[i]["title"])[:1000] for i in changed_rows
        ]
        vecs = embedder.encode(texts)
        if vecs.shape[1] == emb.shape[1]:
            for row, v in zip(changed_rows, vecs):
                emb[row] = v
            np.save(ARTIFACTS / "embeddings.npy", emb)
            print(f"re-embedded {len(changed_rows)} rows "
                  f"({type(embedder).__name__}, dim {vecs.shape[1]})")
        else:
            print(f"SKIPPED re-embedding: embedder dim {vecs.shape[1]} != artifact dim {emb.shape[1]}")


if __name__ == "__main__":
    main()
