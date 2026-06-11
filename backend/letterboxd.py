"""Letterboxd import: public RSS feed + CSV/ZIP export parsing and matching.

Letterboxd's official API is approval-gated, so Queued connects without it:

* **RSS** — every public profile exposes ``letterboxd.com/{user}/rss/`` with
  the ~50 most recent diary entries, including ``letterboxd:filmTitle``,
  ``letterboxd:filmYear``, ``letterboxd:memberRating`` and ``tmdb:movieId``.
* **CSV/ZIP** — the full-history path: users upload their Letterboxd data
  export (``ratings.csv`` / ``watched.csv``).

Films are matched against the catalog by TMDB id first, then by normalized
title + year (±1). Matches feed the account: well-rated films (≥3.5★) become
"liked" seeds, everything watched joins the seen-set so it stops appearing in
the deck, and newly imported likes nudge the persisted taste vector.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.database import ExternalRating, Movie, UserProfile, UserSavedTitle
from ml.artifacts import normalize_title
from schemas import Recommendation

# A rating at or above this many stars counts as a "like".
LIKED_THRESHOLD = 3.5
# Cap parsed rows per import (a full export is a few thousand films).
MAX_IMPORT_ROWS = 20_000

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{2,32}$")

# Trailing "<title>, <year> - ★★★½" pattern in RSS <title> fallback parsing.
_RSS_TITLE_RE = re.compile(r"^(?P<title>.+?), (?P<year>\d{4})(?: - (?P<stars>[★½]+))?$")


def valid_username(username: str) -> bool:
    """Letterboxd usernames: alphanumeric + underscore. Also blocks URL tricks
    (the username is interpolated into the fetch URL)."""
    return bool(_USERNAME_RE.match(username))


@dataclass(slots=True)
class ImportedFilm:
    """One film parsed from a feed or export."""

    title: str
    year: int | None
    rating: float | None  # stars (0.5–5.0), None for watched-only rows
    tmdb_id: int | None = None


@dataclass(slots=True)
class ImportSummary:
    """Outcome of one import run (returned to the UI)."""

    total: int = 0
    matched: int = 0
    liked: int = 0
    seen: int = 0
    unmatched: list[str] | None = None


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _stars_to_float(stars: str) -> float | None:
    value = stars.count("★") + (0.5 if "½" in stars else 0.0)
    return value or None


def _find_text(item: ElementTree.Element, local: str) -> str | None:
    """Find a child by local tag name, ignoring its XML namespace."""
    for child in item.iter():
        if child.tag.rsplit("}", 1)[-1] == local and child.text:
            return child.text.strip()
    return None


def parse_rss(xml_text: str) -> list[ImportedFilm]:
    """Parse a Letterboxd profile RSS feed into films.

    Tolerant of namespace/format drift: the ``letterboxd:``/``tmdb:`` elements
    are matched by local name, with the ``<title>`` string as a fallback.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    films: list[ImportedFilm] = []
    for item in root.iter("item"):
        title = _find_text(item, "filmTitle")
        year_text = _find_text(item, "filmYear")
        rating_text = _find_text(item, "memberRating")
        tmdb_text = _find_text(item, "movieId")

        rating = None
        if rating_text:
            try:
                rating = float(rating_text) or None
            except ValueError:
                rating = None

        if not title:
            raw = _find_text(item, "title") or ""
            m = _RSS_TITLE_RE.match(raw)
            if not m:
                continue
            title = m.group("title")
            year_text = m.group("year")
            if rating is None and m.group("stars"):
                rating = _stars_to_float(m.group("stars"))

        films.append(
            ImportedFilm(
                title=title,
                year=int(year_text) if year_text and year_text.isdigit() else None,
                rating=rating,
                tmdb_id=int(tmdb_text) if tmdb_text and tmdb_text.isdigit() else None,
            )
        )
    return films[:MAX_IMPORT_ROWS]


