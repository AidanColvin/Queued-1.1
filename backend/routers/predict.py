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
 if len(payload.current_profile) != 384 or len(payload.candidate_embedding) != 384: raise HTTPException(status_code=400, detail="Must be 384.")
 steps = [{"action": s.action, "embedding": s.embedding} for s in payload.simulated_steps]
 score = p.predict_future_affinity(payload.current_profile, steps, payload.candidate_embedding)
 return {"predicted_affinity": score, "will_like_in_future": score >= 0.5, "recommendation_status": "surface" if score >= 0.5 else "suppress"}

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

    from routers.adaptive import ADAPTIVE_MIN_CONFIDENCE, _load_taste

    vector, confidence = _load_taste(db, user, session_id)
    if vector and confidence >= ADAPTIVE_MIN_CONFIDENCE:
        loves, hates = recommender.predict_extremes(np.asarray(vector, dtype=np.float32))
        if loves:
            return {"loves": loves, "hates": hates, "personalized": True}
    # Cold start: crowd favorites, no hate predictions (no signal to oppose).
    top = recommender.popular({}, count=5).recommendations
    loves = [{"id": r.id, "title": r.title, "year": r.year, "score": r.score} for r in top]
    return {"loves": loves, "hates": [], "personalized": False}
