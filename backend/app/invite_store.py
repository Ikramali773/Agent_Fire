"""Reviewer invitation persistence - the same thin-seam pattern app/store.py
uses (callers go through these functions, never a DB session).

The raw token is returned once, at creation, so it can be put in a link;
only its hash is stored. A leaked database must not hand over live access
to every shared project.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.db.models import CaseFileInviteRecord
from app.db.session import get_session
from app.models.invite import CaseFileInvite
from app.timestamps import as_utc

# Long enough to survive "I'll look at it next week", short enough that a
# link forwarded around an office stops being a key before long.
INVITE_TTL = timedelta(days=14)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _to_invite(record: CaseFileInviteRecord) -> CaseFileInvite:
    return CaseFileInvite(
        session_id=record.session_id,
        invited_email=record.invited_email,
        invited_by_user_id=record.invited_by_user_id,
        created_at=as_utc(record.created_at),
        expires_at=as_utc(record.expires_at),
        accepted_at=as_utc(record.accepted_at) if record.accepted_at else None,
        accepted_by_user_id=record.accepted_by_user_id,
    )


def create(session_id: str, invited_email: str, invited_by_user_id: str) -> tuple[str, CaseFileInvite]:
    """Issues an invite, returning (raw token, invite).

    Any earlier unaccepted invite to the same address for the same project
    is dropped: re-inviting someone should make the previous link dead,
    rather than leaving two working keys in circulation.
    """
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with get_session() as session:
        session.query(CaseFileInviteRecord).filter(
            CaseFileInviteRecord.session_id == session_id,
            CaseFileInviteRecord.invited_email == invited_email,
            CaseFileInviteRecord.accepted_at.is_(None),
        ).delete()
        record = CaseFileInviteRecord(
            token_hash=_hash(token),
            session_id=session_id,
            invited_email=invited_email,
            invited_by_user_id=invited_by_user_id,
            expires_at=now + INVITE_TTL,
            created_at=now,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return token, _to_invite(record)


def get_by_token(token: str) -> CaseFileInvite | None:
    """The invite a link refers to, accepted or not, expired or not.

    Callers decide what to do about state - the preview endpoint wants to
    show "already accepted" rather than pretend the link never existed.
    """
    with get_session() as session:
        record = session.get(CaseFileInviteRecord, _hash(token))
        return None if record is None else _to_invite(record)


def accept(token: str, user_id: str) -> CaseFileInvite | None:
    """Spends an invite for `user_id`. None if it cannot be spent.

    The conditions are part of the UPDATE, so two requests racing the same
    link cannot both succeed.
    """
    now = datetime.now(timezone.utc)
    with get_session() as session:
        updated = (
            session.query(CaseFileInviteRecord)
            .filter(
                CaseFileInviteRecord.token_hash == _hash(token),
                CaseFileInviteRecord.accepted_at.is_(None),
                CaseFileInviteRecord.expires_at > now,
            )
            .update({"accepted_at": now, "accepted_by_user_id": user_id})
        )
        if updated != 1:
            session.rollback()
            return None
        record = session.get(CaseFileInviteRecord, _hash(token))
        invite = _to_invite(record) if record else None
        session.commit()
        return invite


def list_for_session(session_id: str) -> list[CaseFileInvite]:
    """Every invite on a project - the owner's "invited" list. Never
    includes a token: they are stored hashed and cannot be shown again."""
    with get_session() as session:
        records = (
            session.query(CaseFileInviteRecord)
            .filter(CaseFileInviteRecord.session_id == session_id)
            .order_by(CaseFileInviteRecord.created_at.asc())
            .all()
        )
        return [_to_invite(record) for record in records]


def revoke(session_id: str, invited_email: str) -> bool:
    """Cancels an outstanding invite. Returns whether one existed.

    Only unaccepted invites: once accepted the access is a grant, and it is
    revoked through the shares endpoint like any other.
    """
    with get_session() as session:
        deleted = (
            session.query(CaseFileInviteRecord)
            .filter(
                CaseFileInviteRecord.session_id == session_id,
                CaseFileInviteRecord.invited_email == invited_email,
                CaseFileInviteRecord.accepted_at.is_(None),
            )
            .delete()
        )
        session.commit()
        return deleted > 0


def delete_for_session(session_id: str) -> int:
    """Called when a project is deleted - an invite to a project that no
    longer exists must not stay redeemable."""
    with get_session() as session:
        deleted = (
            session.query(CaseFileInviteRecord)
            .filter(CaseFileInviteRecord.session_id == session_id)
            .delete()
        )
        session.commit()
        return deleted


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(CaseFileInviteRecord).delete()
        session.commit()
