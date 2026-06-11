#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch
echo "== frontend env =="
grep -n "NEXT_PUBLIC_API_BASE_URL" frontend/.env.local || true
echo
echo "== backend health =="
curl -sS http://127.0.0.1:8000/health | python3 -m json.tool || true
echo
echo "== backend recs =="
curl -sS "http://127.0.0.1:8000/api/recommendations/1?top_n=5" | python3 -m json.tool || true
echo
echo "Frontend page:"
echo "http://127.0.0.1:3000/api-test"
