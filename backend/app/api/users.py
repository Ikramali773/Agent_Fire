"""Account-scoped views over Case Files - Phase 2. Split from
app/api/case_files.py (which is keyed entirely by session_id, no account
concept) and app/api/auth.py (accounts, no case file concept) since this
is the one place both meet.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app import (
    assignment_store,
    grant_store,
    message_store,
    organisation_store,
    preferences_store,
    review_store,
)
from app.auth.dependencies import get_current_user_required
from app.models.case_file import CaseFile
from app.models.organisation import Assignment
from app.models.preferences import UserPreferences
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
    assignment: Assignment | None = Field(
        default=None,
        description=(
            "The current assignment, if the case has one. Carried on the queue row so the "
            "list can show who owes this and by when without a request per row."
        ),
    )
    assigned_to_me: bool = Field(
        default=False,
        description="Whether the current assignment names this account - what 'my queue' filters on.",
    )
    is_overdue: bool = Field(
        default=False,
        description=(
            "Past its due date and not yet settled. Advisory: nothing in this product acts "
            "when a due date passes, it only says so."
        ),
    )


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
    # Phase 4 adds a third source: projects shared with an organisation
    # this account belongs to. Folded into the same `extra_session_ids`
    # the query already takes, so the queue stays one indexed query
    # however many ways a case reaches you.
    reachable_ids = set(grant_store.list_session_ids_for_user(current_user.id))
    reachable_ids.update(organisation_store.session_ids_for_user(current_user.id))
    flagged = list_flagged_for_review(current_user.id, sorted(reachable_ids))
    session_ids = [case_file.session_id for case_file in flagged]
    statuses = review_store.current_statuses(session_ids)
    # One query for every row's assignment, not one per row - the O(n)
    # round trips this queue was rewritten to avoid.
    assignments = assignment_store.current_for_sessions(session_ids)
    now = datetime.now(timezone.utc)

    items = []
    for case_file in flagged:
        status = statuses.get(case_file.session_id, ReviewStatus.NEEDS_REVIEW)
        settled = status in _SETTLED_STATUSES
        if not include_settled and settled:
            continue
        reasons = case_file.classification_result.review_reasons
        assignment = assignments.get(case_file.session_id)
        # An assignment row with no assignee means the case was explicitly
        # UNASSIGNED, which is not the same as never assigned - but for
        # "is this mine" and "is this late" both read the same way.
        assigned_to = assignment.assigned_to_user_id if assignment else None
        due_at = assignment.due_at if assignment else None
        items.append(
            ReviewQueueItem(
                session_id=case_file.session_id,
                project_name=case_file.project_name,
                reason_codes=sorted({reason.code.value for reason in reasons}),
                reason_count=len(reasons),
                status=status,
                is_owner=case_file.owner_user_id == current_user.id,
                updated_at=case_file.updated_at,
                assignment=assignment,
                assigned_to_me=assigned_to == current_user.id,
                # A settled case is not late - it is done. Saying otherwise
                # would leave permanent red rows nobody can clear.
                is_overdue=bool(due_at and due_at < now and not settled),
            )
        )
    # The query already returns oldest-first; nothing here reorders it.
    return items


@router.get("/me/preferences", response_model=UserPreferences)
def get_my_preferences(
    current_user: User = Depends(get_current_user_required),
) -> UserPreferences:
    """How this account likes to work - see app/models/preferences.py.

    Always answers, defaults included: an account that has never set
    anything is not an error, and making the frontend distinguish "no
    preferences yet" from "no preferences set" would buy nothing.
    """
    return preferences_store.get(current_user.id)


@router.put("/me/preferences", response_model=UserPreferences)
def replace_my_preferences(
    preferences: UserPreferences,
    current_user: User = Depends(get_current_user_required),
) -> UserPreferences:
    """Replaces this account's preferences wholesale.

    Returns what was actually stored, not what was sent: duplicates are
    dropped and the list is capped, so a caller that echoed its own
    request back would drift out of step with the server.

    Requires an account, obviously - there is nothing to attach a
    preference to without one. An anonymous session keeps using the
    browser's own storage, which is the correct place for it.
    """
    return preferences_store.save(current_user.id, preferences)
