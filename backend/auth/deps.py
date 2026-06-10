"""Current-user FastAPI dependencies.

``get_current_user`` guards account-only endpoints (401 when signed out);
``get_optional_user`` is for endpoints that must keep working anonymously
(``/swipe``) and simply returns ``None`` for a guest.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth.security import AUTH_COOKIE, decode_token
from db.database import User, get_db


def _user_from_request(request: Request, db: Session) -> User | None:
    """Resolve the signed-in user from the auth cookie, or ``None``."""
    claims = decode_token(request.cookies.get(AUTH_COOKIE, ""))
    if not claims:
        return None
    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    return db.get(User, user_id)


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Return the current user, or ``None`` if the request is anonymous."""
    return _user_from_request(request, db)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Return the current user or raise ``401`` if not signed in."""
    user = _user_from_request(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user
