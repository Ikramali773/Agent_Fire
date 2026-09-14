"""Tests for account recovery.

Before this, the entire auth surface was signup/login/logout/me: a
forgotten password lost the account and every project in it, permanently,
with no admin path either.

Two properties carry most of the weight. A reset link must never reach
anyone but the account's owner - so it is never in an HTTP response, and
the request endpoint answers identically whether or not the address exists.
And changing a password must close the sessions that already existed, or it
is no use to someone whose password was stolen.
"""

import pytest
from fastapi.testclient import TestClient

from app import mail
from app.auth import password_resets, rate_limit, revoked_tokens
from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


class _CapturingMailer:
    """Stands in for a mail provider, and lets a test read the link."""

    def __init__(self) -> None:
        self.sent: list[mail.Message] = []

    def send(self, message: mail.Message) -> None:
        self.sent.append(message)

    @property
    def last_token(self) -> str:
        return self.sent[-1].body.split("reset=")[1].split()[0]


@pytest.fixture
def mailbox():
    captured = _CapturingMailer()
    mail.set_mailer(captured)
    yield captured
    mail.set_mailer(mail.LoggingMailer())


@pytest.fixture(autouse=True)
def _reset():
    delete_all_case_files()
    delete_all_users()
    revoked_tokens.delete_all()
    password_resets.delete_all()
    rate_limit.reset()


def _signup(email: str = "a@example.com", password: str = "correct-horse") -> dict:
    return client.post("/auth/signup", json={"email": email, "password": password}).json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(email: str = "a@example.com", password: str = "correct-horse"):
    rate_limit.reset()
    return client.post("/auth/login", json={"email": email, "password": password})


class TestTheCutOffIsNotARace:
    """The sign-out-everywhere cut-off is a full-precision instant, so the
    token's `iat` has to be one too.

    With `iat` truncated to whole seconds, a change at t=100.7 stamped a
    cut-off of 100.7 while a login a fraction later still minted iat=100 -
    and 100 < 100.7, so the brand-new token was rejected. It failed or
    passed depending on where in the second the change happened to land,
    which is how it survived one full test run before failing the next.
    The frontend re-logs in the moment a password changes, so this locked
    people out of their own account at random.
    """

    def test_a_token_minted_after_the_cut_off_is_accepted(self):
        # Deterministic where the end-to-end version was a coin flip: the
        # cut-off is stamped first, the token second, so a correct
        # implementation accepts it however the clock happens to fall.
        from app.auth.dependencies import get_current_user_optional
        from app.auth.tokens import create_token
        from app.auth.user_store import set_password

        account = _signup()
        user_id = client.get("/auth/me", headers=_headers(account["access_token"])).json()["id"]

        set_password(user_id, "battery-staple")
        fresh = create_token(user_id)

        assert get_current_user_optional(f"Bearer {fresh}") is not None

    def test_a_token_minted_before_the_cut_off_is_rejected(self):
        # The precision fix must not quietly widen the hole it closes.
        from app.auth.dependencies import get_current_user_optional
        from app.auth.tokens import create_token
        from app.auth.user_store import set_password

        account = _signup()
        user_id = client.get("/auth/me", headers=_headers(account["access_token"])).json()["id"]

        stale = create_token(user_id)
        set_password(user_id, "battery-staple")

        assert get_current_user_optional(f"Bearer {stale}") is None

    def test_the_whole_flow_holds_end_to_end(self):
        # The same thing through the API, which is where it actually bit.
        account = _signup()

        client.post(
            "/auth/password",
            json={"current_password": "correct-horse", "new_password": "battery-staple"},
            headers=_headers(account["access_token"]),
        )
        token = _login(password="battery-staple").json()["access_token"]

        assert client.get("/auth/me", headers=_headers(token)).status_code == 200
        assert client.get("/auth/me", headers=_headers(account["access_token"])).status_code == 401


