"""Revoked session tokens - the store behind logout.

Same thin-seam pattern as app/store.py: callers go through these functions,
never a DB session directly.

`is_revoked` is on the hot path - it runs for every authenticated request -
so it is a single primary-key lookup and nothing else.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import RevokedTokenRecord
from app.db.session import get_session


def revoke(token_id: str, user_id: str, expires_at: datetime) -> None:
    """Marks one token dead. Idempotent - logging out twice is not an error.

    Also prunes rows whose tokens have expired anyway: after that point the
    signature check rejects them without help, so keeping the row would
    only grow the table forever.
    """
    if not token_id:
        # A token issued before token ids existed. Nothing to key a
        # revocation on; it expires within the TTL regardless.
        return
    now = datetime.now(timezone.utc)
    with get_session() as session:
        session.query(RevokedTokenRecord).filter(RevokedTokenRecord.expires_at < now).delete()
        if session.get(RevokedTokenRecord, token_id) is None:
            session.add(
                RevokedTokenRecord(
                    token_id=token_id,
                    user_id=user_id,
                    expires_at=expires_at,
                    revoked_at=now,
                )
            )
        session.commit()


def is_revoked(token_id: str) -> bool:
    if not token_id:
        return False
    with get_session() as session:
        return session.get(RevokedTokenRecord, token_id) is not None


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(RevokedTokenRecord).delete()
        session.commit()
