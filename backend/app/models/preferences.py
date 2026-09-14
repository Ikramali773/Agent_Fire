"""Per-user preferences.

The thing that forced this: a pinned chat is per-USER UI state. The Case
File schema is fixed and has no field for "this person pinned this
project" - and inventing one would be wrong anyway, since it would put one
account's preference on a record that can be shared with reviewers. So pins
lived in `localStorage`, which meant they did not follow the account to a
second browser or a phone. That was documented as a limitation rather than
hidden, and this is the fix.

Deliberately TYPED rather than an open JSON bag. A free-form key-value
store would let the frontend write anything, which is how a preferences
table turns into an unversioned second schema nobody can reason about.
Adding a preference here is a deliberate act with a migration behind it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# A generous ceiling that still bounds the row. Someone with more pinned
# projects than this is not using pins as pins.
MAX_PINNED = 200


class UserPreferences(BaseModel):
    """Everything this product remembers about how one person likes to work.

    Note what is NOT here: the active project and the session token. Those
    are per-BROWSER, not per-user - "which project was I last looking at"
    should differ between the laptop and the phone, and syncing it would
    make two open tabs fight. They stay in localStorage on purpose.
    """

    pinned_session_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Projects this account has pinned, most recently pinned first. Ids only - the "
            "projects themselves are read through the ordinary access checks, so a pin can "
            "never be a way to see a project you no longer have access to."
        ),
    )
