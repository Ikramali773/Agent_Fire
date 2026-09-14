"""Auth API - Phase 2 (accounts). Signup/login issue a session token
(app/auth/tokens.py); every existing case-file endpoint keeps working with
none, since an anonymous case file (owner_user_id=None) is still open to
anyone who knows its session_id, same as all of Phase 1 - see
app/api/case_files.py's _check_access().
"""

from __future__ import annotations

import os
import re

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.auth.dependencies import get_current_user_required
from app import mail
from app.auth import password_resets, rate_limit, revoked_tokens
from app.mail import messages
from app.auth.tokens import create_token, decode_token
from app.auth.security import MAX_PASSWORD_BYTES, password_is_too_long
from app.auth.user_store import (
    create_user,
    get_user_by_email,
    set_password,
    verify_credentials,
)
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Deliberately not pydantic's EmailStr - that needs the `email-validator`
# extra just for one field; a plain "looks like an email" check is enough
# here (real deliverability is proven by actually logging in, not by regex).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LENGTH = 8


class Credentials(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User


def _validate_credentials(body: Credentials) -> None:
    if not _EMAIL_RE.match(body.email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if len(body.password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"Password must be at least {_MIN_PASSWORD_LENGTH} characters.")
    # bcrypt's own limit, and a byte one rather than a character one - an
    # emoji is four bytes. Rejected here with a clear message instead of
    # reaching bcrypt, which raises and turned signup into a 500.
    if password_is_too_long(body.password):
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at most {MAX_PASSWORD_BYTES} bytes long (about {MAX_PASSWORD_BYTES} characters).",
        )


@router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(body: Credentials) -> AuthResponse:
    _validate_credentials(body)
    if get_user_by_email(body.email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = create_user(body.email, body.password)
    return AuthResponse(access_token=create_token(user.id), user=user)


def _reset_url(token: str) -> str:
    """Where the link points. The frontend reads `reset` from the query
    string and shows the "choose a new password" form."""
    base = os.environ.get("FIRE_AGENT_APP_URL", "http://localhost:5173").rstrip("/")
    return f"{base}/?reset={token}"


def _rate_limit_key(request: Request, email: str) -> str:
    """Keyed on the client AND the account, so one attacker cannot lock a
    victim out of their own account by burning the limit on their email
    from somewhere else."""
    client = request.client.host if request.client else "unknown"
    return f"{client}:{email.strip().lower()}"


@router.post("/login", response_model=AuthResponse)
def login(body: Credentials, request: Request) -> AuthResponse:
    """Rate-limited: without one, passwords could be tried against a known
    email as fast as the network allowed - and because bcrypt is expensive
    by design, each attempt costs the SERVER more than the attacker, so an
    unlimited endpoint is a denial-of-service lever too.
    """
    key = _rate_limit_key(request, body.email)
    retry_after = rate_limit.check(key)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Wait a moment and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    user = verify_credentials(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    # A correct password clears the counter, so a person who mistyped a few
    # times is not left throttled once they get it right.
    rate_limit.reset(key)
    return AuthResponse(access_token=create_token(user.id), user=user)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


def _validate_new_password(password: str) -> None:
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422, detail=f"Password must be at least {_MIN_PASSWORD_LENGTH} characters."
        )
    if password_is_too_long(password):
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at most {MAX_PASSWORD_BYTES} bytes long.",
        )


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChange, current_user: User = Depends(get_current_user_required)
) -> Response:
    """Changes the signed-in account's password.

    Requires the current one: a session token alone should not be enough to
    lock the real owner out of their own account.

    Every other session is closed as a side effect (see
    user_store.set_password). Someone changing their password because it may
    have been stolen gains nothing if the thief's session stays alive.
    """
    _validate_new_password(body.new_password)
    if verify_credentials(current_user.email, body.current_password) is None:
        raise HTTPException(status_code=403, detail="Current password is incorrect.")
    set_password(current_user.id, body.new_password)
    return Response(status_code=204)


@router.post("/password-reset/request", status_code=204)
def request_password_reset(body: PasswordResetRequest, request: Request) -> Response:
    """Starts a password reset.

    Always 204, whether or not the address has an account: answering
    differently would turn this endpoint into a way to ask "does this person
    use the product?", and for a compliance tool the client list is itself
    worth protecting.

    The link is never returned here - it goes to the delivery backend (see
    app/auth/delivery.py). Returning it would mean anyone could take over
    any account just by typing its address.

    Rate-limited on the same counter shape as login, so this cannot be used
    to flood an inbox or to fish for addresses.
    """
    email = body.email.strip().lower()
    if rate_limit.check(_rate_limit_key(request, email)) is not None:
        raise HTTPException(
            status_code=429, detail="Too many reset requests. Wait a moment and try again."
        )

    user = get_user_by_email(email)
    if user is not None:
        token = password_resets.create(user.id)
        mail.sender.send(messages.password_reset(_reset_url(token)), user.email)
    return Response(status_code=204)


@router.post("/password-reset/confirm", status_code=204)
def confirm_password_reset(body: PasswordResetConfirm) -> Response:
    """Completes a reset with the token from the link.

    Single-use and expiring (see app/auth/password_resets.py), and like a
    change it closes every session the account already had - which is the
    point when the reason for resetting is that someone else got in.
    """
    _validate_new_password(body.new_password)
    user_id = password_resets.consume(body.token)
    if user_id is None:
        raise HTTPException(
            status_code=400, detail="This reset link is invalid, already used, or expired."
        )
    if not set_password(user_id, body.new_password):
        raise HTTPException(status_code=400, detail="This reset link is no longer valid.")
    return Response(status_code=204)


@router.post("/logout", status_code=204)
def logout(authorization: str | None = Header(default=None)) -> Response:
    """Revokes the presented token.

    Until this existed, logging out only made the frontend forget the
    token - it stayed valid for the rest of its seven-day life, so anyone
    who had captured it still had the account. Revoking is per token, so
    signing out on one device leaves other sessions alone.

    Always 204, even for a missing or already-dead token: "am I logged
    out?" should have exactly one answer, and reporting failure would both
    confuse the caller and confirm to an attacker which tokens are live.
    """
    if authorization and authorization.startswith("Bearer "):
        claims = decode_token(authorization[len("Bearer ") :])
        if claims is not None:
            revoked_tokens.revoke(
                claims.token_id,
                claims.user_id,
                datetime.fromtimestamp(claims.expires_at, tz=timezone.utc),
            )
    return Response(status_code=204)


@router.get("/me", response_model=User)
def me(current_user: User = Depends(get_current_user_required)) -> User:
    return current_user
