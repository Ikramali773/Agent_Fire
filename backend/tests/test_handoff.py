"""Tests for the Phase 3 consultant handoff pack.

The point of the pack is that a licensed professional signing off needs to
know where every number came from. The report states conclusions; these
tests check the pack actually carries the provenance, the review reasons
and the change history behind them.
"""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import change_log, grant_store, review_store
from app.auth.user_store import delete_all as delete_all_users
from app.main import app
from app.message_store import delete_all as delete_all_messages
from app.models.case_file import OccupancyType
from app.reports.exporters import render_docx
from app.store import delete_all as delete_all_case_files

client = TestClient(app)

FLAGGED = {
    "occupancy_type": OccupancyType.INSTITUTIONAL.value,
    "height_m": 30.0,
    "built_up_area_sqm": 4000.0,
    "floors_above_ground": 10,
    "project_name": "St Mary Hospital",
}


@pytest.fixture(autouse=True)
def _reset_store():
    delete_all_case_files()
    delete_all_messages()
    delete_all_users()
    change_log.delete_all()
    review_store.delete_all()
    grant_store.delete_all()


def _flagged_project() -> str:
    session_id = client.post("/case-files", json=None).json()["session_id"]
    client.put(f"/case-files/{session_id}", json=FLAGGED)
    client.post(f"/case-files/{session_id}/classify")
    return session_id


def _handoff(session_id: str) -> str:
    resp = client.get(f"/case-files/{session_id}/handoff")
    assert resp.status_code == 200, resp.text
    return resp.json()["markdown"]


class TestContent:
    def test_the_pack_still_contains_the_whole_report(self):
        # It is an addition to the report, never a replacement for it.
        session_id = _flagged_project()
        report = client.get(f"/case-files/{session_id}/report").json()["markdown"]

        assert report.strip() in _handoff(session_id)

    def test_it_lists_the_engines_typed_reasons_for_review(self):
        session_id = _flagged_project()

        markdown = _handoff(session_id)

        assert "Why this case requires human review" in markdown
        assert "mandatory_occupancy" in markdown

    def test_it_says_when_review_was_not_actually_required(self):
        # Being honest about this matters: a pack that implies the engine
        # demanded review when it did not is misleading in a filing.
        session_id = client.post("/case-files", json=None).json()["session_id"]
        client.put(
            f"/case-files/{session_id}",
            json={"occupancy_type": OccupancyType.RESIDENTIAL.value, "height_m": 12.0, "built_up_area_sqm": 400.0},
        )
        client.post(f"/case-files/{session_id}/classify")

        markdown = _handoff(session_id)

        assert "did **not** flag this case" in markdown

    def test_it_shows_where_each_fact_came_from(self):
        session_id = _flagged_project()

        markdown = _handoff(session_id)

        assert "Where every fact came from" in markdown
        assert "Confirmed by user" in markdown
        assert "height_m" in markdown

    def test_it_shows_the_change_history_oldest_first(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]
        client.put(f"/case-files/{session_id}", json={"height_m": 24.0})
        client.put(f"/case-files/{session_id}", json={"height_m": 68.0})

        markdown = _handoff(session_id)

        assert "Change history" in markdown
        first = markdown.index("| 24 |")
        second = markdown.index("| 68 |")
        assert first < second, "a handoff document reads oldest-first"

    def test_it_shows_the_recorded_verdicts(self):
        session_id = _flagged_project()
        client.post(
            f"/case-files/{session_id}/review",
            json={"status": "approved", "note": "Checked against the drawings."},
            headers={},
        )

        markdown = _handoff(session_id)

        assert "Review status" in markdown
        assert "Checked against the drawings." in markdown

    def test_it_says_plainly_that_a_verdict_never_replaces_the_classification(self):
        session_id = _flagged_project()
        client.post(f"/case-files/{session_id}/review", json={"status": "approved"})

        assert "never replaces it" in _handoff(session_id)

    def test_it_is_honest_about_an_empty_history(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]

        markdown = _handoff(session_id)

        assert "Nothing has been changed" in markdown

    def test_a_pipe_in_a_value_cannot_break_the_table(self):
        # A project name is user input, and an unescaped pipe would split
        # the row into extra columns and silently misalign the document.
        session_id = client.post("/case-files", json=None).json()["session_id"]
        client.put(f"/case-files/{session_id}", json={"project_name": "A | B"})

        markdown = _handoff(session_id)

        assert "A \\| B" in markdown


