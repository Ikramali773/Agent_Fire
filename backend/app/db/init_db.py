from __future__ import annotations

import json

from sqlalchemy import inspect, text

from app.db.models import Base
from app.db.session import get_engine


def create_all_tables() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _add_missing_columns(engine)
    _backfill_requires_review(engine)


def _add_missing_columns(engine) -> None:
    """Lightweight, additive-only migration.

    `create_all` above only creates tables that don't exist yet - it never
    alters an existing table, so a column added to a model after a
    database file/instance was first created (e.g. CaseFileRecord's
    owner_user_id, added for Phase 2 accounts) is silently missing from
    any pre-existing database, and every query mentioning it then fails
    with "no such column: case_files.owner_user_id" (hit live against a
    pre-Phase-2 local case_files.db). This adds any column present on a
    model but missing from the live table.

    Not a real migration tool - no renames, drops, type changes, or data
    backfill (see main.py's lifespan docstring for why Alembic hasn't
    been adopted yet). Only ever safe for a nullable column with no
    dependent default/backfill, which is true of every column added this
    way so far; a future non-nullable addition needs a real migration,
    not this.
    """
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            ddl_type = column.type.compile(dialect=engine.dialect)
            with engine.begin() as connection:
                connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'))


def _backfill_requires_review(engine) -> None:
    """Fills in CaseFileRecord.requires_review for rows written before it
    existed.

    Unlike every other column added by _add_missing_columns above, this one
    is NOT safe to leave NULL: it is the filter the review queue runs on, so
    a NULL row is a flagged case that has become invisible - exactly the
    failure the review queue exists to prevent. The value lives inside the
    JSON blob, so it cannot be derived in SQL; this reads only the rows that
    still need it, and does nothing at all once they are done.

    One bounded pass on startup, not a general migration tool. A future
    column needing a backfill deserves a real migration rather than another
    function here.
    """
    inspector = inspect(engine)
    if "case_files" not in inspector.get_table_names():
        return

    with engine.begin() as connection:
        rows = connection.execute(
            text('SELECT session_id, data FROM case_files WHERE requires_review IS NULL')
        ).fetchall()
        for session_id, data in rows:
            payload = json.loads(data) if isinstance(data, str) else (data or {})
            flagged = bool(
                (payload.get("classification_result") or {}).get("require_human_review_flag", False)
            )
            connection.execute(
                text("UPDATE case_files SET requires_review = :flagged WHERE session_id = :session_id"),
                {"flagged": flagged, "session_id": session_id},
            )
