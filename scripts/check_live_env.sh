#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch/frontend

echo "== local env file =="
if [ -f .env.local ]; then
  grep -n "NEXT_PUBLIC_API_BASE_URL" .env.local || true
else
  echo ".env.local not found"
fi

echo
echo "== reminder =="
echo "In Vercel dashboard, set:"
echo "NEXT_PUBLIC_API_BASE_URL=https://YOUR-BACKEND.onrender.com"
echo
echo "Frontend production URL should be:"
echo "https://queued-2.vercel.app"
