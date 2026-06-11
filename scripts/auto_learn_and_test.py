from __future__ import annotations
import json
import math
import time
from pathlib import Path

import joblib
import pandas as pd
from rich.console import Console
from rich.table import Table
from surprise import Dataset, Reader, SVD, accuracy
from surprise.model_selection import train_test_split
from tqdm import tqdm

console = Console()
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw" / "ml-latest-small"
TRAINING_DIR = ROOT / "training"
LOGS_DIR = ROOT / "logs"
TRAINING_DIR.mkdir(exist_ok=True, parents=True)
LOGS_DIR.mkdir(exist_ok=True, parents=True)

BEST_METRICS_FILE = TRAINING_DIR / "best_metrics.json"
HISTORY_FILE = TRAINING_DIR / "training_history.json"
BEST_MODEL_FILE = TRAINING_DIR / "best_svd_model.joblib"

def load_previous_best():
    if BEST_METRICS_FILE.exists():
        return json.loads(BEST_METRICS_FILE.read_text())
    return None

def append_history(row: dict):
    history = []
    if HISTORY_FILE.exists():
        history = json.loads(HISTORY_FILE.read_text())
    history.append(row)
    HISTORY_FILE.write_text(json.dumps(history, indent=2))

def build_dataset():
    ratings = pd.read_csv(DATA_DIR / "ratings.csv")
    movies = pd.read_csv(DATA_DIR / "movies.csv")
    reader = Reader(rating_scale=(0.5, 5.0))
    data = Dataset.load_from_df(ratings[["userId", "movieId", "rating"]], reader)
    return ratings, movies, data

def evaluate_combo(trainset, testset, params):
    algo = SVD(
        n_factors=params["n_factors"],
        n_epochs=params["n_epochs"],
        lr_all=params["lr_all"],
        reg_all=params["reg_all"],
        random_state=42,
    )
    algo.fit(trainset)
    preds = algo.test(testset)
    rmse = float(accuracy.rmse(preds, verbose=False))
    mae = float(accuracy.mae(preds, verbose=False))
    return algo, rmse, mae

def main():
    started = time.time()
    console.rule("[bold cyan]NextWatch Auto Learn + Test")

    ratings, movies, data = build_dataset()
    trainset, testset = train_test_split(data, test_size=0.2, random_state=42)

    grid = [
        {"n_factors": 50, "n_epochs": 15, "lr_all": 0.002, "reg_all": 0.02},
        {"n_factors": 64, "n_epochs": 20, "lr_all": 0.005, "reg_all": 0.02},
        {"n_factors": 100, "n_epochs": 20, "lr_all": 0.005, "reg_all": 0.05},
        {"n_factors": 120, "n_epochs": 30, "lr_all": 0.003, "reg_all": 0.08},
        {"n_factors": 150, "n_epochs": 35, "lr_all": 0.002, "reg_all": 0.10},
    ]

    best_algo = None
    best_row = None

    for params in tqdm(grid, desc="tuning models", unit="model"):
        algo, rmse, mae = evaluate_combo(trainset, testset, params)
        row = {
            **params,
            "rmse": rmse,
            "mae": mae,
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        append_history(row)
        if best_row is None or rmse < best_row["rmse"]:
            best_row = row
            best_algo = algo

    previous = load_previous_best()
    improved = previous is None or best_row["rmse"] < previous["rmse"]

    summary = {
        "dataset": "MovieLens Latest Small",
        "n_ratings": int(len(ratings)),
        "n_movies": int(ratings["movieId"].nunique()),
        "n_users": int(ratings["userId"].nunique()),
        "candidate_best": best_row,
        "previous_best": previous,
        "improved": improved,
        "duration_seconds": round(time.time() - started, 2),
    }

    movies.to_csv(TRAINING_DIR / "movies_catalog.csv", index=False)
    ratings.to_csv(TRAINING_DIR / "ratings_catalog.csv", index=False)

    if improved:
        full_trainset = data.build_full_trainset()
        best_algo.fit(full_trainset)
        joblib.dump(best_algo, BEST_MODEL_FILE)
        BEST_METRICS_FILE.write_text(json.dumps(best_row, indent=2))
        summary["promoted_model"] = str(BEST_MODEL_FILE.relative_to(ROOT))
    else:
        summary["promoted_model"] = None

    (TRAINING_DIR / "auto_learn_summary.json").write_text(json.dumps(summary, indent=2))

    table = Table(title="Best Candidate")
    table.add_column("Field")
    table.add_column("Value")
    for k, v in best_row.items():
        table.add_row(str(k), str(v))
    console.print(table)

    if improved:
        console.print(f"[green]Improved RMSE. Promoted new model to[/green] {BEST_MODEL_FILE}")
    else:
        console.print("[yellow]No RMSE improvement. Kept previous best model.[/yellow]")

if __name__ == "__main__":
    main()