class TestChangingPassword:
    def test_the_new_password_works_and_the_old_one_does_not(self):
        account = _signup()

        resp = client.post(
            "/auth/password",
            json={"current_password": "correct-horse", "new_password": "battery-staple"},
            headers=_headers(account["access_token"]),
        )

        assert resp.status_code == 204
        assert _login(password="battery-staple").status_code == 200
        assert _login(password="correct-horse").status_code == 401

    def test_the_current_password_is_required(self):
        # A stolen session token alone must not be enough to lock the real
        # owner out of their own account.
        account = _signup()

        resp = client.post(
            "/auth/password",
            json={"current_password": "wrong", "new_password": "battery-staple"},
            headers=_headers(account["access_token"]),
        )

        assert resp.status_code == 403
        assert _login().status_code == 200

    def test_changing_it_closes_every_existing_session(self):
        # The whole point when the reason for changing is that someone else
        # has the old password.
        _signup()
        first = _login().json()["access_token"]
        second = _login().json()["access_token"]
        assert client.get("/auth/me", headers=_headers(first)).status_code == 200

        client.post(
            "/auth/password",
            json={"current_password": "correct-horse", "new_password": "battery-staple"},
            headers=_headers(second),
        )

        assert client.get("/auth/me", headers=_headers(first)).status_code == 401
        assert client.get("/auth/me", headers=_headers(second)).status_code == 401

    def test_a_fresh_login_after_the_change_works(self):
        # The cut-off must not lock the account out of itself.
        account = _signup()
        client.post(
            "/auth/password",
            json={"current_password": "correct-horse", "new_password": "battery-staple"},
            headers=_headers(account["access_token"]),
        )

        token = _login(password="battery-staple").json()["access_token"]

        assert client.get("/auth/me", headers=_headers(token)).status_code == 200

    def test_the_new_password_must_meet_the_same_rules_as_signup(self):
        account = _signup()
        headers = _headers(account["access_token"])

        short = client.post(
            "/auth/password", json={"current_password": "correct-horse", "new_password": "abc"}, headers=headers
        )
        long = client.post(
            "/auth/password",
            json={"current_password": "correct-horse", "new_password": "a" * 100},
            headers=headers,
        )

        assert short.status_code == 422
        assert long.status_code == 422

    def test_it_requires_a_signed_in_account(self):
        assert client.post(
            "/auth/password", json={"current_password": "x", "new_password": "battery-staple"}
        ).status_code == 401


class TestRequestingAReset:
    def test_the_link_is_never_in_the_response(self, mailbox):
        # Returning it would let anyone take over any account just by
        # typing its address.
        _signup()

        resp = client.post("/auth/password-reset/request", json={"email": "a@example.com"})

        assert resp.status_code == 204
        assert resp.content in (b"", b"null")
        assert mailbox.sent, "the link should have been mailed"

    def test_an_unknown_address_is_answered_identically(self, mailbox):
        # Otherwise this endpoint answers "does this person use the
        # product?" - and for a compliance tool the client list is itself
        # worth protecting.
        _signup()
        known = client.post("/auth/password-reset/request", json={"email": "a@example.com"})
        rate_limit.reset()

        unknown = client.post("/auth/password-reset/request", json={"email": "nobody@example.com"})

        assert known.status_code == unknown.status_code == 204
        assert known.content == unknown.content
        assert len(mailbox.sent) == 1, "no link for an address with no account"

    def test_the_link_goes_to_the_accounts_own_address(self, mailbox):
        _signup("owner@example.com")

        client.post("/auth/password-reset/request", json={"email": "owner@example.com"})

        assert mailbox.sent[0].to == "owner@example.com"

    def test_requests_are_rate_limited(self, mailbox):
        _signup()

        statuses = [
            client.post("/auth/password-reset/request", json={"email": "a@example.com"}).status_code
            for _ in range(rate_limit.MAX_ATTEMPTS + 2)
        ]

        assert 429 in statuses

    def test_asking_again_kills_the_previous_link(self, mailbox):
        # A forwarded email must stop working once the real owner has asked
        # for a new one.
        _signup()
        client.post("/auth/password-reset/request", json={"email": "a@example.com"})
        first_token = mailbox.last_token
        rate_limit.reset()
        client.post("/auth/password-reset/request", json={"email": "a@example.com"})

        resp = client.post(
            "/auth/password-reset/confirm",
            json={"token": first_token, "new_password": "battery-staple"},
        )

        assert resp.status_code == 400


