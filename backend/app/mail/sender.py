"""Getting a Message to a mailbox.

One small protocol with a swappable implementation, exactly as
`app/auth/delivery.py` had. Two backends ship:

  * `LoggingMailer` (the default) writes the message where an operator can
    find it and sends nothing. It is honest about that in every line it
    writes, because a silent no-op is how people come to believe mail is
    working when it is not.
  * `SmtpMailer` sends over SMTP, configured entirely from the
    environment. `smtplib` is in the standard library, so this adds no
    dependency for a deployment that does not use it.

**Sending never fails a request**, and that is enforced at `send()` below
rather than trusted to each backend: signing up, resetting a password,
inviting a reviewer and assigning a case all have to work whether or not a
mail server is reachable, and an exception here would turn a mail outage
into an application outage. The cost is that a message can be silently
lost, which is why the logging backend exists and why the README says
plainly what an unconfigured deployment does.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.mail.messages import Message

_LOG = logging.getLogger("uvicorn.error")


class Mailer(Protocol):
    def send(self, message: Message) -> None:
        """Delivers `message`. May raise - `sender.send` below contains it."""


class LoggingMailer:
    """The default: writes the message out, sends nothing, says so."""

    def send(self, message: Message) -> None:
        _LOG.warning(
            "MAIL NOT SENT (no SMTP configured - set FIRE_AGENT_SMTP_HOST). "
            "To: %s | Subject: %s\n%s",
            message.to,
            message.subject,
            message.body,
        )


class SmtpMailer:
    """Sends over SMTP.

    STARTTLS by default because a password-reset link in cleartext on the
    wire defeats the point of the link being secret. Set
    FIRE_AGENT_SMTP_TLS=ssl for an implicit-TLS port (465), or =off only
    for a relay on localhost that does not offer TLS at all.
    """

    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        sender: str = "noreply@localhost",
        tls: str = "starttls",
        timeout: int = 10,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.tls = tls
        self.timeout = timeout

    def send(self, message: Message) -> None:
        payload = EmailMessage()
        payload["From"] = self.sender
        payload["To"] = message.to
        payload["Subject"] = message.subject
        payload.set_content(message.body)
        try:
            if self.tls == "ssl":
                with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout) as server:
                    self._authenticate_and_send(server, payload)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:
                    if self.tls != "off":
                        server.starttls()
                    self._authenticate_and_send(server, payload)
        except Exception:
            # Logged here too, where the SMTP detail is, rather than only
            # at the boundary. `sender.send` is what actually guarantees a
            # failure cannot reach the request.
            _LOG.exception("SMTP delivery to %s failed (%s)", message.to, message.subject)

    def _authenticate_and_send(self, server: smtplib.SMTP, payload: EmailMessage) -> None:
        if self.username:
            server.login(self.username, self.password or "")
        server.send_message(payload)


def mailer_from_environment() -> Mailer:
    """The backend this deployment is configured for.

    No FIRE_AGENT_SMTP_HOST means no mail server, which is the default and
    is not an error - it gets the logging backend and a startup warning.
    """
    host = os.environ.get("FIRE_AGENT_SMTP_HOST", "").strip()
    if not host:
        return LoggingMailer()
    return SmtpMailer(
        host=host,
        port=int(os.environ.get("FIRE_AGENT_SMTP_PORT", "587")),
        username=os.environ.get("FIRE_AGENT_SMTP_USER") or None,
        password=os.environ.get("FIRE_AGENT_SMTP_PASSWORD") or None,
        sender=os.environ.get("FIRE_AGENT_MAIL_FROM", f"noreply@{host}"),
        tls=os.environ.get("FIRE_AGENT_SMTP_TLS", "starttls").strip().lower(),
    )


_mailer: Mailer | None = None


def get_mailer() -> Mailer:
    global _mailer
    if _mailer is None:
        _mailer = mailer_from_environment()
    return _mailer


def set_mailer(mailer: Mailer) -> None:
    """Swaps the backend - for a provider, or for a fake in tests."""
    global _mailer
    _mailer = mailer


def send(message: Message, to: str) -> None:
    """Sends `message` to `to`. The one call site everything else uses.

    The never-fail guarantee lives HERE rather than in each backend. It was
    inside SmtpMailer first, which meant the guarantee only held for the
    one backend that remembered it - a custom or future one that raised
    took the request down with it, turning a mail outage into an
    application outage. Caught by a test standing in a deliberately broken
    mailer, which is exactly the shape a real provider SDK failure takes.
    """
    if not to:
        return
    try:
        get_mailer().send(Message(to=to, subject=message.subject, body=message.body))
    except Exception:
        _LOG.exception("Could not send mail to %s (%s)", to, message.subject)
