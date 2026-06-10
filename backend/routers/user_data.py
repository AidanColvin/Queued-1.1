"""``/account`` — a signed-in user's saved state (Phase 3).

Backs the watchlist/liked deck and the seen-set across devices. ``SwipeEvent``
stays the analytics/training log; this is the UI-facing state, stored as full
``Recommendation`` JSON so the SPA can re-render cards verbatim.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_current_user
from db.database import User, UserSavedTitle, get_db
from schemas import HistoryResponse, MergeRequest, Recommendation, SaveTitleRequest

router = APIRouter(prefix="/account", tags=["account"])

# kinds stored in ``user_saved_titles.kind``.
_LIKED, _WISHLIST, _SEEN = "liked", "wishlist", "seen"


def _load_history(db: Session, user_id: int) -> HistoryResponse:
    """Assemble a user's liked/wishlist recs + seen ids from saved titles."""
    rows = db.scalars(select(UserSavedTitle).where(UserSavedTitle.user_id == user_id)).all()
    liked: list[Recommendation] = []
    wishlist: list[Recommendation] = []
    seen: list[int] = []
    for row in rows:
        if row.kind == _SEEN:
            seen.append(row.movie_id)
        elif row.rec_json is not None:
            rec = Recommendation.model_validate(row.rec_json)
            (liked if row.kind == _LIKED else wishlist).append(rec)
    return HistoryResponse(liked=liked, wishlist=wishlist, seen=seen)


def _upsert_saved(
    db: Session,
    user_id: int,
    liked: list[Recommendation],
    wishlist: list[Recommendation],
    seen: list[int],
) -> None:
    """Insert any (movie_id, kind) rows not already saved for the user.

    Deduped in-process against the user's existing rows, so calling it twice with
    the same data is a no-op — the merge endpoint is safe to retry.
    """
    existing = db.execute(
        select(UserSavedTitle.movie_id, UserSavedTitle.kind).where(UserSavedTitle.user_id == user_id)
    ).all()
    have = {(movie_id, kind) for movie_id, kind in existing}

    for kind, recs in ((_LIKED, liked), (_WISHLIST, wishlist)):
        for rec in recs:
            if (rec.id, kind) not in have:
                db.add(UserSavedTitle(user_id=user_id, movie_id=rec.id, kind=kind, rec_json=rec.model_dump()))
                have.add((rec.id, kind))
    for movie_id in seen:
        if (movie_id, _SEEN) not in have:
            db.add(UserSavedTitle(user_id=user_id, movie_id=movie_id, kind=_SEEN, rec_json=None))
            have.add((movie_id, _SEEN))


@router.get("/history", response_model=HistoryResponse)
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> HistoryResponse:
    """Return the signed-in user's liked/wishlist recs and seen movie_ids."""
    return _load_history(db, user.id)


@router.post("/merge", response_model=HistoryResponse)
def merge(
    payload: MergeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HistoryResponse:
    """Merge a guest's local state into the account and return the merged result.

    Idempotent: re-running with the same payload adds nothing. The SPA replaces
    its local state with the returned authoritative state.
    """
    _upsert_saved(db, user.id, payload.liked, payload.wishlist, payload.seen)
    db.commit()
    return _load_history(db, user.id)


@router.post("/saved", status_code=204)
def save_title(
    payload: SaveTitleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Persist one liked/watch-listed card (and mark it seen) for the user.

    Called fire-and-forget by the SPA on a like/super-like (``liked``) or a save
    (``wishlist``) swipe, so the account's deck stays in sync without a full
    merge. Idempotent on ``(movie_id, kind)``.
    """
    liked = [payload.rec] if payload.kind == _LIKED else []
    wishlist = [payload.rec] if payload.kind == _WISHLIST else []
    _upsert_saved(db, user.id, liked=liked, wishlist=wishlist, seen=[payload.rec.id])
    db.commit()
    return Response(status_code=204)
