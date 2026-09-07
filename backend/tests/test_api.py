from fastapi.testclient import TestClient

from app.main import app
from app.store import delete_all

client = TestClient(app)


def setup_function() -> None:
    delete_all()


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


def test_get_missing_case_file_404():
    resp = client.get("/case-files/does-not-exist")
    assert resp.status_code == 404
