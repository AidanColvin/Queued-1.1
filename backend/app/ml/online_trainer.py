from __future__ import annotations
import json
import math
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any

MODEL_PATH = Path("training/model_state.json")
RUN_LOG_PATH = Path("logs/training_runs.jsonl")

@dataclass
class Example:
    features: List[float]
    label: int
    title: str

class OnlineLogReg:
    def __init__(self, n_features: int = 4, lr: float = 0.15):
        self.n_features = n_features
        self.lr = lr
        self.weights = [0.0] * n_features
        self.bias = 0.0

    def sigmoid(self, z: float) -> float:
        z = max(min(z, 20), -20)
        return 1.0 / (1.0 + math.exp(-z))

    def predict_proba(self, x: List[float]) -> float:
        z = sum(w * xi for w, xi in zip(self.weights, x)) + self.bias
        return self.sigmoid(z)

    def predict(self, x: List[float], threshold: float = 0.5) -> int:
        return 1 if self.predict_proba(x) >= threshold else 0

    def update(self, x: List[float], y: int) -> Dict[str, Any]:
        p = self.predict_proba(x)
        error = y - p
        for i in range(self.n_features):
            self.weights[i] += self.lr * error * x[i]
        self.bias += self.lr * error
        return {"probability": p, "predicted": 1 if p >= 0.5 else 0, "error": error}

    def save(self) -> None:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        MODEL_PATH.write_text(json.dumps({
            "n_features": self.n_features,
            "lr": self.lr,
            "weights": self.weights,
            "bias": self.bias
        }, indent=2))

    @classmethod
    def load_or_create(cls) -> "OnlineLogReg":
        if MODEL_PATH.exists():
            data = json.loads(MODEL_PATH.read_text())
            obj = cls(n_features=data["n_features"], lr=data["lr"])
            obj.weights = data["weights"]
            obj.bias = data["bias"]
            return obj
        return cls()

def generate_examples(n: int = 80) -> List[Example]:
    random.seed(42)
    examples: List[Example] = []
    for i in range(n):
        popularity = random.uniform(0, 1)
        similarity = random.uniform(0, 1)
        freshness = random.uniform(0, 1)
        rewatchability = random.uniform(0, 1)
        score = 0.35 * similarity + 0.3 * rewatchability + 0.2 * popularity + 0.15 * freshness
        label = 1 if score >= 0.58 else 0
        examples.append(
            Example(
                features=[popularity, similarity, freshness, rewatchability],
                label=label,
                title=f"title_{i+1}"
            )
        )
    return examples

def append_run_log(row: Dict[str, Any]) -> None:
    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG_PATH.open("a") as f:
        f.write(json.dumps(row) + "\n")

def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    incorrect = total - correct
    accuracy = correct / total if total else 0.0
    false_positive = sum(1 for r in rows if r["predicted"] == 1 and r["label"] == 0)
    false_negative = sum(1 for r in rows if r["predicted"] == 0 and r["label"] == 1)
    return {
        "total": total,
        "correct": correct,
        "incorrect": incorrect,
        "accuracy": round(accuracy, 4),
        "false_positive": false_positive,
        "false_negative": false_negative,
    }
