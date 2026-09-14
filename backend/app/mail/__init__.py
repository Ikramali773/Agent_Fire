"""Sending mail, and everything this product sends.

Nothing was ever emailed. That was survivable while the only thing with a
link was password reset - documented as "only works for someone who can
read the server log" rather than papered over - but three features shipped
since that all depend on somebody being told something:

  * a password reset link has to reach a mailbox to be worth anything;
  * a reviewer invite link had to be copied by the owner and passed on by
    hand, so the reviewer only knew about it if someone said so;
  * a case assigned to a colleague, with a due date, told that colleague
    nothing at all - they had to come and look.

`app/auth/delivery.py`'s single-method protocol has grown into the Mailer
below. It is still one small interface with a swappable implementation,
and the default is still one that writes where an operator can find it
rather than pretending to send.

**A deployment with no SMTP configured still sends nothing.** That is the
honest default (see `backend/README.md`): the alternative - failing
requests because mail is not set up - would break password reset, invites
and assignment for anyone who has not configured it, which is worse than
telling them plainly that nothing went out.
"""

from app.mail.messages import Message
from app.mail import sender  # noqa: F401
from app.mail.sender import (
    LoggingMailer,
    Mailer,
    SmtpMailer,
    get_mailer,
    mailer_from_environment,
    set_mailer,
)

__all__ = [
    "sender",
    "LoggingMailer",
    "Mailer",
    "Message",
    "SmtpMailer",
    "get_mailer",
    "mailer_from_environment",
    "set_mailer",
]
