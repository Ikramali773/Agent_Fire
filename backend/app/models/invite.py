"""Reviewer invitations - Phase 4.

An invite exists because sharing by account email cannot reach someone who
has never signed up, which is most consultants the first time they are
asked to look at something. The link is handed to the OWNER, not mailed:
they are already authorised to share the project, so letting them pass it
on is secure without a mail transport, and keeps this product free of one
more thing to operate.

A link is a credential for the project while it lives, so it is single-use,
expiring, revocable, and stored only as a hash.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CaseFileInvite(BaseModel):
    """An invite as its owner sees it."""

    session_id: str
    invited_email: str
    invited_by_user_id: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    accepted_by_user_id: Optional[str] = None
    invite_url: Optional[str] = Field(
        default=None,
        description=(
            "The full link, present ONLY in the response that created the invite - the token "
            "is stored hashed and cannot be shown again. Listing invites later shows who was "
            "invited and whether they accepted, never the link."
        ),
    )


class InvitePreview(BaseModel):
    """What the recipient is shown before signing up.

    Deliberately thin: enough to know what they are accepting and from
    whom, and nothing about the building. Whoever holds the link has not
    accepted yet, and may not be the person it was meant for.
    """

    project_name: str
    invited_by_email: str
    invited_email: str
    expires_at: datetime
    already_accepted: bool
