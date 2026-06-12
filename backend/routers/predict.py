from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.deps import get_optional_user
from db.database import get_db
from dependencies import get_recommender
from pydantic import BaseModel
from typing import List
try: from ml.predictor import TrajectoryPredictor
except: from backend.ml.predictor import TrajectoryPredictor
router = APIRouter(prefix="/predict", tags=["prediction"])
p = TrajectoryPredictor()
class SwipeSimulation(BaseModel):
 action: str
 embedding: List[float]
class PredictionRequest(BaseModel):
 current_profile: List[float]
 simulated_steps: List[SwipeSimulation]
 candidate_embedding: List[float]
@router.post("/trajectory")
async def forecast_trajectory(payload: PredictionRequest):
 if len(payload.current_profile) != len(payload.candidate_embedding) or not payload.current_profile:
  raise HTTPException(status_code=400, detail="current_profile and candidate_embedding must be same-length non-empty vectors.")
 for step in payload.simulated_steps:
  if len(step.embedding) != len(payload.current_profile):
   raise HTTPException(status_code=400, detail="every simulated_steps.embedding must match current_profile length.")
 steps = [{"action": s.action, "embedding": s.embedding} for s in payload.simulated_steps]
 score = p.predict_future_affinity(payload.current_profile, steps, payload.candidate_embedding)
 return {"predicted_affinity": score, "will_like_in_future": score >= 0.5, "recommendation_status": "surface" if score >= 0.5 else "suppress"}

@router.get("/accuracy")
def get_prediction_accuracy(db: Session = Depends(get_db)):
    """Live scoreboard: how often the model's pre-swipe guesses were right.

    Every swipe logs the model's prediction for the card BEFORE the user acted
    (``SwipeEvent.predicted_score``); this compares those guesses to what users
    actually did. Likes/superlikes count as positive, dismisses as negative;
    saves and skips carry no like/dislike verdict and are excluded.

    Reports ROC-AUC (P(a liked card was scored above a dismissed one); 0.5 =
    guessing, 1.0 = perfect) plus the mean guess for each outcome — a healthy
    model keeps ``mean_score_liked`` above ``mean_score_dismissed``.
    """
    import numpy as np
    from sqlalchemy import select

    from db.database import SwipeEvent

    rows = db.execute(
        select(SwipeEvent.predicted_score, SwipeEvent.action).where(
            SwipeEvent.predicted_score.is_not(None),
            SwipeEvent.action.in_(("liked", "superliked", "dismissed")),
        )
    ).all()
    scores = np.array([r[0] for r in rows], dtype=np.float64)
    labels = np.array([0 if r[1] == "dismissed" else 1 for r in rows], dtype=np.int64)
    n_pos, n_neg = int(labels.sum()), int((labels == 0).sum())

    out = {
        "judged_predictions": len(rows),
        "likes": n_pos,
        "dislikes": n_neg,
        "auc": None,
        "mean_score_liked": round(float(scores[labels == 1].mean()), 4) if n_pos else None,
        "mean_score_dismissed": round(float(scores[labels == 0].mean()), 4) if n_neg else None,
    }
    if n_pos and n_neg:
        # Rank-sum AUC with average ranks for ties (numpy-only Mann-Whitney).
        order = np.argsort(scores, kind="mergesort")
        ranks = np.empty(len(scores), dtype=np.float64)
        sorted_scores = scores[order]
        i = 0
        while i < len(sorted_scores):
            j = i
            while j + 1 < len(sorted_scores) and sorted_scores[j + 1] == sorted_scores[i]:
                j += 1
            ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0  # average 1-based rank
            i = j + 1
        out["auc"] = round(float((ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)), 4)
    return out


@router.get("/crystal-ball")
def get_crystal_ball(
    session_id: str = "",
    recommender=Depends(get_recommender),
    db: Session = Depends(get_db),
    user=Depends(get_optional_user),
):
    """Predict the titles this viewer will most love and most hate.

    Loads the caller's REAL taste vector (signed-in profile or anonymous
    session — the same one /swipe trains and /recommend/adaptive ranks with)
    and scores the whole catalog in the production taste space. Before there
    is enough signal the forecast is not personalized: loves fall back to the
    popularity prior and hates stay empty.
    """
    import numpy as np
    from sqlalchemy import select

    from db.database import SwipeEvent
    from routers.adaptive import ADAPTIVE_MIN_CONFIDENCE, _load_taste

    vector, confidence = _load_taste(db, user, session_id)
    if vector and confidence >= ADAPTIVE_MIN_CONFIDENCE:
        # A forecast must not name titles the caller already swiped — liked
        # titles are by construction the nearest neighbours of their own vector.
        scope = SwipeEvent.user_id == user.id if user is not None else SwipeEvent.session_id == session_id
        swiped = set(db.scalars(select(SwipeEvent.tmdb_id).where(scope).distinct()).all())
        loves, hates = recommender.predict_extremes(
            np.asarray(vector, dtype=np.float32),
            exclude_tmdb_ids=swiped,
            confidence=confidence,
        )
        if loves:
            return {"loves": loves, "hates": hates, "personalized": True}
    # Cold start: crowd favorites, no hate predictions (no signal to oppose).
    top = recommender.popular({}, count=5).recommendations
    loves = [{"id": r.id, "title": r.title, "year": r.year, "score": r.score} for r in top]
    return {"loves": loves, "hates": [], "personalized": False}
