"""Tests for chat titles - GET /users/me/chat-titles and the query behind
it (app/message_store.py::first_user_messages).

A project's name is collected partway through the intake, so without this
a sidebar of freshly-started chats is a column of identical "Untitled
project" rows.
"""

import pytest
from fastapi.testclient import TestClient

from app import message_store
from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.message_store import TITLE_MAX_CHARS, delete_all as delete_all_messages
from app.models.conversation import MessageKind, MessageRole
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store():
    delete_all_case_files()
    delete_all_messages()
    delete_all_users()


def _signup(email: str = "a@example.com") -> dict:
    resp = client.post("/auth/signup", json={"email": email, "password": "correct-horse"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestFirstUserMessages:
    def test_takes_the_first_user_message(self):
        message_store.append("s", MessageRole.AGENT, "Which state and city?")
        message_store.append("s", MessageRole.USER, "Gujarat, Ahmedabad")
        message_store.append("s", MessageRole.USER, "Actually Surat")

        assert message_store.first_user_messages(["s"]) == {"s": "Gujarat, Ahmedabad"}

    def test_ignores_the_agent_greeting(self):
        # It is identical in every conversation and would title them all
        # the same.
        message_store.append("s", MessageRole.AGENT, "Hi - I can help you understand...")

        assert message_store.first_user_messages(["s"]) == {}

    def test_a_session_with_no_user_message_is_simply_absent(self):
        assert message_store.first_user_messages(["never-spoke"]) == {}

    def test_a_whitespace_only_message_does_not_become_a_title(self):
        message_store.append("s", MessageRole.USER, "   ")

        assert message_store.first_user_messages(["s"]) == {}

    def test_sessions_are_kept_apart(self):
        message_store.append("s1", MessageRole.USER, "A hospital in Pune")
        message_store.append("s2", MessageRole.USER, "A warehouse in Surat")

        assert message_store.first_user_messages(["s1", "s2"]) == {
            "s1": "A hospital in Pune",
            "s2": "A warehouse in Surat",
        }

    def test_only_the_requested_sessions_are_returned(self):
        # This is what scopes the endpoint to one account's case files.
        message_store.append("mine", MessageRole.USER, "Mine")
        message_store.append("theirs", MessageRole.USER, "Theirs")

        assert message_store.first_user_messages(["mine"]) == {"mine": "Mine"}

    def test_asking_for_nothing_queries_nothing(self):
        assert message_store.first_user_messages([]) == {}

    def test_a_long_message_is_trimmed_at_a_word_boundary(self):
        long_message = "I need a fire NOC for a twelve storey hospital building located in Pune Maharashtra"
        message_store.append("s", MessageRole.USER, long_message)

        title = message_store.first_user_messages(["s"])["s"]

        assert title.endswith("…")
        assert len(title) <= TITLE_MAX_CHARS + 1
        assert not title[:-1].endswith(" ")
        assert long_message.startswith(title[:-1])

    def test_newlines_are_collapsed_so_a_title_stays_one_line(self):
        message_store.append("s", MessageRole.USER, "Gujarat\n\nAhmedabad")

        assert message_store.first_user_messages(["s"]) == {"s": "Gujarat Ahmedabad"}

    def test_a_structured_message_without_text_is_not_a_title(self):
        message_store.append(
            "s", MessageRole.AGENT, kind=MessageKind.DOCUMENT_RESULT, payload={"file_name": "plan.pdf"}
        )

        assert message_store.first_user_messages(["s"]) == {}


class TestEndpoint:
    def test_returns_a_title_for_each_of_this_accounts_chats(self):
        account = _signup()
        headers = _auth_header(account["access_token"])
        session_id = client.post("/case-files", json=None, headers=headers).json()["session_id"]
        message_store.append(session_id, MessageRole.USER, "A hospital in Pune")

        body = client.get("/users/me/chat-titles", headers=headers).json()

        assert body == [{"session_id": session_id, "title": "A hospital in Pune"}]

    def test_never_exposes_another_accounts_conversation(self):
        owner = _signup("owner@example.com")
        owned = client.post(
            "/case-files", json=None, headers=_auth_header(owner["access_token"])
        ).json()["session_id"]
        message_store.append(owned, MessageRole.USER, "Confidential project")
        other = _signup("other@example.com")

        body = client.get("/users/me/chat-titles", headers=_auth_header(other["access_token"])).json()

        assert body == []

    def test_an_anonymous_case_file_has_no_titles_to_list(self):
        # It has no owner, so it belongs to no account's rail.
        session_id = client.post("/case-files", json=None).json()["session_id"]
        message_store.append(session_id, MessageRole.USER, "Anonymous project")
        account = _signup()

        body = client.get("/users/me/chat-titles", headers=_auth_header(account["access_token"])).json()

        assert body == []

    def test_requires_authentication(self):
        assert client.get("/users/me/chat-titles").status_code == 401

    def test_a_real_conversation_gets_its_title_from_the_users_answer(self):
        # End-to-end through the API rather than by writing messages
        # directly: /start records the greeting, the user's turn follows.
        account = _signup()
        headers = _auth_header(account["access_token"])
        session_id = client.post("/case-files", json=None, headers=headers).json()["session_id"]
        client.post(f"/case-files/{session_id}/start", headers=headers)
        client.post(f"/case-files/{session_id}/message", json={"message": "Gujarat, Ahmedabad"}, headers=headers)

        body = client.get("/users/me/chat-titles", headers=headers).json()

        assert body == [{"session_id": session_id, "title": "Gujarat, Ahmedabad"}]
