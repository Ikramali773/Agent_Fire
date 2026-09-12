"""Tests for app/message_store.py - the append-only chat transcript store.

Covers what the store actually has to guarantee: stable ordering within a
single turn (a user message and the agent's reply can share a timestamp),
isolation between sessions, structured payload round-tripping, and the
cursor paging that keeps a long conversation from ever being loaded whole.
"""

import pytest

from app import message_store
from app.models.conversation import MessageKind, MessageRole


@pytest.fixture(autouse=True)
def _reset_messages():
    message_store.delete_all()


def test_append_and_list_preserves_order_within_a_turn():
    message_store.append("s1", MessageRole.AGENT, "Which state and city?")
    message_store.append("s1", MessageRole.USER, "Gujarat, Vadodara")
    message_store.append("s1", MessageRole.AGENT, "Thanks.")

    messages = message_store.list_for_session("s1")

    assert [(m.role, m.text) for m in messages] == [
        (MessageRole.AGENT, "Which state and city?"),
        (MessageRole.USER, "Gujarat, Vadodara"),
        (MessageRole.AGENT, "Thanks."),
    ]


def test_messages_are_isolated_per_session():
    message_store.append("s1", MessageRole.USER, "belongs to s1")
    message_store.append("s2", MessageRole.USER, "belongs to s2")

    assert [m.text for m in message_store.list_for_session("s1")] == ["belongs to s1"]
    assert [m.text for m in message_store.list_for_session("s2")] == ["belongs to s2"]


def test_structured_payload_round_trips():
    message_store.append(
        "s1",
        MessageRole.AGENT,
        kind=MessageKind.DOCUMENT_RESULT,
        payload={"file_name": "plan.pdf", "summary": {"tier_used": 2, "fields_extracted": ["height_m"]}},
    )

    [message] = message_store.list_for_session("s1")

    assert message.kind == MessageKind.DOCUMENT_RESULT
    assert message.text == ""
    assert message.payload["file_name"] == "plan.pdf"
    assert message.payload["summary"]["fields_extracted"] == ["height_m"]


def test_list_returns_the_most_recent_page_in_chronological_order():
    for index in range(10):
        message_store.append("s1", MessageRole.USER, f"message {index}")

    messages = message_store.list_for_session("s1", limit=3)

    # The newest three, still oldest-first - a user reopening a long
    # conversation needs where they left off, not where it started.
    assert [m.text for m in messages] == ["message 7", "message 8", "message 9"]


def test_before_id_pages_further_back():
    for index in range(10):
        message_store.append("s1", MessageRole.USER, f"message {index}")

    newest = message_store.list_for_session("s1", limit=3)
    older = message_store.list_for_session("s1", limit=3, before_id=newest[0].id)

    assert [m.text for m in older] == ["message 4", "message 5", "message 6"]


def test_list_for_unknown_session_is_empty():
    assert message_store.list_for_session("never-existed") == []
