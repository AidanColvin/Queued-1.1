#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch
source .venv/bin/activate 2>/dev/null || true

echo
echo "=============================="
echo "1) TRAINING WITH PROGRESS"
echo "=============================="
python3 scripts/train_and_serve_movielens.py | tee logs/live_training_output.log

echo
echo "=============================="
echo "2) BACKEND TESTS WITH LIVE LOGS"
echo "=============================="
./scripts/run_big_tests.sh

echo
echo "=============================="
echo "3) API SMOKE TEST"
echo "=============================="
curl -sS http://127.0.0.1:8000/health | python3 -m json.tool || true
echo
curl -sS "http://127.0.0.1:8000/api/recommendations/1?top_n=5" | python3 -m json.tool || true

echo
echo "Saved logs:"
echo "  logs/live_training_output.log"
echo "  logs/live_test_output.log"
