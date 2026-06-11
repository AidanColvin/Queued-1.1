"""``POST /swipe`` — record a swipe and re-rank the remaining deck (Layer 1).

The frontend fires this immediately after each swipe commits (fire-and-forget,
non-blocking). The call does two things:

1. Updates the session taste vector and re-orders the remaining deck.
2. Appends the swipe to ``swipe_events`` — the durable log that Layer 3's
   offline retraining consumes.

Anonymous callers are keyed by the client-supplied ``session_id`` and their
taste vector lives only in memory (Layer 1). A signed-in caller (Phase 3) is
keyed by their account instead: the reranker warm-starts from their persisted
``UserProfile.taste_vector`` and the updated vector is written back, so taste
carries across sessions and devices (Layer 2).
"""

from __future__ import annotations

import logging

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth.deps import get_optional_user
from db.database import AnonSessionProfile, SwipeEvent, User, UserProfile, get_db
from dependencies import get_provider_index, get_session_store
from ml.reranker import SessionReranker, SessionStore
from providers import ProviderIndex
from routers.providers import user_provider_ids
from schemas import SwipeRequest, SwipeResponse

logger = logging.getLogger("queued")

router = APIRouter(tags=["swipe"])


def _user_reranker(db: Session, store: SessionStore, user: User) -> tuple[SessionReranker, UserProfile]:
    """Build a reranker warm-started from the user's persisted taste vector.

    Returns the reranker plus the (possibly newly created) ``UserProfile`` row to
    write the updated vector back to. A stored vector whose length no longer
    matches the current embedding dim (model re-trained) is ignored — the user
    warm-starts cold rather than crashing.
    """
    profile = db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    vec = profile.taste_vector
    init_vector = np.asarray(vec, dtype=np.float32) if vec and len(vec) == store.dim else None
    return store.reranker_for_user(init_vector, profile.confidence or 0.0), profile


def _anon_reranker(db: Session, store: SessionStore, session_id: str) -> tuple[SessionReranker, AnonSessionProfile]:
    """Return the session's reranker plus its durable DB row.

    The in-memory store is the hot path; on a miss (new session, process
    restart, or a different instance) the reranker warm-starts from the
    persisted ``anon_session_profiles`` row, so live re-ranking survives
    restarts and multi-instance deployments. The row is created lazily and is
    written back by the caller after each applied swipe.
    """
    row = db.get(AnonSessionProfile, session_id)
    if row is None:
        row = AnonSessionProfile(session_id=session_id)
        db.add(row)

    reranker = store.peek(session_id)
    if reranker is None:
        vec = row.taste_vector
        init_vector = np.asarray(vec, dtype=np.float32) if vec and len(vec) == store.dim else None
        reranker = store.get_or_create(session_id, init_vector, row.confidence or 0.0)
    return reranker, row


@router.post("/swipe", response_model=SwipeResponse)
def record_swipe(
    payload: SwipeRequest,
    store: SessionStore = Depends(get_session_store),
    index: ProviderIndex = Depends(get_provider_index),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> SwipeResponse:
    """Record one swipe, persist it, and return the re-ranked remaining deck.

    Args:
        payload: The swipe (session, card, action, deliberation time, remaining deck).
        store: Injected per-session reranker store.
        db: Injected database session.
        user: The signed-in account, or ``None`` for an anonymous swipe.

    Returns:
        A :class:`~schemas.SwipeResponse` with the updated deck order and the
        session's current confidence.
    """
    # Build the right reranker: account-scoped + warm-started for a signed-in
    # user (Layer 2), else the session one — in-memory cache backed by a durable
    # ``anon_session_profiles`` row (Layer 1, restart-safe).
    profile: UserProfile | None = None
    anon_row: AnonSessionProfile | None = None
    if user is not None:
        reranker, profile = _user_reranker(db, store, user)
    else:
        try:
            reranker, anon_row = _anon_reranker(db, store, payload.session_id)
        except Exception:  # noqa: BLE001 — DB down: degrade to memory-only
            db.rollback()
            logger.exception("Failed to load anon session profile (memory-only fallback)")
            reranker = store.get_or_create(payload.session_id)

    applied = reranker.update(payload.tmdb_id, payload.action, payload.time_on_card_ms)

    # Persist the swipe log (+ the updated taste vector). A DB hiccup here must
    # not break the swipe: the reranked deck is computed from the in-memory
    # reranker and returned regardless, matching the client's fire-and-forget use.
    try:
        if applied:
            target = profile if profile is not None else anon_row
            if target is not None:
                target.taste_vector = reranker.session_vector.tolist()
                target.confidence = reranker.confidence
        db.add(
            SwipeEvent(
                session_id=payload.session_id,
                user_id=user.id if user is not None else None,
                tmdb_id=payload.tmdb_id,
                action=payload.action,
                time_on_card_ms=payload.time_on_card_ms,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 — never 500 a fire-and-forget swipe
        db.rollback()
        logger.exception("Failed to persist swipe/profile (returning rerank anyway)")

    # "Prefer my services": softly boost on-service cards in the re-rank. The
    # hard filter has no work to do here — an "only" deck was already filtered
    # when it was fetched.
    boost_ids: set[int] | None = None
    if payload.provider_filter == "prefer" and index.has_data:
        try:
            selected = set(user_provider_ids(db, user) or payload.providers)
        except Exception:  # noqa: BLE001 — never let prefs lookup break a swipe
            selected = set(payload.providers)
        if selected:
            boost_ids = {tid for tid in payload.remaining if index.available(tid) & selected}

    return SwipeResponse(
        reranked_queue=reranker.rerank(payload.remaining, boost_ids=boost_ids),
        session_confidence=round(reranker.confidence, 3),
        applied=applied,
    )
