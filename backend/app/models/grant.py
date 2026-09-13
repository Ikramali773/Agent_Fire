"""Case File sharing - Phase 3.

Until now access was binary: you own a case file or you get a 403. That is
enough while the only person who ever looks at a project is the person who
started it, and it stops being enough the moment the product's answer to a
flagged case is "hand this to a licensed fire consultant" - because that
consultant has to be able to read the project without owning it.

A grant is deliberately narrow:

- it is per case file, never per account ("share my whole workspace" is not
  a thing here);
- it conveys READ plus the ability to record a review verdict, and nothing
  else. A reviewer cannot edit facts, continue the conversation, delete the
  project, or re-share it. Their job is to judge what is there, and the
  Case File staying exactly as the owner left it is what makes their
  verdict mean something;
- it is revocable by the owner at any time, and revoking is immediate.

`granted_to_email` is stored alongside the id for the same reason
ReviewEvent stores one: a compliance record has to stay readable years
later, when an account may have been renamed or deleted.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class GrantRole(str, Enum):
    REVIEWER = "reviewer"
    """Read the case file and record review verdicts. Cannot edit or delete."""


class CaseFileGrant(BaseModel):
    id: int
    session_id: str
    granted_to_user_id: str
    granted_to_email: str = Field(
        description="The reviewer's email as it was when the grant was made."
    )
    granted_by_user_id: str
    role: GrantRole = GrantRole.REVIEWER
    created_at: datetime
