"""The messages this product sends, and their wording.

Kept apart from the transport so what goes out can be read, reviewed and
tested without a mail server in sight - and so the wording, which is the
part that can quietly break a security property, sits in one place.

Plain text only. An HTML mail would mean a second copy of every message to
keep in step, and none of these say anything a paragraph cannot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Prefixed so a person can filter them, and so a message from this product
# is recognisable in an inbox that has never seen one before.
SUBJECT_PREFIX = "[Fire Safety NOC]"


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    body: str


def password_reset(reset_url: str) -> Message:
    """Deliberately says nothing about the account beyond that someone asked.

    A reset mail reaches a mailbox that may be shared, forwarded or
    breached, and the request endpoint answers identically whether or not
    the address has an account - so this must not confirm one exists to
    anyone who reads it in passing. It also says what to do if it was not
    you, because that is the one case where the mail is a warning.
    """
    return Message(
        to="",
        subject=f"{SUBJECT_PREFIX} Reset your password",
        body=(
            "Someone asked to reset the password for this address.\n\n"
            f"{reset_url}\n\n"
            "The link works once and expires in an hour. Using it signs out every "
            "device currently signed in to the account.\n\n"
            "If this wasn't you, you can ignore this message - nothing has changed, "
            "and whoever asked cannot see this mail."
        ),
    )


def reviewer_invite(project_name: str, invited_by_email: str, invite_url: str) -> Message:
    """Names the project and who sent it, and nothing about the building.

    Same restraint as the invite preview endpoint: whoever reads this has
    not accepted yet, and may not be the person it was meant for.
    """
    return Message(
        to="",
        subject=f"{SUBJECT_PREFIX} {invited_by_email} asked you to review {project_name}",
        body=(
            f"{invited_by_email} has asked you to review a fire-safety case file "
            f"for {project_name}.\n\n"
            f"{invite_url}\n\n"
            "The link works once and expires in two weeks. You'll need an account to "
            "accept it - a review has to be attributable to a person.\n\n"
            "Accepting lets you read the case file, download its handoff pack and record "
            "a verdict. It does not let you change any fact, which is what makes the "
            "verdict worth recording."
        ),
    )


def case_assigned(
    project_name: str,
    assigned_by_email: str,
    app_url: str,
    due_at: datetime | None = None,
    note: str = "",
) -> Message:
    """Tells someone a case is theirs. Without this they had to come and look.

    The due date is described the way the rest of the product describes it -
    as a date somebody chose, not a deadline the system enforces - because
    it does not enforce one.
    """
    when = f" It's marked due {due_at.date().isoformat()}." if due_at else ""
    because = f"\n\nThey added: “{note}”" if note.strip() else ""
    return Message(
        to="",
        subject=f"{SUBJECT_PREFIX} {project_name} is waiting for your review",
        body=(
            f"{assigned_by_email} has asked you to review {project_name}.{when}"
            f"{because}\n\n"
            f"{app_url}\n\n"
            "It's in your review queue. A due date here is a note between the people "
            "involved - nothing in this system acts when one passes."
        ),
    )
