"""Account-scoped views over Case Files - Phase 2. Split from
app/api/case_files.py (which is keyed entirely by session_id, no account
concept) and app/api/auth.py (accounts, no case file concept) since this
is the one place both meet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import message_store
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


class ChatTitle(BaseModel):
    """A chat's title derived from what was actually said in it.

    Deliberately NOT a field on the Case File: a title is a presentation
    detail of the conversation, the Case File schema is fixed, and
    persisting one would mean keeping it in step with a transcript that
    already contains the answer. Served as a small side-lookup the chat
    rail merges over the project list it already has.
    """

    session_id: str
    title: str


@router.get("/me/chat-titles", response_model=list[ChatTitle])
def list_my_chat_titles(current_user: User = Depends(get_current_user_required)) -> list[ChatTitle]:
    """A title for each of this account's chats, from its first user
    message - what lets the sidebar tell projects apart before one is
    named. Scoped to case files this account owns, so it can never expose
    another account's conversation. Sessions with no user message yet are
    simply absent.
    """
    session_ids = [case_file.session_id for case_file in list_by_owner(current_user.id)]
    titles = message_store.first_user_messages(session_ids)
    return [ChatTitle(session_id=session_id, title=title) for session_id, title in titles.items()]
