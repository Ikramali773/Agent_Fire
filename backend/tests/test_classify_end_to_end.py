from app.engine.classifier import classify
from app.models.case_file import CaseFile, IndustrialHazardBand, OccupancyType


def make_case_file(**overrides) -> CaseFile:
    defaults = dict(session_id="test-session")
    defaults.update(overrides)
    return CaseFile(**defaults)


def test_small_residential_building_out_of_scope_but_survivor_note_included():
    case_file = make_case_file(
        occupancy_type=OccupancyType.RESIDENTIAL,
        occupancy_subdivision="A-III",
        height_m=10,
        built_up_area_sqm=400,
        number_of_staircases=1,
    )
    result = classify(case_file)
    assert result.applies is False
    assert any("firefighting-shaft-type staircase" in n for n in result.notes)


def test_high_rise_apartment_stacks_annex_d_on_top_of_table7():
    case_file = make_case_file(
        occupancy_type=OccupancyType.RESIDENTIAL,
        occupancy_subdivision="A-III",
        height_m=70,
        built_up_area_sqm=5000,
    )
    result = classify(case_file)
    assert result.applies is True
    assert result.is_high_rise is True
    assert result.table_7_ref == "7A"
    assert result.protection_level == "CL-4"
    assert any("Annex D" in c for c in result.applicable_clauses)


def test_hospital_always_flagged_for_human_review():
    case_file = make_case_file(
        occupancy_type=OccupancyType.INSTITUTIONAL,
        occupancy_subdivision="C-I",
        height_m=20,
        built_up_area_sqm=800,
    )
    result = classify(case_file)
    assert result.require_human_review_flag is True


def test_industrial_requires_hazard_band_before_classifying():
    case_file = make_case_file(
        occupancy_type=OccupancyType.INDUSTRIAL,
        height_m=10,
        built_up_area_sqm=3000,
    )
    result = classify(case_file)
    assert result.applies is None
    assert any("industrial_hazard_band" in n for n in result.notes)


def test_mixed_use_routes_to_human_review_not_silently_classified():
    case_file = make_case_file(occupancy_type=OccupancyType.MIXED_USE)
    result = classify(case_file)
    assert result.require_human_review_flag is True
