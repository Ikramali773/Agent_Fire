"""Case File sharing persistence - the same thin-seam pattern app/store.py
uses (every caller goes through these functions, never a DB session).

`has_grant` is on the hot path: app/api/case_files.py's _check_access calls
it on every request that touches a case file the caller does not own, so it
is a single indexed lookup and nothing more.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.db.models import CaseFileGrantRecord
from app.db.session import get_session
from app.models.grant import CaseFileGrant, GrantRole
from app.timestamps import as_utc


def _to_grant(record: CaseFileGrantRecord) -> CaseFileGrant:
    return CaseFileGrant(
        id=record.id,
        session_id=record.session_id,
        granted_to_user_id=record.granted_to_user_id,
        granted_to_email=record.granted_to_email,
        granted_by_user_id=record.granted_by_user_id,
        role=GrantRole(record.role),
        created_at=as_utc(record.created_at),
    )


def grant(
    session_id: str,
    granted_to_user_id: str,
    granted_to_email: str,
    granted_by_user_id: str,
    role: GrantRole = GrantRole.REVIEWER,
) -> CaseFileGrant:
    """Shares a case file. Re-sharing with the same person returns the
    existing grant rather than creating a second one or erroring - the
    owner's intent ("this person can see it") is already satisfied.
    """
    existing = get(session_id, granted_to_user_id)
    if existing is not None:
        return existing
    with get_session() as session:
        record = CaseFileGrantRecord(
            session_id=session_id,
            granted_to_user_id=granted_to_user_id,
            granted_to_email=granted_to_email,
            granted_by_user_id=granted_by_user_id,
            role=role.value,
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        try:
            session.commit()
        except IntegrityError:
            # Two concurrent shares to the same person - the unique index
            # is the authority, and the loser simply reads back the winner.
            session.rollback()
            existing = get(session_id, granted_to_user_id)
            if existing is None:
                raise
            return existing
        session.refresh(record)
        return _to_grant(record)


def get(session_id: str, granted_to_user_id: str) -> CaseFileGrant | None:
    with get_session() as session:
        record = (
            session.query(CaseFileGrantRecord)
            .filter(
                CaseFileGrantRecord.session_id == session_id,
                CaseFileGrantRecord.granted_to_user_id == granted_to_user_id,
            )
            .one_or_none()
        )
        return None if record is None else _to_grant(record)


def has_grant(session_id: str, user_id: str) -> bool:
    """Hot path - called by _check_access on every non-owner request."""
    with get_session() as session:
        return (
            session.query(CaseFileGrantRecord.id)
            .filter(
                CaseFileGrantRecord.session_id == session_id,
                CaseFileGrantRecord.granted_to_user_id == user_id,
            )
            .first()
            is not None
        )


def list_for_session(session_id: str) -> list[CaseFileGrant]:
    """Everyone a case file is shared with - the owner's "Shared with" list."""
    with get_session() as session:
        records = (
            session.query(CaseFileGrantRecord)
            .filter(CaseFileGrantRecord.session_id == session_id)
            .order_by(CaseFileGrantRecord.id.asc())
            .all()
        )
        return [_to_grant(record) for record in records]


def list_session_ids_for_user(user_id: str) -> list[str]:
    """Every case file shared WITH this account - what puts someone else's
    project into this reviewer's queue.
    """
    with get_session() as session:
        rows = (
            session.query(CaseFileGrantRecord.session_id)
            .filter(CaseFileGrantRecord.granted_to_user_id == user_id)
            .all()
        )
        return [row[0] for row in rows]


def revoke(session_id: str, granted_to_user_id: str) -> bool:
    """Removes one grant. Returns whether it existed. Takes effect at once -
    the next request from that reviewer is a 403.
    """
    with get_session() as session:
        deleted = (
            session.query(CaseFileGrantRecord)
            .filter(
                CaseFileGrantRecord.session_id == session_id,
                CaseFileGrantRecord.granted_to_user_id == granted_to_user_id,
            )
            .delete()
        )
        session.commit()
        return deleted > 0


def delete_for_session(session_id: str) -> int:
    """Called when a project is deleted: a grant on a case file that no
    longer exists would otherwise linger and put a dead row in a reviewer's
    queue.
    """
    with get_session() as session:
        deleted = (
            session.query(CaseFileGrantRecord)
            .filter(CaseFileGrantRecord.session_id == session_id)
            .delete()
        )
        session.commit()
        return deleted


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(CaseFileGrantRecord).delete()
        session.commit()
