#!/usr/bin/env bash
# Vercel "ignored build step": decides whether a push is SAFE TO DEPLOY.
# Exit 1 = proceed with the build. Exit 0 = SKIP the deploy (the previous
# good deployment stays live). Every check below corresponds to a real
# production outage from 2026-06-10/11 — do not weaken them casually.

fail() { echo "DEPLOY GATE: $1 — skipping deploy, last good deployment stays live."; exit 0; }

# 1. The serverless entrypoint must mount the app under /api via create_app
#    (a bare `from backend.main import app` 404'd every route).
grep -q "create_app" api/index.py || fail "api/index.py no longer calls create_app"
grep -q "def create_app" backend/main.py || fail "backend/main.py lost create_app()"

# 2. The function's dependency set must include the ML runtime
#    (it was once reduced to fastapi+pytest and the function could not boot).
grep -qi "^numpy" requirements.txt || fail "requirements.txt lost numpy"
grep -qi "^fastapi" requirements.txt || fail "requirements.txt lost fastapi"
grep -qi "^SQLAlchemy" requirements.txt || fail "requirements.txt lost SQLAlchemy"

# 3. A root pyproject.toml without a [project] table crashes Vercel's uv path.
if [ -f pyproject.toml ] && ! grep -q "^\[project\]" pyproject.toml; then
  fail "root pyproject.toml without [project] table breaks the Python builder"
fi

# 4. The deployed model must be the enriched catalog — a regenerated,
#    poster-less catalog once shipped and emptied the deck for every user.
[ -f backend/data/artifacts/movie_index.json ] || fail "movie_index.json missing"
posters=$(grep -c '"poster_url": "http' backend/data/artifacts/movie_index.json)
[ "$posters" -ge 5000 ] || fail "catalog has only $posters posters (enrichment lost)"
[ -f backend/data/artifacts/embeddings.npy ] || fail "embeddings.npy missing"
[ -f backend/data/artifacts/tv_index.json ] || fail "tv_index.json missing (TV deck)"

# 5. The reranker must still export what the recommender imports.
grep -q "POP_BETA" backend/ml/reranker.py || fail "reranker lost POP_BETA (import crash)"

echo "DEPLOY GATE: all invariants hold — deploying."
exit 1
