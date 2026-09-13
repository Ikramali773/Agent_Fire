"""Account-scoped views over Case Files - Phase 2. Split from
app/api/case_files.py (which is keyed entirely by session_id, no account
concept) and app/api/auth.py (accounts, no case file concept) since this
is the one place both meet.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import grant_store, message_store, review_store
from app.auth.dependencies import get_current_user_required
from app.models.case_file import CaseFile
from app.models.review import ReviewStatus
from app.models.user import User
from app.store import get as store_get
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


class ReviewQueueItem(BaseModel):
    """One row of the review queue."""

    session_id: str
    project_name: str = ""
    reason_codes: list[str] = Field(
        default_factory=list, description="ReviewReasonCode values, for grouping the queue."
    )
    reason_count: int = 0
    status: ReviewStatus
    is_owner: bool = Field(
        description="Whether this account owns the project or is reviewing it for someone else."
    )
    updated_at: datetime


# Terminal from the queue's point of view: the case has had its answer and
# stops competing for attention. It is still readable, and a later event
# (say, after the facts change) brings it back.
_SETTLED_STATUSES = frozenset({ReviewStatus.APPROVED, ReviewStatus.REJECTED})


@router.get("/me/review-queue", response_model=list[ReviewQueueItem])
def list_my_review_queue(
    include_settled: bool = False,
    current_user: User = Depends(get_current_user_required),
) -> list[ReviewQueueItem]:
    """Phase 3: every flagged case this account is responsible for - its
    own projects, plus projects shared with it for review.

    OLDEST FIRST, unlike every other list in this product. A chat rail is
    newest-first because you are resuming what you were just doing; a
    compliance queue is oldest-first because the case that has been waiting
    longest is the one most at risk of being forgotten.

    Approved and rejected cases are excluded by default: they have had
    their answer and should stop competing for attention. Pass
    include_settled=true to see the whole picture.
    """
    owned = list_by_owner(current_user.id)
    owned_ids = {case_file.session_id for case_file in owned}

    shared: list[CaseFile] = []
    for session_id in grant_store.list_session_ids_for_user(current_user.id):
        if session_id in owned_ids:
            continue
        case_file = store_get(session_id)
        # A grant whose case file is gone should not put a dead row in the
        # queue. Deleting a project revokes its grants, so this is a
        # belt-and-braces guard, not the main path.
        if case_file is not None:
            shared.append(case_file)

    flagged = [
        case_file
        for case_file in [*owned, *shared]
        if case_file.classification_result.require_human_review_flag
    ]
    statuses = review_store.current_statuses([case_file.session_id for case_file in flagged])

    items = []
    for case_file in flagged:
        status = statuses.get(case_file.session_id, ReviewStatus.NEEDS_REVIEW)
        if not include_settled and status in _SETTLED_STATUSES:
            continue
        reasons = case_file.classification_result.review_reasons
        items.append(
            ReviewQueueItem(
                session_id=case_file.session_id,
                project_name=case_file.project_name,
                reason_codes=sorted({reason.code.value for reason in reasons}),
                reason_count=len(reasons),
                status=status,
                is_owner=case_file.owner_user_id == current_user.id,
                updated_at=case_file.updated_at,
            )
        )
    items.sort(key=lambda item: item.updated_at)
    return items
