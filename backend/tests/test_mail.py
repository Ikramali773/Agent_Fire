"""Mail: what goes out, and what must never.

Nothing was ever emailed before this. Three shipped features depended on
somebody being told something out of band - a reset link that only reached
the server log, an invite the owner had to copy and pass on by hand, and
an assignment that told the assignee nothing at all.

Most of what follows is about the wording, because in these three messages
the wording IS the security property: a reset mail that confirmed an
account exists would undo the whole point of the request endpoint
answering identically either way.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import assignment_store, invite_store, mail, organisation_store
from app.auth import rate_limit
from app.auth.user_store import delete_all as delete_all_users
from app.mail import LoggingMailer, Message, SmtpMailer, messages
from app.mail.sender import mailer_from_environment
from app.main import app
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


class Mailbox:
    def __init__(self) -> None:
        self.sent: list[Message] = []

    def send(self, message: Message) -> None:
        self.sent.append(message)


@pytest.fixture
def mailbox():
    box = Mailbox()
    mail.set_mailer(box)
    yield box
    mail.set_mailer(LoggingMailer())


@pytest.fixture(autouse=True)
def _reset():
    delete_all_case_files()
    delete_all_users()
    invite_store.delete_all()
    organisation_store.delete_all()
    assignment_store.delete_all()
    rate_limit.reset()


def account(email: str) -> dict:
    body = client.post("/auth/signup", json={"email": email, "password": "correct-horse"}).json()
    return {"headers": {"Authorization": f"Bearer {body['access_token']}"}, "id": body["user"]["id"]}


class TestWhatTheMessagesSay:
    def test_a_reset_mail_never_confirms_the_account_exists(self):
        # The request endpoint answers identically whether or not the
        # address has an account, precisely so it cannot be used to ask
        # who uses the product. A mail that said "your account" would give
        # that away to anyone who reads it over a shoulder.
        body = messages.password_reset("https://example.test/?reset=tok").body.lower()

        assert "someone asked" in body
        assert "your account" not in body

    def test_a_reset_mail_says_what_to_do_if_it_was_not_you(self):
        # The one case where this mail is a warning rather than a favour.
        assert "wasn't you" in messages.password_reset("https://example.test/?reset=t").body

    def test_a_reset_mail_states_the_expiry_and_the_single_use(self):
        body = messages.password_reset("https://example.test/?reset=t").body
        assert "once" in body and "hour" in body

    def test_an_invite_says_nothing_about_the_building(self):
        # Whoever reads this has not accepted yet and may not be the
        # person it was meant for - the same restraint the unauthenticated
        # preview endpoint applies.
        message = messages.reviewer_invite("St Mary Hospital", "owner@example.com", "https://x/?invite=t")

        assert "St Mary Hospital" in message.subject
        assert "owner@example.com" in message.subject
        for leaked in ("occupancy", "height", "sprinkler", "storey"):
            assert leaked not in message.body.lower()

    def test_an_invite_says_the_reviewer_cannot_change_anything(self):
        # It is what makes the verdict worth recording, so it is said up
        # front rather than discovered after accepting.
        body = messages.reviewer_invite("P", "o@example.com", "https://x").body
        assert "does not let you change any fact" in body

    def test_an_assignment_does_not_pretend_the_due_date_is_enforced(self):
        # The rest of the product is careful to call a due date advisory.
        # A mail that said "you must" would undo that in one line.
        due = datetime(2026, 7, 1, tzinfo=timezone.utc)
        body = messages.case_assigned("P", "lead@example.com", "https://x", due_at=due).body

        assert "2026-07-01" in body
        assert "nothing in this system acts when one passes" in body

    def test_an_assignment_without_a_due_date_mentions_none(self):
        body = messages.case_assigned("P", "lead@example.com", "https://x").body
        assert "due" not in body.split("A due date here")[0]


class TestWhatActuallyGetsSent:
    def test_a_reset_request_mails_the_account_s_own_address(self, mailbox):
        account("owner@example.com")

        client.post("/auth/password-reset/request", json={"email": "owner@example.com"})

        assert [message.to for message in mailbox.sent] == ["owner@example.com"]
        assert "?reset=" in mailbox.sent[0].body

    def test_an_address_with_no_account_is_mailed_nothing(self, mailbox):
        client.post("/auth/password-reset/request", json={"email": "nobody@example.com"})

        assert mailbox.sent == []

    def test_inviting_a_reviewer_mails_them_the_link(self, mailbox):
        # Before this the owner had to copy the link and tell the reviewer
        # out of band that something was waiting.
        owner = account("owner@example.com")
        session_id = client.post("/case-files", json=None, headers=owner["headers"]).json()["session_id"]

        response = client.post(
            f"/case-files/{session_id}/invites",
            json={"email": "consultant@example.com"},
            headers=owner["headers"],
        )

        assert [message.to for message in mailbox.sent] == ["consultant@example.com"]
        # Still returned to the owner as well - that is what makes invites
        # work at all on a deployment with no mail server.
        assert response.json()["invite_url"] in mailbox.sent[0].body

    def test_assigning_a_case_tells_the_assignee(self, mailbox):
        owner = account("owner@example.com")
        member = account("member@example.com")
        org_id = client.post(
            "/organisations", json={"name": "Team"}, headers=owner["headers"]
        ).json()["id"]
        client.post(
            f"/organisations/{org_id}/members",
            json={"email": "member@example.com"},
            headers=owner["headers"],
        )
        session_id = client.post("/case-files", json=None, headers=owner["headers"]).json()["session_id"]
        client.post(
            f"/organisations/{org_id}/case-files",
            json={"session_id": session_id},
            headers=owner["headers"],
        )
        mailbox.sent.clear()

        client.post(
            f"/case-files/{session_id}/assignment",
            json={
                "assigned_to_user_id": member["id"],
                "due_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "note": "Check the risers",
            },
            headers=owner["headers"],
        )

        assert [message.to for message in mailbox.sent] == ["member@example.com"]
        assert "Check the risers" in mailbox.sent[0].body

    def test_unassigning_mails_nobody(self, mailbox):
        # There is no news in "you are not doing this any more" worth an
        # inbox.
        owner = account("owner@example.com")
        session_id = client.post("/case-files", json=None, headers=owner["headers"]).json()["session_id"]
        client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": None},
            headers=owner["headers"],
        )

        assert mailbox.sent == []


class TestTheTransport:
    def test_no_smtp_configured_gets_the_logging_backend(self, monkeypatch):
        # The default, and not an error: failing to start would break
        # password reset, invites and assignment for anyone who has not
        # configured a server.
        monkeypatch.delenv("FIRE_AGENT_SMTP_HOST", raising=False)

        assert isinstance(mailer_from_environment(), LoggingMailer)

    def test_smtp_host_switches_to_the_real_backend(self, monkeypatch):
        monkeypatch.setenv("FIRE_AGENT_SMTP_HOST", "smtp.example.test")
        monkeypatch.setenv("FIRE_AGENT_SMTP_PORT", "2525")
        monkeypatch.setenv("FIRE_AGENT_MAIL_FROM", "noc@example.test")

        mailer = mailer_from_environment()

        assert isinstance(mailer, SmtpMailer)
        assert (mailer.host, mailer.port, mailer.sender) == (
            "smtp.example.test",
            2525,
            "noc@example.test",
        )

    def test_starttls_is_the_default(self, monkeypatch):
        # A reset link in cleartext on the wire defeats the point of the
        # link being secret.
        monkeypatch.setenv("FIRE_AGENT_SMTP_HOST", "smtp.example.test")
        monkeypatch.delenv("FIRE_AGENT_SMTP_TLS", raising=False)

        assert mailer_from_environment().tls == "starttls"

    def test_a_send_failure_never_raises(self):
        # A mail outage must not become an application outage.
        mailer = SmtpMailer(host="this-host-does-not-exist.invalid", timeout=1)

        mailer.send(Message(to="a@example.com", subject="s", body="b"))

    def test_a_failing_mailer_does_not_fail_the_request(self):
        # The whole reason send() swallows: signing up, resetting and
        # inviting all have to work whether or not mail does.
        class Broken:
            def send(self, message: Message) -> None:
                raise RuntimeError("smtp is down")

        mail.set_mailer(Broken())
        try:
            account("owner@example.com")
            resp = client.post("/auth/password-reset/request", json={"email": "owner@example.com"})
        finally:
            mail.set_mailer(LoggingMailer())

        assert resp.status_code == 204
