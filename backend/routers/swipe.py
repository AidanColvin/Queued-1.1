"""``POST /swipe`` — record a swipe and re-rank the remaining deck (Layer 1).

The frontend fires this immediately after each swipe commits (fire-and-forget,
non-blocking). The call does two things:

1. Updates the in-memory session vector and re-orders the remaining deck.
2. Appends the swipe to ``swipe_events`` — the durable log that Layer 3's
   offline retraining consumes.

It is fully anonymous: the only identity is the client-supplied ``session_id``.
Cross-session personalization (Layer 2) and accounts arrive in Phase 3.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import SwipeEvent, get_db
from dependencies import get_session_store
from ml.reranker import SessionStore
from schemas import SwipeRequest, SwipeResponse

router = APIRouter(tags=["swipe"])


@router.post("/swipe", response_model=SwipeResponse)
def record_swipe(
    payload: SwipeRequest,
    store: SessionStore = Depends(get_session_store),
    db: Session = Depends(get_db),
) -> SwipeResponse:
    """Record one swipe, persist it, and return the re-ranked remaining deck.

    Args:
        payload: The swipe (session, card, action, deliberation time, remaining deck).
        store: Injected per-session reranker store.
        db: Injected database session.

    Returns:
        A :class:`~schemas.SwipeResponse` with the updated deck order and the
        session's current confidence.
    """
    reranker = store.get_or_create(payload.session_id)
    applied = reranker.update(payload.tmdb_id, payload.action, payload.time_on_card_ms)

    db.add(
        SwipeEvent(
            session_id=payload.session_id,
            tmdb_id=payload.tmdb_id,
            action=payload.action,
            time_on_card_ms=payload.time_on_card_ms,
        )
    )
    db.commit()

    return SwipeResponse(
        reranked_queue=reranker.rerank(payload.remaining),
        session_confidence=round(reranker.confidence, 3),
        applied=applied,
    )
