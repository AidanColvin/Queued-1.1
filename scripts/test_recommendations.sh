#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch
echo "== health =="
curl -sS http://127.0.0.1:8000/health | python3 -m json.tool
echo
echo "== recommendations =="
curl -sS "http://127.0.0.1:8000/api/recommendations/1?top_n=10" | python3 -m json.tool
