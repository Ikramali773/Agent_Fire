"""Case File change log persistence - the same thin-seam pattern
app/store.py and app/message_store.py use (every caller goes through these
functions, never a DB session directly).

Scale notes, since a change log grows without bound like a transcript does:
- `record` is one INSERT per changed field and never reads or rewrites
  existing rows, so an edit costs the same on change 5 and change 5,000.
- `list_for_session` is indexed by session_id and always bounded by
  `limit`, with a `before_id` cursor for paging further back.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.models import CaseFileChangeRecord
from app.db.session import get_session
from app.timestamps import as_utc
from app.models.case_file import CaseFile
from app.models.change_log import ChangeSource, FieldChange

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500

# Bookkeeping, not facts about the building - see app/models/change_log.py
# for why each one is out of scope.
_UNTRACKED_FIELDS = frozenset(
    {
        "session_id",
        "owner_user_id",
        "created_at",
        "updated_at",
        "field_sources",
        "classification_result",
    }
)


def _to_change(record: CaseFileChangeRecord) -> FieldChange:
    return FieldChange(
        id=record.id,
        session_id=record.session_id,
        field=record.field,
        old_value=record.old_value,
        new_value=record.new_value,
        source=ChangeSource(record.source),
        actor_user_id=record.actor_user_id,
        created_at=as_utc(record.created_at),
    )


def diff(before: CaseFile, after: CaseFile) -> dict[str, tuple[Any, Any]]:
    """The tracked fields whose value differs, as {field: (old, new)}.

    Compares the JSON-mode dumps rather than the models themselves so an
    enum and its string value, or a datetime and its ISO form, don't read
    as a change when nothing actually changed.
    """
    old_data = before.model_dump(mode="json")
    new_data = after.model_dump(mode="json")
    changes: dict[str, tuple[Any, Any]] = {}
    for field, new_value in new_data.items():
        if field in _UNTRACKED_FIELDS:
            continue
        old_value = old_data.get(field)
        if old_value != new_value:
            changes[field] = (old_value, new_value)
    return changes


def record(
    before: CaseFile,
    after: CaseFile,
    source: ChangeSource,
    actor_user_id: str | None = None,
) -> list[FieldChange]:
    """Logs every tracked field that differs between the two versions.

    Called with a snapshot taken BEFORE the mutation - note that the
    dialogue manager and the ingest pipeline mutate the case file in place,
    so the caller must deep-copy rather than keep a reference to the same
    object (`case_file.model_copy(deep=True)`).

    Returns [] and writes nothing when nothing changed, so a no-op PUT or a
    conversational turn that answered no field doesn't pad the timeline.
    """
    changes = diff(before, after)
    if not changes:
        return []

    now = datetime.now(timezone.utc)
    with get_session() as session:
        records = [
            CaseFileChangeRecord(
                session_id=after.session_id,
                field=field,
                old_value=old_value,
                new_value=new_value,
                source=source.value,
                actor_user_id=actor_user_id,
                created_at=now,
            )
            # Sorted so one multi-field edit lands in a stable, readable
            # order rather than whatever order the dict happened to have.
            for field, (old_value, new_value) in sorted(changes.items())
        ]
        session.add_all(records)
        session.commit()
        for item in records:
            session.refresh(item)
        return [_to_change(item) for item in records]


def list_for_session(
    session_id: str, limit: int = DEFAULT_PAGE_SIZE, before_id: int | None = None
) -> list[FieldChange]:
    """The most recent `limit` changes for a session, NEWEST first.

    Opposite order to a transcript on purpose: a conversation is read
    top-to-bottom from where you left off, whereas "what changed recently"
    is the question an activity timeline answers. `before_id` pages further
    back: pass the id of the oldest change you already have.
    """
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    with get_session() as session:
        query = session.query(CaseFileChangeRecord).filter(
            CaseFileChangeRecord.session_id == session_id
        )
        if before_id is not None:
            query = query.filter(CaseFileChangeRecord.id < before_id)
        records = query.order_by(CaseFileChangeRecord.id.desc()).limit(limit).all()
        return [_to_change(item) for item in records]


def delete_for_session(session_id: str) -> int:
    """Removes a session's whole change log. Returns how many entries went.

    Called when a project is deleted, for the same reason the transcript is:
    leaving the history of a deleted project in the database would keep the
    user's data after they asked for the project to be removed.
    """
    with get_session() as session:
        deleted = (
            session.query(CaseFileChangeRecord)
            .filter(CaseFileChangeRecord.session_id == session_id)
            .delete()
        )
        session.commit()
        return deleted


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(CaseFileChangeRecord).delete()
        session.commit()
