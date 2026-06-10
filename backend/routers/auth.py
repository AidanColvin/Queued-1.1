"""``/auth`` — account creation and sign-in (Phase 3).

Email/password and Google OAuth both end the same way: a session JWT is minted
and set as the ``nextwatch_auth`` httpOnly cookie, and the SPA learns who it is
by calling ``GET /auth/me``. There is no server-side session — the cookie is the
whole session, which is what keeps this working on serverless.

The Google routes live in :mod:`auth.google` and are attached to this router at
import time.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import google
from auth.deps import get_current_user
from auth.security import clear_auth_cookie, create_access_token, hash_password, set_auth_cookie, verify_password
from config import get_settings
from db.database import User, UserProfile, get_db
from schemas import LoginRequest, RegisterRequest, UserOut

logger = logging.getLogger("nextwatch")

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_session(response: Response, user: User) -> UserOut:
    """Mint the session cookie for ``user`` and return their public view."""
    set_auth_cookie(response, create_access_token(user.id, user.email))
    return UserOut(id=user.id, email=user.email, display_name=user.display_name)


@router.post("/register", response_model=UserOut)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> UserOut:
    """Create an email/password account, sign the user in, and return them.

    Raises:
        HTTPException: ``409`` if the email is already registered.
    """
    exists = db.scalar(select(User).where(User.email == payload.email))
    if exists is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    db.flush()  # assign user.id
    db.add(UserProfile(user_id=user.id))
    db.commit()
    db.refresh(user)
    return _issue_session(response, user)


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> UserOut:
    """Verify credentials and start a session.

    Raises:
        HTTPException: ``401`` on unknown email or wrong password (same message
            either way, so the response can't be used to probe which emails
            exist).
    """
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return _issue_session(response, user)


@router.post("/logout", status_code=204)
def logout() -> Response:
    """Clear the session cookie."""
    response = Response(status_code=204)
    clear_auth_cookie(response)
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    """Return the signed-in user, or ``401`` if there is no valid session."""
    return UserOut(id=user.id, email=user.email, display_name=user.display_name)


# --------------------------------------------------------------------------- #
# Google OAuth — "Continue with Google"
# --------------------------------------------------------------------------- #
def _ensure_google_configured() -> None:
    if not google.google_configured():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured on this server.")


@router.get("/google/login")
def google_login() -> RedirectResponse:
    """Start the Google flow: stash a CSRF ``state`` cookie and redirect to the
    Google consent screen."""
    _ensure_google_configured()
    settings = get_settings()
    state = secrets.token_urlsafe(24)
    redirect = RedirectResponse(google.build_authorize_url(state), status_code=302)
    redirect.set_cookie(
        key=google.OAUTH_STATE_COOKIE,
        value=state,
        max_age=300,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return redirect


@router.get("/google/callback")
def google_callback(request: Request, state: str = "", code: str = "", db: Session = Depends(get_db)) -> RedirectResponse:
    """Finish the Google flow: verify state, resolve/create the account, set the
    session cookie, and bounce back to the SPA.

    Resolves a user by ``google_sub`` → else by ``email`` (linking an existing
    email/password account) → else creates a new account.

    Raises:
        HTTPException: ``400`` if the CSRF ``state`` does not match (tampering).
    """
    _ensure_google_configured()
    settings = get_settings()

    cookie_state = request.cookies.get(google.OAUTH_STATE_COOKIE)
    if not cookie_state or not state or not secrets.compare_digest(cookie_state, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    try:
        token = google.exchange_code(code)
        info = google.fetch_userinfo(token["access_token"])
    except Exception:  # noqa: BLE001 — surface as a friendly SPA error, not a 500
        logger.exception("Google OAuth token/userinfo exchange failed")
        return _finish_oauth(RedirectResponse(f"{settings.frontend_url}/?login=error", status_code=302))

    sub = info.get("sub")
    email = (info.get("email") or "").strip().lower()
    if not sub or not email:
        return _finish_oauth(RedirectResponse(f"{settings.frontend_url}/?login=error", status_code=302))

    user = db.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            user.google_sub = sub  # link Google to the existing email account
        else:
            user = User(email=email, google_sub=sub, display_name=info.get("name"))
            db.add(user)
            db.flush()
            db.add(UserProfile(user_id=user.id))
    db.commit()
    db.refresh(user)

    redirect = RedirectResponse(f"{settings.frontend_url}/?login=success", status_code=302)
    set_auth_cookie(redirect, create_access_token(user.id, user.email))
    return _finish_oauth(redirect)


def _finish_oauth(redirect: RedirectResponse) -> RedirectResponse:
    """Clear the one-shot OAuth state cookie on the way back to the SPA."""
    redirect.delete_cookie(google.OAUTH_STATE_COOKIE, path="/")
    return redirect
