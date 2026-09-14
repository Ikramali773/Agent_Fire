"""Storage for per-user preferences (app/models/preferences.py).

Same thin-seam pattern as app/store.py: callers go through these functions,
never a DB session directly.

One row per user holding one JSON blob, for the reason CaseFileRecord is a
blob: preferences are always read and written whole, and there is no query
that needs to filter on one of them at the SQL level. If that ever changes,
the column comes out of the blob the way owner_user_id did.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import UserPreferenceRecord
from app.db.session import get_session
from app.models.preferences import MAX_PINNED, UserPreferences


def get(user_id: str) -> UserPreferences:
    """This account's preferences, or the defaults.

    Never None: an account that has never set anything has defaults, and
    making every caller handle "no row yet" separately would be noise.
    """
    with get_session() as session:
        record = session.get(UserPreferenceRecord, user_id)
        if record is None:
            return UserPreferences()
        return UserPreferences.model_validate(record.data)


def save(user_id: str, preferences: UserPreferences) -> UserPreferences:
    """Replaces this account's preferences.

    Whole-object replace rather than a patch: the object is small, it is
    always edited as a whole in the UI, and a patch endpoint would need a
    way to say "set this list to empty" that is distinct from "don't touch
    this list" - which is exactly the ambiguity that makes patch APIs
    error-prone for collections.
    """
    trimmed = _trim(preferences)
    now = datetime.now(timezone.utc)
    with get_session() as session:
        record = session.get(UserPreferenceRecord, user_id)
        if record is None:
            session.add(
                UserPreferenceRecord(
                    user_id=user_id, data=trimmed.model_dump(mode="json"), updated_at=now
                )
            )
        else:
            record.data = trimmed.model_dump(mode="json")
            record.updated_at = now
        session.commit()
    return trimmed


def forget_session(session_id: str) -> None:
    """Drops a deleted project from every account that pinned it.

    Without this a pin outlives the project it points at, and the list
    grows forever with ids that resolve to nothing. Called from the case
    file delete cascade, alongside the messages, changes, reviews, grants
    and invites.
    """
    with get_session() as session:
        # Small table, and this runs only on an explicit delete - a scan is
        # the right shape here, not an index on the inside of a JSON list.
        for record in session.query(UserPreferenceRecord).all():
            pinned = record.data.get("pinned_session_ids") or []
            if session_id not in pinned:
                continue
            record.data = {
                **record.data,
                "pinned_session_ids": [item for item in pinned if item != session_id],
            }
        session.commit()


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(UserPreferenceRecord).delete()
        session.commit()


def _trim(preferences: UserPreferences) -> UserPreferences:
    """Bounds the row, and drops duplicates while keeping pin order."""
    seen: set[str] = set()
    unique: list[str] = []
    for session_id in preferences.pinned_session_ids:
        if session_id and session_id not in seen:
            seen.add(session_id)
            unique.append(session_id)
    return preferences.model_copy(update={"pinned_session_ids": unique[:MAX_PINNED]})
