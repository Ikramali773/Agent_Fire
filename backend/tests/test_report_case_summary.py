"""Tests for the report generator's "Case Summary" section - field-source
tagging (e.g. "(confirmed by user)") and the floor-wise area breakdown.
"""

from app.models.case_file import (
    CaseFile,
    FieldSource,
    FieldSourceKind,
    FloorAreaItem,
    OccupancyType,
)
from app.reports.generator import generate_report_markdown


def test_field_source_tag_actually_matches_the_field():
    # Regression test: _case_summary_lines used to look up field_sources by
    # the human-readable label ("Project name") instead of the real
    # snake_case field name ("project_name") - the two never matched, so
    # the "(confirmed by user)" tag never appeared for any field.
    case_file = CaseFile(session_id="s1", project_name="Sunrise Towers")
    case_file.field_sources["project_name"] = FieldSource(
        value="Sunrise Towers", source=FieldSourceKind.USER, confidence=1.0
    )

    report = generate_report_markdown(case_file)

    assert "**Project name:** Sunrise Towers _(confirmed by user)_" in report


def test_floor_wise_area_shown_when_present():
    case_file = CaseFile(
        session_id="s1",
        floor_wise_area=[
            FloorAreaItem(floor="Ground", area_sqm=120.5),
            FloorAreaItem(floor="First", area_sqm=110.0),
        ],
    )
    case_file.field_sources["floor_wise_area"] = FieldSource(
        value=case_file.floor_wise_area, source=FieldSourceKind.DOCUMENT, confidence=0.8
    )

    report = generate_report_markdown(case_file)

    assert "Floor-wise area" in report
    assert "Ground: 120.5 sqm" in report
    assert "First: 110.0 sqm" in report
    assert "_(extracted from document)_" in report


def test_floor_wise_area_omitted_when_absent():
    case_file = CaseFile(session_id="s1", occupancy_type=OccupancyType.STORAGE)
    report = generate_report_markdown(case_file)
    assert "Floor-wise area" not in report
