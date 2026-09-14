"""How a password-reset link reaches the person who asked for it.

This deployment has no mail transport, and self-serve password reset cannot
be done securely without one: the whole point is that only the person
holding the mailbox can use the link, so returning it in the HTTP response
(or showing it to whoever typed the address) would let anyone take over any
account by asking.

So the link is handed to a delivery backend rather than to the caller. The
default writes it to the server log, which is a real pattern for a
development deployment and is useless to an attacker who cannot read the
logs. Wiring a real provider means implementing one method - the endpoints,
the token, its expiry and its single-use semantics do not change.

**Until a real backend is configured, password reset only works for someone
who can read the server log.** That is stated in backend/README.md rather
than papered over.
"""

from __future__ import annotations

import logging
from typing import Protocol

_logger = logging.getLogger("uvicorn.error")


class ResetDelivery(Protocol):
    def send_password_reset(self, email: str, reset_url: str) -> None:
        """Gets the reset link to `email`. Must never return it to the caller."""


class LoggingDelivery:
    """The default. Writes the link where an operator can find it."""

    def send_password_reset(self, email: str, reset_url: str) -> None:
        _logger.warning(
            "PASSWORD RESET for %s (no mail backend configured, so this link is only "
            "reachable from this log): %s",
            email,
            reset_url,
        )


_delivery: ResetDelivery = LoggingDelivery()


def get_delivery() -> ResetDelivery:
    return _delivery


def set_delivery(delivery: ResetDelivery) -> None:
    """Swaps the backend - for a real provider, or for a fake in tests."""
    global _delivery
    _delivery = delivery
