"""Review assignment persistence - Phase 4.

Append-only, like app/review_store.py and for the same reason: a case
reassigned twice reads differently from one assigned once, and in a
compliance record that difference is exactly what someone will want to
see. The current assignment is derived (`current`), never stored, so
there is no status column that can drift from the history beside it.

Unassigning writes a row with no assignee rather than deleting one - a
deliberate act, recorded as such.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func

from app.db.models import CaseFileAssignmentRecord
from app.db.session import get_session
from app.models.organisation import Assignment
from app.timestamps import as_utc


def _to_assignment(record: CaseFileAssignmentRecord) -> Assignment:
    return Assignment(
        id=record.id,
        session_id=record.session_id,
        assigned_to_user_id=record.assigned_to_user_id,
        assigned_to_email=record.assigned_to_email,
        assigned_by_user_id=record.assigned_by_user_id,
        due_at=as_utc(record.due_at) if record.due_at else None,
        note=record.note or "",
        created_at=as_utc(record.created_at),
    )


def assign(
    session_id: str,
    assigned_by_user_id: str,
    assigned_to_user_id: str | None = None,
    assigned_to_email: str | None = None,
    due_at: datetime | None = None,
    note: str = "",
) -> Assignment:
    """Records one assignment. Never updates an earlier one."""
    record = CaseFileAssignmentRecord(
        session_id=session_id,
        assigned_to_user_id=assigned_to_user_id,
        assigned_to_email=assigned_to_email,
        assigned_by_user_id=assigned_by_user_id,
        due_at=due_at,
        note=note,
        created_at=datetime.now(timezone.utc),
    )
    with get_session() as session:
        session.add(record)
        session.commit()
        session.refresh(record)
        return _to_assignment(record)


def current(session_id: str) -> Assignment | None:
    """The latest assignment, or None if the case has never been assigned.

    An assignment whose `assigned_to_user_id` is None means it was
    explicitly unassigned - which is NOT the same as never assigned, and
    callers that care can tell the two apart.
    """
    with get_session() as session:
        record = (
            session.query(CaseFileAssignmentRecord)
            .filter(CaseFileAssignmentRecord.session_id == session_id)
            .order_by(CaseFileAssignmentRecord.id.desc())
            .first()
        )
        return _to_assignment(record) if record else None


def history(session_id: str) -> list[Assignment]:
    """Every assignment this case has had, oldest first."""
    with get_session() as session:
        records = (
            session.query(CaseFileAssignmentRecord)
            .filter(CaseFileAssignmentRecord.session_id == session_id)
            .order_by(CaseFileAssignmentRecord.id.asc())
            .all()
        )
        return [_to_assignment(record) for record in records]


def current_for_sessions(session_ids: list[str]) -> dict[str, Assignment]:
    """The current assignment for each of many cases, in one query.

    Exists because the review queue needs this for every row, and doing it
    per row is the O(n) round trips the queue was rewritten to avoid.
    """
    if not session_ids:
        return {}
    with get_session() as session:
        latest_ids = (
            session.query(func.max(CaseFileAssignmentRecord.id))
            .filter(CaseFileAssignmentRecord.session_id.in_(session_ids))
            .group_by(CaseFileAssignmentRecord.session_id)
            .all()
        )
        ids = [row[0] for row in latest_ids]
        if not ids:
            return {}
        records = (
            session.query(CaseFileAssignmentRecord)
            .filter(CaseFileAssignmentRecord.id.in_(ids))
            .all()
        )
        return {record.session_id: _to_assignment(record) for record in records}


def session_ids_assigned_to(user_id: str) -> list[str]:
    """Cases whose CURRENT assignment is this account.

    Deliberately not "cases this account has ever been assigned": a case
    reassigned away is no longer anyone's to do, and a queue that kept
    showing it would be worse than useless.
    """
    with get_session() as session:
        latest_ids = [
            row[0]
            for row in session.query(func.max(CaseFileAssignmentRecord.id))
            .group_by(CaseFileAssignmentRecord.session_id)
            .all()
        ]
        if not latest_ids:
            return []
        return [
            row[0]
            for row in session.query(CaseFileAssignmentRecord.session_id)
            .filter(
                CaseFileAssignmentRecord.id.in_(latest_ids),
                CaseFileAssignmentRecord.assigned_to_user_id == user_id,
            )
            .all()
        ]


def delete_for_session(session_id: str) -> None:
    """Part of the case file delete cascade."""
    with get_session() as session:
        session.query(CaseFileAssignmentRecord).filter(
            CaseFileAssignmentRecord.session_id == session_id
        ).delete(synchronize_session=False)
        session.commit()


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(CaseFileAssignmentRecord).delete()
        session.commit()
