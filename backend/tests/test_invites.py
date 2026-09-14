"""Tests for reviewer invitations by link.

The gap they close: sharing is account-to-account by email, so a consultant
who has never signed up could not be invited at all. The link is handed to
the OWNER rather than mailed, which is secure because the owner is already
authorised to share the project - and which is the only honest option in a
deployment with no mail transport.

A live link IS access to the project, so most of these tests are about it
being single-use, expiring, revocable, and never shown twice.
"""

import pytest
from fastapi.testclient import TestClient

from app import change_log, grant_store, invite_store, review_store
from app.auth import rate_limit, revoked_tokens
from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.message_store import delete_all as delete_all_messages
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    delete_all_case_files()
    delete_all_messages()
    delete_all_users()
    change_log.delete_all()
    review_store.delete_all()
    grant_store.delete_all()
    invite_store.delete_all()
    revoked_tokens.delete_all()
    rate_limit.reset()


def _signup(email: str) -> dict:
    return client.post("/auth/signup", json={"email": email, "password": "correct-horse"}).json()


def _headers(account: dict) -> dict:
    return {"Authorization": f"Bearer {account['access_token']}"}


def _project(owner: dict, name: str = "Lakeview Residences") -> str:
    headers = _headers(owner)
    session_id = client.post("/case-files", json=None, headers=headers).json()["session_id"]
    client.put(f"/case-files/{session_id}", json={"project_name": name}, headers=headers)
    return session_id


def _invite(owner: dict, session_id: str, email: str = "consultant@example.com") -> str:
    resp = client.post(
        f"/case-files/{session_id}/invites", json={"email": email}, headers=_headers(owner)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["invite_url"].split("invite=")[1]


class TestCreatingAnInvite:
    def test_the_owner_gets_a_link_to_pass_on(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)

        resp = client.post(
            f"/case-files/{session_id}/invites",
            json={"email": "consultant@example.com"},
            headers=_headers(owner),
        )

        assert resp.status_code == 201
        assert "invite=" in resp.json()["invite_url"]
        assert resp.json()["invited_email"] == "consultant@example.com"

    def test_an_address_with_no_account_can_be_invited(self):
        # The entire point: /shares answers an honest 404 for someone who
        # has never signed up, which is most consultants the first time.
        owner = _signup("owner@example.com")
        session_id = _project(owner)

        shares = client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "stranger@example.com"},
            headers=_headers(owner),
        )
        invites = client.post(
            f"/case-files/{session_id}/invites",
            json={"email": "stranger@example.com"},
            headers=_headers(owner),
        )

        assert shares.status_code == 404
        assert invites.status_code == 201

    def test_the_link_is_never_shown_again(self):
        # Stored hashed, so listing cannot reveal it - and a leaked
        # database must not hand over live access to shared projects.
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        _invite(owner, session_id)

        listed = client.get(f"/case-files/{session_id}/invites", headers=_headers(owner)).json()

        assert len(listed) == 1
        assert listed[0]["invite_url"] is None

    def test_re_inviting_kills_the_previous_link(self):
        # Two working keys in circulation for one invitation is one too many.
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        first = _invite(owner, session_id)
        _invite(owner, session_id)
        reviewer = _signup("consultant@example.com")

        resp = client.post(f"/invites/{first}/accept", headers=_headers(reviewer))

        assert resp.status_code == 404

    def test_a_reviewer_cannot_invite_a_third_party(self):
        owner = _signup("owner@example.com")
        reviewer = _signup("consultant@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)
        client.post(f"/invites/{token}/accept", headers=_headers(reviewer))

        resp = client.post(
            f"/case-files/{session_id}/invites",
            json={"email": "third@example.com"},
            headers=_headers(reviewer),
        )

        assert resp.status_code == 403

    def test_a_malformed_address_is_refused(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)

        assert client.post(
            f"/case-files/{session_id}/invites", json={"email": "not-an-email"}, headers=_headers(owner)
        ).status_code == 422

    def test_an_anonymous_project_cannot_be_invited_to(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]

        assert client.post(
            f"/case-files/{session_id}/invites", json={"email": "a@example.com"}
        ).status_code == 401


class TestPreviewingAnInvite:
    def test_the_recipient_sees_what_they_are_accepting_without_an_account(self):
        # Being asked to sign up without being told what for is how an
        # invitation gets ignored.
        owner = _signup("owner@example.com")
        session_id = _project(owner, "St Mary Hospital")
        token = _invite(owner, session_id)

        preview = client.get(f"/invites/{token}").json()

        assert preview["project_name"] == "St Mary Hospital"
        assert preview["invited_by_email"] == "owner@example.com"
        assert preview["already_accepted"] is False

    def test_the_preview_reveals_nothing_about_the_building(self):
        # Whoever holds the link has not accepted yet, and may not be the
        # person it was meant for.
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        client.put(
            f"/case-files/{session_id}",
            json={"height_m": 30.0, "city": "Pune", "occupancy_type": "Institutional"},
            headers=_headers(owner),
        )
        token = _invite(owner, session_id)

        preview = client.get(f"/invites/{token}").json()

        assert set(preview) == {
            "project_name",
            "invited_by_email",
            "invited_email",
            "expires_at",
            "already_accepted",
        }

    def test_an_invalid_token_is_404(self):
        assert client.get("/invites/not-a-real-token").status_code == 404

    def test_a_deleted_project_says_so_rather_than_500ing(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)
        # Deleting cascades to invites, so this is a belt-and-braces path.
        client.delete(f"/case-files/{session_id}", headers=_headers(owner))

        assert client.get(f"/invites/{token}").status_code == 404


class TestAcceptingAnInvite:
    def test_accepting_grants_reviewer_access(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)
        reviewer = _signup("consultant@example.com")
        assert client.get(f"/case-files/{session_id}", headers=_headers(reviewer)).status_code == 403

        resp = client.post(f"/invites/{token}/accept", headers=_headers(reviewer))

        assert resp.status_code == 200
        assert client.get(f"/case-files/{session_id}", headers=_headers(reviewer)).status_code == 200

    def test_the_accepted_reviewer_is_read_only_like_any_other(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)
        reviewer = _signup("consultant@example.com")
        client.post(f"/invites/{token}/accept", headers=_headers(reviewer))

        assert client.put(
            f"/case-files/{session_id}", json={"height_m": 9.0}, headers=_headers(reviewer)
        ).status_code == 403
        assert client.delete(f"/case-files/{session_id}", headers=_headers(reviewer)).status_code == 403

    def test_the_accepted_reviewer_can_record_a_verdict(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)
        reviewer = _signup("consultant@example.com")
        client.post(f"/invites/{token}/accept", headers=_headers(reviewer))

        resp = client.post(
            f"/case-files/{session_id}/review",
            json={"status": "approved", "note": "Checked."},
            headers=_headers(reviewer),
        )

        assert resp.status_code == 201

    def test_a_link_cannot_be_used_twice(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)
        first = _signup("consultant@example.com")
        second = _signup("someone.else@example.com")
        client.post(f"/invites/{token}/accept", headers=_headers(first))

        resp = client.post(f"/invites/{token}/accept", headers=_headers(second))

        assert resp.status_code == 400
        assert client.get(f"/case-files/{session_id}", headers=_headers(second)).status_code == 403

    def test_an_expired_link_is_refused(self, monkeypatch):
        from datetime import timedelta

        monkeypatch.setattr(invite_store, "INVITE_TTL", timedelta(seconds=-1))
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)
        reviewer = _signup("consultant@example.com")

        assert client.post(f"/invites/{token}/accept", headers=_headers(reviewer)).status_code == 400

    def test_accepting_requires_an_account(self):
        # A verdict has to be attributable to a person, and "someone with
        # the link" is not one.
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)

        assert client.post(f"/invites/{token}/accept").status_code == 401

    def test_a_different_address_may_accept(self):
        # A consultant may well sign up with another address, and refusing
        # that would strand a legitimate reviewer over a typo.
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id, "work@example.com")
        reviewer = _signup("personal@example.com")

        resp = client.post(f"/invites/{token}/accept", headers=_headers(reviewer))

        assert resp.status_code == 200
        assert resp.json()["invited_email"] == "work@example.com"
        assert resp.json()["accepted_by_user_id"] == reviewer["user"]["id"]

    def test_the_owner_cannot_accept_their_own_invite(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)

        assert client.post(f"/invites/{token}/accept", headers=_headers(owner)).status_code == 422

    def test_the_owner_can_see_who_accepted(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)
        reviewer = _signup("consultant@example.com")
        client.post(f"/invites/{token}/accept", headers=_headers(reviewer))

        listed = client.get(f"/case-files/{session_id}/invites", headers=_headers(owner)).json()

        assert listed[0]["accepted_by_user_id"] == reviewer["user"]["id"]
        assert listed[0]["accepted_at"] is not None


