#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch

echo "Opening backend in new Terminal..."
osascript <<'APPLESCRIPT'
tell application "Terminal"
  do script "cd ~/nextwatch && ./scripts/dev_backend.sh"
end tell
APPLESCRIPT

sleep 4

echo "Opening frontend in new Terminal..."
osascript <<'APPLESCRIPT'
tell application "Terminal"
  do script "cd ~/nextwatch && ./scripts/dev_frontend.sh"
end tell
APPLESCRIPT

sleep 8

echo "Testing local API..."
./scripts/test_recommendations.sh || true

echo "Opening browser..."
./scripts/open_browser.sh "http://127.0.0.1:3000/api-test"
