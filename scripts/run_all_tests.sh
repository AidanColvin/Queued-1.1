#!/bin/bash
set -e
# Add the current directory (where 'backend' lives) to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(pwd)

echo "--- Running Backend Tests ---"
python3 -m pytest tests/ -v

echo "--- Running Frontend Tests ---"
cd frontend
npm test -- run --passWithNoTests