def parse_csv(content: bytes) -> list[ImportedFilm]:
    """Parse a Letterboxd export CSV (``ratings.csv`` or ``watched.csv``).

    Both share the columns ``Date,Name,Year,Letterboxd URI``; ``ratings.csv``
    adds ``Rating`` (stars as a decimal).
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")

    films: list[ImportedFilm] = []
    for row in csv.DictReader(io.StringIO(text)):
        title = (row.get("Name") or "").strip()
        if not title:
            continue
        year_text = (row.get("Year") or "").strip()
        rating_text = (row.get("Rating") or "").strip()
        rating = None
        if rating_text:
            try:
                rating = float(rating_text) or None
            except ValueError:
                rating = None
        films.append(
            ImportedFilm(
                title=title,
                year=int(year_text) if year_text.isdigit() else None,
                rating=rating,
            )
        )
        if len(films) >= MAX_IMPORT_ROWS:
            break
    return films


def parse_upload(filename: str, content: bytes) -> list[ImportedFilm]:
    """Parse an uploaded export: a bare CSV, or the full export ZIP (uses
    ``ratings.csv`` + ``watched.csv``; rated rows win over watched-only)."""
    if not filename.lower().endswith(".zip"):
        return parse_csv(content)

    films: dict[tuple[str, int | None], ImportedFilm] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            for wanted in ("watched.csv", "ratings.csv"):  # ratings last → wins
                for name in names:
                    if name.rsplit("/", 1)[-1] == wanted:
                        for film in parse_csv(archive.read(name)):
                            key = (normalize_title(film.title), film.year)
                            if film.rating is not None or key not in films:
                                films[key] = film
    except zipfile.BadZipFile:
        return []
    return list(films.values())[:MAX_IMPORT_ROWS]


# --------------------------------------------------------------------------- #
# Matching + applying
# --------------------------------------------------------------------------- #
def _match(db: Session, film: ImportedFilm) -> Movie | None:
    """Resolve a film to a catalog row: TMDB id, then title (+year ±1)."""
    if film.tmdb_id is not None:
        movie = db.scalar(select(Movie).where(Movie.tmdb_id == film.tmdb_id, Movie.type == "movie"))
        if movie is not None:
            return movie
    candidates = db.scalars(select(Movie).where(Movie.title_norm == normalize_title(film.title))).all()
    if not candidates:
        return None
    if film.year is None:
        return candidates[0]
    by_year = [m for m in candidates if m.year is not None and abs(m.year - film.year) <= 1]
    return by_year[0] if by_year else (candidates[0] if all(m.year is None for m in candidates) else None)


def _movie_to_rec(movie: Movie, why: str) -> Recommendation:
    """Build the stored card for an imported like (the watchlist renders it)."""
    return Recommendation(
        id=movie.movie_id,
        title=movie.title,
        year=movie.year,
        type="movie",
        score=0.85,
        genres=list(movie.genres or []),
        poster_url=movie.poster_url,
        tmdb_id=movie.tmdb_id,
        why=why,
    )


def apply_import(db: Session, user_id: int, films: list[ImportedFilm], session_store=None) -> ImportSummary:
    """Fold parsed films into the user's account (idempotent).

    * upserts ``external_ratings`` rows (re-syncs update ratings in place),
    * matched films join the seen-set; well-rated ones also become likes,
    * **newly** imported likes nudge the persisted taste vector (Layer 2) when
      a ``session_store`` is available.

    The caller commits.
    """
    existing_ext = {
        (r.title.lower(), r.year): r
        for r in db.scalars(select(ExternalRating).where(ExternalRating.user_id == user_id))
    }
    existing_saved = {
        (row.movie_id, row.kind)
        for row in db.scalars(select(UserSavedTitle).where(UserSavedTitle.user_id == user_id))
    }

    summary = ImportSummary(unmatched=[])
    new_liked_tmdb: list[int] = []
    seen_keys: set[tuple[str, int | None]] = set()

    for film in films:
        key = (film.title.lower(), film.year)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        summary.total += 1

        movie = _match(db, film)

        ext = existing_ext.get(key)
        if ext is None:
            ext = ExternalRating(user_id=user_id, source="letterboxd", title=film.title, year=film.year)
            db.add(ext)
            existing_ext[key] = ext
        if film.rating is not None:
            ext.rating = film.rating
        if movie is not None:
            ext.movie_id = movie.movie_id
            ext.tmdb_id = movie.tmdb_id

        if movie is None:
            if len(summary.unmatched) < 50:
                summary.unmatched.append(f"{film.title}{f' ({film.year})' if film.year else ''}")
            continue
        summary.matched += 1

        # Watched → seen (kept out of the deck).
        if (movie.movie_id, "seen") not in existing_saved:
            db.add(UserSavedTitle(user_id=user_id, movie_id=movie.movie_id, kind="seen", rec_json=None))
            existing_saved.add((movie.movie_id, "seen"))
            summary.seen += 1

        # Well-rated → liked seed.
        if film.rating is not None and film.rating >= LIKED_THRESHOLD:
            if (movie.movie_id, "liked") not in existing_saved:
                rec = _movie_to_rec(movie, f"You rated it {film.rating:g}★ on Letterboxd.")
                db.add(
                    UserSavedTitle(
                        user_id=user_id, movie_id=movie.movie_id, kind="liked", rec_json=rec.model_dump()
                    )
                )
                existing_saved.add((movie.movie_id, "liked"))
                summary.liked += 1
                if movie.tmdb_id is not None:
                    new_liked_tmdb.append(movie.tmdb_id)

    if new_liked_tmdb and session_store is not None:
        _nudge_taste_vector(db, user_id, new_liked_tmdb, session_store)

    return summary


def _nudge_taste_vector(db: Session, user_id: int, liked_tmdb_ids: list[int], store) -> None:
    """Fold newly imported likes into the persisted cross-session taste vector."""
    import numpy as np

    profile = db.get(UserProfile, user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    vec = profile.taste_vector
    init = np.asarray(vec, dtype=np.float32) if vec and len(vec) == store.dim else None
    reranker = store.reranker_for_user(init, profile.confidence or 0.0)
    applied = False
    for tmdb_id in liked_tmdb_ids:
        applied = reranker.update(tmdb_id, "liked", 3000) or applied
    if applied:
        profile.taste_vector = reranker.session_vector.tolist()
        profile.confidence = reranker.confidence
