from app.ingest.fact_extraction import extract_case_file_facts
from app.llm.client import LLMClient
from app.models.case_file import FloorAreaItem


class FakeBackend:
    def __init__(self, json_return):
        self.json_return = json_return
        self.calls = []

    def generate_json(self, system, user_message, json_schema, model):
        self.calls.append({"system": system, "user_message": user_message})
        return self.json_return


def test_extracts_case_file_fields_from_document_text():
    backend = FakeBackend(
        json_return={
            "project_name": "Sunrise Apartments",
            "state": "Gujarat",
            "height_m": 28.5,
            "occupancy_type": "Residential",
        }
    )
    llm = LLMClient(backend=backend)

    result = extract_case_file_facts("Sunrise Apartments, Gujarat, 28.5m tall residential building", llm)

    assert result == {
        "project_name": "Sunrise Apartments",
        "state": "Gujarat",
        "height_m": 28.5,
        "occupancy_type": "Residential",
    }
    assert "uploaded document" in backend.calls[0]["system"]


def test_extracts_floor_wise_area_table_from_document_text():
    # Mirrors what app/ingest/tiers.py's table detection now hands the LLM
    # for a drawing's area-statement schedule: "Floor | Area (sqm) | ..."
    # rows, distinct from the whole-building built_up_area_sqm total.
    backend = FakeBackend(
        json_return={
            "built_up_area_sqm": 230.5,
            "floor_wise_area": [
                {"floor": "Ground", "area_sqm": 120.5},
                {"floor": "First", "area_sqm": 110.0},
            ],
        }
    )
    llm = LLMClient(backend=backend)

    result = extract_case_file_facts(
        "[Table(s) detected on this page]\nFloor | Area (sqm) | Remarks\n"
        "Ground | 120.5 | Retail\nFirst | 110.0 | Office",
        llm,
    )

    assert result["built_up_area_sqm"] == 230.5
    assert result["floor_wise_area"] == [
        FloorAreaItem(floor="Ground", area_sqm=120.5),
        FloorAreaItem(floor="First", area_sqm=110.0),
    ]


def test_extracts_occupancy_subdivision_when_implied_by_document():
    backend = FakeBackend(
        json_return={
            "occupancy_type": "Residential",
            "occupancy_subdivision": "A-V",
        }
    )
    llm = LLMClient(backend=backend)

    result = extract_case_file_facts("A 5-star hotel development in Ahmedabad", llm)

    assert result == {"occupancy_type": "Residential", "occupancy_subdivision": "A-V"}


def test_drops_occupancy_subdivision_code_that_does_not_exist():
    backend = FakeBackend(json_return={"occupancy_subdivision": "NOT-A-REAL-CODE"})
    llm = LLMClient(backend=backend)

    result = extract_case_file_facts("some document text", llm)

    assert result == {}


def test_empty_text_short_circuits_without_calling_llm():
    backend = FakeBackend(json_return={"should": "never see this"})
    llm = LLMClient(backend=backend)

    result = extract_case_file_facts("   ", llm)

    assert result == {}
    assert backend.calls == []
