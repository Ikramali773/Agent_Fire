"""Tests for Phase 3: sharing a case file with a reviewer, recording
verdicts, and the review queue.

Two rules carry most of the weight here:

1. A reviewer can READ and judge, and can change NOTHING. A verdict on
   facts the reviewer could have edited is worth nothing.
2. A verdict never rewrites the classification (Part G Principle 1). The
   engine decides; a person's opinion is recorded alongside it.
"""

import pytest
from fastapi.testclient import TestClient

from app import grant_store, review_store
from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.message_store import delete_all as delete_all_messages
from app.models.case_file import OccupancyType
from app.models.review import ReviewStatus
from app import change_log
from app.store import delete_all as delete_all_case_files

client = TestClient(app)

# A case the engine always flags: Institutional is mandatory review.
FLAGGED = {
    "occupancy_type": OccupancyType.INSTITUTIONAL.value,
    "height_m": 30.0,
    "built_up_area_sqm": 4000.0,
    "floors_above_ground": 10,
}
# A case the engine never flags.
CLEAN = {
    "occupancy_type": OccupancyType.RESIDENTIAL.value,
    "height_m": 12.0,
    "built_up_area_sqm": 400.0,
    "floors_above_ground": 4,
}


@pytest.fixture(autouse=True)
def _reset_store():
    delete_all_case_files()
    delete_all_messages()
    delete_all_users()
    change_log.delete_all()
    review_store.delete_all()
    grant_store.delete_all()


def _signup(email: str) -> dict:
    resp = client.post("/auth/signup", json={"email": email, "password": "correct-horse"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _headers(account: dict) -> dict:
    return {"Authorization": f"Bearer {account['access_token']}"}


def _project(account: dict, fields: dict = FLAGGED) -> str:
    headers = _headers(account)
    session_id = client.post("/case-files", json=None, headers=headers).json()["session_id"]
    client.put(f"/case-files/{session_id}", json=fields, headers=headers)
    client.post(f"/case-files/{session_id}/classify", headers=headers)
    return session_id


class TestSharing:
    def test_an_owner_can_share_with_another_account(self):
        owner = _signup("owner@example.com")
        reviewer = _signup("reviewer@example.com")
        session_id = _project(owner)

        resp = client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=_headers(owner),
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["granted_to_user_id"] == reviewer["user"]["id"]
        assert resp.json()["role"] == "reviewer"

    def test_sharing_is_case_insensitive_about_the_email(self):
        owner = _signup("owner@example.com")
        _signup("reviewer@example.com")
        session_id = _project(owner)

        resp = client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "REVIEWER@Example.com"},
            headers=_headers(owner),
        )

        assert resp.status_code == 201, resp.text

    def test_sharing_twice_is_the_same_grant_not_two(self):
        owner = _signup("owner@example.com")
        _signup("reviewer@example.com")
        session_id = _project(owner)
        body = {"email": "reviewer@example.com"}

        first = client.post(f"/case-files/{session_id}/shares", json=body, headers=_headers(owner))
        second = client.post(f"/case-files/{session_id}/shares", json=body, headers=_headers(owner))

        assert first.json()["id"] == second.json()["id"]
        assert len(client.get(f"/case-files/{session_id}/shares", headers=_headers(owner)).json()) == 1

    def test_sharing_with_an_address_that_has_no_account_is_an_honest_404(self):
        # Better than silently creating an account for someone, or
        # pretending it worked and never telling them.
        owner = _signup("owner@example.com")
        session_id = _project(owner)

        resp = client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "nobody@example.com"},
            headers=_headers(owner),
        )

        assert resp.status_code == 404
        assert "sign up" in resp.json()["detail"].lower()

    def test_you_cannot_share_a_project_with_yourself(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)

        resp = client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "owner@example.com"},
            headers=_headers(owner),
        )

        assert resp.status_code == 422

    def test_a_reviewer_cannot_share_the_project_onward(self):
        # The sharpest edge of the whole feature: a reviewer must never be
        # able to pass someone else's project to a third party.
        owner = _signup("owner@example.com")
        reviewer = _signup("reviewer@example.com")
        _signup("third@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=_headers(owner),
        )

        resp = client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "third@example.com"},
            headers=_headers(reviewer),
        )

        assert resp.status_code == 403

    def test_revoking_takes_effect_immediately(self):
        owner = _signup("owner@example.com")
        reviewer = _signup("reviewer@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=_headers(owner),
        )
        assert client.get(f"/case-files/{session_id}", headers=_headers(reviewer)).status_code == 200

        revoked = client.delete(
            f"/case-files/{session_id}/shares/{reviewer['user']['id']}", headers=_headers(owner)
        )

        assert revoked.status_code == 204
        assert client.get(f"/case-files/{session_id}", headers=_headers(reviewer)).status_code == 403

    def test_revoking_keeps_the_verdicts_that_were_already_recorded(self):
        # A review that happened, happened. Deleting the record of it
        # because access was withdrawn would make the history lie.
        owner = _signup("owner@example.com")
        reviewer = _signup("reviewer@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=_headers(owner),
        )
        client.post(
            f"/case-files/{session_id}/review",
            json={"status": "approved", "note": "Checked against the drawings."},
            headers=_headers(reviewer),
        )

        client.delete(
            f"/case-files/{session_id}/shares/{reviewer['user']['id']}", headers=_headers(owner)
        )

        state = client.get(f"/case-files/{session_id}/review", headers=_headers(owner)).json()
        assert state["status"] == "approved"
        assert state["events"][0]["actor_email"] == "reviewer@example.com"

    def test_a_stranger_can_neither_read_nor_share(self):
        owner = _signup("owner@example.com")
        stranger = _signup("stranger@example.com")
        session_id = _project(owner)

        assert client.get(f"/case-files/{session_id}", headers=_headers(stranger)).status_code == 403
        assert (
            client.get(f"/case-files/{session_id}/shares", headers=_headers(stranger)).status_code == 403
        )


