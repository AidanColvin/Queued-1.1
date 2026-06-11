#!/usr/bin/env bash
set -Eeuo pipefail
curl -sS -X POST http://127.0.0.1:8000/ops/run-now | python3 -m json.tool
