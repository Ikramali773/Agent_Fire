"""Tests for POST /case-files/{id}/claim - attaching an anonymous case file
to an account after the fact.

The interesting cases are all about NOT letting this become a way to take
over someone else's project: only an unowned case file can be claimed, and
claiming an owned one is refused with the same 403 as any other access to
it, whether or not the caller guessed a real session id.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store():
    delete_all_case_files()
    delete_all_users()


def _signup(email: str = "a@example.com", password: str = "correct-horse") -> dict:
    resp = client.post("/auth/signup", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _anonymous_case_file() -> str:
    resp = client.post("/case-files", json=None)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["owner_user_id"] is None
    return body["session_id"]


def test_claiming_an_anonymous_case_file_sets_the_owner():
    session_id = _anonymous_case_file()
    account = _signup()

    resp = client.post(f"/case-files/{session_id}/claim", headers=_auth_header(account["access_token"]))

    assert resp.status_code == 200, resp.text
    assert resp.json()["owner_user_id"] == account["user"]["id"]


def test_a_claimed_case_file_shows_up_in_project_history():
    # The whole point of claiming: before it, a project started while
    # signed out was invisible to the account that created it.
    session_id = _anonymous_case_file()
    account = _signup()
    headers = _auth_header(account["access_token"])
    assert client.get("/users/me/case-files", headers=headers).json() == []

    client.post(f"/case-files/{session_id}/claim", headers=headers)

    listed = client.get("/users/me/case-files", headers=headers).json()
    assert [item["session_id"] for item in listed] == [session_id]


def test_claiming_your_own_case_file_again_is_a_no_op():
    # Idempotent on purpose - a retry, or React's double-invoked effect in
    # StrictMode, must not turn into an error the user sees.
    account = _signup()
    headers = _auth_header(account["access_token"])
    session_id = client.post("/case-files", json=None, headers=headers).json()["session_id"]

    first = client.post(f"/case-files/{session_id}/claim", headers=headers)
    second = client.post(f"/case-files/{session_id}/claim", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["owner_user_id"] == account["user"]["id"]


def test_claiming_someone_elses_case_file_is_refused():
    owner = _signup("owner@example.com")
    session_id = client.post(
        "/case-files", json=None, headers=_auth_header(owner["access_token"])
    ).json()["session_id"]
    intruder = _signup("intruder@example.com")

    resp = client.post(f"/case-files/{session_id}/claim", headers=_auth_header(intruder["access_token"]))

    assert resp.status_code == 403
    # And the owner is untouched, not merely the response refused.
    still_owned = client.get(f"/case-files/{session_id}", headers=_auth_header(owner["access_token"]))
    assert still_owned.json()["owner_user_id"] == owner["user"]["id"]


def test_claiming_requires_authentication():
    session_id = _anonymous_case_file()

    assert client.post(f"/case-files/{session_id}/claim").status_code == 401


def test_claiming_an_unknown_case_file_is_404():
    account = _signup()

    resp = client.post("/case-files/does-not-exist/claim", headers=_auth_header(account["access_token"]))

    assert resp.status_code == 404


def test_claim_does_not_shadow_the_classify_route():
    # Both are POST /case-files/{session_id}/<literal>; a mistake in route
    # ordering or path spelling would make one swallow the other.
    account = _signup()
    headers = _auth_header(account["access_token"])
    session_id = client.post("/case-files", json=None, headers=headers).json()["session_id"]

    resp = client.post(f"/case-files/{session_id}/classify", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["conversation_stage"] == "classified"
