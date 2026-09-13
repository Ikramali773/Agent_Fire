"""Conversation transcript persistence - the same thin-seam pattern
app/store.py uses for Case Files (every caller goes through these functions,
never a DB session directly).

Scale notes, since a transcript is the one thing here that grows without
bound:
- `append` is a single INSERT - it never reads or rewrites existing rows,
  so a turn costs the same on message 5 and message 5,000.
- `list_for_session` is indexed by session_id and always bounded by
  `limit`, with a `before_id` cursor for paging further back, so a long
  conversation is never loaded whole just to show the latest exchange.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import ConversationMessageRecord
from app.db.session import get_session
from app.timestamps import as_utc
from app.models.conversation import ConversationMessage, MessageKind, MessageRole

# The default page size for a transcript read. Large enough that a normal
# intake conversation (a few dozen turns) arrives in one request, small
# enough that a pathologically long one can't blow up a response.
DEFAULT_PAGE_SIZE = 200
MAX_PAGE_SIZE = 500


def _to_message(record: ConversationMessageRecord) -> ConversationMessage:
    return ConversationMessage(
        id=record.id,
        session_id=record.session_id,
        role=MessageRole(record.role),
        kind=MessageKind(record.kind),
        text=record.text,
        payload=record.payload,
        created_at=as_utc(record.created_at),
    )


def append(
    session_id: str,
    role: MessageRole,
    text: str = "",
    kind: MessageKind = MessageKind.TEXT,
    payload: dict | None = None,
) -> ConversationMessage:
    with get_session() as session:
        record = ConversationMessageRecord(
            session_id=session_id,
            role=role.value,
            kind=kind.value,
            text=text,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return _to_message(record)


def list_for_session(
    session_id: str, limit: int = DEFAULT_PAGE_SIZE, before_id: int | None = None
) -> list[ConversationMessage]:
    """The most recent `limit` messages for a session, oldest-first (i.e.
    ready to render top-to-bottom). `before_id` pages further back: pass
    the id of the oldest message you already have to get the ones before
    it.
    """
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    with get_session() as session:
        query = session.query(ConversationMessageRecord).filter(
            ConversationMessageRecord.session_id == session_id
        )
        if before_id is not None:
            query = query.filter(ConversationMessageRecord.id < before_id)
        # Take the newest `limit` rows, then flip to chronological order -
        # selecting the oldest rows instead would show the start of a long
        # conversation rather than where the user actually left off.
        records = query.order_by(ConversationMessageRecord.id.desc()).limit(limit).all()
        return [_to_message(record) for record in reversed(records)]


def delete_for_session(session_id: str) -> int:
    """Removes a session's whole transcript. Returns how many messages went.

    Called when a project is deleted: deleting the case file but leaving its
    conversation behind would keep the user's chat content in the database
    after they asked for the project to be removed.
    """
    with get_session() as session:
        deleted = (
            session.query(ConversationMessageRecord)
            .filter(ConversationMessageRecord.session_id == session_id)
            .delete()
        )
        session.commit()
        return deleted


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(ConversationMessageRecord).delete()
        session.commit()
