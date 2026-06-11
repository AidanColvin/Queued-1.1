#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch
source .venv/bin/activate

echo "Run this in terminal 1:"
echo "  cd ~/nextwatch && ./scripts/learn_large_then_test.sh"
echo
echo "Run this in terminal 2:"
echo "  cd ~/nextwatch && python3 scripts/train_adult_dataset.py"
