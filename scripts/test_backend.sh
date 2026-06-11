#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch
source .venv/bin/activate 2>/dev/null || true
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -r requirements.txt
pytest -q || true
