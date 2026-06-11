from __future__ import annotations
import json, time
from pathlib import Path
import joblib
import pandas as pd
from rich.console import Console
from surprise import Dataset, Reader, SVD, accuracy
from surprise.model_selection import train_test_split
from tqdm import tqdm

console = Console()
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "backend" / "data" / "raw" / "adult"
OUT_DIR = ROOT / "training" / "adult"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ratings_path = RAW_DIR / "ratings.csv"
movies_path = RAW_DIR / "movies.csv"
if not ratings_path.exists() or not movies_path.exists():
    raise FileNotFoundError(f"Need {ratings_path} and {movies_path}")

started = time.time()
console.rule("[bold cyan]Train Adult Dataset")

ratings = pd.read_csv(ratings_path)
movies = pd.read_csv(movies_path)

reader = Reader(rating_scale=(0.5, 5.0))
data = Dataset.load_from_df(ratings[["userId","movieId","rating"]], reader)
trainset, testset = train_test_split(data, test_size=0.1, random_state=42)

grid = [
    {"n_factors": 80, "n_epochs": 20, "lr_all": 0.003, "reg_all": 0.04},
    {"n_factors": 120, "n_epochs": 25, "lr_all": 0.003, "reg_all": 0.05},
    {"n_factors": 160, "n_epochs": 30, "lr_all": 0.002, "reg_all": 0.08},
]

best = None
best_algo = None
history = []

for p in tqdm(grid, desc="adult tuning", unit="model"):
    algo = SVD(**p, random_state=42)
    algo.fit(trainset)
    preds = algo.test(testset)
    rmse = float(accuracy.rmse(preds, verbose=False))
    mae = float(accuracy.mae(preds, verbose=False))
    row = {**p, "rmse": rmse, "mae": mae, "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    history.append(row)
    if best is None or rmse < best["rmse"]:
        best = row
        best_algo = algo

full_train = data.build_full_trainset()
best_algo.fit(full_train)
joblib.dump(best_algo, OUT_DIR / "best_adult_svd.joblib")

(OUT_DIR / "adult_best_metrics.json").write_text(json.dumps(best, indent=2))
(OUT_DIR / "adult_history.json").write_text(json.dumps(history, indent=2))
(OUT_DIR / "adult_summary.json").write_text(json.dumps({
    "dataset": "adult",
    "n_ratings": int(len(ratings)),
    "n_users": int(ratings["userId"].nunique()),
    "n_movies": int(ratings["movieId"].nunique()),
    "best": best,
    "duration_seconds": round(time.time() - started, 2),
}, indent=2))

movies.to_csv(OUT_DIR / "movies_catalog.csv", index=False)
ratings.to_csv(OUT_DIR / "ratings_catalog.csv", index=False)

console.print(f"[green]Saved model to[/green] {OUT_DIR / 'best_adult_svd.joblib'}")