class TestReviewerIsReadOnly:
    @pytest.fixture
    def shared(self):
        owner = _signup("owner@example.com")
        reviewer = _signup("reviewer@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=_headers(owner),
        )
        return owner, reviewer, session_id

    def test_a_reviewer_can_read_everything_they_need(self, shared):
        _owner, reviewer, session_id = shared
        headers = _headers(reviewer)

        assert client.get(f"/case-files/{session_id}", headers=headers).status_code == 200
        assert client.get(f"/case-files/{session_id}/messages", headers=headers).status_code == 200
        assert client.get(f"/case-files/{session_id}/changes", headers=headers).status_code == 200
        assert client.get(f"/case-files/{session_id}/report", headers=headers).status_code == 200
        assert client.get(f"/case-files/{session_id}/review", headers=headers).status_code == 200

    def test_a_reviewer_can_download_the_exports(self, shared):
        _owner, reviewer, session_id = shared
        headers = _headers(reviewer)

        assert client.get(f"/case-files/{session_id}/report.pdf", headers=headers).status_code == 200
        assert client.get(f"/case-files/{session_id}/report.docx", headers=headers).status_code == 200

    def test_a_reviewer_cannot_edit_the_facts(self, shared):
        # The point of the whole capability split: a verdict on facts the
        # reviewer could have changed is worth nothing.
        _owner, reviewer, session_id = shared

        resp = client.put(f"/case-files/{session_id}", json={"height_m": 9.0}, headers=_headers(reviewer))

        assert resp.status_code == 403

    def test_a_reviewer_cannot_continue_the_conversation(self, shared):
        _owner, reviewer, session_id = shared

        assert (
            client.post(
                f"/case-files/{session_id}/message", json={"message": "hi"}, headers=_headers(reviewer)
            ).status_code
            == 403
        )
        assert client.post(f"/case-files/{session_id}/start", headers=_headers(reviewer)).status_code == 403

    def test_a_reviewer_cannot_reclassify(self, shared):
        _owner, reviewer, session_id = shared

        assert (
            client.post(f"/case-files/{session_id}/classify", headers=_headers(reviewer)).status_code == 403
        )

    def test_a_reviewer_cannot_delete_the_project(self, shared):
        _owner, reviewer, session_id = shared

        assert client.delete(f"/case-files/{session_id}", headers=_headers(reviewer)).status_code == 403

    def test_a_reviewer_can_explore_a_what_if(self, shared):
        # Non-destructive by construction (never persisted), and asking
        # "what would change this answer" is exactly a reviewer's job.
        _owner, reviewer, session_id = shared

        resp = client.post(
            f"/case-files/{session_id}/what-if", json={"height_m": 80.0}, headers=_headers(reviewer)
        )

        assert resp.status_code == 200
        assert client.get(f"/case-files/{session_id}", headers=_headers(reviewer)).json()["height_m"] == 30.0


