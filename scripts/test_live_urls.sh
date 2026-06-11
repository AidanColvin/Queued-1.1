#!/usr/bin/env bash
set -Eeuo pipefail

FRONTEND_URL="${1:-https://queued-2.vercel.app}"
BACKEND_URL="${2:-}"

echo "== frontend =="
curl -I "$FRONTEND_URL" | head -n 20

echo
if [ -n "$BACKEND_URL" ]; then
  echo "== backend health =="
  curl -sS "$BACKEND_URL/health" | python3 -m json.tool

  echo
  echo "== backend recommendations =="
  curl -sS "$BACKEND_URL/api/recommendations/1?top_n=5" | python3 -m json.tool
else
  echo "No backend URL provided."
  echo "Usage:"
  echo "./scripts/test_live_urls.sh https://queued-2.vercel.app https://YOUR-BACKEND.onrender.com"
fi
