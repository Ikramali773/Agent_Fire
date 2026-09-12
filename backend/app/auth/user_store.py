"""Account persistence - Phase 2. Same DB-backed pattern as app/store.py
uses for Case Files: SQLAlchemy, no in-memory placeholder (an account only
makes sense as durable state). UserRecord's `hashed_password` never leaves
this module - every function here returns app/models/user.py's User, which
has no password field at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.auth.security import hash_password, verify_password
from app.db.models import UserRecord
from app.db.session import get_session
from app.models.user import User


def _to_user(record: UserRecord) -> User:
    return User(id=record.id, email=record.email, created_at=record.created_at)


def create_user(email: str, password: str) -> User:
    with get_session() as session:
        record = UserRecord(
            id=str(uuid.uuid4()),
            email=email,
            hashed_password=hash_password(password),
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return _to_user(record)


def get_user_by_email(email: str) -> User | None:
    with get_session() as session:
        record = session.query(UserRecord).filter(UserRecord.email == email).one_or_none()
        return _to_user(record) if record is not None else None


def get_user_by_id(user_id: str) -> User | None:
    with get_session() as session:
        record = session.get(UserRecord, user_id)
        return _to_user(record) if record is not None else None


def verify_credentials(email: str, password: str) -> User | None:
    """Returns the User if email+password match a real account, else None -
    the one place a raw hashed_password value is ever read.
    """
    with get_session() as session:
        record = session.query(UserRecord).filter(UserRecord.email == email).one_or_none()
        if record is None or not verify_password(password, record.hashed_password):
            return None
        return _to_user(record)


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(UserRecord).delete()
        session.commit()