class TestRecordingVerdicts:
    def test_a_flagged_case_starts_as_needs_review_with_no_events(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)

        state = client.get(f"/case-files/{session_id}/review", headers=_headers(owner)).json()

        assert state["requires_review"] is True
        assert state["status"] == "needs_review"
        assert state["events"] == []
        assert state["reasons"][0]["code"] == "mandatory_occupancy"

    def test_recording_a_verdict_moves_the_status(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)

        resp = client.post(
            f"/case-files/{session_id}/review",
            json={"status": "approved", "note": "Fire officer signed off."},
            headers=_headers(owner),
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "approved"
        assert resp.json()["events"][0]["note"] == "Fire officer signed off."

    def test_the_verdict_never_rewrites_the_classification(self):
        # Load-bearing: Part G Principle 1. An approved case is still a
        # case the engine says needs a person.
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        before = client.get(f"/case-files/{session_id}", headers=_headers(owner)).json()

        client.post(
            f"/case-files/{session_id}/review",
            json={"status": "approved", "note": "Looks fine."},
            headers=_headers(owner),
        )

        after = client.get(f"/case-files/{session_id}", headers=_headers(owner)).json()
        assert after["classification_result"] == before["classification_result"]
        assert after["classification_result"]["require_human_review_flag"] is True

    def test_a_verdict_does_not_appear_in_the_field_change_log(self):
        # The change log tracks Case File facts. A review is not a fact
        # about the building, and mixing them would blur both.
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        before = client.get(f"/case-files/{session_id}/changes", headers=_headers(owner)).json()

        client.post(
            f"/case-files/{session_id}/review", json={"status": "approved"}, headers=_headers(owner)
        )

        assert client.get(f"/case-files/{session_id}/changes", headers=_headers(owner)).json() == before

    def test_the_whole_sequence_is_kept_not_just_the_latest(self):
        # Approved -> reopened -> approved is a different thing from
        # approved once, and only an append-only log can tell you which.
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        for status in ("in_review", "changes_requested", "approved"):
            client.post(
                f"/case-files/{session_id}/review", json={"status": status}, headers=_headers(owner)
            )

        state = client.get(f"/case-files/{session_id}/review", headers=_headers(owner)).json()

        assert [event["status"] for event in state["events"]] == [
            "in_review",
            "changes_requested",
            "approved",
        ]
        assert state["status"] == "approved"

    def test_needs_review_cannot_be_recorded_as_a_verdict(self):
        # It is derived from "no events yet", so accepting it would let a
        # review be silently rewound.
        owner = _signup("owner@example.com")
        session_id = _project(owner)

        resp = client.post(
            f"/case-files/{session_id}/review", json={"status": "needs_review"}, headers=_headers(owner)
        )

        assert resp.status_code == 422

    def test_an_unknown_status_is_rejected_with_the_valid_ones_listed(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)

        resp = client.post(
            f"/case-files/{session_id}/review", json={"status": "looks_good"}, headers=_headers(owner)
        )

        assert resp.status_code == 422
        assert "approved" in resp.json()["detail"]

    def test_the_reviewers_identity_is_recorded_with_the_verdict(self):
        owner = _signup("owner@example.com")
        reviewer = _signup("reviewer@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=_headers(owner),
        )

        client.post(
            f"/case-files/{session_id}/review", json={"status": "approved"}, headers=_headers(reviewer)
        )

        event = client.get(f"/case-files/{session_id}/review", headers=_headers(owner)).json()["events"][0]
        assert event["actor_user_id"] == reviewer["user"]["id"]
        assert event["actor_email"] == "reviewer@example.com"

    def test_a_stranger_cannot_record_a_verdict(self):
        owner = _signup("owner@example.com")
        stranger = _signup("stranger@example.com")
        session_id = _project(owner)

        resp = client.post(
            f"/case-files/{session_id}/review", json={"status": "approved"}, headers=_headers(stranger)
        )

        assert resp.status_code == 403

    def test_an_unflagged_case_can_still_be_reviewed_deliberately(self):
        # The engine not requiring review is not the same as review being
        # forbidden - an owner may want a second pair of eyes anyway.
        owner = _signup("owner@example.com")
        session_id = _project(owner, CLEAN)
        state = client.get(f"/case-files/{session_id}/review", headers=_headers(owner)).json()
        assert state["requires_review"] is False

        resp = client.post(
            f"/case-files/{session_id}/review", json={"status": "approved"}, headers=_headers(owner)
        )

        assert resp.status_code == 201

    def test_deleting_a_project_takes_its_review_history_and_shares_with_it(self):
        owner = _signup("owner@example.com")
        reviewer = _signup("reviewer@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=_headers(owner),
        )
        client.post(
            f"/case-files/{session_id}/review", json={"status": "approved"}, headers=_headers(owner)
        )

        assert client.delete(f"/case-files/{session_id}", headers=_headers(owner)).status_code == 204

        assert review_store.list_for_session(session_id) == []
        assert grant_store.list_for_session(session_id) == []


class TestReviewQueue:
    def test_only_flagged_cases_are_queued(self):
        owner = _signup("owner@example.com")
        flagged = _project(owner)
        _project(owner, CLEAN)

        queue = client.get("/users/me/review-queue", headers=_headers(owner)).json()

        assert [item["session_id"] for item in queue] == [flagged]

    def test_the_queue_is_oldest_first(self):
        # A compliance queue is FIFO: the case waiting longest is the one
        # most at risk of being forgotten. Opposite to the chat rail.
        owner = _signup("owner@example.com")
        first = _project(owner)
        second = _project(owner)

        queue = client.get("/users/me/review-queue", headers=_headers(owner)).json()

        assert [item["session_id"] for item in queue] == [first, second]

    def test_a_project_shared_with_me_appears_in_my_queue(self):
        owner = _signup("owner@example.com")
        reviewer = _signup("reviewer@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=_headers(owner),
        )

        queue = client.get("/users/me/review-queue", headers=_headers(reviewer)).json()

        assert [item["session_id"] for item in queue] == [session_id]
        assert queue[0]["is_owner"] is False

    def test_my_own_projects_are_marked_as_mine(self):
        owner = _signup("owner@example.com")
        _project(owner)

        queue = client.get("/users/me/review-queue", headers=_headers(owner)).json()

        assert queue[0]["is_owner"] is True

    def test_a_revoked_share_drops_out_of_the_reviewers_queue(self):
        owner = _signup("owner@example.com")
        reviewer = _signup("reviewer@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=_headers(owner),
        )

        client.delete(
            f"/case-files/{session_id}/shares/{reviewer['user']['id']}", headers=_headers(owner)
        )

        assert client.get("/users/me/review-queue", headers=_headers(reviewer)).json() == []

    def test_a_settled_case_leaves_the_queue(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/review", json={"status": "approved"}, headers=_headers(owner)
        )

        assert client.get("/users/me/review-queue", headers=_headers(owner)).json() == []

    def test_a_case_in_progress_stays_in_the_queue(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/review", json={"status": "in_review"}, headers=_headers(owner)
        )

        queue = client.get("/users/me/review-queue", headers=_headers(owner)).json()

        assert [item["status"] for item in queue] == ["in_review"]

    def test_changes_requested_stays_in_the_queue(self):
        # It is waiting on the owner, not finished.
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/review",
            json={"status": "changes_requested"},
            headers=_headers(owner),
        )

        assert len(client.get("/users/me/review-queue", headers=_headers(owner)).json()) == 1

    def test_settled_cases_can_be_asked_for_explicitly(self):
        owner = _signup("owner@example.com")
        session_id = _project(owner)
        client.post(
            f"/case-files/{session_id}/review", json={"status": "approved"}, headers=_headers(owner)
        )

        queue = client.get(
            "/users/me/review-queue?include_settled=true", headers=_headers(owner)
        ).json()

        assert [item["session_id"] for item in queue] == [session_id]

    def test_the_queue_carries_the_reason_codes_for_grouping(self):
        owner = _signup("owner@example.com")
        _project(owner)

        queue = client.get("/users/me/review-queue", headers=_headers(owner)).json()

        assert "mandatory_occupancy" in queue[0]["reason_codes"]
        assert queue[0]["reason_count"] >= 1

    def test_another_accounts_projects_never_appear(self):
        owner = _signup("owner@example.com")
        _project(owner)
        stranger = _signup("stranger@example.com")

        assert client.get("/users/me/review-queue", headers=_headers(stranger)).json() == []

    def test_the_queue_requires_authentication(self):
        assert client.get("/users/me/review-queue").status_code == 401


