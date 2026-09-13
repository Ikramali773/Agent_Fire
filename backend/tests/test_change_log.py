"""Tests for the Case File change log (app/change_log.py, the
case_file_changes table, and GET /case-files/{id}/changes).

This is the "what changed and when" that Project History - a project list
showing each case file's current state only - could never answer.
"""

import pytest
from fastapi.testclient import TestClient

from app import change_log
from app.api.case_files import get_llm_client
from app.auth.user_store import delete_all as delete_all_users
from app.llm.client import LLMNotConfiguredError
from app.main import app
from app.message_store import delete_all as delete_all_messages
from app.models.case_file import (
    CaseFile,
    ConversationStage,
    FieldSource,
    FieldSourceKind,
    FloorAreaItem,
    OccupancyType,
)
from app.models.change_log import ChangeSource
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


class _NoLLM:
    """The dialogue manager's fail-open path - no credentials needed."""

    def extract_fields(self, *args, **kwargs):
        raise LLMNotConfiguredError("no key in tests")

    def classify_intent(self, *args, **kwargs):
        raise LLMNotConfiguredError("no key in tests")

    def answer_question(self, *args, **kwargs):
        raise LLMNotConfiguredError("no key in tests")


@pytest.fixture(autouse=True)
def _reset_store():
    delete_all_case_files()
    delete_all_messages()
    delete_all_users()
    change_log.delete_all()
    app.dependency_overrides[get_llm_client] = lambda: _NoLLM()
    yield
    app.dependency_overrides.clear()


def _new_case_file(headers: dict | None = None) -> str:
    resp = client.post("/case-files", json=None, headers=headers or {})
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


