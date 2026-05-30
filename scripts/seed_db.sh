#!/usr/bin/env bash
# Generate the bundled SAMPLE artifacts and seed the SQLite catalog from them.
# This is the zero-dependency quickstart path (no download, no TMDB key).
#
# Usage: scripts/seed_db.sh
set -euo pipefail

cd "$(dirname "$0")/../backend"

echo "==> Building sample artifacts"
python -m data.sample

echo "==> Seeding SQLite catalog"
python - <<'PY'
from ml.artifacts import load_artifacts
from db.database import init_db, seed_movies
from config import get_settings

bundle = load_artifacts(get_settings().artifacts_dir)
init_db()
n = seed_movies(bundle.catalog)
print(f"Seeded {n} movies into the catalog.")
PY

echo "==> Done. Start the API with: cd backend && uvicorn main:app --reload"
