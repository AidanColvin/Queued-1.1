"""``/auth`` — account creation and sign-in (Phase 3).

Email/password and Google OAuth both end the same way: a session JWT is minted
and set as the ``queued_auth`` httpOnly cookie, and the SPA learns who it is
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

from auth import apple, google
from auth.deps import get_current_user
from auth.emailer import send_email
from auth.ratelimit import rate_limit
from auth.security import (
    clear_auth_cookie,
    create_access_token,
    create_action_token,
    decode_action_token,
    hash_password,
    password_fingerprint,
    set_auth_cookie,
    verify_password,
)
from config import get_settings
from db.database import User, UserProfile, get_db
from schemas import (
    AppleSignInRequest,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    UserOut,
    VerifyEmailRequest,
)

logger = logging.getLogger("queued")

router = APIRouter(prefix="/auth", tags=["auth"])

# Action-token purposes + lifetimes.
_VERIFY_PURPOSE = "verify_email"
_RESET_PURPOSE = "reset_password"
_VERIFY_EXPIRE_MIN = 7 * 24 * 60  # a week — verification is low-risk
_RESET_EXPIRE_MIN = 60  # an hour — resets grant account takeover


def _public_user(user: User) -> UserOut:
    """Map a ``User`` row to its public API view."""
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        email_verified=bool(user.email_verified),
        onboarding_completed=bool(user.onboarding_completed),
    )


def _issue_session(response: Response, user: User) -> UserOut:
    """Start a session: set the cookie AND return the same JWT in the body.

    Browsers use the httpOnly cookie; the Capacitor native shell stores the
    body token and sends it as ``Authorization: Bearer`` instead (cookies are
    unreliable from the capacitor:// origin).
    """
    token = create_access_token(user.id, user.email)
    set_auth_cookie(response, token)
    out = _public_user(user)
    out.access_token = token
    return out


def _send_verification_email(user: User) -> None:
    """Email the user their verification link (console-logged in dev)."""
    token = create_action_token(user.id, _VERIFY_PURPOSE, _VERIFY_EXPIRE_MIN)
    link = f"{get_settings().frontend_url}/verify-email/?token={token}"
    send_email(
        user.email,
        "Verify your Queued email",
        f"Welcome to Queued!\n\nConfirm your email address by opening:\n\n{link}\n\n"
        "If you didn't create this account, you can ignore this message.",
    )


@router.post("/register", response_model=UserOut, dependencies=[Depends(rate_limit("register", 10, 60.0))])
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
    _send_verification_email(user)
    return _issue_session(response, user)


@router.post("/login", response_model=UserOut, dependencies=[Depends(rate_limit("login", 15, 60.0))])
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
    return _public_user(user)


# --------------------------------------------------------------------------- #
# Email verification + password reset
# --------------------------------------------------------------------------- #
@router.post(
    "/request-verification", status_code=204, dependencies=[Depends(rate_limit("verify_req", 5, 300.0))]
)
def request_verification(user: User = Depends(get_current_user)) -> Response:
    """(Re)send the signed-in user's verification email."""
    if not user.email_verified:
        _send_verification_email(user)
    return Response(status_code=204)


@router.post("/verify-email", status_code=204, dependencies=[Depends(rate_limit("verify", 20, 60.0))])
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> Response:
    """Mark the token's account as verified.

    Raises:
        HTTPException: ``400`` if the token is invalid, expired, or not a
            verification token.
    """
    claims = decode_action_token(payload.token, _VERIFY_PURPOSE)
    user = db.get(User, int(claims["sub"])) if claims else None
    if user is None:
        raise HTTPException(status_code=400, detail="This verification link is invalid or has expired.")
    if not user.email_verified:
        user.email_verified = True
        db.commit()
    return Response(status_code=204)


@router.post(
    "/request-password-reset", status_code=204, dependencies=[Depends(rate_limit("reset_req", 5, 300.0))]
)
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)) -> Response:
    """Email a password-reset link.

    Always returns ``204`` — whether or not the email exists — so the endpoint
    cannot be used to probe which addresses have accounts.
    """
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is not None:
        token = create_action_token(
            user.id, _RESET_PURPOSE, _RESET_EXPIRE_MIN, fingerprint=password_fingerprint(user.hashed_password)
        )
        link = f"{get_settings().frontend_url}/reset-password/?token={token}"
        send_email(
            user.email,
            "Reset your Queued password",
            f"Someone (hopefully you) asked to reset your Queued password.\n\n"
            f"Set a new one here (link valid for 1 hour):\n\n{link}\n\n"
            "If this wasn't you, ignore this email — your password is unchanged.",
        )
    return Response(status_code=204)