class TestRevokingAnInvite:
    def test_an_unaccepted_invite_can_be_cancelled(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)

        resp = client.delete(
            f"/case-files/{session_id}/invites/consultant@example.com", headers=_headers(owner)
        )

        assert resp.status_code == 204
        assert client.get(f"/invites/{token}").status_code == 404

    def test_cancelling_an_address_that_was_never_invited_is_404(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)

        assert client.delete(
            f"/case-files/{session_id}/invites/nobody@example.com", headers=_headers(owner)
        ).status_code == 404

    def test_an_accepted_invite_is_revoked_through_shares_instead(self):
        # Once accepted the access is an ordinary grant, so a stale invite
        # and a live reviewer are never confused.
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)
        reviewer = _signup("consultant@example.com")
        client.post(f"/invites/{token}/accept", headers=_headers(reviewer))

        assert client.delete(
            f"/case-files/{session_id}/invites/consultant@example.com", headers=_headers(owner)
        ).status_code == 404
        assert client.delete(
            f"/case-files/{session_id}/shares/{reviewer['user']['id']}", headers=_headers(owner)
        ).status_code == 204
        assert client.get(f"/case-files/{session_id}", headers=_headers(reviewer)).status_code == 403

    def test_deleting_a_project_makes_its_invites_unredeemable(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)
        reviewer = _signup("consultant@example.com")

        client.delete(f"/case-files/{session_id}", headers=_headers(owner))

        assert client.post(f"/invites/{token}/accept", headers=_headers(reviewer)).status_code == 404
        assert invite_store.list_for_session(session_id) == []


class TestTokenStorage:
    def test_the_raw_token_is_never_stored(self):
        from app.db.models import CaseFileInviteRecord
        from app.db.session import get_session

        owner = _signup("owner@example.com")
        session_id = _project(owner)
        token = _invite(owner, session_id)

        with get_session() as session:
            rows = session.query(CaseFileInviteRecord).all()
            assert rows
            assert all(token not in row.token_hash for row in rows)
