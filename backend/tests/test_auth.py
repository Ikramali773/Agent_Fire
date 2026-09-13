"""Tests for Phase 2's accounts: signup/login/me (app/api/auth.py), and the
ownership model layered onto Case Files (app/api/case_files.py's
_check_access) - an anonymous case file must stay exactly as open as Phase
1 always had it, while an owned one must be locked to its account.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store():
    # autouse fixture rather than setup_function - the latter is a
    # pytest/xunit hook that only fires for plain test functions, not for
    # methods inside a test class (several classes below need it too).
    delete_all_case_files()
    delete_all_users()


def _signup(email: str = "a@example.com", password: str = "correct-horse") -> dict:
    resp = client.post("/auth/signup", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_signup_returns_a_token_and_user():
    body = _signup()
    assert body["user"]["email"] == "a@example.com"
    assert "id" in body["user"]
    assert "password" not in body["user"]
    assert "hashed_password" not in body["user"]
    assert body["access_token"]


def test_signup_rejects_duplicate_email():
    _signup()
    resp = client.post("/auth/signup", json={"email": "a@example.com", "password": "another-pass"})
    assert resp.status_code == 409


def test_signup_rejects_invalid_email_and_short_password():
    assert client.post("/auth/signup", json={"email": "not-an-email", "password": "correct-horse"}).status_code == 422
    assert client.post("/auth/signup", json={"email": "a@example.com", "password": "short"}).status_code == 422


def test_login_with_correct_credentials():
    _signup()
    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "correct-horse"})
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "a@example.com"


def test_login_rejects_wrong_password():
    _signup()
    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_rejects_unknown_email():
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "correct-horse"})
    assert resp.status_code == 401


def test_me_requires_a_token():
    assert client.get("/auth/me").status_code == 401


def test_me_returns_the_authenticated_user():
    body = _signup()
    resp = client.get("/auth/me", headers=_auth_header(body["access_token"]))
    assert resp.status_code == 200
    assert resp.json()["email"] == "a@example.com"


def test_me_rejects_a_tampered_token():
    body = _signup()
    tampered = body["access_token"][:-1] + ("0" if body["access_token"][-1] != "0" else "1")
    resp = client.get("/auth/me", headers=_auth_header(tampered))
    assert resp.status_code == 401


class TestCaseFileOwnership:
    def test_anonymous_case_file_stays_open_with_no_token_at_all(self):
        # Phase 1's original model must be completely unaffected: no
        # Authorization header, no owner_user_id, full access.
        session_id = client.post("/case-files", json=None).json()["session_id"]
        assert client.get(f"/case-files/{session_id}").json()["owner_user_id"] is None
        assert client.put(f"/case-files/{session_id}", json={"project_name": "X"}).status_code == 200
        assert client.post(f"/case-files/{session_id}/classify").status_code == 200
        assert client.get(f"/case-files/{session_id}/report").status_code == 200

    def test_logged_in_create_assigns_ownership(self):
        token = _signup()["access_token"]
        resp = client.post("/case-files", json=None, headers=_auth_header(token))
        assert resp.status_code == 201
        session_id = resp.json()["session_id"]
        assert resp.json()["owner_user_id"] is not None

        # The owner can access it normally.
        assert client.get(f"/case-files/{session_id}", headers=_auth_header(token)).status_code == 200

    def test_owned_case_file_rejects_anonymous_access(self):
        token = _signup()["access_token"]
        session_id = client.post("/case-files", json=None, headers=_auth_header(token)).json()["session_id"]

        assert client.get(f"/case-files/{session_id}").status_code == 403
        assert client.put(f"/case-files/{session_id}", json={"project_name": "X"}).status_code == 403
        assert client.post(f"/case-files/{session_id}/classify").status_code == 403
        assert client.get(f"/case-files/{session_id}/report").status_code == 403

    def test_owned_case_file_rejects_a_different_account(self):
        owner_token = _signup(email="owner@example.com")["access_token"]
        session_id = client.post("/case-files", json=None, headers=_auth_header(owner_token)).json()["session_id"]

        other_token = _signup(email="other@example.com")["access_token"]
        resp = client.get(f"/case-files/{session_id}", headers=_auth_header(other_token))
        assert resp.status_code == 403

    def test_put_cannot_reassign_ownership(self):
        owner_token = _signup(email="owner@example.com")["access_token"]
        session_id = client.post("/case-files", json=None, headers=_auth_header(owner_token)).json()["session_id"]
        owner_id = client.get(f"/case-files/{session_id}", headers=_auth_header(owner_token)).json()["owner_user_id"]

        client.put(
            f"/case-files/{session_id}",
            json={"owner_user_id": "someone-elses-id"},
            headers=_auth_header(owner_token),
        )

        assert (
            client.get(f"/case-files/{session_id}", headers=_auth_header(owner_token)).json()["owner_user_id"]
            == owner_id
        )


class TestMyCaseFiles:
    def test_requires_authentication(self):
        assert client.get("/users/me/case-files").status_code == 401

    def test_lists_only_this_accounts_case_files(self):
        token_a = _signup(email="a@example.com")["access_token"]
        token_b = _signup(email="b@example.com")["access_token"]
        client.post("/case-files", json=None, headers=_auth_header(token_a))
        client.post("/case-files", json=None, headers=_auth_header(token_a))
        client.post("/case-files", json=None, headers=_auth_header(token_b))

        resp_a = client.get("/users/me/case-files", headers=_auth_header(token_a))
        assert resp_a.status_code == 200
        assert len(resp_a.json()["items"]) == 2
        assert resp_a.json()["total"] == 2

        resp_b = client.get("/users/me/case-files", headers=_auth_header(token_b))
        assert len(resp_b.json()["items"]) == 1
