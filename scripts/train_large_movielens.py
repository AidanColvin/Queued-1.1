from __future__ import annotations
import json
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
RAW_DIR = ROOT / "backend" / "data" / "raw" / "ml-25m"
TRAINING_DIR = ROOT / "training"
TRAINING_DIR.mkdir(parents=True, exist_ok=True)

BEST_FILE = TRAINING_DIR / "best_large_metrics.json"
MODEL_FILE = TRAINING_DIR / "best_large_svd_model.joblib"
SUMMARY_FILE = TRAINING_DIR / "large_training_summary.json"
HISTORY_FILE = TRAINING_DIR / "large_training_history.json"

def load_previous():
    if BEST_FILE.exists():
        return json.loads(BEST_FILE.read_text())
    return None

def save_json(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2))

def append_history(row):
    history = []
    if HISTORY_FILE.exists():
        history = json.loads(HISTORY_FILE.read_text())
    history.append(row)
    save_json(HISTORY_FILE, history)

def main():
    ratings_path = RAW_DIR / "ratings.csv"
    movies_path = RAW_DIR / "movies.csv"

    if not ratings_path.exists() or not movies_path.exists():
        raise FileNotFoundError(f"Need {ratings_path} and {movies_path}")

    console.rule("[bold cyan]Train on MovieLens 25M")
    started = time.time()

    console.print("[cyan]Loading ratings...[/cyan]")
    ratings = pd.read_csv(ratings_path)
    movies = pd.read_csv(movies_path)

    console.print(f"[green]Ratings:[/green] {len(ratings):,}")
    console.print(f"[green]Users:[/green] {ratings['userId'].nunique():,}")
    console.print(f"[green]Movies:[/green] {ratings['movieId'].nunique():,}")

    reader = Reader(rating_scale=(0.5, 5.0))
    data = Dataset.load_from_df(ratings[["userId", "movieId", "rating"]], reader)
    trainset, testset = train_test_split(data, test_size=0.1, random_state=42)

    grid = [
        {"n_factors": 80, "n_epochs": 20, "lr_all": 0.003, "reg_all": 0.04},
        {"n_factors": 120, "n_epochs": 25, "lr_all": 0.003, "reg_all": 0.05},
        {"n_factors": 160, "n_epochs": 30, "lr_all": 0.002, "reg_all": 0.06},
        {"n_factors": 200, "n_epochs": 35, "lr_all": 0.002, "reg_all": 0.08},
    ]

    best_model = None
    best_row = None

    for params in tqdm(grid, desc="hyperparameter search", unit="model"):
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

        row = {
            **params,
            "rmse": rmse,
            "mae": mae,
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset": "ml-25m",
        }
        append_history(row)

        if best_row is None or rmse < best_row["rmse"]:
            best_row = row
            best_model = algo

    previous = load_previous()
    improved = previous is None or best_row["rmse"] < previous["rmse"]

    if improved:
        console.print("[cyan]Refitting best model on full dataset...[/cyan]")
        full_trainset = data.build_full_trainset()
        best_model.fit(full_trainset)
        joblib.dump(best_model, MODEL_FILE)
        save_json(BEST_FILE, best_row)

    movies.to_csv(TRAINING_DIR / "movies_catalog_large.csv", index=False)

    summary = {
        "dataset": "ml-25m",
        "n_ratings": int(len(ratings)),
        "n_users": int(ratings["userId"].nunique()),
        "n_movies": int(ratings["movieId"].nunique()),
        "candidate_best": best_row,
        "previous_best": previous,
        "improved": improved,
        "model_file": str(MODEL_FILE.relative_to(ROOT)) if improved else None,
        "duration_seconds": round(time.time() - started, 2),
    }
    save_json(SUMMARY_FILE, summary)

    table = Table(title="Large Dataset Best Candidate")
    table.add_column("Metric")
    table.add_column("Value")
    for k, v in best_row.items():
        table.add_row(str(k), str(v))
    console.print(table)

    if improved:
        console.print(f"[bold green]Promoted new best model:[/bold green] {MODEL_FILE}")
    else:
        console.print("[bold yellow]No improvement over current best; existing best kept.[/bold yellow]")

if __name__ == "__main__":
    main()
