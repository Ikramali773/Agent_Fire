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

from app.auth import revoked_tokens
from app.auth.tokens import decode_token
from app.auth.user_store import get_user_by_id, sessions_valid_from
from app.models.user import User


def get_current_user_optional(authorization: Optional[str] = Header(default=None)) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer ") :]
    claims = decode_token(token)
    if claims is None:
        return None
    # A signed, unexpired token is not enough: it may have been logged out.
    # This is the one place signature validity and revocation are combined.
    if revoked_tokens.is_revoked(claims.token_id):
        return None
    # A password change closes every session that existed before it. There
    # is no list of stateless tokens to walk, so the account carries a
    # cut-off instead and each token is checked against it.
    cutoff = sessions_valid_from(claims.user_id)
    if cutoff is not None and claims.issued_at < cutoff.timestamp():
        return None
    return get_user_by_id(claims.user_id)


def get_current_user_required(user: User | None = Depends(get_current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
