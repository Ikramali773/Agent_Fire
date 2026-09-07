"""Tests for the deterministic classification engine, exercised against the
actual digitized NBCS 2026 Part F rule data (not mocks) - if these pass, the
engine's numeric logic genuinely agrees with what's in data/rules/nbcs_2026_partf/.
"""

from app.engine.classifier import (
    ClassificationError,
    check_applicability,
    compute_is_high_rise,
    lookup_table7,
)
from app.models.case_file import CaseFile, IndustrialHazardBand, OccupancyType


def make_case_file(**overrides) -> CaseFile:
    defaults = dict(session_id="test-session")
    defaults.update(overrides)
    return CaseFile(**defaults)


class TestApplicability:
    def test_residential_below_both_thresholds_does_not_apply(self):
        applies, note = check_applicability("Residential", None, height_m=10, area_sqm=500)
        assert applies is False
        assert "clause 1.2" in note

    def test_residential_area_exceeds_threshold_applies(self):
        applies, _ = check_applicability("Residential", None, height_m=10, area_sqm=800)
        assert applies is True

    def test_residential_height_exceeds_threshold_applies(self):
        applies, _ = check_applicability("Residential", None, height_m=30, area_sqm=100)
        assert applies is True

    def test_residential_at_exactly_threshold_does_not_apply(self):
        # Source language is "exceeding" - equal to the threshold does not trigger.
        applies, _ = check_applicability("Residential", None, height_m=24, area_sqm=750)
        assert applies is False

    def test_industrial_g1_is_area_only_regardless_of_height(self):
        applies, _ = check_applicability(
            "Industrial", IndustrialHazardBand.G1_LOW, height_m=200, area_sqm=1500
        )
        assert applies is False  # tall but under the 2000 sqm area-only threshold

        applies, _ = check_applicability(
            "Industrial", IndustrialHazardBand.G1_LOW, height_m=0, area_sqm=2500
        )
        assert applies is True  # any height, area exceeds 2000

    def test_industrial_g3_reverts_to_height_or_area(self):
        applies, _ = check_applicability(
            "Industrial", IndustrialHazardBand.G3_HIGH, height_m=16, area_sqm=100
        )
        assert applies is True  # height alone exceeds 15 m

    def test_industrial_without_hazard_band_raises(self):
        try:
            check_applicability("Industrial", None, height_m=10, area_sqm=100)
            assert False, "expected ClassificationError"
        except ClassificationError:
            pass

    def test_storage_and_hazardous_use_9m_500sqm_threshold(self):
        applies_h, _ = check_applicability("Storage", None, height_m=9.5, area_sqm=100)
        assert applies_h is True
        applies_j, _ = check_applicability("Hazardous", None, height_m=1, area_sqm=600)
        assert applies_j is True


class TestHighRiseFlag:
    def test_high_rise_is_occupancy_independent_and_uses_gte_24(self):
        assert compute_is_high_rise(24) is True
        assert compute_is_high_rise(23.99) is False
        assert compute_is_high_rise(None) is None


class TestTable7Lookup:
    def test_storage_building_matches_correct_band(self):
        case_file = make_case_file(
            occupancy_type=OccupancyType.STORAGE,
            height_m=9.5,
            built_up_area_sqm=600,
        )
        result = lookup_table7("Storage", None, case_file)
        assert result.table_ref == "7H"
        assert len(result.matched_bands) == 1
        assert result.matched_bands[0].band_id == "HL-5"
        assert result.matched_bands[0].installations["wet_riser"] == "R"
        assert result.matched_bands[0].installations["automatic_wet_sprinkler_system"] == "NR"

    def test_industrial_g3_high_hazard_small_area(self):
        case_file = make_case_file(
            occupancy_type=OccupancyType.INDUSTRIAL,
            industrial_hazard_band=IndustrialHazardBand.G3_HIGH,
            height_m=16,
            built_up_area_sqm=200,
        )
        result = lookup_table7("Industrial", IndustrialHazardBand.G3_HIGH, case_file)
        assert result.table_ref == "7G"
        assert result.matched_bands[0].band_id == "CL-4"

    def test_residential_without_subdivision_raises(self):
        case_file = make_case_file(
            occupancy_type=OccupancyType.RESIDENTIAL, height_m=30, built_up_area_sqm=2000
        )
        try:
            lookup_table7("Residential", None, case_file)
            assert False, "expected ClassificationError requiring occupancy_subdivision"
        except ClassificationError as exc:
            assert "occupancy_subdivision" in str(exc)

    def test_residential_starred_hotel_with_subdivision(self):
        case_file = make_case_file(
            occupancy_type=OccupancyType.RESIDENTIAL,
            occupancy_subdivision="A-V",
            height_m=40,
            built_up_area_sqm=5000,
        )
        result = lookup_table7("Residential", None, case_file)
        assert result.matched_bands[0].band_id == "CL-5"

    def test_hazardous_single_storey_vs_multi_storey(self):
        single = make_case_file(
            occupancy_type=OccupancyType.HAZARDOUS,
            height_m=10,
            built_up_area_sqm=300,
            floors_above_ground=1,
        )
        multi = make_case_file(
            occupancy_type=OccupancyType.HAZARDOUS,
            height_m=10,
            built_up_area_sqm=300,
            floors_above_ground=3,
        )
        result_single = lookup_table7("Hazardous", None, single)
        result_multi = lookup_table7("Hazardous", None, multi)
        assert result_single.matched_bands[0].band_id == "CL-7"
        assert result_multi.matched_bands[0].band_id == "CL-8"
