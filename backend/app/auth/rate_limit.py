"""Rate limiting for the credential endpoints.

Why it exists: /auth/login had no limit at all, so an attacker could try
passwords against a known email as fast as the network allowed. bcrypt
makes each attempt expensive for the SERVER, which is the wrong way round -
it is a denial-of-service lever as much as it is a brute-force defence.
/auth/password-reset/request shares the counter shape so it cannot be used
to flood an inbox or to fish for addresses.

The limiter was in-process, and honest about what that cost: counters lived
in one worker's memory, so they reset on restart and were not shared, and
behind N workers the effective limit was N times the configured one. A
limit an attacker can multiply by starting more connections is not really a
limit.

It is now backed by the database - which this product already requires, so
nothing new has to be operated - and shared by every worker and every
instance pointed at it. The backend is swappable (see `set_backend`): the
in-memory one is kept for tests and single-process use, and a Redis or
edge-level limiter can drop in without touching the endpoints.

Window semantics are a SLIDING window, not a fixed one: a fixed window can
be walked around by timing requests to its edge, which doubles the real
allowance for anyone who bothers.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from app.db.models import RateLimitAttemptRecord
from app.db.session import get_session

_LOG = logging.getLogger("uvicorn.error")

# Five attempts a minute per key is far more than a person mistyping their
# own password needs, and far less than a brute-force run wants.
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60

# The credential endpoints are not the expensive ones. A chat turn calls an
# LLM and a document upload runs the OCR pipeline; both cost real money and
# real CPU per request, and both were completely unlimited - so one script,
# or one runaway client, could spend an account's LLM budget or pin every
# worker on OCR. These are deliberately generous: they are a ceiling on
# runaway use, not a throttle a person doing the work would ever feel.
#
# A conversation is a person typing. Twenty turns a minute is faster than
# anyone reads a reply.
CHAT_MAX_ATTEMPTS = 20
# OCR is the most expensive thing this product does per request, and
# uploading ten documents a minute is already a bulk operation.
UPLOAD_MAX_ATTEMPTS = 10


class RateLimitBackend(Protocol):
    def check(self, key: str, max_attempts: int = MAX_ATTEMPTS) -> int | None:
        """Records an attempt against `key`.

        Returns None when it is allowed, or the number of seconds to wait
        when the window is full. The attempt is recorded either way, so
        hammering a blocked key keeps it blocked.
        """

    def reset(self, key: str | None = None) -> None:
        """Clears one key (after a successful login) or all of them."""


class InMemoryBackend:
    """Counters in this process's memory.

    Kept for tests and for anyone deliberately running a single process.
    NOT shared across workers - which is the whole reason it is no longer
    the default.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_attempts: int = MAX_ATTEMPTS) -> int | None:
        now = time.time()
        with self._lock:
            recent = [stamp for stamp in self._attempts[key] if now - stamp < WINDOW_SECONDS]
            recent.append(now)
            self._attempts[key] = recent
            if len(recent) <= max_attempts:
                return None
            return max(1, int(WINDOW_SECONDS - (now - recent[0])))

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._attempts.clear()
            else:
                self._attempts.pop(key, None)


class DatabaseBackend:
    """Counters in the database, so every worker sees the same ones.

    One row per attempt, which is what makes the window slide: the oldest
    row still inside the window is what the retry-after is measured from.
    Rows outside the window are deleted on every check, so the table holds
    at most the last minute of credential attempts across the whole
    deployment - it does not grow.

    A failure here is logged and ALLOWED through rather than raised. Both
    endpoints behind this limiter need the database to do their actual job
    (verify a password, look up an account), so a database that cannot
    serve the limiter cannot serve the login either - failing closed would
    turn a limiter problem into an outage without protecting anything.
    """

    def check(self, key: str, max_attempts: int = MAX_ATTEMPTS) -> int | None:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=WINDOW_SECONDS)
        try:
            with get_session() as session:
                # Global, not just this key: keeps the table bounded
                # without a separate sweep. Indexed on created_at, and the
                # table only ever holds a minute of rows.
                session.query(RateLimitAttemptRecord).filter(
                    RateLimitAttemptRecord.created_at < cutoff
                ).delete(synchronize_session=False)
                session.add(RateLimitAttemptRecord(key=key, created_at=now))
                session.commit()

                stamps = [
                    row[0]
                    for row in session.query(RateLimitAttemptRecord.created_at)
                    .filter(RateLimitAttemptRecord.key == key)
                    .order_by(RateLimitAttemptRecord.created_at)
                    .all()
                ]
        except SQLAlchemyError:
            _LOG.exception("Rate limiter unavailable - allowing the attempt through.")
            return None

        if len(stamps) <= max_attempts:
            return None
        oldest = _as_utc(stamps[0])
        return max(1, int(WINDOW_SECONDS - (now - oldest).total_seconds()))

    def reset(self, key: str | None = None) -> None:
        try:
            with get_session() as session:
                query = session.query(RateLimitAttemptRecord)
                if key is not None:
                    query = query.filter(RateLimitAttemptRecord.key == key)
                query.delete(synchronize_session=False)
                session.commit()
        except SQLAlchemyError:
            _LOG.exception("Could not clear rate limiter counters.")


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; every row here is written in UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


_backend: RateLimitBackend = DatabaseBackend()


def get_backend() -> RateLimitBackend:
    return _backend


def set_backend(backend: RateLimitBackend) -> None:
    """Swaps the backend - for Redis, for an edge limiter, or for a test."""
    global _backend
    _backend = backend


def check(key: str, max_attempts: int = MAX_ATTEMPTS) -> int | None:
    return _backend.check(key, max_attempts)


def reset(key: str | None = None) -> None:
    _backend.reset(key)
