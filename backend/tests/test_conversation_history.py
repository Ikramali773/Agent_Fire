"""Tests for the persisted chat transcript at the API level.

Two user-reported problems drove this:
1. Opening the Overview page created (and so persisted) a project every
   time, littering Project History with empty projects - hence
   GET /case-files/opening-message, which returns the greeting while
   persisting nothing at all.
2. Switching sections lost the entire conversation, with no way to get it
   back - hence /start, /message and /documents recording messages, and
   GET /case-files/{id}/messages reading them back.
"""

import pytest
from fastapi.testclient import TestClient

from app import message_store
from app.api.case_files import get_llm_client
from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


class FakeLLMClient:
    def classify_intent(self, user_text, pending_question):
        return "answer"

    def extract_fields(self, user_text, field_types, context=""):
        return {"state": "Gujarat", "city": "Ahmedabad"} if "state" in field_types else {}

    def answer_question(self, question, knowledge_context, model_tier="reasoning"):
        return "fake answer"


@pytest.fixture(autouse=True)
def _reset():
    delete_all_case_files()
    delete_all_users()
    message_store.delete_all()
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()
    yield
    app.dependency_overrides.clear()


class TestOpeningMessage:
    def test_returns_the_greeting_and_first_question(self):
        resp = client.get("/case-files/opening-message")

        assert resp.status_code == 200
        agent_message = resp.json()["agent_message"]
        assert "fire-safety requirements" in agent_message
        assert "state and city" in agent_message

    def test_persists_nothing(self):
        # The whole point: showing the opening message must not create a
        # project. Before this endpoint existed, every visit to Overview
        # created one.
        client.get("/case-files/opening-message")
        client.get("/case-files/opening-message")
        client.get("/case-files/opening-message")

        from app.db.models import CaseFileRecord
        from app.db.session import get_session

        with get_session() as session:
            assert session.query(CaseFileRecord).count() == 0

    def test_is_not_shadowed_by_the_session_id_route(self):
        # "/case-files/opening-message" and "/case-files/{session_id}" are
        # both one path segment - declaration order is what keeps this from
        # being read as a lookup for a case file named "opening-message".
        assert "agent_message" in client.get("/case-files/opening-message").json()


class TestTranscriptPersistence:
    def _session(self) -> str:
        return client.post("/case-files", json=None).json()["session_id"]

    def test_start_records_the_opening_message(self):
        session_id = self._session()
        client.post(f"/case-files/{session_id}/start")

        messages = client.get(f"/case-files/{session_id}/messages").json()

        assert len(messages) == 1
        assert messages[0]["role"] == "agent"
        assert messages[0]["kind"] == "text"
        assert "state and city" in messages[0]["text"]

    def test_message_records_both_sides_of_the_turn_in_order(self):
        session_id = self._session()
        client.post(f"/case-files/{session_id}/start")
        client.post(f"/case-files/{session_id}/message", json={"message": "Gujarat, Ahmedabad"})

        messages = client.get(f"/case-files/{session_id}/messages").json()

        assert [m["role"] for m in messages] == ["agent", "user", "agent"]
        assert messages[1]["text"] == "Gujarat, Ahmedabad"

    def test_classification_is_recorded_as_a_structured_message(self):
        session_id = self._session()
        client.put(
            f"/case-files/{session_id}",
            json={
                "state": "Gujarat",
                "occupancy_type": "Storage",
                "height_m": 9.5,
                "built_up_area_sqm": 600,
                "number_of_staircases": 1,
                "project_stage": "concept",
                "goal": "prep_noc",
                "number_of_exits": 2,
                "existing_fire_systems": ["none"],
                "floors_above_ground": 2,
                "floors_below_ground": 0,
                "conversation_stage": "confirming",
            },
        )
        client.post(f"/case-files/{session_id}/message", json={"message": "yes that's correct"})

        messages = client.get(f"/case-files/{session_id}/messages").json()
        classification_messages = [m for m in messages if m["kind"] == "classification_result"]

        assert len(classification_messages) == 1
        assert classification_messages[0]["payload"]["table_7_ref"] == "7H"

    def test_transcript_survives_independently_of_the_case_file_response(self):
        # The transcript is deliberately NOT part of the Case File payload -
        # it's read separately so a long history never rides along on every
        # case file response.
        session_id = self._session()
        client.post(f"/case-files/{session_id}/start")

        case_file = client.get(f"/case-files/{session_id}").json()

        assert "messages" not in case_file
        assert len(client.get(f"/case-files/{session_id}/messages").json()) == 1

    def test_messages_endpoint_supports_paging(self):
        session_id = self._session()
        for index in range(6):
            client.post(f"/case-files/{session_id}/message", json={"message": f"answer {index}"})

        page = client.get(f"/case-files/{session_id}/messages", params={"limit": 4}).json()
        assert len(page) == 4

        older = client.get(
            f"/case-files/{session_id}/messages", params={"limit": 4, "before_id": page[0]["id"]}
        ).json()
        assert all(m["id"] < page[0]["id"] for m in older)

    def test_messages_404_for_a_missing_case_file(self):
        assert client.get("/case-files/does-not-exist/messages").status_code == 404

    def test_deleting_a_project_removes_its_transcript_too(self):
        session_id = self._session()
        client.post(f"/case-files/{session_id}/start")
        client.post(f"/case-files/{session_id}/message", json={"message": "Gujarat, Ahmedabad"})
        assert len(client.get(f"/case-files/{session_id}/messages").json()) == 3

        delete_resp = client.delete(f"/case-files/{session_id}")

        assert delete_resp.status_code == 204
        assert client.get(f"/case-files/{session_id}").status_code == 404
        # The transcript must not survive the project it belonged to - check
        # the store directly, since the endpoint now 404s on the case file.
        assert message_store.list_for_session(session_id) == []

    def test_deleting_one_project_leaves_another_untouched(self):
        keep = self._session()
        remove = self._session()
        client.post(f"/case-files/{keep}/start")
        client.post(f"/case-files/{remove}/start")

        client.delete(f"/case-files/{remove}")

        assert client.get(f"/case-files/{keep}").status_code == 200
        assert len(client.get(f"/case-files/{keep}/messages").json()) == 1

    def test_delete_404_for_a_missing_case_file(self):
        assert client.delete("/case-files/does-not-exist").status_code == 404

    def test_delete_respects_ownership(self):
        owner_token = client.post(
            "/auth/signup", json={"email": "owner@example.com", "password": "correct-horse"}
        ).json()["access_token"]
        session_id = client.post(
            "/case-files", json=None, headers={"Authorization": f"Bearer {owner_token}"}
        ).json()["session_id"]

        # Anonymous, and a different account, are both refused.
        assert client.delete(f"/case-files/{session_id}").status_code == 403
        other_token = client.post(
            "/auth/signup", json={"email": "other@example.com", "password": "correct-horse"}
        ).json()["access_token"]
        assert (
            client.delete(f"/case-files/{session_id}", headers={"Authorization": f"Bearer {other_token}"}).status_code
            == 403
        )
        # ...and the owner can.
        assert (
            client.delete(f"/case-files/{session_id}", headers={"Authorization": f"Bearer {owner_token}"}).status_code
            == 204
        )

    def test_messages_respect_case_file_ownership(self):
        owner_token = client.post(
            "/auth/signup", json={"email": "owner@example.com", "password": "correct-horse"}
        ).json()["access_token"]
        session_id = client.post(
            "/case-files", json=None, headers={"Authorization": f"Bearer {owner_token}"}
        ).json()["session_id"]

        assert client.get(f"/case-files/{session_id}/messages").status_code == 403
