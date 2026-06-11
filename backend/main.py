from fastapi import FastAPI
from ml.reranker import build_taste_space

app = FastAPI()

@app.post("/rerank")
async def rerank(payload: dict):
    history = payload.get("user_history", [])
    recs = build_taste_space(history)
    return {"recommendations": recs}
