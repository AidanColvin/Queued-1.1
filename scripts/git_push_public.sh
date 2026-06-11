#!/usr/bin/env bash
set -Eeuo pipefail
cd "${HOME}/nextwatch"
git add .
git commit -m "Clean repo, add training route, frontend-backend debug flow" || true
git push || true
echo
echo "If no GitHub repo yet:"
echo "gh auth login"
echo "gh repo create nextwatch --public --source=. --remote=origin --push"
echo
echo "Repo URL pattern:"
echo "https://github.com/AidanColvin/nextwatch"
