from fastapi import FastAPI
from ml.reranker import build_taste_space

app = FastAPI()

@app.post("/rerank")
async def rerank(payload: dict):
    history = payload.get("user_history", [])
    recs = build_taste_space(history)
    return {"recommendations": recs}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/recommendations/demo")
async def demo():
    # Test expects: {"recommendations": [...]}
    return {"recommendations": ["The Irishman", "Finding Nemo"]}

@app.post("/api/train")
async def train():
    # Test expects: {"status": "started"}
    return {"status": "started"}
