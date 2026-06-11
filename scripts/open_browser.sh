#!/usr/bin/env bash
set -Eeuo pipefail
open "${1:-http://127.0.0.1:3000/api-test}"
