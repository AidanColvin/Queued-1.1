#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch
echo "== ops status =="
curl -sS http://127.0.0.1:8000/ops/status | python3 -m json.tool || true
echo
echo "== recent train log =="
tail -n 60 logs/auto_train.log 2>/dev/null || true
echo
echo "== recent test log =="
tail -n 60 logs/auto_test.log 2>/dev/null || true
