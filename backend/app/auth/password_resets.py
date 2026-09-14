"""Password-reset tokens.

The raw token is returned to the caller ONCE, at creation, so it can be put
in a link; only its hash is stored. Same reasoning as passwords: a leaked
database must not hand over the ability to take over accounts.

Single-use and short-lived, because for the window it is alive a reset
token IS a credential for the account.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.db.models import PasswordResetRecord
from app.db.session import get_session

# Long enough to be useful to someone checking their mail, short enough
# that a link lying around in an inbox stops being a key before long.
TOKEN_TTL = timedelta(hours=1)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create(user_id: str) -> str:
    """Issues a token and returns it - the only time it exists in the clear.

    Any earlier token for the same account is dropped first: asking for a
    new link should make the old one dead, or a forwarded email stays usable
    after the real owner has already recovered.
    """
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with get_session() as session:
        session.query(PasswordResetRecord).filter(
            PasswordResetRecord.user_id == user_id
        ).delete()
        session.query(PasswordResetRecord).filter(PasswordResetRecord.expires_at < now).delete()
        session.add(
            PasswordResetRecord(
                token_hash=_hash(token),
                user_id=user_id,
                expires_at=now + TOKEN_TTL,
                created_at=now,
            )
        )
        session.commit()
    return token


def consume(token: str) -> str | None:
    """Spends a token, returning the account it belongs to.

    Marks it used in the same transaction that reads it, so the same link
    cannot be redeemed twice - including by two requests arriving together.
    """
    now = datetime.now(timezone.utc)
    with get_session() as session:
        # The WHERE clause is the check: an UPDATE that matches no row means
        # the token was already used, expired, or never existed. Doing this
        # as a read-then-write would let two requests both pass the read.
        updated = (
            session.query(PasswordResetRecord)
            .filter(
                PasswordResetRecord.token_hash == _hash(token),
                PasswordResetRecord.used_at.is_(None),
                PasswordResetRecord.expires_at > now,
            )
            .update({"used_at": now})
        )
        if updated != 1:
            session.rollback()
            return None
        record = session.get(PasswordResetRecord, _hash(token))
        user_id = record.user_id if record else None
        session.commit()
        return user_id


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(PasswordResetRecord).delete()
        session.commit()
