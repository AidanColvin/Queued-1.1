from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import os

# Initialize FastAPI app
app = FastAPI()

# Add CORS so your frontend can talk to the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://queued-2.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock SessionStore logic for Vercel Serverless
class SessionStore:
    def __init__(self):
        self.dim = 384
        weight_path = "backend/ml/artifacts/prod_weights.npy"
        if os.path.exists(weight_path):
            self._embeddings = np.load(weight_path)
        else:
            self._embeddings = np.random.rand(100, self.dim)

    def get_semantic_score(self, movie_id, user_preferences):
        if movie_id < len(self._embeddings):
            movie_tags = self._embeddings[movie_id, -5:] 
            return float(np.dot(movie_tags, user_preferences))
        return 0.0

# Global instance
store = SessionStore()

@app.get("/api/health/ml")
async def ml_health():
    return {
        "status": "ok", 
        "embedding_shape": list(store._embeddings.shape), 
        "injected_dimensions": 5
    }

@app.get("/api/predict")
async def predict(movie_id: int, user_prefs: str = "0,0,0,0,0"):
    # Convert comma-separated string to list of floats
    prefs = [float(x) for x in user_prefs.split(",")]
    return {"score": store.get_semantic_score(movie_id, prefs)}
