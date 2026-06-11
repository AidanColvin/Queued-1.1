from __future__ import annotations
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAINING_DIR = ROOT / "training"
LOG_DIR = ROOT / "logs"
STATUS_FILE = TRAINING_DIR / "auto_status.json"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def write_status(payload: dict):
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(payload, indent=2))

def read_status() -> dict:
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text())
    return {
        "last_train_started_at": None,
        "last_train_finished_at": None,
        "last_train_ok": None,
        "last_test_started_at": None,
        "last_test_finished_at": None,
        "last_test_ok": None,
        "last_error": None,
    }

def run_cmd(cmd: list[str], log_name: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / log_name
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n\n===== {now_iso()} =====\n")
        f.write("$ " + " ".join(cmd) + "\n")
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True,
        )
    return proc.returncode, str(log_path)

def auto_train_and_test():
    status = read_status()
    status["last_train_started_at"] = now_iso()
    status["last_error"] = None
    write_status(status)

    code, train_log = run_cmd(
        ["bash", "-lc", "source .venv/bin/activate && python3 scripts/train_and_serve_movielens.py"],
        "auto_train.log",
    )
    status["last_train_finished_at"] = now_iso()
    status["last_train_ok"] = (code == 0)
    status["train_log"] = train_log
    write_status(status)

    if code != 0:
        status["last_error"] = "auto training failed"
        write_status(status)
        return status

    status["last_test_started_at"] = now_iso()
    write_status(status)

    code, test_log = run_cmd(
        ["bash", "-lc", "source .venv/bin/activate && pytest -q tests || true"],
        "auto_test.log",
    )
    status["last_test_finished_at"] = now_iso()
    status["last_test_ok"] = (code == 0)
    status["test_log"] = test_log

    if code != 0:
        status["last_error"] = "auto tests failed"

    write_status(status)
    return status
