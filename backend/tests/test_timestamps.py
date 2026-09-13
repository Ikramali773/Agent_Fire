"""Timestamps the API emits must carry their timezone.

Every timestamp in this app is written as UTC, but SQLite has no
timezone-aware type and the Case File's old default was
`datetime.utcnow()` (naive). Serialized without an offset, a browser
parsing "2026-09-13T07:13:16" treats it as LOCAL time - so a change made
seconds ago showed as hours ago for every user outside UTC.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import change_log
from app.main import app
from app.message_store import delete_all as delete_all_messages
from app.models.case_file import CaseFile
from app.models.change_log import ChangeSource
from app.models.conversation import MessageRole
from app import message_store
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store():
    delete_all_case_files()
    delete_all_messages()
    change_log.delete_all()


def _has_timezone(serialized: str) -> bool:
    return serialized.endswith("Z") or "+" in serialized[10:] or serialized[10:].count("-") > 0


def test_a_new_case_file_has_timezone_aware_timestamps():
    case_file = CaseFile(session_id="s")

    assert case_file.created_at.tzinfo is not None
    assert case_file.updated_at.tzinfo is not None


def test_a_case_file_stored_with_naive_timestamps_is_read_back_as_utc():
    # Exactly what a database written before this fix contains.
    case_file = CaseFile.model_validate(
        {"session_id": "s", "created_at": "2026-01-01T10:00:00", "updated_at": "2026-01-01T10:00:00"}
    )

    assert case_file.created_at == datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


def test_the_api_serializes_a_case_file_timestamp_with_an_offset():
    body = client.post("/case-files", json=None).json()

    assert _has_timezone(body["updated_at"]), body["updated_at"]


def test_a_transcript_message_comes_back_with_its_timezone():
    # The DB column drops tzinfo on read; message_store re-labels it.
    message_store.append("s", MessageRole.AGENT, "hello")

    assert message_store.list_for_session("s")[0].created_at.tzinfo is not None


def test_a_change_log_entry_comes_back_with_its_timezone():
    before = CaseFile(session_id="s")
    after = before.model_copy(deep=True)
    after.city = "Ahmedabad"
    change_log.record(before, after, ChangeSource.USER)

    assert change_log.list_for_session("s")[0].created_at.tzinfo is not None


def test_the_changes_endpoint_serializes_an_offset():
    session_id = client.post("/case-files", json=None).json()["session_id"]
    client.put(f"/case-files/{session_id}", json={"city": "Ahmedabad"})

    body = client.get(f"/case-files/{session_id}/changes").json()

    assert _has_timezone(body[0]["created_at"]), body[0]["created_at"]


def test_the_messages_endpoint_serializes_an_offset():
    session_id = client.post("/case-files", json=None).json()["session_id"]
    client.post(f"/case-files/{session_id}/start")

    body = client.get(f"/case-files/{session_id}/messages").json()

    assert _has_timezone(body[0]["created_at"]), body[0]["created_at"]
