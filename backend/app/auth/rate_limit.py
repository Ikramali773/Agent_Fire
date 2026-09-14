"""A small fixed-window rate limiter for the login endpoint.

Why it exists: /auth/login had no limit at all, so an attacker could try
passwords against a known email as fast as the network allowed. bcrypt
makes each attempt expensive for the SERVER, which is the wrong way round -
it is a denial-of-service lever as much as it is a brute-force defence.

Deliberately in-process and dependency-free, and honest about what that
means: the counters live in this worker's memory, so they reset on restart
and are NOT shared across workers or instances. Behind several processes
the effective limit is the configured one times the worker count. That is a
large improvement on "no limit" and a poor substitute for a shared store
(Redis) or a limit at the edge - see backend/README.md.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

# Five attempts a minute per key is far more than a person mistyping their
# own password needs, and far less than a brute-force run wants.
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60

_lock = threading.Lock()
_attempts: dict[str, list[float]] = defaultdict(list)


def _prune(timestamps: list[float], now: float) -> list[float]:
    return [stamp for stamp in timestamps if now - stamp < WINDOW_SECONDS]


def check(key: str) -> int | None:
    """Records an attempt against `key`.

    Returns None when it is allowed, or the number of seconds to wait when
    the window is full. The attempt is recorded either way, so hammering a
    blocked key keeps it blocked rather than letting a fixed window be
    walked around by timing requests to its edge.
    """
    now = time.time()
    with _lock:
        timestamps = _prune(_attempts[key], now)
        timestamps.append(now)
        _attempts[key] = timestamps
        if len(timestamps) <= MAX_ATTEMPTS:
            return None
        return max(1, int(WINDOW_SECONDS - (now - timestamps[0])))


def reset(key: str | None = None) -> None:
    """Clears one key (after a successful login) or all of them (tests)."""
    with _lock:
        if key is None:
            _attempts.clear()
        else:
            _attempts.pop(key, None)
