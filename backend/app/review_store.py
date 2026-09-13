"""Human review persistence - Phase 3.

Append-only, like the transcript and the change log, and for a sharper
reason than either: a compliance sign-off's value is that the WHOLE
sequence stays visible. A case that was approved, reopened when a fact
changed, and approved again is a different thing from a case that was
approved once, and a table that updated a status column in place could not
tell you which you were looking at.

The current status is therefore never stored - it is derived (`current_status`
below) as "the latest event, or NEEDS_REVIEW if there are none yet". That
also means a newly flagged case needs no write at all to appear in a queue.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func

from app.db.models import CaseFileReviewRecord
from app.db.session import get_session
from app.models.review import ReviewEvent, ReviewStatus
from app.timestamps import as_utc


def _to_event(record: CaseFileReviewRecord) -> ReviewEvent:
    return ReviewEvent(
        id=record.id,
        session_id=record.session_id,
        status=ReviewStatus(record.status),
        note=record.note,
        actor_user_id=record.actor_user_id,
        actor_email=record.actor_email,
        created_at=as_utc(record.created_at),
    )


def record(
    session_id: str,
    status: ReviewStatus,
    note: str = "",
    actor_user_id: str | None = None,
    actor_email: str | None = None,
) -> ReviewEvent:
    """Records one verdict. Never updates an earlier one."""
    with get_session() as session:
        row = CaseFileReviewRecord(
            session_id=session_id,
            status=status.value,
            note=note,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_event(row)


def list_for_session(session_id: str) -> list[ReviewEvent]:
    """The whole review history, oldest-first - it reads as a narrative.

    Unbounded on purpose, unlike the transcript and change log: a review
    history is a handful of entries even on a case that has gone round
    several times, and paging it would hide the very thing it exists to
    show.
    """
    with get_session() as session:
        records = (
            session.query(CaseFileReviewRecord)
            .filter(CaseFileReviewRecord.session_id == session_id)
            .order_by(CaseFileReviewRecord.id.asc())
            .all()
        )
        return [_to_event(item) for item in records]


def current_status(session_id: str) -> ReviewStatus:
    """The latest verdict, or NEEDS_REVIEW if nobody has recorded one."""
    with get_session() as session:
        row = (
            session.query(CaseFileReviewRecord.status)
            .filter(CaseFileReviewRecord.session_id == session_id)
            .order_by(CaseFileReviewRecord.id.desc())
            .first()
        )
        return ReviewStatus.NEEDS_REVIEW if row is None else ReviewStatus(row[0])


def current_statuses(session_ids: list[str]) -> dict[str, ReviewStatus]:
    """current_status for many sessions in one query - what the queue needs.

    Doing this per row would be one round trip per project in the queue.
    """
    if not session_ids:
        return {}
    with get_session() as session:
        latest = (
            session.query(
                CaseFileReviewRecord.session_id.label("session_id"),
                func.max(CaseFileReviewRecord.id).label("latest_id"),
            )
            .filter(CaseFileReviewRecord.session_id.in_(session_ids))
            .group_by(CaseFileReviewRecord.session_id)
            .subquery()
        )
        rows = (
            session.query(CaseFileReviewRecord.session_id, CaseFileReviewRecord.status)
            .join(latest, CaseFileReviewRecord.id == latest.c.latest_id)
            .all()
        )
        return {session_id: ReviewStatus(status) for session_id, status in rows}


def delete_for_session(session_id: str) -> int:
    """Called when a project is deleted - its review history goes with it."""
    with get_session() as session:
        deleted = (
            session.query(CaseFileReviewRecord)
            .filter(CaseFileReviewRecord.session_id == session_id)
            .delete()
        )
        session.commit()
        return deleted


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(CaseFileReviewRecord).delete()
        session.commit()
