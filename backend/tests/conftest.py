"""Points the whole test suite at a throwaway SQLite file instead of
whatever DATABASE_URL might be set to in the real environment (e.g. the
local Postgres instance used to manually verify app/store.py against a real
Postgres - see backend/README.md). This must run before any test module
imports app.store/app.db, since app/db/session.py caches its engine on first
use - setting the env var at conftest's module level (collected before test
modules) guarantees that ordering.
"""

import os
import tempfile

_tmp_fd, _tmp_path = tempfile.mkstemp(suffix=".db")
os.close(_tmp_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_path}"

from app.db.init_db import create_all_tables  # noqa: E402

create_all_tables()
