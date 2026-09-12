"""FastAPI dependencies for the current authenticated user - Phase 2.

Two variants, matching the two situations case_files.py's endpoints need:
`get_current_user_optional` for every existing case-file endpoint (an
anonymous case file, Phase 1's original model, must keep working with no
Authorization header at all - see _check_access() there), and
`get_current_user_required` for endpoints that only make sense for a
logged-in account (signup/login aside, "list my case files").
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException

from app.auth.tokens import verify_token
from app.auth.user_store import get_user_by_id
from app.models.user import User


def get_current_user_optional(authorization: Optional[str] = Header(default=None)) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer ") :]
    user_id = verify_token(token)
    if user_id is None:
        return None
    return get_user_by_id(user_id)


def get_current_user_required(user: User | None = Depends(get_current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
