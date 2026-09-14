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

from sqlalchemy import func

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


# How much of a first message to keep as a chat title. Long enough to tell
# two projects apart at a glance, short enough for a sidebar row.
TITLE_MAX_CHARS = 60


def _to_title(text: str) -> str:
    """One line of a first message, trimmed to fit a sidebar row."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= TITLE_MAX_CHARS:
        return collapsed
    # Cut at a word boundary rather than mid-word, unless the first word is
    # itself longer than the limit.
    clipped = collapsed[:TITLE_MAX_CHARS].rsplit(" ", 1)[0] or collapsed[:TITLE_MAX_CHARS]
    return f"{clipped}…"


def first_user_messages(session_ids: list[str]) -> dict[str, str]:
    """The opening user message of each given session, as a chat title.

    What a chat rail needs to tell projects apart before one has a name:
    the project name is collected partway through the intake, so a rail of
    freshly-started chats would otherwise be a column of identical
    "Untitled project" rows.

    Only USER messages count - the agent's greeting is identical in every
    conversation and would title them all the same.
    """
    if not session_ids:
        return {}
    with get_session() as session:
        # The lowest id per session is its first message; grouping and then
        # joining back is what fetches only those rows rather than pulling
        # every message of every project into Python to pick the first.
        firsts = (
            session.query(
                ConversationMessageRecord.session_id.label("session_id"),
                func.min(ConversationMessageRecord.id).label("first_id"),
            )
            .filter(
                ConversationMessageRecord.role == MessageRole.USER.value,
                ConversationMessageRecord.session_id.in_(session_ids),
            )
            .group_by(ConversationMessageRecord.session_id)
            .subquery()
        )
        rows = (
            session.query(ConversationMessageRecord.session_id, ConversationMessageRecord.text)
            .join(firsts, ConversationMessageRecord.id == firsts.c.first_id)
            .all()
        )
        return {session_id: _to_title(text) for session_id, text in rows if text.strip()}


# How much of the matching message to show. Enough to recognise why a
# project matched, short enough that twenty results stay a list.
SNIPPET_RADIUS = 60


def search(session_ids: list[str], query: str, limit: int = 20) -> dict[str, str]:
    """Sessions whose transcript contains `query`, with the bit that matched.

    Chat search used to match the TITLE only - and a title is the first
    message verbatim - so "that project where we discussed the atrium"
    still meant opening chats one by one. This looks inside the
    conversation.

    Scoped by `session_ids`, which the caller has already reduced to what
    this account may read. Nothing here checks access, deliberately: the
    query would be the wrong place to decide it, and one function that
    "sometimes" filters is how a leak gets written.

    **A substring match, case-insensitive, with no ranking and no
    stemming** - "sprinkler" does not find "sprinklers". Real full-text
    search means SQLite FTS5 or Postgres tsvector, which are dialect-
    specific, and everything here is written against portable SQLAlchemy so
    the same code path runs on both (see app/db/session.py). Worth
    revisiting if search becomes central rather than a way to find a chat.
    """
    needle = query.strip()
    if not needle or not session_ids:
        return {}
    with get_session() as session:
        rows = (
            session.query(ConversationMessageRecord.session_id, ConversationMessageRecord.text)
            .filter(
                ConversationMessageRecord.session_id.in_(session_ids),
                ConversationMessageRecord.text.ilike(f"%{needle}%"),
            )
            .order_by(ConversationMessageRecord.id.asc())
            .all()
        )
    found: dict[str, str] = {}
    for session_id, text in rows:
        # First match per session only: a rail row shows one snippet, and
        # a project that mentions the word forty times is not forty hits.
        if session_id in found:
            continue
        found[session_id] = _snippet(text or "", needle)
        if len(found) >= limit:
            break
    return found


def _snippet(text: str, needle: str) -> str:
    """The matching phrase with a little either side, ellipsed if clipped."""
    collapsed = " ".join(text.split())
    at = collapsed.lower().find(needle.lower())
    if at < 0:
        return _to_title(collapsed)
    start = max(0, at - SNIPPET_RADIUS)
    end = min(len(collapsed), at + len(needle) + SNIPPET_RADIUS)
    return (
        ("…" if start > 0 else "")
        + collapsed[start:end].strip()
        + ("…" if end < len(collapsed) else "")
    )


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
