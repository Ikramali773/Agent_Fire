"""Auth API - Phase 2 (accounts). Signup/login issue a session token
(app/auth/tokens.py); every existing case-file endpoint keeps working with
none, since an anonymous case file (owner_user_id=None) is still open to
anyone who knows its session_id, same as all of Phase 1 - see
app/api/case_files.py's _check_access().
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user_required
from app.auth.tokens import create_token
from app.auth.security import MAX_PASSWORD_BYTES, password_is_too_long
from app.auth.user_store import create_user, get_user_by_email, verify_credentials
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


@router.post("/login", response_model=AuthResponse)
def login(body: Credentials) -> AuthResponse:
    user = verify_credentials(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return AuthResponse(access_token=create_token(user.id), user=user)


@router.get("/me", response_model=User)
def me(current_user: User = Depends(get_current_user_required)) -> User:
    return current_user
