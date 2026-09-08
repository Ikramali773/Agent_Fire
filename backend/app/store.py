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

from app.db.models import CaseFileRecord
from app.db.session import get_session
from app.models.case_file import CaseFile


def save(case_file: CaseFile) -> CaseFile:
    with get_session() as session:
        record = session.get(CaseFileRecord, case_file.session_id)
        payload = case_file.model_dump(mode="json")
        now = datetime.now(timezone.utc)
        if record is None:
            record = CaseFileRecord(
                session_id=case_file.session_id,
                data=payload,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
        else:
            record.data = payload
            record.updated_at = now
        session.commit()
    return case_file


def get(session_id: str) -> CaseFile | None:
    with get_session() as session:
        record = session.get(CaseFileRecord, session_id)
        if record is None:
            return None
        return CaseFile.model_validate(record.data)


def delete_all() -> None:
    """Test-only helper to reset store state between test runs."""
    with get_session() as session:
        session.query(CaseFileRecord).delete()
        session.commit()