@router.post("/reset-password", status_code=204, dependencies=[Depends(rate_limit("reset", 10, 60.0))])
def reset_password(payload: PasswordResetConfirm, db: Session = Depends(get_db)) -> Response:
    """Set a new password from a reset token.

    The token carries a fingerprint of the password hash it was minted against,
    so it is single-use: once the password changes the fingerprint no longer
    matches and the same link cannot be replayed.

    Raises:
        HTTPException: ``400`` on an invalid, expired, or already-used token.
    """
    claims = decode_action_token(payload.token, _RESET_PURPOSE)
    user = db.get(User, int(claims["sub"])) if claims else None
    if user is None or claims.get("fp") != password_fingerprint(user.hashed_password):
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    user.hashed_password = hash_password(payload.new_password)
    # A completed reset also proves control of the inbox.
    user.email_verified = True
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Sign in with Apple — native iOS builds (App Store guideline 4.8: required
# whenever third-party sign-in like Google is offered).
# --------------------------------------------------------------------------- #
@router.post("/apple", response_model=UserOut, dependencies=[Depends(rate_limit("apple", 15, 60.0))])
def apple_sign_in(payload: AppleSignInRequest, response: Response, db: Session = Depends(get_db)) -> UserOut:
    """Verify a native Sign-in-with-Apple identity token and start a session.

    Resolves a user by ``apple_sub`` → else by ``email`` (linking an existing
    account) → else creates a new one. Apple verifies addresses, so the
    account is marked ``email_verified``.

    Raises:
        HTTPException: ``503`` when Apple sign-in isn't configured, ``401`` on
            a token that fails verification.
    """
    if not apple.apple_configured():
        raise HTTPException(status_code=503, detail="Sign in with Apple is not configured on this server.")

    claims = apple.verify_identity_token(payload.identity_token)
    if not claims or not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Apple sign-in could not be verified.")

    sub = str(claims["sub"])
    email = (claims.get("email") or "").strip().lower()

    user = db.scalar(select(User).where(User.apple_sub == sub))
    if user is None and email:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            user.apple_sub = sub  # link Apple to the existing account
    if user is None:
        if not email:
            # Apple omits the email after the first authorization; without a
            # stored apple_sub we can't create an account from this token.
            raise HTTPException(
                status_code=401,
                detail="Apple did not share an email for this account. Remove Queued from your Apple ID's "
                "Sign in with Apple settings and try again.",
            )
        user = User(email=email, apple_sub=sub, display_name=payload.display_name)
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id))
    if payload.display_name and not user.display_name:
        user.display_name = payload.display_name
    user.email_verified = True
    db.commit()
    db.refresh(user)
    return _issue_session(response, user)


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
    # Google only issues tokens for addresses it has verified.
    user.email_verified = True
    db.commit()
    db.refresh(user)

    redirect = RedirectResponse(f"{settings.frontend_url}/?login=success", status_code=302)
    set_auth_cookie(redirect, create_access_token(user.id, user.email))
    return _finish_oauth(redirect)


def _finish_oauth(redirect: RedirectResponse) -> RedirectResponse:
    """Clear the one-shot OAuth state cookie on the way back to the SPA."""
    redirect.delete_cookie(google.OAUTH_STATE_COOKIE, path="/")
    return redirect