class TestConfirmingAReset:
    def _request_token(self, mailbox) -> str:
        client.post("/auth/password-reset/request", json={"email": "a@example.com"})
        return mailbox.last_token

    def test_the_token_sets_a_new_password(self, mailbox):
        _signup()
        token = self._request_token(mailbox)

        resp = client.post(
            "/auth/password-reset/confirm", json={"token": token, "new_password": "battery-staple"}
        )

        assert resp.status_code == 204
        assert _login(password="battery-staple").status_code == 200

    def test_a_token_cannot_be_used_twice(self, mailbox):
        _signup()
        token = self._request_token(mailbox)
        client.post(
            "/auth/password-reset/confirm", json={"token": token, "new_password": "battery-staple"}
        )

        again = client.post(
            "/auth/password-reset/confirm", json={"token": token, "new_password": "something-else"}
        )

        assert again.status_code == 400
        assert _login(password="battery-staple").status_code == 200

    def test_an_expired_token_is_refused(self, mailbox, monkeypatch):
        from datetime import timedelta

        monkeypatch.setattr(password_resets, "TOKEN_TTL", timedelta(seconds=-1))
        _signup()
        token = self._request_token(mailbox)

        resp = client.post(
            "/auth/password-reset/confirm", json={"token": token, "new_password": "battery-staple"}
        )

        assert resp.status_code == 400

    def test_a_made_up_token_is_refused(self):
        _signup()

        resp = client.post(
            "/auth/password-reset/confirm",
            json={"token": "not-a-real-token", "new_password": "battery-staple"},
        )

        assert resp.status_code == 400

    def test_resetting_closes_every_existing_session(self, mailbox):
        # The reason for resetting is usually that someone else got in.
        account = _signup()
        token = self._request_token(mailbox)

        client.post(
            "/auth/password-reset/confirm", json={"token": token, "new_password": "battery-staple"}
        )

        assert client.get("/auth/me", headers=_headers(account["access_token"])).status_code == 401

    def test_the_new_password_must_meet_the_same_rules(self, mailbox):
        _signup()
        token = self._request_token(mailbox)

        resp = client.post(
            "/auth/password-reset/confirm", json={"token": token, "new_password": "abc"}
        )

        assert resp.status_code == 422

    def test_a_rejected_password_does_not_spend_the_token(self, mailbox):
        # Otherwise one typo costs the user their only link.
        _signup()
        token = self._request_token(mailbox)
        client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "abc"})

        resp = client.post(
            "/auth/password-reset/confirm", json={"token": token, "new_password": "battery-staple"}
        )

        assert resp.status_code == 204


class TestTokenStorage:
    def test_the_raw_token_is_never_stored(self):
        # A leaked database must not hand over the ability to take over
        # accounts - the same reasoning as for passwords.
        from app.db.models import PasswordResetRecord
        from app.db.session import get_session

        account = _signup()
        token = password_resets.create(account["user"]["id"])

        with get_session() as session:
            rows = session.query(PasswordResetRecord).all()
            assert rows
            assert all(token not in row.token_hash for row in rows)

    def test_one_account_has_at_most_one_live_token(self):
        from app.db.models import PasswordResetRecord
        from app.db.session import get_session

        account = _signup()
        password_resets.create(account["user"]["id"])
        password_resets.create(account["user"]["id"])

        with get_session() as session:
            assert session.query(PasswordResetRecord).count() == 1