class TestAnonymousCaseFilesAreUnchanged:
    """Phase 1's model: no owner means open to anyone with the session id.
    Phase 3 must not have quietly narrowed or widened that.
    """

    def test_an_anonymous_case_file_is_still_fully_usable_with_no_account(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]

        assert client.put(f"/case-files/{session_id}", json=FLAGGED).status_code == 200
        assert client.post(f"/case-files/{session_id}/classify").status_code == 200
        assert client.get(f"/case-files/{session_id}/review").status_code == 200
        assert client.delete(f"/case-files/{session_id}").status_code == 204

    def test_an_anonymous_case_file_cannot_be_shared(self):
        # Nobody to share it as, and no owner for the grant to protect.
        session_id = client.post("/case-files", json=None).json()["session_id"]

        resp = client.post(f"/case-files/{session_id}/shares", json={"email": "a@example.com"})

        assert resp.status_code == 401

    def test_an_anonymous_case_file_can_be_reviewed_by_whoever_holds_its_id(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]
        client.put(f"/case-files/{session_id}", json=FLAGGED)
        client.post(f"/case-files/{session_id}/classify")

        resp = client.post(f"/case-files/{session_id}/review", json={"status": "approved"})

        assert resp.status_code == 201
        assert resp.json()["events"][0]["actor_user_id"] is None
