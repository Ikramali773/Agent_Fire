"""The rate limiter is shared, not per-worker.

The limiter used to keep its counters in one process's memory. Behind N
workers that made the effective limit N times the configured one - and an
attacker multiplies N simply by opening more connections, which means it
was not really a limit at all. These tests are about that specific
property, not about the window arithmetic (see test_auth_hardening.py's
TestLoginRateLimit for that).
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.auth import rate_limit
from app.auth.rate_limit import DatabaseBackend, InMemoryBackend

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean_counters():
    rate_limit.reset()
    yield
    rate_limit.reset()


def _attempt_in_a_separate_process(key: str, times: int) -> list[str]:
    """Runs `times` attempts against the same database from a FRESH Python
    process - a second worker in every sense that matters here: its own
    memory, its own engine, its own import of the limiter.
    """
    script = textwrap.dedent(
        f"""
        from app.auth import rate_limit
        for _ in range({times}):
            print(rate_limit.check({key!r}))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": os.environ["DATABASE_URL"]},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


class TestTheCounterIsShared:
    def test_a_second_process_sees_attempts_made_by_the_first(self):
        # The heart of it. Before this change the second process started
        # from zero and the attacker simply got a second full allowance.
        for _ in range(rate_limit.MAX_ATTEMPTS):
            assert rate_limit.check("shared-key") is None

        verdicts = _attempt_in_a_separate_process("shared-key", 1)

        assert verdicts != ["None"], "a fresh worker handed out a fresh allowance"

    def test_attempts_spread_across_processes_still_add_up(self):
        # Three from here, three from there: six attempts against a limit
        # of five must be refused however they are divided up.
        for _ in range(3):
            rate_limit.check("split-key")

        verdicts = _attempt_in_a_separate_process("split-key", 3)

        assert "None" not in verdicts[-1:], f"the sixth attempt was allowed: {verdicts}"

    def test_a_process_that_never_saw_the_attempts_still_refuses(self):
        _attempt_in_a_separate_process("elsewhere-key", rate_limit.MAX_ATTEMPTS + 1)

        # This process has no memory of any of that, and must still refuse.
        assert rate_limit.check("elsewhere-key") is not None

    def test_clearing_a_key_clears_it_everywhere(self):
        # A correct password clears the counter. If that only cleared it in
        # one worker, the person who just signed in successfully would
        # still be throttled by the others.
        for _ in range(rate_limit.MAX_ATTEMPTS + 1):
            rate_limit.check("cleared-key")
        rate_limit.reset("cleared-key")

        assert _attempt_in_a_separate_process("cleared-key", 1) == ["None"]


class TestTheTableStaysBounded:
    def test_rows_outside_the_window_are_deleted(self, monkeypatch):
        # A counter, not a log. Without pruning this table would grow by a
        # row per credential attempt forever.
        from app.db.models import RateLimitAttemptRecord
        from app.db.session import get_session

        monkeypatch.setattr(rate_limit, "WINDOW_SECONDS", 0.2)
        for index in range(4):
            rate_limit.check(f"key-{index}")

        import time

        time.sleep(0.25)
        rate_limit.check("later-key")

        with get_session() as session:
            remaining = session.query(RateLimitAttemptRecord).count()
        assert remaining == 1, "old rows across ALL keys should be gone, not just this one's"


class TestTheBackendIsSwappable:
    def test_the_default_is_the_shared_one(self):
        # The in-process backend still exists for tests and single-process
        # use; it must not be what a deployment gets by default.
        assert isinstance(rate_limit.get_backend(), DatabaseBackend)

    def test_an_alternative_backend_is_used_when_set(self):
        # This is the seam a Redis or edge-level limiter drops into
        # without the endpoints changing.
        original = rate_limit.get_backend()
        try:
            rate_limit.set_backend(InMemoryBackend())
            for _ in range(rate_limit.MAX_ATTEMPTS):
                assert rate_limit.check("swapped") is None
            assert rate_limit.check("swapped") is not None
        finally:
            rate_limit.set_backend(original)

    def test_a_broken_backend_lets_the_attempt_through_rather_than_erroring(self, monkeypatch):
        # Both endpoints behind this limiter need the database to do their
        # real job, so a database that cannot serve the limiter cannot
        # serve the login either. Failing closed would turn a limiter
        # problem into an outage while protecting nothing.
        from sqlalchemy.exc import OperationalError

        def broken(*args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("database is gone"))

        monkeypatch.setattr("app.auth.rate_limit.get_session", broken)

        assert DatabaseBackend().check("anything") is None
