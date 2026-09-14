"""Account persistence - Phase 2. Same DB-backed pattern as app/store.py
uses for Case Files: SQLAlchemy, no in-memory placeholder (an account only
makes sense as durable state). UserRecord's `hashed_password` never leaves
this module - every function here returns app/models/user.py's User, which
has no password field at all.
"""

from __future__ import annotations

import secrets

import uuid
from datetime import datetime, timezone

from app.auth.security import hash_password, verify_password
from app.db.models import UserRecord
from app.db.session import get_session
from app.models.user import User
from app.timestamps import as_utc


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


def set_password(user_id: str, password: str) -> bool:
    """Replaces an account's password and closes every existing session.

    The two go together on purpose: someone changing their password
    because it may have been stolen gains nothing if the thief's session
    stays alive. `sessions_valid_from` is the cut-off every token is
    checked against (see app/auth/dependencies.py).
    """
    with get_session() as session:
        record = session.get(UserRecord, user_id)
        if record is None:
            return False
        record.hashed_password = hash_password(password)
        record.sessions_valid_from = datetime.now(timezone.utc)
        session.commit()
        return True


def sessions_valid_from(user_id: str) -> datetime | None:
    """The instant before which this account's tokens are no longer valid."""
    with get_session() as session:
        record = session.get(UserRecord, user_id)
        return as_utc(record.sessions_valid_from) if record and record.sessions_valid_from else None


def get_user_by_email(email: str) -> User | None:
    with get_session() as session:
        record = session.query(UserRecord).filter(UserRecord.email == email).one_or_none()
        return _to_user(record) if record is not None else None


def get_user_by_id(user_id: str) -> User | None:
    with get_session() as session:
        record = session.get(UserRecord, user_id)
        return _to_user(record) if record is not None else None


# A real bcrypt hash of a value nobody can supply, verified against when
# the account does not exist. Computed once at import: the point is to
# spend the same time as a real check, not to be a usable credential.
_ABSENT_ACCOUNT_HASH = hash_password(secrets.token_urlsafe(32))


def verify_credentials(email: str, password: str) -> User | None:
    """Returns the User if email+password match a real account, else None -
    the one place a raw hashed_password value is ever read.

    **Takes the same time whether or not the account exists.** It used to
    short-circuit - `record is None or not verify_password(...)` - so bcrypt
    never ran for an unknown address. Measured: 311 ms when the account
    exists against 0.3 ms when it does not, a 1000x difference anybody can
    time from outside.

    That mattered here more than usual, because this product goes to real
    lengths elsewhere to hide exactly this: /auth/password-reset/request
    answers 204 whether or not the address has an account, specifically so
    it cannot be used to ask who uses the product. Leaking the same fact
    through a stopwatch on /auth/login made that promise worthless.

    So an unknown address is verified against a throwaway hash instead.
    The comparison always fails; the cost is the same either way.
    """
    with get_session() as session:
        record = session.query(UserRecord).filter(UserRecord.email == email).one_or_none()
        # Deliberately NOT short-circuited - see the docstring. Both
        # branches run one bcrypt verification.
        if record is None:
            verify_password(password, _ABSENT_ACCOUNT_HASH)
            return None
        if not verify_password(password, record.hashed_password):
            return None
        return _to_user(record)


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(UserRecord).delete()
        session.commit()
