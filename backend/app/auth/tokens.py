"""Signed session tokens - Phase 2 (accounts).

Hand-rolled instead of a JWT library on purpose: this dev sandbox's
system-installed `cryptography` package (pulled in by every JWT library
for its non-HMAC algorithms) is broken - `import jwt` crashes with a
pyo3/cffi panic, confirmed directly in this environment (a Debian-packaged
`cryptography` build pip can't cleanly replace: "Cannot uninstall
cryptography ... RECORD file not found"). Rather than depend on an
environment-specific `pip install --ignore-installed` workaround to shadow
it, this uses only the standard library - `hmac`/`hashlib` give exactly
what a same-service session token needs (integrity, not encryption; no
multi-service key rotation or asymmetric verification requirement exists
yet). Same two-part shape as a JWT (payload + signature) so swapping to a
real JWT library later, if a use case genuinely needs one of its other
features, doesn't require redesigning the token format's callers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

# MUST be overridden via FIRE_AGENT_AUTH_SECRET in any real deployment -
# this default only exists so local dev/tests work with zero setup, the
# same pattern as GROQ_API_KEY/ANTHROPIC_API_KEY being optional for the
# deterministic parts of the app (see README.md).
_SECRET = os.environ.get("FIRE_AGENT_AUTH_SECRET", "dev-insecure-secret-change-in-production")
_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded)


def _sign(payload_b64: str) -> str:
    return hmac.new(_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()


def create_token(user_id: str) -> str:
    payload = {"sub": user_id, "iat": int(time.time())}
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_token(token: str) -> str | None:
    """Returns the user_id the token was issued for, or None if it's
    missing, malformed, tampered with, or expired.
    """
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError:
        return None

    if not hmac.compare_digest(signature, _sign(payload_b64)):
        return None

    try:
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, UnicodeDecodeError):
        return None

    issued_at = payload.get("iat")
    if not isinstance(issued_at, int) or time.time() - issued_at > _TOKEN_TTL_SECONDS:
        return None

    user_id = payload.get("sub")
    return user_id if isinstance(user_id, str) else None
