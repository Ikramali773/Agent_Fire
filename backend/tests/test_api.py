import pymupdf
from fastapi.testclient import TestClient

from app.api.case_files import get_llm_client
from app.main import app
from app.store import delete_all

client = TestClient(app)


class FakeLLMClient:
    def classify_intent(self, user_text, pending_question):
        return "answer"

    def extract_fields(self, user_text, field_types, context=""):
        return {"state": "Gujarat", "city": "Ahmedabad"} if "state" in field_types else {}

    def answer_question(self, question, knowledge_context, model_tier="reasoning"):
        return "fake answer"


def setup_function() -> None:
    delete_all()
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200


def test_full_flow_create_update_classify_report():
    create_resp = client.post("/case-files", json=None)
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]

    update_resp = client.put(
        f"/case-files/{session_id}",
        json={
            "project_name": "Test Warehouse",
            "state": "Gujarat",
            "occupancy_type": "Storage",
            "height_m": 9.5,
            "built_up_area_sqm": 600,
            "number_of_staircases": 1,
        },
    )
    assert update_resp.status_code == 200

    classify_resp = client.post(f"/case-files/{session_id}/classify")
    assert classify_resp.status_code == 200
    result = classify_resp.json()["classification_result"]
    assert result["applies"] is True
    assert result["table_7_ref"] == "7H"
    assert result["protection_level"] == "HL-5"

    report_resp = client.get(f"/case-files/{session_id}/report")
    assert report_resp.status_code == 200
    markdown = report_resp.json()["markdown"]
    assert "Test Warehouse" in markdown
    assert "7H" in markdown
    assert "advisory only" in markdown

    pdf_resp = client.get(f"/case-files/{session_id}/report.pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert "Test Warehouse" in pdf_resp.headers["content-disposition"]
    assert pdf_resp.content.startswith(b"%PDF")
    pdf_text = "\n".join(page.get_text() for page in pymupdf.open(stream=pdf_resp.content, filetype="pdf"))
    assert "Test Warehouse" in pdf_text
    assert "7H" in pdf_text

    docx_resp = client.get(f"/case-files/{session_id}/report.docx")
    assert docx_resp.status_code == 200
    assert docx_resp.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert docx_resp.content.startswith(b"PK")


def test_get_missing_case_file_404():
    resp = client.get("/case-files/does-not-exist")
    assert resp.status_code == 404


def test_report_exports_404_for_missing_case_file():
    assert client.get("/case-files/does-not-exist/report.pdf").status_code == 404
    assert client.get("/case-files/does-not-exist/report.docx").status_code == 404


def test_start_and_message_conversation_endpoints():
    create_resp = client.post("/case-files", json=None)
    session_id = create_resp.json()["session_id"]

    start_resp = client.post(f"/case-files/{session_id}/start")
    assert start_resp.status_code == 200
    assert "state and city" in start_resp.json()["agent_message"]

    message_resp = client.post(
        f"/case-files/{session_id}/message", json={"message": "Gujarat, Ahmedabad"}
    )
    assert message_resp.status_code == 200
    body = message_resp.json()
    assert body["case_file"]["state"] == "Gujarat"
    assert body["case_file"]["city"] == "Ahmedabad"


def test_message_requires_message_field():
    create_resp = client.post("/case-files", json=None)
    session_id = create_resp.json()["session_id"]
    resp = client.post(f"/case-files/{session_id}/message", json={})
    assert resp.status_code == 422


def _make_text_pdf_bytes(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=14)
        y += 24
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_document_upload_extracts_and_merges_fields():
    create_resp = client.post("/case-files", json=None)
    session_id = create_resp.json()["session_id"]

    pdf_bytes = _make_text_pdf_bytes(["Fire NOC Certificate", "State: Gujarat", "City: Ahmedabad"])
    resp = client.post(
        f"/case-files/{session_id}/documents",
        files={"file": ("noc.pdf", pdf_bytes, "application/pdf")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["tier_used"] == 1
    assert body["case_file"]["state"] == "Gujarat"
    assert body["case_file"]["field_sources"]["state"]["source"] == "document"
    assert len(body["case_file"]["source_documents"]) == 1
    assert body["case_file"]["source_documents"][0]["filename"] == "noc.pdf"


def test_document_upload_fields_are_skipped_in_subsequent_chat_questions():
    """Real end-to-end proof that an uploaded document is actually 'linked'
    to the chat flow, not just recorded: once state/city come from a
    document, /start + /message should never ask the location question
    again - the next question should be the one after it (goal), not a
    repeat of "which state and city".
    """
    create_resp = client.post("/case-files", json=None)
    session_id = create_resp.json()["session_id"]

    pdf_bytes = _make_text_pdf_bytes(["Fire NOC Certificate", "State: Gujarat", "City: Ahmedabad"])
    upload_resp = client.post(
        f"/case-files/{session_id}/documents",
        files={"file": ("noc.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.json()["case_file"]["field_sources"]["state"]["source"] == "document"

    start_resp = client.post(f"/case-files/{session_id}/start")
    start_message = start_resp.json()["agent_message"]

    assert "state and city" not in start_message.lower()
    assert "trying to do" in start_message.lower()  # the goal question, next in line

    message_resp = client.post(
        f"/case-files/{session_id}/message", json={"message": "just want to understand requirements"}
    )
    next_message = message_resp.json()["agent_message"]
    assert "state and city" not in next_message.lower()


def test_document_upload_rejects_unsupported_type():
    create_resp = client.post("/case-files", json=None)
    session_id = create_resp.json()["session_id"]

    resp = client.post(
        f"/case-files/{session_id}/documents",
        files={"file": ("doc.docx", b"whatever", "application/msword")},
    )
    assert resp.status_code == 415


def test_document_upload_missing_case_file_404():
    pdf_bytes = _make_text_pdf_bytes(["hello world this is long enough text"])
    resp = client.post(
        "/case-files/does-not-exist/documents",
        files={"file": ("noc.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 404