class TestExports:
    def test_the_pdf_renders(self):
        session_id = _flagged_project()

        resp = client.get(f"/case-files/{session_id}/handoff.pdf")

        assert resp.status_code == 200
        assert resp.content[:5] == b"%PDF-"
        assert "reviewer handoff.pdf" in resp.headers["content-disposition"]

    def test_the_docx_renders(self):
        session_id = _flagged_project()

        resp = client.get(f"/case-files/{session_id}/handoff.docx")

        assert resp.status_code == 200
        assert zipfile.is_zipfile(io.BytesIO(resp.content))
        assert "reviewer handoff.docx" in resp.headers["content-disposition"]

    def test_the_docx_keeps_the_provenance_table_as_a_real_table(self):
        # The whole reason the walker learned about tables: a provenance
        # table flattened to prose is unreadable, which would defeat the
        # purpose of sending it to a consultant at all.
        from docx import Document

        docx_bytes = render_docx(
            "| Field | Source |\n| --- | --- |\n| height_m | Extracted from document |\n"
        )

        document = Document(io.BytesIO(docx_bytes))
        assert len(document.tables) == 1
        assert document.tables[0].cell(0, 0).text == "Field"
        assert document.tables[0].cell(1, 1).text == "Extracted from document"

    def test_the_docx_still_renders_ordinary_prose_around_a_table(self):
        from docx import Document

        docx_bytes = render_docx("# Title\n\nSome prose.\n\n| A |\n| --- |\n| 1 |\n\nAfter the table.\n")

        document = Document(io.BytesIO(docx_bytes))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        assert "Some prose." in text
        assert "After the table." in text
        assert len(document.tables) == 1


class TestAccess:
    def test_a_reviewer_can_download_the_pack_for_a_shared_project(self):
        owner = client.post(
            "/auth/signup", json={"email": "owner@example.com", "password": "correct-horse"}
        ).json()
        reviewer = client.post(
            "/auth/signup", json={"email": "reviewer@example.com", "password": "correct-horse"}
        ).json()
        owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
        reviewer_headers = {"Authorization": f"Bearer {reviewer['access_token']}"}
        session_id = client.post("/case-files", json=None, headers=owner_headers).json()["session_id"]
        client.put(f"/case-files/{session_id}", json=FLAGGED, headers=owner_headers)
        client.post(f"/case-files/{session_id}/classify", headers=owner_headers)
        client.post(
            f"/case-files/{session_id}/shares",
            json={"email": "reviewer@example.com"},
            headers=owner_headers,
        )

        assert client.get(f"/case-files/{session_id}/handoff", headers=reviewer_headers).status_code == 200
        assert (
            client.get(f"/case-files/{session_id}/handoff.pdf", headers=reviewer_headers).status_code == 200
        )

    def test_a_stranger_cannot_download_the_pack(self):
        owner = client.post(
            "/auth/signup", json={"email": "owner@example.com", "password": "correct-horse"}
        ).json()
        stranger = client.post(
            "/auth/signup", json={"email": "stranger@example.com", "password": "correct-horse"}
        ).json()
        owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
        session_id = client.post("/case-files", json=None, headers=owner_headers).json()["session_id"]

        resp = client.get(
            f"/case-files/{session_id}/handoff",
            headers={"Authorization": f"Bearer {stranger['access_token']}"},
        )

        assert resp.status_code == 403

    def test_an_unknown_case_file_is_404(self):
        assert client.get("/case-files/nope/handoff").status_code == 404


class TestProvenanceOnDirectEdits:
    """A gap the handoff pack exposed: a field typed into the Case File page
    recorded no provenance at all.

    The dialogue path and the ingest path had always recorded it; the PUT
    path never did, so a user-confirmed fact showed up in the pack - whose
    whole purpose is telling a reviewer where each number came from - with
    no source.
    """

    def test_a_directly_edited_field_is_recorded_as_user_confirmed(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]

        body = client.put(f"/case-files/{session_id}", json={"height_m": 68.0}).json()

        assert body["field_sources"]["height_m"]["source"] == "user"
        assert body["field_sources"]["height_m"]["confidence"] == 1.0
        assert body["field_sources"]["height_m"]["value"] == 68.0

    def test_the_recorded_value_is_the_coerced_one_not_the_raw_request(self):
        # "Storage" arrives as a plain string and becomes an OccupancyType;
        # the provenance has to show what was stored, not what was sent.
        session_id = client.post("/case-files", json=None).json()["session_id"]

        body = client.put(f"/case-files/{session_id}", json={"occupancy_type": "Storage"}).json()

        assert body["field_sources"]["occupancy_type"]["value"] == "Storage"

    def test_derived_fields_never_get_user_provenance(self):
        # conversation_stage and classification_result are the system's
        # conclusions, not the user's assertions.
        session_id = client.post("/case-files", json=None).json()["session_id"]

        body = client.put(
            f"/case-files/{session_id}", json={"height_m": 20.0, "conversation_stage": "classified"}
        ).json()

        assert "height_m" in body["field_sources"]
        assert "conversation_stage" not in body["field_sources"]

    def test_editing_a_field_overwrites_its_earlier_document_provenance(self):
        # A user correcting an OCR-extracted number is the strongest signal
        # available, and must not keep claiming it came from a document.
        session_id = client.post("/case-files", json=None).json()["session_id"]
        client.put(f"/case-files/{session_id}", json={"height_m": 24.0})

        body = client.put(f"/case-files/{session_id}", json={"height_m": 68.0}).json()

        assert body["field_sources"]["height_m"]["value"] == 68.0
        assert body["field_sources"]["height_m"]["source"] == "user"

    def test_the_handoff_pack_now_shows_that_provenance(self):
        session_id = client.post("/case-files", json=None).json()["session_id"]
        client.put(f"/case-files/{session_id}", json=FLAGGED)

        markdown = _handoff(session_id)

        assert "Confirmed by user" in markdown
        assert "No provenance has been recorded" not in markdown
