"""Alembic environment.

Two things are deliberately different from the generated default:

1. The database URL comes from `app.db.session`, not from alembic.ini.
   There is exactly one answer to "which database is this?" in this
   product - `DATABASE_URL`, defaulting to a local SQLite file - and a
   second copy in an ini file is a second thing to get wrong, silently,
   in the direction of migrating the wrong database.

2. `render_as_batch` is on. SQLite cannot ALTER a column, so without it
   any migration beyond "add a nullable column" fails on the database
   this project uses for local development and for its entire test suite.
   Batch mode rebuilds the table instead. It is a no-op on Postgres.

3. Logging is configured from alembic.ini ONLY when the `alembic` CLI is
   driving. `logging.config.fileConfig` disables every logger not named in
   the file it reads, and alembic.ini names none of the application's - so
   running migrations in-process at startup silently switched off
   `uvicorn.error`, taking the "running on the development signing key"
   SECURITY warning and uvicorn's request log with it. Found because an
   unrelated test asserting that warning started failing; the test was
   right and the startup path was wrong.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base  # noqa: E402
from app.db.session import database_url, get_engine  # noqa: E402

config = context.config

# app/db/init_db.py sets this to False when the application is driving -
# see (3) above.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """`alembic upgrade --sql`: emits DDL without connecting."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Reuses the application's own engine rather than building a second
    # one, so a test that points DATABASE_URL at a throwaway file gets
    # migrations against THAT file and not the developer's real database.
    connectable = config.attributes.get("connection", None)
    if connectable is not None:
        _run(connectable)
        return
    with get_engine().connect() as connection:
        _run(connection)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
