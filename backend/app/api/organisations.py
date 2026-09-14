"""Organisations, their members, their projects, and review assignment -
Phase 4.

Its own router rather than more of app/api/case_files.py: these endpoints
are addressed by organisation, and the access question is "what may you do
to this TEAM", which is a different question from "what may you do to this
project". The two meet in exactly one place - _check_access in
case_files.py, which now also honours organisation membership.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import assignment_store, grant_store, mail, organisation_store
from app.auth.dependencies import get_current_user_required
from app.auth.user_store import get_user_by_email
from app.mail import messages
from app.models.organisation import (
    OrganisationCaseFile,
    Assignment,
    MemberRole,
    Organisation,
    OrganisationMember,
    OrganisationSummary,
)
from app.models.user import User
from app.store import get as store_get
from app.store import list_by_session_ids

router = APIRouter(prefix="/organisations", tags=["organisations"])

MAX_NAME_LENGTH = 120


def _app_url() -> str:
    """Where to send someone to act on a notification. Same variable the
    reset and invite links are built from (see app/api/auth.py)."""
    import os

    return os.environ.get("FIRE_AGENT_APP_URL", "http://localhost:5173").rstrip("/")


def _require_membership(
    organisation_id: str, user: User, admin: bool = False
) -> OrganisationMember:
    """The caller's membership, or a 404/403.

    A 404 rather than a 403 for a non-member, deliberately: whether an
    organisation exists is itself something only its members should be
    able to find out, and answering differently would let anyone probe for
    one by id.
    """
    membership = organisation_store.get_member(organisation_id, user.id)
    if membership is None:
        raise HTTPException(status_code=404, detail="No such organisation")
    if admin and membership.role is not MemberRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Only an administrator of this organisation can do that."
        )
    return membership


def _validate_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="An organisation needs a name.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise HTTPException(
            status_code=422, detail=f"A name can be at most {MAX_NAME_LENGTH} characters."
        )
    return cleaned


class OrganisationCreate(BaseModel):
    name: str


@router.post("", response_model=Organisation, status_code=201)
def create_organisation(
    body: OrganisationCreate, current_user: User = Depends(get_current_user_required)
) -> Organisation:
    """Creates an organisation with the caller as its first administrator."""
    return organisation_store.create(
        _validate_name(body.name), current_user.id, current_user.email
    )


@router.get("", response_model=list[OrganisationSummary])
def list_my_organisations(
    current_user: User = Depends(get_current_user_required),
) -> list[OrganisationSummary]:
    return organisation_store.list_for_user(current_user.id)


@router.patch("/{organisation_id}", response_model=Organisation)
def rename_organisation(
    organisation_id: str,
    body: OrganisationCreate,
    current_user: User = Depends(get_current_user_required),
) -> Organisation:
    _require_membership(organisation_id, current_user, admin=True)
    renamed = organisation_store.rename(organisation_id, _validate_name(body.name))
    if renamed is None:
        raise HTTPException(status_code=404, detail="No such organisation")
    return renamed


@router.delete("/{organisation_id}", status_code=204)
def delete_organisation(
    organisation_id: str, current_user: User = Depends(get_current_user_required)
):
    """Deletes the organisation, its memberships and its project links.

    The projects themselves are untouched - an organisation is a way of
    sharing them, never where they live. Restricted to the person who
    created it: an administrator added later can manage the team, but
    dissolving it is not theirs to do.
    """
    _require_membership(organisation_id, current_user, admin=True)
    organisation = organisation_store.get(organisation_id)
    if organisation is None:
        raise HTTPException(status_code=404, detail="No such organisation")
    if organisation.created_by_user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the person who created this organisation can delete it.",
        )
    organisation_store.delete(organisation_id)
    from fastapi import Response

    return Response(status_code=204)


# --- Members ----------------------------------------------------------


class MemberAdd(BaseModel):
    email: str
    role: MemberRole = MemberRole.MEMBER


@router.get("/{organisation_id}/members", response_model=list[OrganisationMember])
def list_members(
    organisation_id: str, current_user: User = Depends(get_current_user_required)
) -> list[OrganisationMember]:
    """Visible to every member: you should be able to see who else can read
    the projects you put in here."""
    _require_membership(organisation_id, current_user)
    return organisation_store.list_members(organisation_id)


@router.post("/{organisation_id}/members", response_model=OrganisationMember, status_code=201)
def add_member(
    organisation_id: str,
    body: MemberAdd,
    current_user: User = Depends(get_current_user_required),
) -> OrganisationMember:
    """Adds an existing account to the organisation.

    The address must already have an account. Silently creating one for
    someone is worse than an honest 404, and there is no mail transport
    here to invite them through - the per-project invite link (see
    app/api/invites.py) is the route for someone who has not signed up.
    """
    _require_membership(organisation_id, current_user, admin=True)
    email = body.email.strip().lower()
    user = get_user_by_email(email)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail=f"No account found for {email}. They need to sign up first.",
        )
    return organisation_store.add_member(
        organisation_id, user.id, user.email, body.role, current_user.id
    )


class RoleChange(BaseModel):
    role: MemberRole


@router.patch("/{organisation_id}/members/{user_id}", response_model=OrganisationMember)
def set_member_role(
    organisation_id: str,
    user_id: str,
    body: RoleChange,
    current_user: User = Depends(get_current_user_required),
) -> OrganisationMember:
    """Promotes or demotes a member.

    The creator cannot be demoted, by anyone including themselves: an
    organisation whose last administrator demoted themselves is one nobody
    can add a member to or delete, and there is no support desk here to
    unstick it.
    """
    _require_membership(organisation_id, current_user, admin=True)
    organisation = organisation_store.get(organisation_id)
    if organisation is None:
        raise HTTPException(status_code=404, detail="No such organisation")
    if user_id == organisation.created_by_user_id and body.role is not MemberRole.ADMIN:
        raise HTTPException(
            status_code=422,
            detail="The person who created this organisation stays an administrator.",
        )
    updated = organisation_store.set_role(organisation_id, user_id, body.role)
    if updated is None:
        raise HTTPException(status_code=404, detail="That account is not a member")
    return updated


@router.delete("/{organisation_id}/members/{user_id}", status_code=204)
def remove_member(
    organisation_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user_required),
):
    """Removes a member. Their access to every one of this organisation's
    projects goes with it, in one step - which is the point of having one.

    Leaving voluntarily is allowed for anyone; removing somebody else needs
    to be an administrator. The creator cannot be removed at all, for the
    same reason they cannot be demoted.
    """
    from fastapi import Response

    organisation = organisation_store.get(organisation_id)
    membership = _require_membership(organisation_id, current_user)
    if organisation is None:
        raise HTTPException(status_code=404, detail="No such organisation")
    leaving = user_id == current_user.id
    if not leaving and membership.role is not MemberRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Only an administrator can remove someone else."
        )
    if user_id == organisation.created_by_user_id:
        raise HTTPException(
            status_code=422,
            detail="The person who created this organisation cannot be removed from it.",
        )
    if not organisation_store.remove_member(organisation_id, user_id):
        raise HTTPException(status_code=404, detail="That account is not a member")
    return Response(status_code=204)


# --- Projects ---------------------------------------------------------


class CaseFileLink(BaseModel):
    session_id: str


@router.get("/{organisation_id}/case-files", response_model=list[OrganisationCaseFile])
def list_organisation_case_files(
    organisation_id: str, current_user: User = Depends(get_current_user_required)
) -> list[OrganisationCaseFile]:
    """The team's projects, by name.

    This returned bare session ids, which meant the Team page could say how
    many projects a team held but not which - a list of uuids being no use
    to anyone. Names come from one query over the ids rather than a fetch
    per row.

    Every member can already read each of these, so naming them exposes
    nothing new; the membership check above is what guards it.
    """
    _require_membership(organisation_id, current_user)
    session_ids = organisation_store.session_ids_for_organisation(organisation_id)
    return [
        OrganisationCaseFile(
            session_id=case_file.session_id,
            project_name=case_file.project_name or "Untitled project",
            requires_review=bool(
                case_file.classification_result
                and case_file.classification_result.require_human_review_flag
            ),
            updated_at=case_file.updated_at,
        )
        for case_file in list_by_session_ids(session_ids)
    ]


@router.post("/{organisation_id}/case-files", status_code=201)
def add_case_file(
    organisation_id: str,
    body: CaseFileLink,
    current_user: User = Depends(get_current_user_required),
):
    """Shares a project with the organisation.

    Only its OWNER may do this, not an organisation administrator: being
    able to administer a team must never become a way to pull in projects
    belonging to its members. It is the same rule as individual sharing -
    a reviewer cannot re-share onward - applied to teams.
    """
    from fastapi import Response

    _require_membership(organisation_id, current_user)
    case_file = store_get(body.session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    if case_file.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the owner of a project can share it with a team."
        )
    organisation_store.add_case_file(organisation_id, body.session_id, current_user.id)
    return Response(status_code=201)


@router.delete("/{organisation_id}/case-files/{session_id}", status_code=204)
def remove_case_file(
    organisation_id: str,
    session_id: str,
    current_user: User = Depends(get_current_user_required),
):
    """Stops sharing a project with the organisation.

    Either its owner or an administrator: the owner is taking their own
    project back, and an administrator is deciding what their team holds.
    Neither deletes anything.
    """
    from fastapi import Response

    membership = _require_membership(organisation_id, current_user)
    case_file = store_get(session_id)
    owns = case_file is not None and case_file.owner_user_id == current_user.id
    if not owns and membership.role is not MemberRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only the project's owner or an administrator can remove it.",
        )
    if not organisation_store.remove_case_file(organisation_id, session_id):
        raise HTTPException(status_code=404, detail="That project is not shared with this team")
    return Response(status_code=204)


# --- Assignment -------------------------------------------------------


class AssignmentRequest(BaseModel):
    assigned_to_user_id: str | None = Field(
        default=None,
        description="None unassigns the case - a deliberate act, recorded as its own row.",
    )
    due_at: datetime | None = None
    note: str = ""


assignment_router = APIRouter(prefix="/case-files", tags=["organisations"])


def _may_assign(session_id: str, user: User) -> None:
    """Who may decide whose job a review is.

    The project's owner, or an administrator of a team it is shared with.
    A plain member cannot: being able to read a case is not the same as
    being able to hand it to a colleague.
    """
    case_file = store_get(session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    if case_file.owner_user_id == user.id:
        return
    shared_with = set(organisation_store.organisations_for_case_file(session_id))
    for organisation_id in shared_with:
        membership = organisation_store.get_member(organisation_id, user.id)
        if membership is not None and membership.role is MemberRole.ADMIN:
            return
    raise HTTPException(status_code=403, detail="You cannot assign this case.")


def _may_be_assigned(session_id: str, user_id: str) -> bool:
    """Whether this account can already READ the case.

    Assignment must never be a back door to access: you can only hand a
    case to someone who could already open it. Otherwise "assign to
    anyone" would quietly become "share with anyone", bypassing both the
    owner-only share rule and the organisation it is shared through.
    """
    case_file = store_get(session_id)
    if case_file is None:
        return False
    if case_file.owner_user_id == user_id:
        return True
    if grant_store.has_grant(session_id, user_id):
        return True
    shared_with = set(organisation_store.organisations_for_case_file(session_id))
    return bool(shared_with & set(organisation_store.organisation_ids_for_user(user_id)))


@assignment_router.get("/{session_id}/assignment", response_model=Assignment | None)
def get_assignment(
    session_id: str, current_user: User = Depends(get_current_user_required)
) -> Assignment | None:
    """The current assignment, or null if the case has never had one.

    Readable by anyone who can read the case - knowing whose job something
    is should not need more access than seeing the case itself.
    """
    if not _may_be_assigned(session_id, current_user.id):
        raise HTTPException(status_code=403, detail="You do not have access to this case file")
    return assignment_store.current(session_id)


@assignment_router.get("/{session_id}/assignment/history", response_model=list[Assignment])
def get_assignment_history(
    session_id: str, current_user: User = Depends(get_current_user_required)
) -> list[Assignment]:
    """Every assignment this case has had, oldest first. Append-only, so a
    case reassigned twice reads differently from one assigned once."""
    if not _may_be_assigned(session_id, current_user.id):
        raise HTTPException(status_code=403, detail="You do not have access to this case file")
    return assignment_store.history(session_id)


@assignment_router.post("/{session_id}/assignment", response_model=Assignment, status_code=201)
def set_assignment(
    session_id: str,
    body: AssignmentRequest,
    current_user: User = Depends(get_current_user_required),
) -> Assignment:
    """Assigns the case to someone, with an optional due date.

    The due date is ADVISORY. Nothing in this product enforces one or acts
    when it passes - the queue says a case is overdue and that is all.
    Pretending otherwise in a compliance tool would be worse than not
    having due dates.
    """
    _may_assign(session_id, current_user)

    email: str | None = None
    if body.assigned_to_user_id is not None:
        if not _may_be_assigned(session_id, body.assigned_to_user_id):
            raise HTTPException(
                status_code=422,
                detail=(
                    "That account cannot see this project, so it cannot be assigned to them. "
                    "Share it with them or add them to a team it belongs to first."
                ),
            )
        from app.auth.user_store import get_user_by_id

        assignee = get_user_by_id(body.assigned_to_user_id)
        if assignee is None:
            raise HTTPException(status_code=404, detail="No such account")
        email = assignee.email

    assignment = assignment_store.assign(
        session_id,
        assigned_by_user_id=current_user.id,
        assigned_to_user_id=body.assigned_to_user_id,
        assigned_to_email=email,
        due_at=body.due_at,
        note=body.note,
    )
    if email:
        # Without this, being assigned a case told the assignee nothing at
        # all - they had to come and look. Unassigning mails nobody: there
        # is no news in "you are not doing this any more" worth an inbox.
        case_file = store_get(session_id)
        mail.sender.send(
            messages.case_assigned(
                (case_file.project_name if case_file else "") or "a project",
                current_user.email,
                _app_url(),
                due_at=body.due_at,
                note=body.note,
            ),
            email,
        )
    return assignment
