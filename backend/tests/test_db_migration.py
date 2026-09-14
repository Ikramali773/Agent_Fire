"""Migrations, and the three states a database can be found in.

Alembic owns the schema (backend/migrations/). This covers what
app/db/init_db.py does with the database it is handed: build one from
nothing, apply what is new to one already under Alembic, and - the case
with teeth - adopt one that predates migrations entirely without losing
its data or lying about its schema.

The legacy fixtures here hand-build the old schema with raw sqlite3,
bypassing the current models completely. That is the point: a fixture
built from today's models could not reproduce the bug these guard
against.
"""

import os
import sqlite3
import tempfile
from contextlib import contextmanager

import pytest
from sqlalchemy import inspect, text

from app.db import session as db_session
from alembic.script import ScriptDirectory

from app.db import init_db
from app.db.init_db import create_all_tables, run_migrations
from app.db.models import Base


def head_revision() -> str:
    """Whatever the newest migration is, read from the scripts rather than
    hard-coded - otherwise these tests quietly stop checking anything the
    day a second migration is added."""
    return ScriptDirectory.from_config(init_db.alembic_config()).get_current_head()


@contextmanager
def database_at(path: str):
    """Points the app at `path` for the duration, then restores."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    db_session.reset_engine_for_testing()
    try:
        yield
    finally:
        db_session.reset_engine_for_testing()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        db_session.reset_engine_for_testing()


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # an EMPTY file is not the same as no database
    yield path
    if os.path.exists(path):
        os.remove(path)


def build_pre_alembic_database(path: str) -> None:
    """The oldest schema this project ever shipped: `case_files` and
    nothing else. No users, no conversation history, no grants, no
    reviews, no owner_user_id, no requires_review.
    """
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
    for session_id, name, flagged in [
        ("legacy-flagged", "Legacy Flagged Project", True),
        ("legacy-plain", "Legacy Plain Project", False),
    ]:
        conn.execute(
            "INSERT INTO case_files (session_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (
                session_id,
                '{"session_id": "%s", "project_name": "%s", '
                '"classification_result": {"require_human_review_flag": %s}}'
                % (session_id, name, "true" if flagged else "false"),
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )
    conn.commit()
    conn.close()


def table_names(path: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def stamped_revision(path: str) -> str | None:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        return rows[0][0] if rows else None
    finally:
        conn.close()


# --- 1. Nothing there ------------------------------------------------


def test_an_empty_database_gets_the_whole_schema(db_path):
    with database_at(db_path):
        run_migrations()

    present = table_names(db_path)
    for table in Base.metadata.sorted_tables:
        assert table.name in present, f"{table.name} was never created"
    assert stamped_revision(db_path) == head_revision()


def test_running_migrations_twice_changes_nothing(db_path):
    # Migrations run on every boot by default, so "idempotent" is not a
    # nicety here - it is the thing that makes that safe.
    with database_at(db_path):
        run_migrations()
        before = stamped_revision(db_path)
        run_migrations()
        assert stamped_revision(db_path) == before


# --- 2. Already under Alembic ----------------------------------------


def test_an_alembic_database_is_never_reconciled_a_second_time(db_path, monkeypatch):
    # Adoption is a one-shot path, and re-running it on an already-versioned
    # database would re-stamp it at the BASELINE - silently undoing every
    # migration applied since. Today head and baseline are the same
    # revision, so comparing version numbers afterwards would prove
    # nothing; watch for the call itself instead.
    with database_at(db_path):
        run_migrations()

        called = []
        monkeypatch.setattr(init_db, "_reconcile_legacy", lambda conn: called.append(conn))
        run_migrations()

        assert called == []
    assert stamped_revision(db_path) == head_revision()


def test_a_legacy_database_is_reconciled_exactly_once(db_path, monkeypatch):
    build_pre_alembic_database(db_path)
    calls = []
    real = init_db._reconcile_legacy
    monkeypatch.setattr(
        init_db, "_reconcile_legacy", lambda conn: (calls.append(conn), real(conn))[1]
    )
    with database_at(db_path):
        run_migrations()
        run_migrations()
        run_migrations()
    assert len(calls) == 1


# --- 3. Predates Alembic ---------------------------------------------


def test_a_legacy_database_keeps_its_rows(db_path):
    build_pre_alembic_database(db_path)
    with database_at(db_path):
        create_all_tables()

        from app.store import get as store_get

        case_file = store_get("legacy-flagged")
        assert case_file is not None
        assert case_file.project_name == "Legacy Flagged Project"
        assert case_file.owner_user_id is None  # column added, row kept


def test_a_legacy_database_gains_the_tables_it_never_had(db_path):
    # The bug this caught for real: the first version of the adoption path
    # stamped the database at the baseline and left seven tables missing,
    # so the stamp asserted a schema that was not there and the first
    # query against conversation_messages failed.
    build_pre_alembic_database(db_path)
    assert table_names(db_path) == {"case_files"}

    with database_at(db_path):
        create_all_tables()

    present = table_names(db_path)
    for table in Base.metadata.sorted_tables:
        assert table.name in present, f"{table.name} missing after adoption"


def test_a_legacy_database_ends_up_at_head_having_walked_every_revision(db_path):
    # Not stamped at the baseline and left there: it takes the ordinary
    # upgrade path through every revision in order, which is what makes a
    # later migration - schema or data - apply to it at all.
    build_pre_alembic_database(db_path)
    with database_at(db_path):
        create_all_tables()
    assert stamped_revision(db_path) == head_revision()


def test_a_legacy_flagged_case_stays_visible_to_the_review_queue(db_path):
    # requires_review is the column the review queue filters on, and it
    # lives inside the JSON blob, so it cannot be derived in SQL. Left
    # NULL, a flagged case simply disappears from the queue - exactly the
    # failure the queue exists to prevent.
    build_pre_alembic_database(db_path)
    with database_at(db_path):
        create_all_tables()
        engine = db_session.get_engine()
        with engine.connect() as connection:
            rows = dict(
                connection.execute(
                    text("SELECT session_id, requires_review FROM case_files")
                ).fetchall()
            )
    assert rows["legacy-flagged"] == 1
    assert rows["legacy-plain"] == 0


def test_an_adopted_database_serves_the_endpoints_its_schema_never_had(db_path):
    # The real proof: not "the tables exist" but "the application works".
    build_pre_alembic_database(db_path)
    with database_at(db_path):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            # A table the legacy database did not have at all.
            assert client.get("/case-files/legacy-flagged/messages").json() == []
            # An entire feature it predates.
            signup = client.post(
                "/auth/signup", json={"email": "after@example.com", "password": "password-123"}
            )
            assert signup.status_code == 201
            token = signup.json()["access_token"]
            queue = client.get(
                "/users/me/review-queue", headers={"Authorization": f"Bearer {token}"}
            )
            assert queue.status_code == 200
            # And the pre-existing row is still there and still readable.
            assert client.get("/case-files/legacy-plain").json()["project_name"] == (
                "Legacy Plain Project"
            )


def test_adoption_does_not_run_on_a_database_that_is_merely_empty(db_path):
    # An empty database has no tables, so it must take the ordinary
    # upgrade path and end up at head - not be "adopted" and pinned at the
    # baseline forever.
    with database_at(db_path):
        run_migrations()
        engine = db_session.get_engine()
        with engine.connect() as connection:
            assert "alembic_version" in inspect(connection).get_table_names()


def test_auto_migrate_can_be_turned_off(db_path, monkeypatch):
    # A multi-worker deployment wants migrating to be a deploy step, not
    # something N workers race to do on boot.
    monkeypatch.setenv("FIRE_AGENT_AUTO_MIGRATE", "0")
    with database_at(db_path):
        create_all_tables()
    # Nothing was created at all - not an empty schema, no database file.
    assert not os.path.exists(db_path)

    # And the switch is off only when asked: the default is on.
    monkeypatch.delenv("FIRE_AGENT_AUTO_MIGRATE")
    with database_at(db_path):
        create_all_tables()
    assert stamped_revision(db_path) == head_revision()


def test_a_legacy_database_gets_tables_from_migrations_after_the_baseline(db_path):
    """The flaw the FIRST post-baseline migration exposed.

    Adoption used to build today's whole schema with `create_all` and then
    stamp the database at the baseline. That is a contradiction: the
    database had tables from today's models while its version claimed
    "baseline", so the next migration ran against a table that already
    existed and blew up with "table rate_limit_attempts already exists".
    Had it not blown up it would have been worse - a later migration
    silently skipped.

    So: a legacy database must end up holding the tables introduced AFTER
    the baseline, and must have got them by running those migrations.
    """
    build_pre_alembic_database(db_path)
    with database_at(db_path):
        create_all_tables()

    present = table_names(db_path)
    baseline_tables = {"case_files", "users"}
    later_tables = {
        table.name for table in Base.metadata.sorted_tables if table.name not in baseline_tables
    }
    assert later_tables <= present
    assert stamped_revision(db_path) == head_revision()


def test_the_baseline_leaves_a_table_that_already_exists_alone(db_path):
    # It creates only what is absent. If it dropped and recreated
    # `case_files` instead, a legacy database would lose every project on
    # the first boot after upgrading.
    build_pre_alembic_database(db_path)
    with database_at(db_path):
        run_migrations()

        from app.store import get as store_get

        assert store_get("legacy-plain") is not None
        assert store_get("legacy-flagged") is not None


# --- Drift -----------------------------------------------------------


def test_the_migrations_still_match_the_models(db_path):
    """The one guard that keeps this honest over time.

    Migrations are only worth having if they describe the models. The way
    that stops being true is quiet: someone adds a column to
    app/db/models.py, the test suite passes (its database is built from
    `upgrade head`... which is now missing the column, so it does not),
    or worse, built from create_all and never notices. `alembic check`
    autogenerates against the live database and fails if anything would
    be emitted.

    When this fails, the fix is to generate the migration, not to edit
    this test:  alembic revision --autogenerate -m "what changed"
    """
    from alembic import command
    from alembic.util.exc import AutogenerateDiffsDetected

    with database_at(db_path):
        run_migrations()
        try:
            command.check(init_db.alembic_config())
        except AutogenerateDiffsDetected as diffs:  # pragma: no cover - the failure path
            pytest.fail(
                "app/db/models.py has changed without a migration. Run:\n"
                "  cd backend && alembic revision --autogenerate -m \"what changed\"\n"
                f"Alembic reports: {diffs}"
            )
