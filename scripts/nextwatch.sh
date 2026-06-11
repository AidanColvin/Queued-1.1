#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch

CMD="${1:-help}"

case "$CMD" in
  train)
    ./scripts/train.sh
    ;;
  backend)
    ./scripts/dev_backend.sh
    ;;
  frontend)
    ./scripts/dev_frontend.sh
    ;;
  test)
    ./scripts/test_backend.sh
    ;;
  recs)
    ./scripts/test_recommendations.sh
    ;;
  debug)
    ./scripts/debug_connection.sh
    ;;
  browser)
    ./scripts/open_browser.sh
    ;;
  all)
    ./scripts/run_all_local.sh
    ;;
  help|*)
    echo "Use one of:"
    echo "  ./scripts/nextwatch.sh train"
    echo "  ./scripts/nextwatch.sh backend"
    echo "  ./scripts/nextwatch.sh frontend"
    echo "  ./scripts/nextwatch.sh test"
    echo "  ./scripts/nextwatch.sh recs"
    echo "  ./scripts/nextwatch.sh debug"
    echo "  ./scripts/nextwatch.sh browser"
    echo "  ./scripts/nextwatch.sh all"
    ;;
esac
