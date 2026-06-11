from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import numpy as np
from db.database import get_db, AnonSessionProfile, UserProfile
from dependencies import get_session_store
from ml.reranker import SessionStore
from schemas import MatchResponse

router = APIRouter(prefix="/social", tags=["social"])

def fetch_taste_vector(db: Session, identifier: str) -> np.ndarray:
    # 1. Try to fetch as an authenticated user
    if identifier.isdigit():
        profile = db.get(UserProfile, int(identifier))
        if profile and profile.taste_vector:
            return np.array(profile.taste_vector)
    
    # 2. Fall back to anonymous session profile
    anon_profile = db.get(AnonSessionProfile, identifier)
    if anon_profile and anon_profile.taste_vector:
        return np.array(anon_profile.taste_vector)
        
    raise HTTPException(status_code=404, detail=f"Taste profile not found for {identifier}")

@router.get("/match", response_model=dict)
def calculate_match_rate(
    user_a: str,
    user_b: str,
    db: Session = Depends(get_db),
    store: SessionStore = Depends(get_session_store)
):
    """
    Takes: Two user identifiers (session strings or integer IDs).
    Does: Fetches both taste vectors, normalizes them, and calculates cosine similarity.
    Returns: A dictionary with the raw cosine score and a scaled 0-100% Match Rate.
    """
    vec_a = fetch_taste_vector(db, user_a)
    vec_b = fetch_taste_vector(db, user_b)
    
    # Validate dimensions match current model
    if len(vec_a) != store.dim or len(vec_b) != store.dim:
        raise HTTPException(status_code=400, detail="Vector dimension mismatch. One profile needs retraining.")
        
    # Normalize vectors
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    
    if norm_a == 0 or norm_b == 0:
        return {"cosine_similarity": 0.0, "match_percentage": 0}
        
    unit_a = vec_a / norm_a
    unit_b = vec_b / norm_b
    
    # Calculate cosine similarity (-1.0 to 1.0)
    cosine = float(np.dot(unit_a, unit_b))
    
    # Scale to intuitive percentage: 
    # Cosine 1.0 = 100%, Cosine 0.0 = 50%, Cosine -1.0 = 0%
    match_pct = round(((cosine + 1) / 2) * 100)
    
    return {
        "user_a": user_a,
        "user_b": user_b,
        "cosine_similarity": round(cosine, 3),
        "match_percentage": match_pct
    }
