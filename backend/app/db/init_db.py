from __future__ import annotations

from sqlalchemy import inspect, text

from app.db.models import Base
from app.db.session import get_engine


def create_all_tables() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _add_missing_columns(engine)


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
