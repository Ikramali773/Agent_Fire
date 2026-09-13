"""Account-scoped views over Case Files - Phase 2. Split from
app/api/case_files.py (which is keyed entirely by session_id, no account
concept) and app/api/auth.py (accounts, no case file concept) since this
is the one place both meet.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app import grant_store, message_store, review_store
from app.auth.dependencies import get_current_user_required
from app.models.case_file import CaseFile
from app.models.review import ReviewStatus
from app.models.user import User
from app.store import count_by_owner, list_by_owner, list_flagged_for_review

router = APIRouter(prefix="/users", tags=["users"])


# Big enough that a normal account's whole project list arrives in one
# request, small enough that a heavy user cannot be sent a megabyte of JSON
# to render eight rows in the chat rail.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class CaseFilePage(BaseModel):
    """A page of projects, with the total so the UI can say what it is not
    showing rather than silently implying this is everything."""

    items: list[CaseFile]
    total: int
    limit: int
    offset: int


@router.get("/me/case-files", response_model=CaseFilePage)
def list_my_case_files(
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user_required),
) -> CaseFilePage:
    """Phase 2's starting point for Project History (§ "Project history"):
    the case files this account owns, newest-updated first.

    Paged. Unbounded, this response grew linearly with the account's whole
    history - measured at 0.81 MB of JSON for 500 projects, with no ceiling
    - even though the chat rail renders eight of them.
    """
    return CaseFilePage(
        items=list_by_owner(current_user.id, limit=limit, offset=offset),
        total=count_by_owner(current_user.id),
        limit=limit,
        offset=offset,
    )


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
def list_my_chat_titles(
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user_required),
) -> list[ChatTitle]:
    """A title for each of this account's chats, from its first user
    message - what lets the sidebar tell projects apart before one is
    named. Scoped to case files this account owns, so it can never expose
    another account's conversation. Sessions with no user message yet are
    simply absent.
    """
    # Scoped to the same page the project list returns, so this cannot
    # quietly become the unbounded query the project list just stopped
    # being.
    session_ids = [
        case_file.session_id
        for case_file in list_by_owner(current_user.id, limit=limit, offset=offset)
    ]
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
    # One indexed query over the denormalized requires_review column,
    # covering owned and shared-with-me together. This used to load every
    # owned case file plus one lookup per grant, then discard the ones that
    # were not flagged - O(all your projects) to answer a question about a
    # handful of them.
    shared_ids = grant_store.list_session_ids_for_user(current_user.id)
    flagged = list_flagged_for_review(current_user.id, shared_ids)
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
    # The query already returns oldest-first; nothing here reorders it.
    return items
