"""Findings from the security review of the access-control surface.

Each of these failed against the code as it stood. They are grouped here
rather than scattered because what they have in common is the lesson: two
places that decide the same thing will drift, and a promise kept in one
endpoint can be broken by another.
"""

from __future__ import annotations

import statistics
import time

import pytest
from fastapi.testclient import TestClient

from app import grant_store, organisation_store, review_store
from app.auth import rate_limit
from app.auth.user_store import create_user, delete_all as delete_all_users, verify_credentials
from app.main import app
from app.message_store import append, delete_all as delete_all_messages, search
from app.models.case_file import OccupancyType
from app.models.conversation import MessageRole
from app.store import delete_all as delete_all_case_files

client = TestClient(app)

FLAGGED = {
    "occupancy_type": OccupancyType.INSTITUTIONAL.value,
    "height_m": 30.0,
    "built_up_area_sqm": 4000.0,
    "floors_above_ground": 10,
}


@pytest.fixture(autouse=True)
def _reset():
    delete_all_case_files()
    delete_all_messages()
    delete_all_users()
    grant_store.delete_all()
    organisation_store.delete_all()
    review_store.delete_all()
    rate_limit.reset()


def account(email: str) -> dict:
    body = client.post("/auth/signup", json={"email": email, "password": "correct-horse"}).json()
    return {"headers": {"Authorization": f"Bearer {body['access_token']}"}, "id": body["user"]["id"]}


class TestLoginDoesNotRevealWhoHasAnAccount:
    """`verify_credentials` short-circuited when the address was unknown, so
    bcrypt never ran: 311 ms against 0.3 ms, a thousandfold difference
    anybody can time from outside.

    It mattered here more than usual. /auth/password-reset/request answers
    204 whether or not the address has an account, specifically so it
    cannot be used to ask who uses the product - and for a compliance tool
    the client list is itself worth protecting. Leaking the same fact
    through a stopwatch on /auth/login made that promise worthless.
    """

    def _median_ms(self, email: str, rounds: int = 7) -> float:
        timings = []
        for _ in range(rounds):
            started = time.perf_counter()
            verify_credentials(email, "wrong-password-guess")
            timings.append((time.perf_counter() - started) * 1000)
        return statistics.median(timings)

    def test_a_failed_login_costs_the_same_either_way(self):
        create_user("real@example.com", "correct-horse")

        known = self._median_ms("real@example.com")
        unknown = self._median_ms("nobody@example.com")

        # Generous: the point is that one is not orders of magnitude
        # faster, not that a shared machine produces identical numbers.
        assert max(known, unknown) / min(known, unknown) < 3, (
            f"account existence is timeable: {known:.1f} ms vs {unknown:.1f} ms"
        )

    def test_the_real_check_still_works(self):
        # A constant-time failure that also fails on the right password
        # would be a very secure way of locking everyone out.
        create_user("real@example.com", "correct-horse")

        assert verify_credentials("real@example.com", "correct-horse") is not None
        assert verify_credentials("real@example.com", "wrong") is None
        assert verify_credentials("nobody@example.com", "correct-horse") is None


class TestOneDefinitionOfWhoCanRead:
    """`_check_access` honoured organisation membership from the day teams
    shipped; `can_record_verdict` was written before teams existed and
    still asked only about ownership and individual grants.

    So a team member assigned a case saw it in their queue, opened it, and
    found no verdict form - while the API would have accepted the verdict.
    That failed CLOSED, so it was a usability bug. The same two-definitions
    mistake failing open is a breach, which is why the fix was one function
    rather than a second expression.
    """

    def _team_case(self):
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
        session_id = client.post("/case-files", json=None, headers=owner["headers"]).json()[
            "session_id"
        ]
        client.put(f"/case-files/{session_id}", json=FLAGGED, headers=owner["headers"])
        client.post(f"/case-files/{session_id}/classify", headers=owner["headers"])
        client.post(
            f"/organisations/{org_id}/case-files",
            json={"session_id": session_id},
            headers=owner["headers"],
        )
        return owner, member, session_id

    def test_the_api_and_the_ui_agree_that_a_team_member_may_review(self):
        _, member, session_id = self._team_case()

        state = client.get(f"/case-files/{session_id}/review", headers=member["headers"]).json()
        recorded = client.post(
            f"/case-files/{session_id}/review",
            json={"status": "approved", "note": "Checked."},
            headers=member["headers"],
        )

        assert state["can_record_verdict"] is True
        assert recorded.status_code == 201

    def test_a_stranger_is_still_refused_outright(self):
        _, _, session_id = self._team_case()
        stranger = account("stranger@example.com")

        assert client.get(
            f"/case-files/{session_id}/review", headers=stranger["headers"]
        ).status_code == 403

    def test_reading_still_does_not_mean_writing(self):
        # The restriction is what makes the verdict worth anything, and
        # widening READ must not have widened WRITE with it.
        _, member, session_id = self._team_case()

        assert client.put(
            f"/case-files/{session_id}", json={"height_m": 99.0}, headers=member["headers"]
        ).status_code == 403


class TestSearchTreatsWhatYouTypedAsText:
    """The query is parameterised, so this was never an injection route.
    But `%` and `_` are LIKE metacharacters and were passed through
    unescaped: a search for "%%" matched every message the caller could
    reach, and a literal underscore matched any character. Wrong answers,
    and a cheap way to make the database scan everything you own.
    """

    def _corpus(self) -> list[str]:
        owner = account("owner@example.com")
        ids = []
        for name, said in [
            ("Alpha", "the atrium is large"),
            ("Beta", "nothing relevant"),
            ("Gamma", "coverage is 100% throughout"),
        ]:
            session_id = client.post("/case-files", json=None, headers=owner["headers"]).json()[
                "session_id"
            ]
            client.put(
                f"/case-files/{session_id}", json={"project_name": name}, headers=owner["headers"]
            )
            append(session_id, MessageRole.USER, said)
            ids.append(session_id)
        return ids

    def test_a_wildcard_no_longer_matches_everything(self):
        # "%%" used to match all three. Now it matches nothing, because no
        # message contains the literal text "%%".
        ids = self._corpus()

        assert search(ids, "%%") == {}

    def test_a_lone_percent_matches_only_text_containing_one(self):
        # Not "nothing" - that would be over-escaping. Exactly one of the
        # three messages mentions a percentage.
        ids = self._corpus()

        assert len(search(ids, "%")) == 1

    def test_an_underscore_is_a_literal_underscore(self):
        ids = self._corpus()

        assert search(ids, "a_rium") == {}

    def test_a_literal_percent_is_findable(self):
        # The escaping has to make "100%" work, not merely stop "%" working.
        ids = self._corpus()

        assert len(search(ids, "100%")) == 1

    def test_ordinary_searching_is_unaffected(self):
        ids = self._corpus()

        assert len(search(ids, "atrium")) == 1

    def test_sql_shaped_input_is_just_text(self):
        # It always was - the query is parameterised - and a test saying so
        # is what stops someone "optimising" that away later.
        ids = self._corpus()

        assert search(ids, "' OR 1=1 --") == {}
