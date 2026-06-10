"""Per-IP rate limiting for the auth endpoints.

A small in-process sliding-window limiter — no Redis dependency. Each process
enforces its own window, which is the right trade-off here: the goal is to
blunt credential stuffing and reset-email spam, not to provide a globally
exact quota. Disabled via ``RATE_LIMIT_ENABLED=false`` (tests).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from config import get_settings

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
# Bound total tracked keys so a spoofed-IP flood can't grow memory unbounded.
_MAX_KEYS = 50_000


def _client_ip(request: Request) -> str:
    """Best-effort client IP: first hop of X-Forwarded-For (Render/Vercel sit
    behind a proxy), else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def reset() -> None:
    """Clear all counters (test helper)."""
    with _lock:
        _hits.clear()


def rate_limit(scope: str, max_calls: int, window_seconds: float):
    """Build a FastAPI dependency enforcing ``max_calls`` per ``window_seconds``
    per client IP for the given ``scope``.

    Raises ``429`` with a ``Retry-After`` header when exceeded.
    """

    def dependency(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        key = (scope, _client_ip(request))
        now = time.monotonic()
        with _lock:
            window = _hits[key]
            while window and now - window[0] > window_seconds:
                window.popleft()
            if len(window) >= max_calls:
                retry_after = max(1, int(window_seconds - (now - window[0])))
                raise HTTPException(
                    status_code=429,
                    detail="Too many attempts. Please try again shortly.",
                    headers={"Retry-After": str(retry_after)},
                )
            window.append(now)
            if len(_hits) > _MAX_KEYS:
                _hits.pop(next(iter(_hits)))

    return dependency
