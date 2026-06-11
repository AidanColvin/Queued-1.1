from __future__ import annotations
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from backend.app.ml.recommender import recommend_for_user, load_model
from backend.app.auto_ops import auto_train_and_test, read_status

scheduler = BackgroundScheduler()

def allowed_origins():
    raw = os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000,https://queued-2.vercel.app")
    return [x.strip() for x in raw.split(",") if x.strip()]

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    scheduler.add_job(auto_train_and_test, IntervalTrigger(hours=6), id="auto-train-test", replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="NextWatch API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": True}

@app.get("/api/recommendations/{user_id}")
def get_recommendations(user_id: int, top_n: int = 10):
    try:
        recs = recommend_for_user(user_id=user_id, top_n=top_n)
        return {"user_id": user_id, "count": len(recs), "recommendations": recs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ops/status")
def ops_status():
    return read_status()

@app.post("/ops/run-now")
def ops_run_now():
    try:
        result = auto_train_and_test()
        return {"ok": True, "status": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
