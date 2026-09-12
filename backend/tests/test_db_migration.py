"""Regression test for a real bug hit in production: create_all_tables()
only creates NEW tables - it never alters an existing one, so a database
file created before CaseFileRecord.owner_user_id existed (pre-Phase-2 -
accounts) had no such column, and every query touching that table failed
with "no such column: case_files.owner_user_id". app/db/init_db.py's
_add_missing_columns() fixes this by adding any column a model declares
that an existing table is missing, without disturbing existing rows.
"""

import os
import sqlite3
import tempfile

from app.db import session as db_session
from app.db.init_db import create_all_tables


def test_create_all_tables_adds_missing_columns_to_a_pre_existing_table(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        # Simulate a database file created before owner_user_id (and the
        # users table) existed - hand-build the old schema directly with
        # sqlite3, bypassing the current models entirely.
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE case_files (
                session_id VARCHAR PRIMARY KEY,
                data JSON NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
        conn.execute(
            "INSERT INTO case_files (session_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (
                "legacy-session",
                '{"session_id": "legacy-session", "project_name": "Legacy Project"}',
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )
        conn.commit()
        conn.close()

        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
        db_session.reset_engine_for_testing()
        try:
            create_all_tables()

            from app.store import get as store_get

            case_file = store_get("legacy-session")
            assert case_file is not None
            assert case_file.project_name == "Legacy Project"
            assert case_file.owner_user_id is None  # backfilled, not lost
        finally:
            db_session.reset_engine_for_testing()
    finally:
        os.remove(path)
