"""Password hashing - Phase 2 (accounts).

`bcrypt` directly rather than a heavier framework (passlib etc.) - one
well-known, actively maintained C-extension package, no dependency on the
system's `cryptography` install (which this dev sandbox's debian-packaged
copy has broken - see app/auth/tokens.py's docstring for the same issue and
why session tokens are hand-rolled instead of using a JWT library).
"""

from __future__ import annotations

import bcrypt

# bcrypt's own hard limit. Version 5 RAISES on a longer password rather
# than silently truncating it the way older releases did, so an
# unvalidated passphrase from a password manager crashed signup with a 500
# (reproduced). It is a byte limit, not a character one: one emoji is four
# bytes, so a 30-character password can exceed it.
MAX_PASSWORD_BYTES = 72


def password_is_too_long(password: str) -> bool:
    return len(password.encode("utf-8")) > MAX_PASSWORD_BYTES


def hash_password(password: str) -> str:
    """Raises ValueError for a password over bcrypt's byte limit.

    Deliberately NOT truncated here: silently hashing the first 72 bytes
    would mean the rest of someone's passphrase is decorative, and two
    different long passwords would open the same account. The API layer
    rejects it up front (see app/api/auth.py); this is the backstop so no
    future caller can reintroduce the 500.
    """
    if password_is_too_long(password):
        raise ValueError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded"
        )
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    if password_is_too_long(password):
        # Could never have been hashed, so it can never match. Returning
        # False beats letting bcrypt raise on a login attempt.
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # A corrupt/foreign hash format - never a match, never a crash.
        return False
