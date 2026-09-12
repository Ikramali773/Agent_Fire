"""Password hashing - Phase 2 (accounts).

`bcrypt` directly rather than a heavier framework (passlib etc.) - one
well-known, actively maintained C-extension package, no dependency on the
system's `cryptography` install (which this dev sandbox's debian-packaged
copy has broken - see app/auth/tokens.py's docstring for the same issue and
why session tokens are hand-rolled instead of using a JWT library).
"""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # A corrupt/foreign hash format - never a match, never a crash.
        return False
