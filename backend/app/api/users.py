"""Account-scoped views over Case Files - Phase 2. Split from
app/api/case_files.py (which is keyed entirely by session_id, no account
concept) and app/api/auth.py (accounts, no case file concept) since this
is the one place both meet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user_required
from app.models.case_file import CaseFile
from app.models.user import User
from app.store import list_by_owner

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/case-files", response_model=list[CaseFile])
def list_my_case_files(current_user: User = Depends(get_current_user_required)) -> list[CaseFile]:
    """Phase 2's starting point for Project History (§ "Project history"):
    every case file this account owns, newest-updated first.
    """
    return list_by_owner(current_user.id)
