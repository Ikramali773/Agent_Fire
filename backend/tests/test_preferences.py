"""Per-user preferences, and the one thing they exist for so far.

A pinned chat was per-browser state because there was nowhere else to put
it - the Case File schema is fixed, and a pin on a shared record would be
one account's preference riding on everyone's data. That was documented as
a limitation rather than hidden; this is the store that removes it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import preferences_store
from app.auth import rate_limit
from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.models.preferences import MAX_PINNED, UserPreferences
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    delete_all_case_files()
    delete_all_users()
    preferences_store.delete_all()
    rate_limit.reset()


def _account(email: str = "a@example.com") -> dict:
    token = client.post(
        "/auth/signup", json={"email": email, "password": "correct-horse"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestTheEndpoints:
    def test_an_account_that_has_never_set_anything_gets_defaults(self):
        # Not a 404. "Never set a preference" is the normal state for a new
        # account, and making the frontend special-case it buys nothing.
        resp = client.get("/users/me/preferences", headers=_account())

        assert resp.status_code == 200
        assert resp.json()["pinned_session_ids"] == []

    def test_preferences_survive_a_round_trip(self):
        headers = _account()

        client.put(
            "/users/me/preferences", json={"pinned_session_ids": ["a", "b"]}, headers=headers
        )

        assert client.get("/users/me/preferences", headers=headers).json()[
            "pinned_session_ids"
        ] == ["a", "b"]

    def test_a_second_browser_sees_the_same_pins(self):
        # The whole point. A second TestClient is a second browser: no
        # shared localStorage, only the account.
        headers = _account()
        client.put("/users/me/preferences", json={"pinned_session_ids": ["x"]}, headers=headers)

        elsewhere = TestClient(app)
        resp = elsewhere.get("/users/me/preferences", headers=headers)

        assert resp.json()["pinned_session_ids"] == ["x"]

    def test_one_account_cannot_see_another_s_preferences(self):
        first = _account("first@example.com")
        second = _account("second@example.com")
        client.put("/users/me/preferences", json={"pinned_session_ids": ["mine"]}, headers=first)

        assert client.get("/users/me/preferences", headers=second).json()["pinned_session_ids"] == []

    def test_preferences_need_an_account(self):
        # There is nothing to attach a preference to without one, and an
        # anonymous session keeps using the browser's own storage.
        assert client.get("/users/me/preferences").status_code == 401
        assert client.put("/users/me/preferences", json={"pinned_session_ids": []}).status_code == 401

    def test_a_replace_returns_what_was_actually_stored(self):
        # Not what was sent. A caller that echoed its own request back
        # would drift out of step the moment the server trimmed anything.
        headers = _account()

        resp = client.put(
            "/users/me/preferences", json={"pinned_session_ids": ["a", "a", "b"]}, headers=headers
        )

        assert resp.json()["pinned_session_ids"] == ["a", "b"]


class TestTheRowStaysSane:
    def test_duplicates_are_dropped_and_order_is_kept(self):
        stored = preferences_store.save(
            "u1", UserPreferences(pinned_session_ids=["c", "a", "c", "b", "a"])
        )

        assert stored.pinned_session_ids == ["c", "a", "b"]

    def test_the_list_is_capped(self):
        stored = preferences_store.save(
            "u1", UserPreferences(pinned_session_ids=[f"s{i}" for i in range(MAX_PINNED + 50)])
        )

        assert len(stored.pinned_session_ids) == MAX_PINNED

    def test_empty_ids_are_ignored(self):
        stored = preferences_store.save("u1", UserPreferences(pinned_session_ids=["", "a"]))

        assert stored.pinned_session_ids == ["a"]

    def test_saving_twice_replaces_rather_than_appends(self):
        preferences_store.save("u1", UserPreferences(pinned_session_ids=["a"]))
        preferences_store.save("u1", UserPreferences(pinned_session_ids=["b"]))

        assert preferences_store.get("u1").pinned_session_ids == ["b"]


class TestDeletingAProjectClearsItsPin:
    def test_a_deleted_project_is_unpinned_everywhere(self):
        # Without this a pin outlives the project it points at, and the
        # list grows forever with ids that resolve to nothing.
        headers = _account()
        session_id = client.post("/case-files", json=None, headers=headers).json()["session_id"]
        client.put(
            "/users/me/preferences",
            json={"pinned_session_ids": [session_id, "kept"]},
            headers=headers,
        )

        client.delete(f"/case-files/{session_id}", headers=headers)

        assert client.get("/users/me/preferences", headers=headers).json()[
            "pinned_session_ids"
        ] == ["kept"]

    def test_another_account_s_pins_are_untouched(self):
        owner = _account("owner@example.com")
        other = _account("other@example.com")
        session_id = client.post("/case-files", json=None, headers=owner).json()["session_id"]
        client.put(
            "/users/me/preferences", json={"pinned_session_ids": [session_id]}, headers=owner
        )
        client.put("/users/me/preferences", json={"pinned_session_ids": ["theirs"]}, headers=other)

        client.delete(f"/case-files/{session_id}", headers=owner)

        assert client.get("/users/me/preferences", headers=other).json()["pinned_session_ids"] == [
            "theirs"
        ]


class TestAPinIsNotAccess:
    def test_pinning_a_project_you_cannot_see_grants_nothing(self):
        # Ids only. The projects themselves still go through every
        # ordinary access check, so a pin can never become a back door.
        owner = _account("owner@example.com")
        stranger = _account("stranger@example.com")
        session_id = client.post("/case-files", json=None, headers=owner).json()["session_id"]

        client.put(
            "/users/me/preferences", json={"pinned_session_ids": [session_id]}, headers=stranger
        )

        assert client.get(f"/case-files/{session_id}", headers=stranger).status_code == 403
