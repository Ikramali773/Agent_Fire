"""Database engine/session setup - product scope §B.10 ("Database:
PostgreSQL - case files, session state, procedural tables, audit log of
source/confidence per field").

DATABASE_URL is read from the environment. Defaults to a local SQLite file
so `pytest` and local dev work with zero setup - Postgres is what a real
deployment should actually point this at (`postgresql+psycopg://...`), and
everything here is written against plain SQLAlchemy types (no Postgres-only
JSONB, etc.) specifically so the same code path is exercised by both, not
just "should work in theory." See backend/README.md for how this was
verified against a real local Postgres instance, not only SQLite.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./case_files.db"


def _make_engine():
    url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


# Module-level singletons, but built through functions (not evaluated at
# import time against a fixed URL) so tests can point DATABASE_URL at a
# throwaway SQLite file before anything touches the database.
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def reset_engine_for_testing() -> None:
    """Drops the cached engine/sessionmaker so a test that changes
    DATABASE_URL (via monkeypatch) gets a fresh connection instead of the
    previous test's cached one.
    """
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
