from pathlib import Path
import json
import pandas as pd
from surprise import Dataset, Reader, SVD
from surprise.model_selection import train_test_split
from surprise import accuracy

base = Path("data/raw/ml-latest-small")
ratings_path = base / "ratings.csv"
movies_path = base / "movies.csv"

ratings = pd.read_csv(ratings_path)
movies = pd.read_csv(movies_path)

reader = Reader(rating_scale=(0.5, 5.0))
data = Dataset.load_from_df(ratings[["userId", "movieId", "rating"]], reader)

trainset, testset = train_test_split(data, test_size=0.2, random_state=42)

algo = SVD(n_factors=64, n_epochs=20, lr_all=0.005, reg_all=0.02, random_state=42)
algo.fit(trainset)
predictions = algo.test(testset)

rmse = accuracy.rmse(predictions, verbose=False)
mae = accuracy.mae(predictions, verbose=False)

report = {
    "dataset": "MovieLens Latest Small",
    "n_ratings": int(len(ratings)),
    "n_movies": int(ratings["movieId"].nunique()),
    "n_users": int(ratings["userId"].nunique()),
    "rmse": rmse,
    "mae": mae
}

Path("training").mkdir(exist_ok=True, parents=True)
Path("training/movielens_eval.json").write_text(json.dumps(report, indent=2))

top_movies = (
    ratings.groupby("movieId")
    .agg(avg_rating=("rating", "mean"), rating_count=("rating", "count"))
    .reset_index()
    .query("rating_count >= 20")
    .sort_values(["avg_rating", "rating_count"], ascending=[False, False])
    .merge(movies, on="movieId", how="left")
    .head(100)
)

top_movies.to_csv("training/top_movies_baseline.csv", index=False)

print(json.dumps(report, indent=2))
print("Saved training/movielens_eval.json")
print("Saved training/top_movies_baseline.csv")
