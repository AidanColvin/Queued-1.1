from __future__ import annotations
import os

def get_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [x.strip() for x in raw.split(",") if x.strip()]
