"""Account data contract - Phase 2 (§ "Accounts"). Lets a Case File belong
to a person instead of only an anonymous session (see CaseFile.owner_user_id
in app/models/case_file.py).

Deliberately never carries a password or its hash - that lives only in
app/db/models.py's UserRecord and never leaves app/auth/user_store.py.
Every API response involving a user (signup/login/me) returns this public
model only.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    id: str
    email: str
    created_at: datetime
