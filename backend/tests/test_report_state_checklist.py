"""Tests for the report generator's "State NOC Checklist" section - the
report-facing half of the state checklist framework (§B.10). See
data/rules/state_checklists/README.md for why the content is a placeholder.
"""

from app.engine.classifier import classify
from app.models.case_file import CaseFile, OccupancyType
from app.reports.generator import generate_report_markdown


def _classified_case_file(state: str) -> CaseFile:
    case_file = CaseFile(
        session_id="s1",
        state=state,
        occupancy_type=OccupancyType.STORAGE,
        height_m=9.5,
        built_up_area_sqm=600,
    )
    case_file.classification_result = classify(case_file)
    return case_file


def test_report_shows_placeholder_warning_for_launch_state():
    report = generate_report_markdown(_classified_case_file("Gujarat"))
    assert "GJ-FIRE-NOC-PLACEHOLDER" in report
    assert "PLACEHOLDER" in report
    assert "NOT A REAL GOVERNMENT CHECKLIST" in report
    assert "TODO:" in report


def test_report_explains_missing_checklist_for_unsupported_state():
    report = generate_report_markdown(_classified_case_file("Kerala"))
    assert "No NOC checklist is available yet for Kerala" in report
    assert "TODO:" not in report


def test_report_handles_missing_state():
    case_file = CaseFile(session_id="s1", occupancy_type=OccupancyType.STORAGE)
    case_file.classification_result = classify(case_file)
    report = generate_report_markdown(case_file)
    assert "State not specified yet" in report
