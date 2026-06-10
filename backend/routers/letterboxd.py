"""``/account/letterboxd`` — connect a Letterboxd account (no API key needed).

Two import paths, both feeding the same matcher (see :mod:`letterboxd`):

* ``POST /sync`` — fetch the user's **public RSS feed** (their ~50 most recent
  diary entries) by username.
* ``POST /import`` — upload the full **data export** (ZIP, or a bare
  ``ratings.csv``/``watched.csv``).

Imports are idempotent; re-running updates ratings in place and never
duplicates likes or seen entries.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import letterboxd
from auth.deps import get_current_user
from auth.ratelimit import rate_limit
from db.database import ExternalRating, User, get_db
from dependencies import get_session_store
from ml.reranker import SessionStore
from schemas import LetterboxdStatus, LetterboxdSummary, LetterboxdSyncRequest

logger = logging.getLogger("nextwatch")

router = APIRouter(prefix="/account/letterboxd", tags=["letterboxd"])

# Uploads: the full export ZIP for a heavy user is single-digit MB.
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _summary_out(summary: letterboxd.ImportSummary) -> LetterboxdSummary:
    return LetterboxdSummary(
        total=summary.total,
        matched=summary.matched,
        liked=summary.liked,
        seen=summary.seen,
        unmatched=summary.unmatched or [],
    )


def fetch_rss(username: str) -> str:
    """Fetch a profile's public RSS feed. Patchable in tests.

    Raises:
        HTTPException: ``404`` when the profile doesn't exist or is private,
            ``502`` when Letterboxd can't be reached.
    """
    url = f"https://letterboxd.com/{username}/rss/"
    try:
        res = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": "NextWatch/1.0"})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Letterboxd. Try again shortly.") from exc
    if res.status_code == 404:
        raise HTTPException(
            status_code=404, detail="No public Letterboxd profile found for that username."
        )
    if res.status_code != 200:
        raise HTTPException(status_code=502, detail="Letterboxd returned an unexpected response.")
    return res.text


@router.get("", response_model=LetterboxdStatus)
def status(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> LetterboxdStatus:
    """Connection state + import counts for the settings UI."""
    imported = db.scalar(select(func.count()).where(ExternalRating.user_id == user.id)) or 0
    matched = (
        db.scalar(
            select(func.count()).where(ExternalRating.user_id == user.id, ExternalRating.movie_id.is_not(None))
        )
        or 0
    )
    return LetterboxdStatus(username=user.letterboxd_username, imported=imported, matched=matched)


@router.post("/sync", response_model=LetterboxdSummary, dependencies=[Depends(rate_limit("lb_sync", 6, 300.0))])
def sync(
    payload: LetterboxdSyncRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    store: SessionStore = Depends(get_session_store),
) -> LetterboxdSummary:
    """Import the user's recent diary from their public RSS feed.

    Saves the username on the account so future re-syncs are one tap. RSS only
    carries the ~50 most recent entries — the CSV upload covers full history.
    """
    if not letterboxd.valid_username(payload.username):
        raise HTTPException(status_code=422, detail="That doesn't look like a Letterboxd username.")

    films = letterboxd.parse_rss(fetch_rss(payload.username))
    user.letterboxd_username = payload.username
    summary = letterboxd.apply_import(db, user.id, films, session_store=store)
    db.commit()
    logger.info("Letterboxd RSS sync for user %d: %d films, %d matched", user.id, summary.total, summary.matched)
    return _summary_out(summary)


@router.post("/import", response_model=LetterboxdSummary, dependencies=[Depends(rate_limit("lb_import", 6, 300.0))])
async def import_export(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    store: SessionStore = Depends(get_session_store),
) -> LetterboxdSummary:
    """Import a Letterboxd data export (ZIP, or ratings.csv / watched.csv)."""
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Export file is too large.")
    films = letterboxd.parse_upload(file.filename or "export.csv", content)
    if not films:
        raise HTTPException(
            status_code=422,
            detail="Couldn't read any films from that file. Upload your Letterboxd export ZIP, ratings.csv, or watched.csv.",
        )
    summary = letterboxd.apply_import(db, user.id, films, session_store=store)
    db.commit()
    logger.info("Letterboxd CSV import for user %d: %d films, %d matched", user.id, summary.total, summary.matched)
    return _summary_out(summary)
