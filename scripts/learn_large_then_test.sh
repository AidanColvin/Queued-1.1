#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch
source .venv/bin/activate

mkdir -p logs test-results

echo
echo "=================================="
echo "1) TRAIN LARGE DATASET"
echo "=================================="
python3 scripts/train_large_movielens.py | tee logs/train_large_movielens.log

echo
echo "=================================="
echo "2) RUN TESTS"
echo "=================================="
pytest \
  -vv -s --tb=short --log-cli-level=INFO \
  --cov=backend \
  --cov-report=term-missing \
  --cov-report=html:test-results/htmlcov \
  --cov-report=xml:test-results/coverage.xml \
  --junitxml=test-results/junit.xml \
  tests 2>&1 | tee logs/test_after_large_train.log

echo
echo "Saved:"
echo "  logs/train_large_movielens.log"
echo "  logs/test_after_large_train.log"
echo "  training/large_training_summary.json"
echo "  training/large_training_history.json"
