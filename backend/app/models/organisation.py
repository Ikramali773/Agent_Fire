"""Organisations - Phase 4.

Sharing was one project to one person at a time. That works for a
consultant looked in once, and not at all for a practice where six people
need to see the same forty projects: every new project means six more
shares, every new colleague means forty, and the day someone leaves you
have to remember all of them.

An organisation is a named group of accounts. A project shared with it is
readable by every member, and a member who leaves loses that access in one
step rather than forty.

What an organisation deliberately does NOT do: grant WRITE. Members read,
record verdicts, and can be assigned a review - exactly the reviewer
capability that already exists, because the reason for it is unchanged. A
verdict on facts the reviewer could have edited is worth nothing, and that
does not stop being true because the reviewer is a colleague.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MemberRole(str, Enum):
    """What a member may do to the ORGANISATION - not to its projects.

    Project access is the same for both: read and review. The difference is
    administrative.
    """

    ADMIN = "admin"
    """Add and remove members, add and remove projects, assign reviews."""

    MEMBER = "member"
    """Read the organisation's projects and record verdicts on them."""


class Organisation(BaseModel):
    id: str
    name: str
    created_by_user_id: str
    created_at: datetime


class OrganisationMember(BaseModel):
    organisation_id: str
    user_id: str
    email: str
    role: MemberRole
    added_by_user_id: str
    created_at: datetime


class OrganisationSummary(BaseModel):
    """An organisation as one of its members sees it in a list."""

    organisation: Organisation
    role: MemberRole
    member_count: int


class Assignment(BaseModel):
    """Who is expected to review a flagged case, and by when.

    Append-only (see app/assignment_store.py): the current assignment is the
    latest row. A case reassigned twice reads differently from one assigned
    once, and in a compliance record that difference is the point.
    """

    id: int
    session_id: str
    assigned_to_user_id: Optional[str] = Field(
        default=None,
        description="None means the case was explicitly UNASSIGNED - a deliberate act with its own row, not an absence of one.",
    )
    assigned_to_email: Optional[str] = None
    assigned_by_user_id: str
    due_at: Optional[datetime] = Field(
        default=None,
        description="Advisory only. Nothing in this product enforces a due date or acts when one passes; it is a note to the people involved.",
    )
    note: str = ""
    created_at: datetime
