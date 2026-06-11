from __future__ import annotations
from functools import lru_cache
import joblib
import pandas as pd
from pathlib import Path

MODEL_PATH = Path("training/svd_model.joblib")
MOVIES_PATH = Path("training/movies_catalog.csv")
RATINGS_PATH = Path("training/ratings_catalog.csv")

@lru_cache()
def load_model():
    return joblib.load(MODEL_PATH)

@lru_cache()
def load_movies():
    return pd.read_csv(MOVIES_PATH)

@lru_cache()
def load_ratings():
    return pd.read_csv(RATINGS_PATH)

def recommend_for_user(user_id: int, top_n: int = 10):
    model = load_model()
    movies = load_movies()
    ratings = load_ratings()

    seen = set(ratings.loc[ratings["userId"] == user_id, "movieId"].tolist())
    candidates = movies[~movies["movieId"].isin(seen)].copy()

    if candidates.empty:
        return []

    candidates["predicted_rating"] = candidates["movieId"].apply(
        lambda movie_id: model.predict(uid=user_id, iid=movie_id).est
    )

    recs = (
        candidates.sort_values("predicted_rating", ascending=False)
        .head(top_n)[["movieId", "title", "genres", "predicted_rating"]]
        .copy()
    )

    recs["predicted_rating"] = recs["predicted_rating"].round(3)
    return recs.to_dict(orient="records")
