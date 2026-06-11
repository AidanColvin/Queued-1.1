#!/bin/bash
set -e
# Force the project root into the PYTHONPATH
export PYTHONPATH=$(pwd)

echo "--- Running Backend Tests ---"
# -c pytest.ini is implied, --pythonpath . is handled by ini
python3 -m pytest tests/ -v

echo "--- Running Frontend Tests ---"
cd frontend
npm test -- run --passWithNoTests
