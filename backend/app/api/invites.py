"""Redeeming a reviewer invitation - Phase 4.

Split from app/api/case_files.py because these two endpoints are addressed
by TOKEN rather than by session_id, and are reached by someone who may have
no account and no access to the project yet. Keeping them apart makes it
obvious that `_check_access` deliberately does not run here: the token IS
the authorisation, which is exactly why it is single-use, expiring, and
stored only as a hash.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import grant_store, invite_store
from app.auth.dependencies import get_current_user_required
from app.auth.user_store import get_user_by_id
from app.models.invite import CaseFileInvite, InvitePreview
from app.models.user import User
from app.store import get as store_get

router = APIRouter(prefix="/invites", tags=["invites"])


@router.get("/{token}", response_model=InvitePreview)
def preview_invite(token: str) -> InvitePreview:
    """What this link is, before signing up to accept it.

    Unauthenticated on purpose - the recipient has no account yet, and
    being asked to create one without being told what for is how an
    invitation gets ignored.

    Deliberately thin: the project's name and who sent it, and nothing
    about the building. Whoever holds the link has not accepted yet, and
    may not be the person it was meant for.
    """
    invite = invite_store.get_by_token(token)
    if invite is None:
        raise HTTPException(status_code=404, detail="This invitation link is not valid.")

    case_file = store_get(invite.session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="The project this invitation points to is gone.")

    inviter = get_user_by_id(invite.invited_by_user_id)
    return InvitePreview(
        project_name=case_file.project_name or "Untitled project",
        invited_by_email=inviter.email if inviter else "a user of this workspace",
        invited_email=invite.invited_email,
        expires_at=invite.expires_at,
        already_accepted=invite.accepted_at is not None,
    )


@router.post("/{token}/accept", response_model=CaseFileInvite)
def accept_invite(
    token: str, current_user: User = Depends(get_current_user_required)
) -> CaseFileInvite:
    """Redeems an invite, granting the signed-in account reviewer access.

    Requires an account: a verdict has to be attributable to a person, and
    "someone with the link" is not one.

    The invite is accepted by whoever is signed in, which need not be the
    address it was addressed to - a consultant may well sign up with a
    different one, and refusing that would strand a legitimate reviewer
    over a typo. The address it was sent to is kept on the record either
    way, so the owner can see who they meant to invite and who actually
    accepted.
    """
    invite = invite_store.get_by_token(token)
    if invite is None:
        raise HTTPException(status_code=404, detail="This invitation link is not valid.")

    case_file = store_get(invite.session_id)
    if case_file is None:
        raise HTTPException(status_code=404, detail="The project this invitation points to is gone.")
    if case_file.owner_user_id == current_user.id:
        raise HTTPException(status_code=422, detail="You already own this project.")

    accepted = invite_store.accept(token, current_user.id)
    if accepted is None:
        raise HTTPException(
            status_code=400,
            detail="This invitation has already been used, or it has expired.",
        )

    grant_store.grant(
        invite.session_id,
        granted_to_user_id=current_user.id,
        granted_to_email=current_user.email,
        granted_by_user_id=invite.invited_by_user_id,
    )
    return accepted
