#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -r requirements.txt
export ALLOWED_ORIGINS="http://127.0.0.1:3000,http://localhost:3000,https://queued-2.vercel.app"
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
