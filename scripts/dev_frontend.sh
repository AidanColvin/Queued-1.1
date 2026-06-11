#!/usr/bin/env bash
set -Eeuo pipefail
cd ~/nextwatch/frontend
cp -n .env.local.example .env.local || true
if ! grep -q "NEXT_PUBLIC_API_BASE_URL" .env.local 2>/dev/null; then
  echo "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000" >> .env.local
fi
npm install
npm run dev
