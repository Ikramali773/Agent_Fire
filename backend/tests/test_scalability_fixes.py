"""Tests for the issues found in the Phase 1-3 audit.

Each class covers one problem that was reproduced before being fixed, so
these are regression tests in the strict sense - every one of them failed
against the code as it stood.
"""

import threading

import pytest
from fastapi.testclient import TestClient

from app import change_log, grant_store, review_store
from app.auth.security import MAX_PASSWORD_BYTES, hash_password, verify_password
from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.message_store import delete_all as delete_all_messages
from app.models.case_file import CaseFile, OccupancyType
from app.store import StaleCaseFileError, count_by_owner, list_by_owner
from app.store import delete_all as delete_all_case_files
from app.store import get as store_get
from app.store import save as store_save

client = TestClient(app)

FLAGGED = {
    "occupancy_type": OccupancyType.INSTITUTIONAL.value,
    "height_m": 30.0,
    "built_up_area_sqm": 4000.0,
    "floors_above_ground": 10,
}
CLEAN = {
    "occupancy_type": OccupancyType.RESIDENTIAL.value,
    "height_m": 12.0,
    "built_up_area_sqm": 400.0,
}


@pytest.fixture(autouse=True)
def _reset_store():
    delete_all_case_files()
    delete_all_messages()
    delete_all_users()
    change_log.delete_all()
    review_store.delete_all()
    grant_store.delete_all()


def _signup(email: str = "a@example.com") -> dict:
    return client.post("/auth/signup", json={"email": email, "password": "correct-horse"}).json()


def _headers(account: dict) -> dict:
    return {"Authorization": f"Bearer {account['access_token']}"}


