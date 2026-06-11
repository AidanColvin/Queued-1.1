#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch
source .venv/bin/activate

mkdir -p logs test-results

echo
echo "=============================="
echo "1) AUTO LEARN / TUNE"
echo "=============================="
python3 scripts/auto_learn_and_test.py | tee logs/auto_learn.log

echo
echo "=============================="
echo "2) BACKEND TESTS"
echo "=============================="
pytest \
  -vv -s --tb=short --log-cli-level=INFO \
  --cov=backend \
  --cov-report=term-missing \
  --cov-report=html:test-results/htmlcov \
  --cov-report=xml:test-results/coverage.xml \
  --junitxml=test-results/junit.xml \
  tests 2>&1 | tee logs/auto_test.log

echo
echo "=============================="
echo "3) TRAINING SUMMARY"
echo "=============================="
python3 - <<'PY'
import json
from pathlib import Path
p = Path("training/auto_learn_summary.json")
if p.exists():
    print(json.dumps(json.loads(p.read_text()), indent=2))
else:
    print("No summary file found.")
PY

echo
echo "Saved:"
echo "  logs/auto_learn.log"
echo "  logs/auto_test.log"
echo "  training/auto_learn_summary.json"
echo "  training/training_history.json"
