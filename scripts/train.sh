#!/usr/bin/env bash
# Full REAL pipeline: download -> preprocess -> train CF factors.
#
# Requires the training dependencies and a TMDB_API_KEY in backend/.env:
#   pip install -r backend/requirements-train.txt
#
# Usage:
#   scripts/train.sh            # full MovieLens 25M (production model)
#   scripts/train.sh 0.1        # 10% user sample (fast local dev)
set -euo pipefail

SAMPLE_FRAC="${1:-1.0}"
cd "$(dirname "$0")/../backend"

echo "==> [1/3] Downloading MovieLens 25M + IMDb basics"
python -m data.download

echo "==> [2/3] Preprocessing (sample_frac=${SAMPLE_FRAC}) + TMDB enrichment"
python -m data.preprocess --sample-frac "${SAMPLE_FRAC}"

echo "==> [3/3] Training SVD collaborative factors"
python -m ml.collaborative

echo "==> Done. Artifacts written to backend/data/artifacts. Start the API with:"
echo "    cd backend && uvicorn main:app --reload"