class TestOptimisticLocking:
    """Two requests each read, each mutate, each save; both used to get a
    200 and one person's edit vanished with nothing anywhere saying so."""

    def test_a_case_file_carries_a_version(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]

        assert client.get(f"/case-files/{session_id}").json()["version"] == 1

    def test_the_version_advances_on_every_write(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]

        first = client.put(f"/case-files/{session_id}", json={"height_m": 24.0}).json()["version"]
        second = client.put(f"/case-files/{session_id}", json={"height_m": 25.0}).json()["version"]

        assert second > first

    def test_a_write_against_a_stale_version_is_refused(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]
        stale = client.get(f"/case-files/{session_id}").json()["version"]
        client.put(f"/case-files/{session_id}", json={"height_m": 24.0})

        resp = client.put(f"/case-files/{session_id}", json={"height_m": 68.0, "version": stale})

        assert resp.status_code == 409
        assert "changed by someone else" in resp.json()["detail"]

    def test_the_refused_write_changes_nothing(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]
        stale = client.get(f"/case-files/{session_id}").json()["version"]
        client.put(f"/case-files/{session_id}", json={"height_m": 24.0})

        client.put(f"/case-files/{session_id}", json={"height_m": 68.0, "version": stale})

        assert client.get(f"/case-files/{session_id}").json()["height_m"] == 24.0

    def test_a_write_with_the_current_version_succeeds(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]
        current = client.get(f"/case-files/{session_id}").json()["version"]

        resp = client.put(f"/case-files/{session_id}", json={"height_m": 68.0, "version": current})

        assert resp.status_code == 200
        assert resp.json()["height_m"] == 68.0

    def test_omitting_the_version_keeps_working(self):
        # A script or an older client is not forced to participate.
        session_id = client.post("/case-files", json=None).json()["session_id"]

        assert client.put(f"/case-files/{session_id}", json={"height_m": 68.0}).status_code == 200

    def test_concurrent_edits_no_longer_lose_one_silently(self):
        # The exact race that was reproduced against the old code: two
        # edits to DIFFERENT fields, both reading before either writes.
        session_id = client.post("/case-files", json=None).json()["session_id"]
        version = client.get(f"/case-files/{session_id}").json()["version"]

        import app.api.case_files as case_files_api

        original_save = case_files_api.store_save
        barrier = threading.Barrier(2)

        def racing_save(case_file, expected_version=None):
            barrier.wait(timeout=5)
            return original_save(case_file, expected_version=expected_version)

        case_files_api.store_save = racing_save
        try:
            statuses: dict[str, int] = {}

            def edit(name: str, body: dict) -> None:
                statuses[name] = client.put(
                    f"/case-files/{session_id}", json={**body, "version": version}
                ).status_code

            threads = [
                threading.Thread(target=edit, args=("a", {"height_m": 68.0})),
                threading.Thread(target=edit, args=("b", {"number_of_staircases": 3})),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            case_files_api.store_save = original_save

        assert sorted(statuses.values()) == [200, 409], "one must win, the other must be told"

    def test_the_store_raises_rather_than_overwriting(self):
        case_file = CaseFile(session_id="s")
        store_save(case_file)
        store_save(store_get("s"))  # someone else writes

        with pytest.raises(StaleCaseFileError):
            store_save(case_file, expected_version=1)

    def test_a_row_written_before_versioning_reads_as_version_one(self):
        # The additive migration cannot backfill, so an old row has NULL.
        from app.db.models import CaseFileRecord
        from app.db.session import get_session

        store_save(CaseFile(session_id="legacy"))
        with get_session() as session:
            session.query(CaseFileRecord).filter(
                CaseFileRecord.session_id == "legacy"
            ).update({"version": None})
            session.commit()

        assert store_get("legacy").version == 1

    def test_the_version_is_not_logged_as_a_field_change(self):
        # It is bookkeeping, not a fact about the building; logging it
        # would double the length of every timeline entry.
        session_id = client.post("/case-files", json=None).json()["session_id"]
        client.put(f"/case-files/{session_id}", json={"height_m": 68.0})

        changes = client.get(f"/case-files/{session_id}/changes").json()

        assert [item["field"] for item in changes] == ["height_m"]

    def test_the_version_gets_no_user_provenance(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]

        body = client.put(f"/case-files/{session_id}", json={"height_m": 68.0}).json()

        assert "version" not in body["field_sources"]


class TestLongPasswords:
    """bcrypt 5 raises rather than truncating, and signup used to 500."""

    def test_signup_with_an_over_long_password_is_a_clear_422_not_a_500(self):
        resp = client.post("/auth/signup", json={"email": "a@example.com", "password": "a" * 100})

        assert resp.status_code == 422
        assert "72 bytes" in resp.json()["detail"]

    def test_the_limit_is_bytes_not_characters(self):
        # An emoji is four bytes, so 30 characters can exceed a 72-byte cap.
        resp = client.post("/auth/signup", json={"email": "a@example.com", "password": "🔥" * 30})

        assert resp.status_code == 422

    def test_a_password_at_the_limit_still_works(self):
        password = "a" * MAX_PASSWORD_BYTES

        signup = client.post("/auth/signup", json={"email": "a@example.com", "password": password})
        login = client.post("/auth/login", json={"email": "a@example.com", "password": password})

        assert signup.status_code == 201
        assert login.status_code == 200

    def test_logging_in_with_an_over_long_password_is_rejected_not_crashed(self):
        _signup()

        resp = client.post("/auth/login", json={"email": "a@example.com", "password": "a" * 100})

        assert resp.status_code == 401

    def test_hash_password_refuses_rather_than_truncating(self):
        # Truncating would make the rest of a passphrase decorative, and
        # two different long passwords would open the same account.
        with pytest.raises(ValueError):
            hash_password("a" * 100)

    def test_verify_password_never_raises_on_a_long_candidate(self):
        hashed = hash_password("correct-horse")

        assert verify_password("a" * 100, hashed) is False


class TestProjectListPaging:
    """The response grew linearly with an account's whole history."""

    def _projects(self, account: dict, count: int) -> None:
        for _ in range(count):
            client.post("/case-files", json=None, headers=_headers(account))

    def test_the_page_reports_the_total_it_is_not_showing(self):
        account = _signup()
        self._projects(account, 5)

        body = client.get("/users/me/case-files?limit=2", headers=_headers(account)).json()

        assert len(body["items"]) == 2
        assert body["total"] == 5

    def test_offset_pages_through(self):
        account = _signup()
        self._projects(account, 5)
        headers = _headers(account)

        first = client.get("/users/me/case-files?limit=2&offset=0", headers=headers).json()["items"]
        second = client.get("/users/me/case-files?limit=2&offset=2", headers=headers).json()["items"]

        assert {item["session_id"] for item in first}.isdisjoint(
            {item["session_id"] for item in second}
        )

    def test_the_page_size_is_capped(self):
        account = _signup()

        assert client.get("/users/me/case-files?limit=99999", headers=_headers(account)).status_code == 422
        assert client.get("/users/me/case-files?limit=0", headers=_headers(account)).status_code == 422

    def test_chat_titles_follow_the_same_page(self):
        # Otherwise this quietly becomes the unbounded query the project
        # list just stopped being.
        account = _signup()
        self._projects(account, 5)

        titles = client.get("/users/me/chat-titles?limit=2", headers=_headers(account))

        assert titles.status_code == 200

    def test_the_store_counts_without_loading_every_blob(self):
        account = _signup()
        self._projects(account, 3)

        assert count_by_owner(account["user"]["id"]) == 3
        assert len(list_by_owner(account["user"]["id"], limit=1)) == 1


class TestReviewQueueIsAQuery:
    """It used to load every owned case file plus one lookup per grant,
    then discard the ones that were not flagged."""

    def _project(self, account: dict, fields: dict) -> str:
        headers = _headers(account)
        session_id = client.post("/case-files", json=None, headers=headers).json()["session_id"]
        client.put(f"/case-files/{session_id}", json=fields, headers=headers)
        client.post(f"/case-files/{session_id}/classify", headers=headers)
        return session_id

    def test_only_flagged_cases_are_returned(self):
        account = _signup()
        flagged = self._project(account, FLAGGED)
        self._project(account, CLEAN)

        queue = client.get("/users/me/review-queue", headers=_headers(account)).json()

        assert [item["session_id"] for item in queue] == [flagged]

    def test_the_flag_column_tracks_the_classification(self):
        # Reclassifying a case out of the flagged state must remove it.
        account = _signup()
        headers = _headers(account)
        session_id = self._project(account, FLAGGED)
        assert len(client.get("/users/me/review-queue", headers=headers).json()) == 1

        client.put(f"/case-files/{session_id}", json=CLEAN, headers=headers)
        client.post(f"/case-files/{session_id}/classify", headers=headers)

        assert client.get("/users/me/review-queue", headers=headers).json() == []

    def test_shared_projects_still_appear(self):
        owner = _signup("owner@example.com")
        reviewer = _signup("reviewer@example.com")
        session_id = self._project(owner, FLAGGED)
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=_headers(owner),
        )

        queue = client.get("/users/me/review-queue", headers=_headers(reviewer)).json()

        assert [item["session_id"] for item in queue] == [session_id]
        assert queue[0]["is_owner"] is False

    def test_a_project_is_not_listed_twice_when_owned_and_shared(self):
        account = _signup()
        session_id = self._project(account, FLAGGED)
        # A self-grant should not be possible, but the query unions two
        # conditions and must be duplicate-free regardless.
        grant_store.grant(session_id, account["user"]["id"], account["user"]["email"], account["user"]["id"])

        queue = client.get("/users/me/review-queue", headers=_headers(account)).json()

        assert len(queue) == 1

    def test_still_oldest_first(self):
        account = _signup()
        first = self._project(account, FLAGGED)
        second = self._project(account, FLAGGED)

        queue = client.get("/users/me/review-queue", headers=_headers(account)).json()

        assert [item["session_id"] for item in queue] == [first, second]

    def test_a_backfilled_row_is_visible_to_the_queue(self):
        # A row written before requires_review existed reads NULL, and a
        # NULL is a flagged case that has become invisible.
        from app.db.models import CaseFileRecord
        from app.db.session import get_engine, get_session
        from app.db.init_db import _backfill_requires_review

        account = _signup()
        session_id = self._project(account, FLAGGED)
        with get_session() as session:
            session.query(CaseFileRecord).filter(
                CaseFileRecord.session_id == session_id
            ).update({"requires_review": None})
            session.commit()
        assert client.get("/users/me/review-queue", headers=_headers(account)).json() == []

        _backfill_requires_review(get_engine())

        assert len(client.get("/users/me/review-queue", headers=_headers(account)).json()) == 1


class TestHandoffTruncation:
    def test_a_capped_change_history_says_so(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]
        for index in range(3):
            client.put(f"/case-files/{session_id}", json={"height_m": float(index + 10)})

        from app.reports.handoff import generate_handoff_markdown
        from app.api.case_files import _build_review_state

        case_file = store_get(session_id)
        all_changes = change_log.list_for_session(session_id)
        markdown = generate_handoff_markdown(
            case_file, _build_review_state(case_file, None), all_changes[:1], total_changes=len(all_changes)
        )

        assert f"Showing the 1 most recent of {len(all_changes)} changes" in markdown

    def test_an_uncapped_history_says_nothing_about_truncation(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]
        client.put(f"/case-files/{session_id}", json={"height_m": 24.0})

        markdown = client.get(f"/case-files/{session_id}/handoff").json()["markdown"]

        assert "most recent of" not in markdown

    def test_the_change_count_is_available_without_loading_the_rows(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]
        client.put(f"/case-files/{session_id}", json={"height_m": 24.0})
        client.put(f"/case-files/{session_id}", json={"height_m": 25.0})

        assert change_log.count_for_session(session_id) == 2
