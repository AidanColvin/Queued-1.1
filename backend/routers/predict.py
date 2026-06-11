from fastapi import APIRouter, HTTPException
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
