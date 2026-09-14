"""Organisations, team projects, and review assignment - Phase 4.

Sharing was one project to one person at a time. Six colleagues and forty
projects meant two hundred and forty shares, and someone leaving meant
remembering all of them.

The access rules are the risky part of this feature, so most of what
follows is about what an organisation does NOT let you do. A team makes a
project easier to reach; it must not make it easier to change, and being
able to administer a team must not become a way to reach its members'
other work.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import assignment_store, grant_store, organisation_store, preferences_store, review_store
from app import change_log
from app.auth import rate_limit
from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.models.case_file import OccupancyType
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
    delete_all_users()
    organisation_store.delete_all()
    assignment_store.delete_all()
    grant_store.delete_all()
    review_store.delete_all()
    preferences_store.delete_all()
    change_log.delete_all()
    rate_limit.reset()


def account(email: str) -> dict:
    body = client.post("/auth/signup", json={"email": email, "password": "correct-horse"}).json()
    return {"headers": {"Authorization": f"Bearer {body['access_token']}"}, "id": body["user"]["id"]}


def make_org(owner: dict, name: str = "Safal Fire Consultants") -> str:
    return client.post("/organisations", json={"name": name}, headers=owner["headers"]).json()["id"]


def make_project(owner: dict, flagged: bool = False) -> str:
    session_id = client.post("/case-files", json=None, headers=owner["headers"]).json()["session_id"]
    if flagged:
        client.put(f"/case-files/{session_id}", json=FLAGGED, headers=owner["headers"])
        client.post(f"/case-files/{session_id}/classify", headers=owner["headers"])
    return session_id


class TestCreatingATeam:
    def test_the_creator_is_its_first_administrator(self):
        # An organisation with no members is unreachable: nobody could add
        # themselves to it, so it would be an orphan nobody can delete.
        owner = account("owner@example.com")

        org_id = make_org(owner)

        members = client.get(f"/organisations/{org_id}/members", headers=owner["headers"]).json()
        assert [m["email"] for m in members] == ["owner@example.com"]
        assert members[0]["role"] == "admin"

    def test_a_team_needs_a_name(self):
        owner = account("owner@example.com")

        assert client.post("/organisations", json={"name": "   "}, headers=owner["headers"]).status_code == 422

    def test_my_teams_lists_only_mine(self):
        owner = account("owner@example.com")
        stranger = account("stranger@example.com")
        make_org(owner)

        assert client.get("/organisations", headers=stranger["headers"]).json() == []

    def test_a_non_member_cannot_tell_the_team_exists(self):
        # A 404 rather than a 403, deliberately: whether an organisation
        # exists is itself something only its members should learn.
        owner = account("owner@example.com")
        stranger = account("stranger@example.com")
        org_id = make_org(owner)

        resp = client.get(f"/organisations/{org_id}/members", headers=stranger["headers"])

        assert resp.status_code == 404


class TestMembership:
    def test_an_admin_adds_a_colleague(self):
        owner = account("owner@example.com")
        account("colleague@example.com")
        org_id = make_org(owner)

        resp = client.post(
            f"/organisations/{org_id}/members",
            json={"email": "colleague@example.com"},
            headers=owner["headers"],
        )

        assert resp.status_code == 201
        assert resp.json()["role"] == "member"

    def test_adding_someone_without_an_account_says_so(self):
        # Silently creating an account for someone is worse than an honest
        # 404, and there is no mail transport here to invite them through.
        owner = account("owner@example.com")
        org_id = make_org(owner)

        resp = client.post(
            f"/organisations/{org_id}/members",
            json={"email": "nobody@example.com"},
            headers=owner["headers"],
        )

        assert resp.status_code == 404
        assert "need to sign up" in resp.json()["detail"]

    def test_a_plain_member_cannot_add_anyone(self):
        owner = account("owner@example.com")
        member = account("member@example.com")
        account("third@example.com")
        org_id = make_org(owner)
        client.post(
            f"/organisations/{org_id}/members",
            json={"email": "member@example.com"},
            headers=owner["headers"],
        )

        resp = client.post(
            f"/organisations/{org_id}/members",
            json={"email": "third@example.com"},
            headers=member["headers"],
        )

        assert resp.status_code == 403

    def test_adding_the_same_person_twice_is_not_an_error(self):
        owner = account("owner@example.com")
        account("colleague@example.com")
        org_id = make_org(owner)
        body = {"email": "colleague@example.com"}

        client.post(f"/organisations/{org_id}/members", json=body, headers=owner["headers"])
        second = client.post(f"/organisations/{org_id}/members", json=body, headers=owner["headers"])

        assert second.status_code == 201
        assert len(client.get(f"/organisations/{org_id}/members", headers=owner["headers"]).json()) == 2

    def test_re_adding_an_admin_does_not_quietly_demote_them(self):
        owner = account("owner@example.com")
        colleague = account("colleague@example.com")
        org_id = make_org(owner)
        client.post(
            f"/organisations/{org_id}/members",
            json={"email": "colleague@example.com", "role": "admin"},
            headers=owner["headers"],
        )

        client.post(
            f"/organisations/{org_id}/members",
            json={"email": "colleague@example.com", "role": "member"},
            headers=owner["headers"],
        )

        assert organisation_store.get_member(org_id, colleague["id"]).role.value == "admin"

    def test_the_creator_cannot_be_demoted(self):
        # An organisation whose last administrator demoted themselves is
        # one nobody can add a member to or delete, and there is no
        # support desk here to unstick it.
        owner = account("owner@example.com")
        org_id = make_org(owner)

        resp = client.patch(
            f"/organisations/{org_id}/members/{owner['id']}",
            json={"role": "member"},
            headers=owner["headers"],
        )

        assert resp.status_code == 422

    def test_the_creator_cannot_be_removed(self):
        owner = account("owner@example.com")
        org_id = make_org(owner)

        resp = client.delete(
            f"/organisations/{org_id}/members/{owner['id']}", headers=owner["headers"]
        )

        assert resp.status_code == 422

    def test_anyone_may_leave_of_their_own_accord(self):
        owner = account("owner@example.com")
        member = account("member@example.com")
        org_id = make_org(owner)
        client.post(
            f"/organisations/{org_id}/members",
            json={"email": "member@example.com"},
            headers=owner["headers"],
        )

        resp = client.delete(
            f"/organisations/{org_id}/members/{member['id']}", headers=member["headers"]
        )

        assert resp.status_code == 204
        assert client.get("/organisations", headers=member["headers"]).json() == []

    def test_a_member_cannot_remove_someone_else(self):
        owner = account("owner@example.com")
        member = account("member@example.com")
        other = account("other@example.com")
        org_id = make_org(owner)
        for email in ("member@example.com", "other@example.com"):
            client.post(
                f"/organisations/{org_id}/members", json={"email": email}, headers=owner["headers"]
            )

        resp = client.delete(
            f"/organisations/{org_id}/members/{other['id']}", headers=member["headers"]
        )

        assert resp.status_code == 403


class TestTeamProjects:
    def _team_with_a_project(self):
        owner = account("owner@example.com")
        member = account("member@example.com")
        org_id = make_org(owner)
        client.post(
            f"/organisations/{org_id}/members",
            json={"email": "member@example.com"},
            headers=owner["headers"],
        )
        session_id = make_project(owner)
        client.post(
            f"/organisations/{org_id}/case-files",
            json={"session_id": session_id},
            headers=owner["headers"],
        )
        return owner, member, org_id, session_id

    def test_a_member_can_read_a_project_shared_with_the_team(self):
        # The whole point: one share reaches everyone, instead of one per
        # person per project.
        _, member, _, session_id = self._team_with_a_project()

        assert client.get(f"/case-files/{session_id}", headers=member["headers"]).status_code == 200

    def test_a_member_cannot_edit_it(self):
        # A verdict on facts the reviewer could have edited is worth
        # nothing, and that does not stop being true because the reviewer
        # is a colleague.
        _, member, _, session_id = self._team_with_a_project()

        assert client.put(
            f"/case-files/{session_id}", json={"height_m": 99.0}, headers=member["headers"]
        ).status_code == 403

    def test_a_member_cannot_delete_it(self):
        _, member, _, session_id = self._team_with_a_project()

        assert client.delete(f"/case-files/{session_id}", headers=member["headers"]).status_code == 403

    def test_a_member_cannot_share_it_onward(self):
        _, member, _, session_id = self._team_with_a_project()

        assert client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "member@example.com"},
            headers=member["headers"],
        ).status_code == 403

    def test_a_member_can_still_record_a_verdict(self):
        # READ includes recording a verdict - the one thing a reviewer adds.
        _, member, _, session_id = self._team_with_a_project()

        resp = client.post(
            f"/case-files/{session_id}/review",
            json={"status": "approved", "note": "Checked the drawings."},
            headers=member["headers"],
        )

        assert resp.status_code == 201
        assert resp.json()["status"] == "approved"

    def test_only_the_owner_can_put_a_project_into_a_team(self):
        # Being able to administer a team must never become a way to pull
        # in projects belonging to its members.
        owner, member, org_id, _ = self._team_with_a_project()
        theirs = make_project(member)

        resp = client.post(
            f"/organisations/{org_id}/case-files",
            json={"session_id": theirs},
            headers=owner["headers"],
        )

        assert resp.status_code == 403

    def test_removing_a_member_takes_away_every_project_at_once(self):
        # The reason to have a team at all: one step, not forty.
        owner, member, org_id, session_id = self._team_with_a_project()
        second = make_project(owner)
        client.post(
            f"/organisations/{org_id}/case-files",
            json={"session_id": second},
            headers=owner["headers"],
        )
        assert client.get(f"/case-files/{second}", headers=member["headers"]).status_code == 200

        client.delete(f"/organisations/{org_id}/members/{member['id']}", headers=owner["headers"])

        assert client.get(f"/case-files/{session_id}", headers=member["headers"]).status_code == 403
        assert client.get(f"/case-files/{second}", headers=member["headers"]).status_code == 403

    def test_deleting_the_team_leaves_the_projects_alone(self):
        # An organisation is a way of sharing work, never where it lives.
        owner, member, org_id, session_id = self._team_with_a_project()

        assert client.delete(f"/organisations/{org_id}", headers=owner["headers"]).status_code == 204

        assert client.get(f"/case-files/{session_id}", headers=owner["headers"]).status_code == 200
        assert client.get(f"/case-files/{session_id}", headers=member["headers"]).status_code == 403

    def test_only_the_creator_can_delete_the_team(self):
        # An administrator added later can manage the team; dissolving it
        # is not theirs to do.
        owner, member, org_id, _ = self._team_with_a_project()
        client.patch(
            f"/organisations/{org_id}/members/{member['id']}",
            json={"role": "admin"},
            headers=owner["headers"],
        )

        assert client.delete(f"/organisations/{org_id}", headers=member["headers"]).status_code == 403

    def test_a_team_s_projects_are_listed_by_name(self):
        # This returned bare session ids, so the Team page could say how
        # many projects a team held but not which - a list of uuids being
        # no use to anyone.
        owner, _, org_id, session_id = self._team_with_a_project()
        client.put(
            f"/case-files/{session_id}",
            json={"project_name": "Civic Hospital Wing"},
            headers=owner["headers"],
        )

        rows = client.get(f"/organisations/{org_id}/case-files", headers=owner["headers"]).json()

        assert [row["project_name"] for row in rows] == ["Civic Hospital Wing"]
        assert rows[0]["session_id"] == session_id

    def test_an_unnamed_project_still_reads_as_something(self):
        owner, _, org_id, _ = self._team_with_a_project()

        rows = client.get(f"/organisations/{org_id}/case-files", headers=owner["headers"]).json()

        assert rows[0]["project_name"] == "Untitled project"

    def test_the_list_says_which_projects_are_flagged(self):
        # What makes a row worth looking at first.
        owner, _, org_id, _ = self._team_with_a_project()
        flagged_id = make_project(owner, flagged=True)
        client.post(
            f"/organisations/{org_id}/case-files",
            json={"session_id": flagged_id},
            headers=owner["headers"],
        )

        rows = client.get(f"/organisations/{org_id}/case-files", headers=owner["headers"]).json()

        by_id = {row["session_id"]: row["requires_review"] for row in rows}
        assert by_id[flagged_id] is True

    def test_a_member_sees_the_same_list_as_the_owner(self):
        owner, member, org_id, _ = self._team_with_a_project()

        theirs = client.get(f"/organisations/{org_id}/case-files", headers=member["headers"]).json()
        ours = client.get(f"/organisations/{org_id}/case-files", headers=owner["headers"]).json()

        assert theirs == ours

    def test_a_stranger_cannot_list_a_team_s_projects(self):
        _, _, org_id, _ = self._team_with_a_project()
        stranger = account("stranger@example.com")

        assert client.get(
            f"/organisations/{org_id}/case-files", headers=stranger["headers"]
        ).status_code == 404

    def test_deleting_a_project_unlinks_it_from_its_team(self):
        owner, _, org_id, session_id = self._team_with_a_project()

        client.delete(f"/case-files/{session_id}", headers=owner["headers"])

        assert client.get(
            f"/organisations/{org_id}/case-files", headers=owner["headers"]
        ).json() == []


class TestAssignment:
    def _assignable(self):
        owner = account("owner@example.com")
        member = account("member@example.com")
        org_id = make_org(owner)
        client.post(
            f"/organisations/{org_id}/members",
            json={"email": "member@example.com"},
            headers=owner["headers"],
        )
        session_id = make_project(owner, flagged=True)
        client.post(
            f"/organisations/{org_id}/case-files",
            json={"session_id": session_id},
            headers=owner["headers"],
        )
        return owner, member, org_id, session_id

    def test_a_case_starts_unassigned(self):
        owner, _, _, session_id = self._assignable()

        assert client.get(
            f"/case-files/{session_id}/assignment", headers=owner["headers"]
        ).json() is None

    def test_the_owner_assigns_a_colleague_with_a_due_date(self):
        owner, member, _, session_id = self._assignable()
        due = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

        resp = client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": member["id"], "due_at": due, "note": "Second pair of eyes"},
            headers=owner["headers"],
        )

        assert resp.status_code == 201
        assert resp.json()["assigned_to_email"] == "member@example.com"
        assert resp.json()["note"] == "Second pair of eyes"

    def test_a_case_cannot_be_assigned_to_someone_who_cannot_see_it(self):
        # Assignment must never become a back door to access: it would
        # bypass both the owner-only share rule and the team it goes
        # through.
        owner, _, _, session_id = self._assignable()
        stranger = account("stranger@example.com")

        resp = client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": stranger["id"]},
            headers=owner["headers"],
        )

        assert resp.status_code == 422
        assert client.get(f"/case-files/{session_id}", headers=stranger["headers"]).status_code == 403

    def test_a_plain_member_cannot_assign(self):
        # Being able to read a case is not the same as being able to hand
        # it to a colleague.
        _, member, _, session_id = self._assignable()

        resp = client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": member["id"]},
            headers=member["headers"],
        )

        assert resp.status_code == 403

    def test_a_team_admin_can_assign(self):
        owner, member, org_id, session_id = self._assignable()
        client.patch(
            f"/organisations/{org_id}/members/{member['id']}",
            json={"role": "admin"},
            headers=owner["headers"],
        )

        resp = client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": member["id"]},
            headers=member["headers"],
        )

        assert resp.status_code == 201

    def test_reassignment_is_recorded_rather_than_overwritten(self):
        # A case reassigned twice reads differently from one assigned
        # once, and in a compliance record that difference is the point.
        owner, member, _, session_id = self._assignable()
        client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": owner["id"]},
            headers=owner["headers"],
        )
        client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": member["id"]},
            headers=owner["headers"],
        )

        history = client.get(
            f"/case-files/{session_id}/assignment/history", headers=owner["headers"]
        ).json()

        assert [item["assigned_to_email"] for item in history] == [
            "owner@example.com",
            "member@example.com",
        ]

    def test_unassigning_is_its_own_recorded_act(self):
        # Not the absence of a row - a deliberate decision, kept.
        owner, member, _, session_id = self._assignable()
        client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": member["id"]},
            headers=owner["headers"],
        )

        client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": None},
            headers=owner["headers"],
        )

        current = client.get(
            f"/case-files/{session_id}/assignment", headers=owner["headers"]
        ).json()
        assert current["assigned_to_user_id"] is None
        assert len(
            client.get(
                f"/case-files/{session_id}/assignment/history", headers=owner["headers"]
            ).json()
        ) == 2

    def test_a_stranger_cannot_read_who_a_case_is_assigned_to(self):
        owner, _, _, session_id = self._assignable()
        stranger = account("stranger@example.com")

        assert client.get(
            f"/case-files/{session_id}/assignment", headers=stranger["headers"]
        ).status_code == 403


class TestTheQueue:
    def _flagged_team_case(self):
        owner = account("owner@example.com")
        member = account("member@example.com")
        org_id = make_org(owner)
        client.post(
            f"/organisations/{org_id}/members",
            json={"email": "member@example.com"},
            headers=owner["headers"],
        )
        session_id = make_project(owner, flagged=True)
        client.post(
            f"/organisations/{org_id}/case-files",
            json={"session_id": session_id},
            headers=owner["headers"],
        )
        return owner, member, session_id

    def test_a_team_project_reaches_the_member_s_queue(self):
        _, member, session_id = self._flagged_team_case()

        queue = client.get("/users/me/review-queue", headers=member["headers"]).json()

        assert [item["session_id"] for item in queue] == [session_id]
        assert queue[0]["is_owner"] is False

    def test_the_queue_says_what_is_assigned_to_me(self):
        owner, member, session_id = self._flagged_team_case()
        client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": member["id"]},
            headers=owner["headers"],
        )

        mine = client.get("/users/me/review-queue", headers=member["headers"]).json()
        theirs = client.get("/users/me/review-queue", headers=owner["headers"]).json()

        assert mine[0]["assigned_to_me"] is True
        assert theirs[0]["assigned_to_me"] is False
        assert theirs[0]["assignment"]["assigned_to_email"] == "member@example.com"

    def test_a_case_past_its_due_date_is_flagged_overdue(self):
        owner, member, session_id = self._flagged_team_case()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": member["id"], "due_at": past},
            headers=owner["headers"],
        )

        queue = client.get("/users/me/review-queue", headers=member["headers"]).json()

        assert queue[0]["is_overdue"] is True

    def test_a_case_still_within_its_due_date_is_not(self):
        owner, member, session_id = self._flagged_team_case()
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": member["id"], "due_at": future},
            headers=owner["headers"],
        )

        queue = client.get("/users/me/review-queue", headers=member["headers"]).json()

        assert queue[0]["is_overdue"] is False

    def test_a_settled_case_is_never_overdue(self):
        # It is done, not late. Saying otherwise would leave permanent red
        # rows nobody can clear.
        owner, member, session_id = self._flagged_team_case()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        client.post(
            f"/case-files/{session_id}/assignment",
            json={"assigned_to_user_id": member["id"], "due_at": past},
            headers=owner["headers"],
        )
        client.post(
            f"/case-files/{session_id}/review",
            json={"status": "approved", "note": "Done."},
            headers=member["headers"],
        )

        queue = client.get(
            "/users/me/review-queue?include_settled=true", headers=member["headers"]
        ).json()

        assert queue[0]["status"] == "approved"
        assert queue[0]["is_overdue"] is False

    def test_leaving_the_team_empties_the_queue(self):
        owner, member, session_id = self._flagged_team_case()
        org_id = client.get("/organisations", headers=member["headers"]).json()[0]["organisation"]["id"]

        client.delete(f"/organisations/{org_id}/members/{member['id']}", headers=member["headers"])

        assert client.get("/users/me/review-queue", headers=member["headers"]).json() == []
