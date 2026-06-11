#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch

python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install pytest pytest-cov httpx rich

mkdir -p test-results logs

pytest \
  -vv \
  -s \
  --tb=short \
  --log-cli-level=INFO \
  --cov=backend \
  --cov-report=term-missing \
  --cov-report=html:test-results/htmlcov \
  --cov-report=xml:test-results/coverage.xml \
  --junitxml=test-results/junit.xml \
  tests 2>&1 | tee logs/live_test_output.log

echo
echo "Saved:"
echo "  logs/live_test_output.log"
echo "  test-results/junit.xml"
echo "  test-results/coverage.xml"
echo "  test-results/htmlcov/index.html"
