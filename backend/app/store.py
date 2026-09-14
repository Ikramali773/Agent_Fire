"""Case File persistence.

Backed by the database (app/db/) as of this revision - previously an
in-memory dict, explicitly called out as a placeholder to be swapped for
real storage per product scope §B.10. This module's public functions
(get/save/delete_all) are unchanged from that placeholder on purpose: every
caller (app/api/case_files.py, app/dialogue/manager.py, tests) was written
against this interface, not against "in memory" as an assumption, so the
swap needed zero changes anywhere else - which is the whole point of having
this thin module as the seam instead of calling a DB session directly from
the API layer.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, update

from app.db.models import CaseFileRecord
from app.db.session import get_session
from app.models.case_file import CaseFile


class StaleCaseFileError(RuntimeError):
    """Raised when a write is based on a version that is no longer current.

    Means someone else changed this case file between the caller reading it
    and writing it back. The caller must re-read and decide what to do; it
    must NOT retry blindly, which would reintroduce exactly the silent
    overwrite this exists to prevent.
    """

    def __init__(self, session_id: str, expected: int, actual: int):
        super().__init__(
            f"Case file {session_id} has changed since it was read "
            f"(expected version {expected}, found {actual})"
        )
        self.session_id = session_id
        self.expected_version = expected
        self.actual_version = actual


# A row written before the version column existed reads as NULL. It has
# been written exactly once as far as we know, so it is version 1.
def _version_of(record: CaseFileRecord) -> int:
    return record.version or 1


def save(case_file: CaseFile, expected_version: int | None = None) -> CaseFile:
    """Persists a case file, bumping its version.

    Pass `expected_version` (the version that was read at the start of the
    operation) to make this a compare-and-set: if anyone else has written
    since, it raises StaleCaseFileError instead of overwriting them. Every
    request that does read -> mutate -> save should pass it.

    Omitting it keeps the old last-write-wins behavior, which is correct
    only for a caller that is creating the case file or genuinely holds the
    latest state.
    """
    with get_session() as session:
        record = session.get(CaseFileRecord, case_file.session_id)
        now = datetime.now(timezone.utc)

        if record is None:
            case_file.version = 1
            session.add(
                CaseFileRecord(
                    session_id=case_file.session_id,
                    data=case_file.model_dump(mode="json"),
                    created_at=now,
                    updated_at=now,
                    owner_user_id=case_file.owner_user_id,
                    version=1,
                    requires_review=case_file.classification_result.require_human_review_flag,
                )
            )
            session.commit()
            return case_file

        current_version = _version_of(record)
        if expected_version is not None and expected_version != current_version:
            raise StaleCaseFileError(case_file.session_id, expected_version, current_version)

        next_version = current_version + 1
        values = {
            "data": case_file.model_copy(update={"version": next_version}).model_dump(mode="json"),
            "updated_at": now,
            "owner_user_id": case_file.owner_user_id,
            "version": next_version,
            # Denormalized so the review queue can filter in SQL. This is
            # the only writer, so it cannot drift from the blob.
            "requires_review": case_file.classification_result.require_human_review_flag,
        }

        if expected_version is None:
            session.execute(
                update(CaseFileRecord)
                .where(CaseFileRecord.session_id == case_file.session_id)
                .values(**values)
            )
            session.commit()
            case_file.version = next_version
            return case_file

        # The version check has to be part of the UPDATE, not a read
        # followed by a write: two requests can both pass a Python-side
        # check before either commits, and then both write. (That is not
        # hypothetical - the first version of this fix did exactly that,
        # and the concurrency test caught it.) A conditional UPDATE is
        # atomic in every database: whoever gets rowcount 1 won.
        #
        # The NULL arm covers a row written before the version column
        # existed; the additive migration cannot backfill it, and it is
        # read as version 1 everywhere else too.
        result = session.execute(
            update(CaseFileRecord)
            .where(
                CaseFileRecord.session_id == case_file.session_id,
                or_(
                    CaseFileRecord.version == expected_version,
                    and_(CaseFileRecord.version.is_(None), expected_version == 1),
                ),
            )
            .values(**values)
        )
        if result.rowcount != 1:
            session.rollback()
            latest = session.get(CaseFileRecord, case_file.session_id)
            raise StaleCaseFileError(
                case_file.session_id,
                expected_version,
                _version_of(latest) if latest is not None else 0,
            )
        session.commit()
        case_file.version = next_version
    return case_file


def get(session_id: str) -> CaseFile | None:
    with get_session() as session:
        record = session.get(CaseFileRecord, session_id)
        if record is None:
            return None
        return _to_case_file(record)


def _to_case_file(record: CaseFileRecord) -> CaseFile:
    """The version always comes from the COLUMN, never from the blob: the
    blob's copy is whatever was current when it was written, and treating
    that as authoritative would defeat the lock.
    """
    case_file = CaseFile.model_validate(record.data)
    case_file.version = _version_of(record)
    return case_file


def list_by_owner(owner_user_id: str, limit: int | None = None, offset: int = 0) -> list[CaseFile]:
    """Phase 2 (accounts): case files belonging to one account, newest first.
    Filters on the real `owner_user_id` column (see db/models.py), not by
    scanning every row's JSON blob in Python.

    `limit` bounds the page. Unbounded, this response grew linearly with a
    user's whole history - measured at 0.81 MB of JSON for 500 projects,
    with no ceiling - even though the chat rail renders eight of them.
    """
    with get_session() as session:
        query = (
            session.query(CaseFileRecord)
            .filter(CaseFileRecord.owner_user_id == owner_user_id)
            .order_by(CaseFileRecord.updated_at.desc())
            .offset(offset)
        )
        if limit is not None:
            query = query.limit(limit)
        return [_to_case_file(record) for record in query.all()]


def count_by_owner(owner_user_id: str) -> int:
    """How many projects an account has, so a paged response can say how
    many it is NOT showing."""
    with get_session() as session:
        return (
            session.query(CaseFileRecord.session_id)
            .filter(CaseFileRecord.owner_user_id == owner_user_id)
            .count()
        )


def list_by_session_ids(session_ids: list[str]) -> list[CaseFile]:
    """Several case files by id, in one query, newest-updated first.

    Exists so a list of ids can be turned into a list of NAMES without a
    fetch per row - the shape a team's project list needs. Says nothing
    about access: every caller checks that first, because this will
    happily return any id it is given.
    """
    if not session_ids:
        return []
    with get_session() as session:
        records = (
            session.query(CaseFileRecord)
            .filter(CaseFileRecord.session_id.in_(session_ids))
            .order_by(CaseFileRecord.updated_at.desc())
            .all()
        )
        return [_to_case_file(record) for record in records]


def list_flagged_for_review(owner_user_id: str, extra_session_ids: list[str]) -> list[CaseFile]:
    """Every case file needing human review that this account is
    responsible for: its own, plus the given (shared-with-it) ones.

    Filters on the `requires_review` column in SQL. The queue previously
    loaded every owned case file AND issued one lookup per grant, then
    threw away the ones that were not flagged - O(all your projects) to
    answer a question about a handful of them.
    """
    with get_session() as session:
        conditions = [CaseFileRecord.owner_user_id == owner_user_id]
        if extra_session_ids:
            conditions.append(CaseFileRecord.session_id.in_(extra_session_ids))
        records = (
            session.query(CaseFileRecord)
            .filter(CaseFileRecord.requires_review.is_(True), or_(*conditions))
            .order_by(CaseFileRecord.updated_at.asc())
            .all()
        )
        return [_to_case_file(record) for record in records]


def delete(session_id: str) -> bool:
    """Removes one case file. Returns whether it existed.

    Callers are responsible for the conversation transcript that belongs to
    it (app/message_store.py's delete_for_session) - the two are separate
    tables with no DB-level cascade, deliberately: the transcript store is
    its own seam, and a silent ON DELETE CASCADE would make "what else does
    deleting a project destroy?" invisible at the call site.
    """
    with get_session() as session:
        record = session.get(CaseFileRecord, session_id)
        if record is None:
            return False
        session.delete(record)
        session.commit()
        return True


def delete_all() -> None:
    """Test-only helper to reset store state between test runs."""
    with get_session() as session:
        session.query(CaseFileRecord).delete()
        session.commit()
