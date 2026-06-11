from __future__ import annotations
import json
import time
from pathlib import Path
from tqdm import tqdm
from backend.app.ml.online_trainer import OnlineLogReg, generate_examples, append_run_log, summarize

REPORT_PATH = Path("training/latest_training_report.json")

def main():
    model = OnlineLogReg.load_or_create()
    examples = generate_examples(100)
    rows = []

    print("\nStarting training with retrospective feedback loop...\n")
    for ex in tqdm(examples, desc="Learning", unit="item", ncols=100):
        before_prob = model.predict_proba(ex.features)
        predicted = 1 if before_prob >= 0.5 else 0
        correct = predicted == ex.label

        update_info = model.update(ex.features, ex.label)

        row = {
            "title": ex.title,
            "features": ex.features,
            "label": ex.label,
            "predicted": predicted,
            "correct": correct,
            "before_probability": round(before_prob, 4),
            "after_error": round(update_info["error"], 4),
        }
        rows.append(row)
        append_run_log(row)
        time.sleep(0.04)

    model.save()
    summary = summarize(rows)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({
        "summary": summary,
        "weights": model.weights,
        "bias": model.bias,
        "examples": rows[:10]
    }, indent=2))

    print("\nTraining complete.\n")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved report: {REPORT_PATH}")
    print("Saved model: training/model_state.json")
    print("Saved log: logs/training_runs.jsonl\n")

if __name__ == "__main__":
    main()
