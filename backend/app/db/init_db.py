"""Bringing a database to the schema the running code expects.

Alembic owns the schema (migrations/). This module is the glue: it decides
what to do with the database it finds, and it exists because "run the
migrations" is not one case but three.

  1. **Empty database** - no tables at all. `alembic upgrade head` builds
     everything. This is a fresh developer checkout and every test run.
  2. **Already under Alembic** - it has an `alembic_version` row.
     `alembic upgrade head` applies whatever is new. The ordinary case.
  3. **Predates Alembic** - it has our tables but no `alembic_version`,
     because it was created by `Base.metadata.create_all()` back when this
     project had no migrations. Running `upgrade head` here would try to
     CREATE TABLE over live data and fail. It has to be reconciled to the
     baseline's shape and then STAMPED, which is what `_adopt_legacy`
     below does.

Case 3 is the only interesting one, and it is not hypothetical: the
developer's own `case_files.db` is such a database, as is any deployment
made before this commit. It gets exactly one shot at being adopted - after
that it is an ordinary case 2 database forever.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from app.db.models import Base
from app.db.session import get_engine

_LOG = logging.getLogger("uvicorn.error")

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

def alembic_config(connection=None) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    # Keep Alembic's hands off this process's logging. fileConfig() disables
    # every logger not named in the ini it reads, and alembic.ini names none
    # of ours - so migrating in-process at startup silently switched off
    # `uvicorn.error`, which is where the "running on the development
    # signing key" SECURITY warning and uvicorn's request log both go. The
    # `alembic` CLI passes no attributes and so still configures its own.
    config.attributes["configure_logger"] = False
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def run_migrations() -> None:
    """Brings the database to `head`, whatever state it is in."""
    engine = get_engine()
    with engine.begin() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
        if current is None and _has_legacy_tables(connection):
            _reconcile_legacy(connection)
    command.upgrade(alembic_config(), "head")


def create_all_tables() -> None:
    """Startup entry point, kept under its old name so main.py's lifespan
    reads the same.

    Migrations run on boot by default so a developer checkout and the test
    suite stay zero-setup. Set `FIRE_AGENT_AUTO_MIGRATE=0` where migrating
    is a deploy step rather than a startup side effect - which is what a
    multi-worker deployment wants, since N workers booting together would
    otherwise race to apply the same revision.
    """
    if os.environ.get("FIRE_AGENT_AUTO_MIGRATE", "1").strip().lower() in {"0", "false", "no"}:
        _LOG.info("FIRE_AGENT_AUTO_MIGRATE is off - skipping migrations. Run `alembic upgrade head`.")
        return
    run_migrations()


def _has_legacy_tables(connection) -> bool:
    """Whether this database holds our tables without holding a version."""
    present = set(inspect(connection).get_table_names())
    return any(table.name in present for table in Base.metadata.sorted_tables)


def _reconcile_legacy(connection) -> None:
    """Adds the columns a pre-Alembic database is missing, and backfills the
    one that cannot be left NULL.

    Runs BEFORE the baseline migration, and does not create tables or stamp
    anything - the migrations do both. It exists because the baseline
    creates only tables that are absent, so it never touches the
    `case_files` a legacy database already has, and a column added to that
    model after the database was created would stay missing. Every query
    mentioning it then fails ("no such column: case_files.owner_user_id" -
    hit for real against a pre-Phase-2 local database).

    Deliberately additive-only: no renames, drops, or type changes. Those
    are what migrations are for, and from this point on there IS a
    migration path, so nothing new should ever be added here.
    """
    _LOG.info("Database predates Alembic - reconciling it before migrating.")
    _add_missing_columns(connection)
    _backfill_requires_review(connection)


def _add_missing_columns(connection) -> None:
    inspector = inspect(connection)
    present = set(inspector.get_table_names())
    dialect = connection.engine.dialect
    for table in Base.metadata.sorted_tables:
        if table.name not in present:
            # Absent entirely - the baseline migration creates it in full,
            # indexes and all, a moment from now.
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl_type = column.type.compile(dialect=dialect)
            connection.execute(
                text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}')
            )


def _backfill_requires_review(connection) -> None:
    """Fills in `case_files.requires_review` for rows written before it
    existed.

    Unlike every other column added above, this one is NOT safe to leave
    NULL: it is the filter the review queue runs on, so a NULL row is a
    flagged case that has become invisible - exactly the failure the review
    queue exists to prevent. The value lives inside the JSON blob, so it
    cannot be derived in SQL.
    """
    if "case_files" not in set(inspect(connection).get_table_names()):
        return
    rows = connection.execute(
        text("SELECT session_id, data FROM case_files WHERE requires_review IS NULL")
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
