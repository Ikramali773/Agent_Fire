"""Organisation persistence - Phase 4.

Same thin-seam pattern as app/store.py: callers go through these functions,
never a DB session directly.

`organisation_ids_for_user` and `session_ids_for_user` are on the hot path -
_check_access consults them for any project the caller does not own - so
both are indexed lookups and nothing more.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.db.models import (
    OrganisationCaseFileRecord,
    OrganisationMemberRecord,
    OrganisationRecord,
)
from app.db.session import get_session
from app.models.organisation import (
    MemberRole,
    Organisation,
    OrganisationMember,
    OrganisationSummary,
)
from app.timestamps import as_utc


def _to_org(record: OrganisationRecord) -> Organisation:
    return Organisation(
        id=record.id,
        name=record.name,
        created_by_user_id=record.created_by_user_id,
        created_at=as_utc(record.created_at),
    )


def _to_member(record: OrganisationMemberRecord) -> OrganisationMember:
    return OrganisationMember(
        organisation_id=record.organisation_id,
        user_id=record.user_id,
        email=record.email,
        role=MemberRole(record.role),
        added_by_user_id=record.added_by_user_id,
        created_at=as_utc(record.created_at),
    )


def create(name: str, created_by_user_id: str, created_by_email: str) -> Organisation:
    """Creates an organisation with its creator as the first ADMIN.

    The creator is added in the same transaction on purpose: an
    organisation with no members is unreachable - nobody could add
    themselves to it - so a failure between the two writes would leave an
    orphan nobody can see or delete.
    """
    now = datetime.now(timezone.utc)
    org = OrganisationRecord(
        id=str(uuid.uuid4()),
        name=name.strip(),
        created_by_user_id=created_by_user_id,
        created_at=now,
    )
    with get_session() as session:
        session.add(org)
        session.add(
            OrganisationMemberRecord(
                organisation_id=org.id,
                user_id=created_by_user_id,
                email=created_by_email,
                role=MemberRole.ADMIN.value,
                added_by_user_id=created_by_user_id,
                created_at=now,
            )
        )
        session.commit()
        session.refresh(org)
        return _to_org(org)


def get(organisation_id: str) -> Organisation | None:
    with get_session() as session:
        record = session.get(OrganisationRecord, organisation_id)
        return _to_org(record) if record else None


def rename(organisation_id: str, name: str) -> Organisation | None:
    with get_session() as session:
        record = session.get(OrganisationRecord, organisation_id)
        if record is None:
            return None
        record.name = name.strip()
        session.commit()
        session.refresh(record)
        return _to_org(record)


def delete(organisation_id: str) -> bool:
    """Removes the organisation, its memberships and its project links.

    The projects themselves are untouched - an organisation is a way of
    sharing them, never where they live. Deleting one takes away access,
    not work.
    """
    with get_session() as session:
        record = session.get(OrganisationRecord, organisation_id)
        if record is None:
            return False
        session.query(OrganisationMemberRecord).filter(
            OrganisationMemberRecord.organisation_id == organisation_id
        ).delete(synchronize_session=False)
        session.query(OrganisationCaseFileRecord).filter(
            OrganisationCaseFileRecord.organisation_id == organisation_id
        ).delete(synchronize_session=False)
        session.delete(record)
        session.commit()
        return True


# --- Membership -------------------------------------------------------


def add_member(
    organisation_id: str,
    user_id: str,
    email: str,
    role: MemberRole,
    added_by_user_id: str,
) -> OrganisationMember:
    """Adds someone, or returns their existing membership unchanged.

    Idempotent rather than an error: "this person should be in the team"
    is already true, and failing the request would only make the caller
    write the same check themselves. Note it does NOT change an existing
    role - use set_role for that, so a re-add can never quietly demote an
    admin.
    """
    existing = get_member(organisation_id, user_id)
    if existing is not None:
        return existing
    record = OrganisationMemberRecord(
        organisation_id=organisation_id,
        user_id=user_id,
        email=email,
        role=role.value,
        added_by_user_id=added_by_user_id,
        created_at=datetime.now(timezone.utc),
    )
    with get_session() as session:
        session.add(record)
        try:
            session.commit()
        except IntegrityError:
            # Someone added the same person concurrently; their row is as
            # good as ours.
            session.rollback()
            return get_member(organisation_id, user_id)  # type: ignore[return-value]
        session.refresh(record)
        return _to_member(record)


def get_member(organisation_id: str, user_id: str) -> OrganisationMember | None:
    with get_session() as session:
        record = (
            session.query(OrganisationMemberRecord)
            .filter(
                OrganisationMemberRecord.organisation_id == organisation_id,
                OrganisationMemberRecord.user_id == user_id,
            )
            .one_or_none()
        )
        return _to_member(record) if record else None


def list_members(organisation_id: str) -> list[OrganisationMember]:
    with get_session() as session:
        records = (
            session.query(OrganisationMemberRecord)
            .filter(OrganisationMemberRecord.organisation_id == organisation_id)
            .order_by(OrganisationMemberRecord.created_at.asc())
            .all()
        )
        return [_to_member(record) for record in records]


def set_role(organisation_id: str, user_id: str, role: MemberRole) -> OrganisationMember | None:
    with get_session() as session:
        record = (
            session.query(OrganisationMemberRecord)
            .filter(
                OrganisationMemberRecord.organisation_id == organisation_id,
                OrganisationMemberRecord.user_id == user_id,
            )
            .one_or_none()
        )
        if record is None:
            return None
        record.role = role.value
        session.commit()
        session.refresh(record)
        return _to_member(record)


def remove_member(organisation_id: str, user_id: str) -> bool:
    """Removes someone. Their access to every one of the organisation's
    projects goes with it, in one step - which is the point."""
    with get_session() as session:
        deleted = (
            session.query(OrganisationMemberRecord)
            .filter(
                OrganisationMemberRecord.organisation_id == organisation_id,
                OrganisationMemberRecord.user_id == user_id,
            )
            .delete(synchronize_session=False)
        )
        session.commit()
        return bool(deleted)


def list_for_user(user_id: str) -> list[OrganisationSummary]:
    with get_session() as session:
        memberships = (
            session.query(OrganisationMemberRecord)
            .filter(OrganisationMemberRecord.user_id == user_id)
            .all()
        )
        summaries: list[OrganisationSummary] = []
        for membership in memberships:
            org = session.get(OrganisationRecord, membership.organisation_id)
            if org is None:
                continue
            count = (
                session.query(OrganisationMemberRecord)
                .filter(OrganisationMemberRecord.organisation_id == org.id)
                .count()
            )
            summaries.append(
                OrganisationSummary(
                    organisation=_to_org(org),
                    role=MemberRole(membership.role),
                    member_count=count,
                )
            )
        summaries.sort(key=lambda item: item.organisation.name.lower())
        return summaries


def organisation_ids_for_user(user_id: str) -> list[str]:
    with get_session() as session:
        return [
            row[0]
            for row in session.query(OrganisationMemberRecord.organisation_id)
            .filter(OrganisationMemberRecord.user_id == user_id)
            .all()
        ]


# --- Projects ---------------------------------------------------------


def add_case_file(organisation_id: str, session_id: str, added_by_user_id: str) -> bool:
    """Shares a project with the organisation. Idempotent."""
    with get_session() as session:
        existing = (
            session.query(OrganisationCaseFileRecord)
            .filter(
                OrganisationCaseFileRecord.organisation_id == organisation_id,
                OrganisationCaseFileRecord.session_id == session_id,
            )
            .one_or_none()
        )
        if existing is not None:
            return False
        session.add(
            OrganisationCaseFileRecord(
                organisation_id=organisation_id,
                session_id=session_id,
                added_by_user_id=added_by_user_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        return True


def remove_case_file(organisation_id: str, session_id: str) -> bool:
    with get_session() as session:
        deleted = (
            session.query(OrganisationCaseFileRecord)
            .filter(
                OrganisationCaseFileRecord.organisation_id == organisation_id,
                OrganisationCaseFileRecord.session_id == session_id,
            )
            .delete(synchronize_session=False)
        )
        session.commit()
        return bool(deleted)


def session_ids_for_organisation(organisation_id: str) -> list[str]:
    with get_session() as session:
        return [
            row[0]
            for row in session.query(OrganisationCaseFileRecord.session_id)
            .filter(OrganisationCaseFileRecord.organisation_id == organisation_id)
            .all()
        ]


def session_ids_for_user(user_id: str) -> list[str]:
    """Every project readable through any organisation this account is in.

    One query over the join rather than one per organisation: an account in
    several teams would otherwise pay a round trip per team on every
    access check.
    """
    with get_session() as session:
        rows = (
            session.query(OrganisationCaseFileRecord.session_id)
            .join(
                OrganisationMemberRecord,
                OrganisationMemberRecord.organisation_id
                == OrganisationCaseFileRecord.organisation_id,
            )
            .filter(OrganisationMemberRecord.user_id == user_id)
            .distinct()
            .all()
        )
        return [row[0] for row in rows]


def organisations_for_case_file(session_id: str) -> list[str]:
    with get_session() as session:
        return [
            row[0]
            for row in session.query(OrganisationCaseFileRecord.organisation_id)
            .filter(OrganisationCaseFileRecord.session_id == session_id)
            .all()
        ]


def delete_for_session(session_id: str) -> None:
    """Part of the case file delete cascade."""
    with get_session() as session:
        session.query(OrganisationCaseFileRecord).filter(
            OrganisationCaseFileRecord.session_id == session_id
        ).delete(synchronize_session=False)
        session.commit()


def delete_all() -> None:
    """Test-only helper, mirrors app/store.py's delete_all()."""
    with get_session() as session:
        session.query(OrganisationCaseFileRecord).delete()
        session.query(OrganisationMemberRecord).delete()
        session.query(OrganisationRecord).delete()
        session.commit()
