"""Tests for the state NOC checklist framework (§B.10) - loads the actual
placeholder JSON files in data/rules/state_checklists/, not mocks. See that
directory's README for why the content is deliberately a placeholder.
"""

from app.engine import state_checklists
from app.engine.classifier import classify
from app.models.case_file import CaseFile, OccupancyType


def test_gujarat_checklist_loads_as_placeholder():
    checklist = state_checklists.get_checklist_for_state("Gujarat")
    assert checklist is not None
    assert checklist["status"] == "placeholder"
    assert checklist["checklist_id"] == "GJ-FIRE-NOC-PLACEHOLDER"
    assert all(item.startswith("TODO:") for item in checklist["items"])


def test_maharashtra_checklist_loads_as_placeholder():
    checklist = state_checklists.get_checklist_for_state("Maharashtra")
    assert checklist is not None
    assert checklist["status"] == "placeholder"
    assert checklist["checklist_id"] == "MH-FIRE-NOC-PLACEHOLDER"


def test_state_matching_is_case_and_whitespace_insensitive():
    assert state_checklists.checklist_id_for_state("  gujarat ") == "GJ-FIRE-NOC-PLACEHOLDER"
    assert state_checklists.checklist_id_for_state("MAHARASHTRA") == "MH-FIRE-NOC-PLACEHOLDER"


def test_unknown_state_returns_none():
    assert state_checklists.get_checklist_for_state("Kerala") is None
    assert state_checklists.checklist_id_for_state("Kerala") is None
    assert state_checklists.checklist_id_for_state("") is None


def test_classify_attaches_checklist_id_for_launch_state():
    case_file = CaseFile(
        session_id="s1",
        state="Gujarat",
        occupancy_type=OccupancyType.STORAGE,
        height_m=9.5,
        built_up_area_sqm=600,
    )
    result = classify(case_file)
    assert result.applicable_state_checklist_id == "GJ-FIRE-NOC-PLACEHOLDER"


def test_classify_leaves_checklist_id_none_for_unsupported_state():
    case_file = CaseFile(
        session_id="s1",
        state="Kerala",
        occupancy_type=OccupancyType.STORAGE,
        height_m=9.5,
        built_up_area_sqm=600,
    )
    result = classify(case_file)
    assert result.applicable_state_checklist_id is None


def test_classify_attaches_checklist_id_even_when_occupancy_missing():
    case_file = CaseFile(session_id="s1", state="Maharashtra")
    result = classify(case_file)
    assert result.applicable_state_checklist_id == "MH-FIRE-NOC-PLACEHOLDER"
