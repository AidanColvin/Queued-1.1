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

@router.get("/crystal-ball")
async def get_crystal_ball():
    # Placeholder: In Phase 3, this will map to actual user session vectors.
    # Currently serves the schema directly to the UI widget to verify connectivity.
    return {
        "loves": [
            {"id": 693134, "title": "Dune: Part Two", "score": 0.92},
            {"id": 157336, "title": "Interstellar", "score": 0.88}
        ],
        "hates": [
            {"id": 805217, "title": "Madame Web", "score": -0.85},
            {"id": 335983, "title": "Venom", "score": -0.72}
        ]
    }
