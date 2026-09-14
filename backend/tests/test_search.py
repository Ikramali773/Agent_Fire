"""Searching for a project by what was said in it.

Search matched the TITLE only - and a title is the first message verbatim -
so "that project where we discussed the atrium" still meant opening chats
one at a time. This looks inside the conversation.

The access rules matter more than the matching here: search is a way to
turn a word into a list of projects, and a search that reached past what
the caller may read would be a leak dressed up as a feature.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import grant_store, message_store, organisation_store
from app.auth import rate_limit
from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.message_store import delete_all as delete_all_messages
from app.models.conversation import MessageRole
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    delete_all_case_files()
    delete_all_messages()
    delete_all_users()
    grant_store.delete_all()
    organisation_store.delete_all()
    rate_limit.reset()


def account(email: str) -> dict:
    body = client.post("/auth/signup", json={"email": email, "password": "correct-horse"}).json()
    return {"headers": {"Authorization": f"Bearer {body['access_token']}"}, "id": body["user"]["id"]}


def project(owner: dict, name: str = "", said: str = "") -> str:
    session_id = client.post("/case-files", json=None, headers=owner["headers"]).json()["session_id"]
    if name:
        client.put(f"/case-files/{session_id}", json={"project_name": name}, headers=owner["headers"])
    if said:
        message_store.append(session_id, MessageRole.USER, said)
    return session_id


def search(who: dict, q: str) -> list[dict]:
    return client.get(f"/users/me/search?q={q}", headers=who["headers"]).json()


class TestFindingThings:
    def test_finds_a_project_by_something_said_in_it(self):
        # The whole point. This is the query the old title-only search
        # could never answer.
        owner = account("a@example.com")
        session_id = project(
            owner,
            "Tower B",
            "We talked at length about the atrium and its smoke control.",
        )

        hits = search(owner, "atrium")

        assert [hit["session_id"] for hit in hits] == [session_id]
        assert hits[0]["matched_in"] == "conversation"

    def test_the_snippet_shows_why_it_matched(self):
        owner = account("a@example.com")
        project(owner, "Tower B", "A long preamble about nothing much, then the atrium, then more.")

        assert "atrium" in search(owner, "atrium")[0]["snippet"]

    def test_finds_a_project_by_name(self):
        owner = account("a@example.com")
        session_id = project(owner, "Civic Hospital Wing")

        hits = search(owner, "hospital")

        assert [hit["session_id"] for hit in hits] == [session_id]
        assert hits[0]["matched_in"] == "name"

    def test_a_name_match_outranks_a_conversation_match(self):
        # If you typed the project's name, that is what you meant.
        owner = account("a@example.com")
        named = project(owner, "Atrium House")
        project(owner, "Other", "we discussed the atrium at length")

        hits = search(owner, "atrium")

        assert hits[0]["session_id"] == named

    def test_matching_is_case_insensitive(self):
        owner = account("a@example.com")
        project(owner, "Tower", "The ATRIUM needs smoke control.")

        assert len(search(owner, "atrium")) == 1

    def test_one_project_appears_once_however_often_it_matches(self):
        # A project that mentions the word forty times is not forty hits.
        owner = account("a@example.com")
        session_id = project(owner, "Tower", "atrium")
        for _ in range(5):
            message_store.append(session_id, MessageRole.USER, "more about the atrium")

        assert len(search(owner, "atrium")) == 1

    def test_a_project_matching_both_name_and_conversation_appears_once(self):
        owner = account("a@example.com")
        project(owner, "Atrium House", "and we discussed the atrium")

        hits = search(owner, "atrium")

        assert len(hits) == 1
        assert hits[0]["matched_in"] == "name"


class TestWhatSearchCanReach:
    def test_never_reaches_another_account_s_project(self):
        # A search that reached past what the caller may read would be a
        # leak dressed up as a feature.
        owner = account("owner@example.com")
        stranger = account("stranger@example.com")
        project(owner, "Secret Tower", "the atrium is enormous")

        assert search(stranger, "atrium") == []
        assert search(stranger, "secret") == []

    def test_reaches_a_project_shared_with_me(self):
        owner = account("owner@example.com")
        reviewer = account("reviewer@example.com")
        session_id = project(owner, "Tower", "the atrium is enormous")
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=owner["headers"],
        )

        assert [hit["session_id"] for hit in search(reviewer, "atrium")] == [session_id]

    def test_reaches_a_project_shared_with_my_team(self):
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
        session_id = project(owner, "Tower", "the atrium is enormous")
        client.post(
            f"/organisations/{org_id}/case-files",
            json={"session_id": session_id},
            headers=owner["headers"],
        )

        assert [hit["session_id"] for hit in search(member, "atrium")] == [session_id]

    def test_stops_reaching_it_when_i_leave_the_team(self):
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
        session_id = project(owner, "Tower", "the atrium is enormous")
        client.post(
            f"/organisations/{org_id}/case-files",
            json={"session_id": session_id},
            headers=owner["headers"],
        )

        client.delete(f"/organisations/{org_id}/members/{member['id']}", headers=member["headers"])

        assert search(member, "atrium") == []

    def test_search_needs_an_account(self):
        assert client.get("/users/me/search?q=atrium").status_code == 401


class TestTheEdges:
    def test_a_one_character_query_is_refused(self):
        # Every project would match, which is not a search.
        owner = account("a@example.com")

        assert client.get("/users/me/search?q=a", headers=owner["headers"]).status_code == 422

    def test_no_match_is_an_empty_list_not_an_error(self):
        owner = account("a@example.com")
        project(owner, "Tower", "nothing relevant")

        assert search(owner, "atrium") == []

    def test_results_are_capped(self):
        owner = account("a@example.com")
        for index in range(8):
            project(owner, f"Tower {index}", "the atrium again")

        hits = client.get("/users/me/search?q=atrium&limit=3", headers=owner["headers"]).json()

        assert len(hits) == 3

    def test_an_unnamed_project_still_reads_as_something(self):
        owner = account("a@example.com")
        project(owner, said="the atrium is enormous")

        assert search(owner, "atrium")[0]["project_name"] == "Untitled project"