def _signup(email: str = "a@example.com") -> dict:
    resp = client.post("/auth/signup", json={"email": email, "password": "correct-horse"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestDiff:
    def test_only_changed_fields_are_reported(self):
        before = CaseFile(session_id="s", city="Ahmedabad")
        after = before.model_copy(deep=True)
        after.city = "Surat"

        assert change_log.diff(before, after) == {"city": ("Ahmedabad", "Surat")}

    def test_an_unchanged_case_file_produces_nothing(self):
        case_file = CaseFile(session_id="s", city="Ahmedabad", height_m=24.0)

        assert change_log.diff(case_file, case_file.model_copy(deep=True)) == {}

    def test_bookkeeping_fields_are_not_tracked(self):
        # updated_at changes on literally every save; field_sources changes
        # alongside nearly every field. Logging either would bury the real
        # changes in noise.
        before = CaseFile(session_id="s")
        after = before.model_copy(deep=True)
        after.updated_at = after.updated_at.replace(year=2030)
        after.field_sources = {"city": FieldSource(value="Surat", source=FieldSourceKind.USER, confidence=1.0)}

        assert change_log.diff(before, after) == {}

    def test_the_classification_result_is_not_duplicated_here(self):
        # It is already stored in full as a structured transcript message;
        # a second copy would be one more thing to keep in step.
        before = CaseFile(session_id="s")
        after = before.model_copy(deep=True)
        after.classification_result.table_7_ref = "Table 7A"

        assert "classification_result" not in change_log.diff(before, after)

    def test_an_enum_and_its_string_value_do_not_read_as_a_change(self):
        before = CaseFile(session_id="s", occupancy_type=OccupancyType.STORAGE)
        after = CaseFile.model_validate({**before.model_dump(), "occupancy_type": "Storage"})

        assert change_log.diff(before, after) == {}

    def test_a_list_valued_field_is_diffed_by_value(self):
        before = CaseFile(session_id="s", existing_fire_systems=["sprinkler"])
        after = before.model_copy(deep=True)
        after.existing_fire_systems = ["sprinkler", "hydrant"]

        assert change_log.diff(before, after) == {
            "existing_fire_systems": (["sprinkler"], ["sprinkler", "hydrant"])
        }


class TestRecord:
    def test_a_change_is_stored_with_its_source_and_actor(self):
        before = CaseFile(session_id="s")
        after = before.model_copy(deep=True)
        after.height_m = 68.0

        written = change_log.record(before, after, ChangeSource.DOCUMENT, actor_user_id="user-1")

        assert len(written) == 1
        assert written[0].field == "height_m"
        assert written[0].old_value is None
        assert written[0].new_value == 68.0
        assert written[0].source == ChangeSource.DOCUMENT
        assert written[0].actor_user_id == "user-1"

    def test_nothing_is_written_when_nothing_changed(self):
        case_file = CaseFile(session_id="s")

        assert change_log.record(case_file, case_file.model_copy(deep=True), ChangeSource.USER) == []
        assert change_log.list_for_session("s") == []

    def test_one_edit_touching_several_fields_writes_one_row_each(self):
        before = CaseFile(session_id="s")
        after = before.model_copy(deep=True)
        after.city = "Ahmedabad"
        after.state = "Gujarat"
        after.height_m = 68.0

        written = change_log.record(before, after, ChangeSource.USER)

        assert sorted(item.field for item in written) == ["city", "height_m", "state"]

    def test_entries_from_one_edit_are_still_totally_ordered(self):
        # They land in the same clock tick, so created_at alone could not
        # order them - the integer id is what does.
        before = CaseFile(session_id="s")
        after = before.model_copy(deep=True)
        after.city = "Ahmedabad"
        after.state = "Gujarat"
        change_log.record(before, after, ChangeSource.USER)

        ids = [item.id for item in change_log.list_for_session("s")]
        assert len(set(ids)) == 2

    def test_sessions_are_isolated(self):
        for session_id in ("s1", "s2"):
            before = CaseFile(session_id=session_id)
            after = before.model_copy(deep=True)
            after.city = "Ahmedabad"
            change_log.record(before, after, ChangeSource.USER)

        assert len(change_log.list_for_session("s1")) == 1
        assert change_log.list_for_session("s1")[0].session_id == "s1"

    def test_a_structured_field_round_trips_through_json(self):
        before = CaseFile(session_id="s")
        after = before.model_copy(deep=True)
        after.floor_wise_area = [FloorAreaItem(floor="Ground", area_sqm=800.0)]

        written = change_log.record(before, after, ChangeSource.DOCUMENT)

        assert written[0].new_value == [{"floor": "Ground", "area_sqm": 800.0}]
        assert change_log.list_for_session("s")[0].new_value == written[0].new_value


class TestListing:
    def _write(self, session_id: str, count: int) -> None:
        current = CaseFile(session_id=session_id)
        for index in range(count):
            after = current.model_copy(deep=True)
            after.city = f"City {index}"
            change_log.record(current, after, ChangeSource.USER)
            current = after

    def test_newest_first(self):
        # Opposite order to a transcript, on purpose: "what changed
        # recently" is the question an activity timeline answers.
        self._write("s", 3)

        cities = [item.new_value for item in change_log.list_for_session("s")]
        assert cities == ["City 2", "City 1", "City 0"]

    def test_limit_bounds_the_page(self):
        self._write("s", 5)

        assert len(change_log.list_for_session("s", limit=2)) == 2

    def test_before_id_pages_further_back(self):
        self._write("s", 5)
        first_page = change_log.list_for_session("s", limit=2)

        second_page = change_log.list_for_session("s", limit=2, before_id=first_page[-1].id)

        assert [item.new_value for item in second_page] == ["City 2", "City 1"]

    def test_an_unknown_session_is_empty_not_an_error(self):
        assert change_log.list_for_session("never-existed") == []


class TestEndpoint:
    def test_a_direct_edit_is_logged_as_a_user_change(self):
        session_id = _new_case_file()

        client.put(f"/case-files/{session_id}", json={"height_m": 68.0})

        changes = client.get(f"/case-files/{session_id}/changes").json()
        assert [(item["field"], item["new_value"], item["source"]) for item in changes] == [
            ("height_m", 68.0, "user")
        ]

    def test_the_signed_in_account_is_recorded_as_the_actor(self):
        account = _signup()
        headers = _auth_header(account["access_token"])
        session_id = _new_case_file(headers)

        client.put(f"/case-files/{session_id}", json={"city": "Ahmedabad"}, headers=headers)

        changes = client.get(f"/case-files/{session_id}/changes", headers=headers).json()
        assert changes[0]["actor_user_id"] == account["user"]["id"]

    def test_an_anonymous_edit_has_no_actor(self):
        session_id = _new_case_file()

        client.put(f"/case-files/{session_id}", json={"city": "Ahmedabad"})

        assert client.get(f"/case-files/{session_id}/changes").json()[0]["actor_user_id"] is None

    def test_classifying_logs_the_stage_transition(self):
        session_id = _new_case_file()

        client.post(f"/case-files/{session_id}/classify")

        changes = client.get(f"/case-files/{session_id}/changes").json()
        stage_changes = [item for item in changes if item["field"] == "conversation_stage"]
        assert stage_changes[0]["new_value"] == ConversationStage.CLASSIFIED.value
        assert stage_changes[0]["source"] == "system"

    def test_a_what_if_never_appears_in_the_log(self):
        # It reclassifies a hypothetical copy and is never persisted, so it
        # must not look like something that happened to the real project.
        session_id = _new_case_file()
        client.put(f"/case-files/{session_id}", json={"height_m": 24.0})
        before = client.get(f"/case-files/{session_id}/changes").json()

        client.post(f"/case-files/{session_id}/what-if", json={"height_m": 90.0})

        assert client.get(f"/case-files/{session_id}/changes").json() == before

    def test_a_no_op_put_does_not_pad_the_timeline(self):
        session_id = _new_case_file()
        client.put(f"/case-files/{session_id}", json={"city": "Ahmedabad"})

        client.put(f"/case-files/{session_id}", json={"city": "Ahmedabad"})

        assert len(client.get(f"/case-files/{session_id}/changes").json()) == 1

    def test_deleting_a_project_takes_its_change_log_with_it(self):
        session_id = _new_case_file()
        client.put(f"/case-files/{session_id}", json={"city": "Ahmedabad"})
        assert change_log.list_for_session(session_id) != []

        assert client.delete(f"/case-files/{session_id}").status_code == 204

        assert change_log.list_for_session(session_id) == []

    def test_deleting_one_project_leaves_another_projects_log_alone(self):
        keep = _new_case_file()
        drop = _new_case_file()
        client.put(f"/case-files/{keep}", json={"city": "Ahmedabad"})
        client.put(f"/case-files/{drop}", json={"city": "Surat"})

        client.delete(f"/case-files/{drop}")

        assert len(change_log.list_for_session(keep)) == 1

    def test_the_log_of_an_owned_case_file_is_not_readable_by_another_account(self):
        owner = _signup("owner@example.com")
        session_id = _new_case_file(_auth_header(owner["access_token"]))
        intruder = _signup("intruder@example.com")

        resp = client.get(
            f"/case-files/{session_id}/changes", headers=_auth_header(intruder["access_token"])
        )

        assert resp.status_code == 403

    def test_an_unknown_case_file_is_404(self):
        assert client.get("/case-files/does-not-exist/changes").status_code == 404

    def test_paging_parameters_are_validated(self):
        session_id = _new_case_file()

        assert client.get(f"/case-files/{session_id}/changes?limit=0").status_code == 422
        assert client.get(f"/case-files/{session_id}/changes?limit=99999").status_code == 422

    def test_changes_does_not_shadow_the_messages_route(self):
        session_id = _new_case_file()
        client.post(f"/case-files/{session_id}/start")

        messages = client.get(f"/case-files/{session_id}/messages").json()
        changes = client.get(f"/case-files/{session_id}/changes").json()

        assert len(messages) == 1
        assert isinstance(changes, list)
