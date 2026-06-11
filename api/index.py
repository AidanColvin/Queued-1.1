"""Vercel serverless entry point for the Queued backend.

Serves the FastAPI app under ``/api`` on the same Vercel project as the static
frontend, so the deployed site is fully self-contained (same origin, no CORS,
no separate backend host). Model + DB load lazily on the first request (Vercel
does not run FastAPI lifespan events); the SQLite catalog lives in ``/tmp`` (the
only writable path on the serverless filesystem).
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_ROOT, "backend")
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MODEL_ARTIFACTS_PATH", os.path.join(_BACKEND, "data", "artifacts"))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/queued.db")
os.environ.setdefault("AUTO_SAMPLE", "false")
# Same-origin in production (the SPA and this function share the Vercel host),
# so CORS stays locked to the deployed frontend + local dev — never "*".
# Capacitor native shells serve the bundled SPA from capacitor://localhost.
os.environ.setdefault(
    "CORS_ORIGINS",
    "https://queued.vercel.app,http://localhost:3000,capacitor://localhost,ionic://localhost",
)
# Vercel is always HTTPS, so default the auth cookie to Secure. Accounts/history
# need a persistent DATABASE_URL (Postgres) plus the JWT/Google/FRONTEND_URL env
# vars set in the Vercel project — without a real DATABASE_URL the /tmp SQLite is
# wiped between invocations, so accounts won't persist.
os.environ.setdefault("COOKIE_SECURE", "true")

from main import create_app  # noqa: E402  (must follow the sys.path / env setup)

# Served behind the static frontend at /api/*.
app = create_app(api_prefix="/api")
