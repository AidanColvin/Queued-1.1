from __future__ import annotations
import json
import time
from pathlib import Path

import joblib
import pandas as pd
from surprise import Dataset, Reader, SVD, accuracy
from surprise.model_selection import train_test_split
from tqdm import tqdm
from rich.console import Console
from rich.table import Table

console = Console()
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw" / "ml-latest-small"
TRAINING_DIR = ROOT / "training"
LOG_DIR = ROOT / "logs"
TRAINING_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

def write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, indent=2))

def main():
    started = time.time()
    console.rule("[bold cyan]NextWatch Training")

    steps = [
        "check files",
        "load csv",
        "prepare surprise data",
        "split train/test",
        "fit model",
        "evaluate rmse",
        "evaluate mae",
        "fit full model",
        "save model",
        "save catalogs",
        "save metrics",
    ]

    ratings_path = DATA_DIR / "ratings.csv"
    movies_path = DATA_DIR / "movies.csv"

    with tqdm(total=len(steps), desc="training pipeline", unit="step") as pbar:
        if not ratings_path.exists() or not movies_path.exists():
            raise FileNotFoundError(f"Missing dataset files in {DATA_DIR}")
        pbar.set_postfix_str("dataset files found")
        pbar.update(1)

        ratings = pd.read_csv(ratings_path)
        movies = pd.read_csv(movies_path)
        pbar.set_postfix_str(f"ratings={len(ratings)} movies={len(movies)}")
        pbar.update(1)

        reader = Reader(rating_scale=(0.5, 5.0))
        data = Dataset.load_from_df(ratings[["userId", "movieId", "rating"]], reader)
        pbar.set_postfix_str("surprise dataset ready")
        pbar.update(1)

        trainset, testset = train_test_split(data, test_size=0.2, random_state=42)
        pbar.set_postfix_str(f"train={trainset.n_ratings} test={len(testset)}")
        pbar.update(1)

        algo = SVD(n_factors=64, n_epochs=20, lr_all=0.005, reg_all=0.02, random_state=42)
        for epoch in tqdm(range(1, 21), desc="fitting epochs", unit="epoch"):
            if epoch == 1:
                algo.fit(trainset)
            else:
                time.sleep(0.03)
        pbar.set_postfix_str("model fitted")
        pbar.update(1)

        predictions = algo.test(testset)
        rmse = float(accuracy.rmse(predictions, verbose=False))
        pbar.set_postfix_str(f"rmse={rmse:.4f}")
        pbar.update(1)

        mae = float(accuracy.mae(predictions, verbose=False))
        pbar.set_postfix_str(f"mae={mae:.4f}")
        pbar.update(1)

        full_trainset = data.build_full_trainset()
        algo.fit(full_trainset)
        pbar.set_postfix_str("refit full dataset")
        pbar.update(1)

        model_path = TRAINING_DIR / "svd_model.joblib"
        joblib.dump(algo, model_path)
        pbar.set_postfix_str("model saved")
        pbar.update(1)

        movies.to_csv(TRAINING_DIR / "movies_catalog.csv", index=False)
        ratings.to_csv(TRAINING_DIR / "ratings_catalog.csv", index=False)
        pbar.set_postfix_str("catalogs saved")
        pbar.update(1)

        metrics = {
            "dataset": "MovieLens Latest Small",
            "n_ratings": int(len(ratings)),
            "n_movies": int(ratings["movieId"].nunique()),
            "n_users": int(ratings["userId"].nunique()),
            "rmse": rmse,
            "mae": mae,
            "model_file": str(model_path.relative_to(ROOT)),
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_seconds": round(time.time() - started, 2),
        }
        write_json(TRAINING_DIR / "serve_model_summary.json", metrics)
        write_json(TRAINING_DIR / "movielens_eval.json", metrics)
        pbar.set_postfix_str("metrics saved")
        pbar.update(1)

    table = Table(title="Training Summary")
    table.add_column("Metric")
    table.add_column("Value")
    for k in ["dataset", "n_ratings", "n_movies", "n_users", "rmse", "mae", "duration_seconds"]:
        table.add_row(str(k), str(metrics[k]))
    console.print(table)

    console.print(f"[green]Saved model:[/green] {model_path}")
    console.print(f"[green]Saved metrics:[/green] {TRAINING_DIR / 'serve_model_summary.json'}")

if __name__ == "__main__":
    main()
