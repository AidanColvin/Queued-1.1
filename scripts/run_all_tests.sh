#!/bin/bash
set -e
# Explicitly set PYTHONPATH to the current directory
export PYTHONPATH=$(pwd)

echo "--- Running Backend Tests ---"
# Remove the invalid --pythonpath flag, rely on PYTHONPATH
python3 -m pytest tests/ -v

echo "--- Running Frontend Tests ---"
cd frontend
npm test -- run --passWithNoTests
