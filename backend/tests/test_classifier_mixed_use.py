"""Tests for classify_mixed_use() - Group K / Mixed Occupancy, clause 3.1.11,
product scope §B.6.3. Exercised against the real digitized rule data
(data/rules/nbcs_2026_partf/group_k_mixed_occupancy_separation.json and the
per-occupancy Table 7 files), not mocks - if these pass, the union-of-clauses
and separation-matrix logic genuinely agrees with the source tables.
"""

from app.engine.classifier import classify_mixed_use
from app.models.case_file import (
    CaseFile,
    IndustrialHazardBand,
    OccupancyBreakdownItem,
    OccupancyType,
)


def make_mixed_case_file(breakdown: list[OccupancyBreakdownItem], **overrides) -> CaseFile:
    defaults = dict(
        session_id="test-session",
        occupancy_type=OccupancyType.MIXED_USE,
        occupancy_breakdown=breakdown,
    )
    defaults.update(overrides)
    return CaseFile(**defaults)


class TestMixedUseUnionOfClauses:
    def test_two_permitted_components_union_bands_and_separation(self):
        # Storage 600 sqm -> Table 7H band HL-5 (501-1000 sqm, no height/floor
        # dependency); Mercantile (subdivision F) 1200 sqm at height 9.5 m ->
        # Table 7F band CL-4 (<=30 m, >=1001 sqm). Neither occupancy carries a
        # mandatory-review flag, and Storage/Mercantile separation is a plain
        # 120-minute rating (not NP) per the Group K matrix.
        case_file = make_mixed_case_file(
            height_m=9.5,
            floors_above_ground=1,
            breakdown=[
                OccupancyBreakdownItem(
                    type=OccupancyType.STORAGE, floor_range="G", floor_area_sqm=600
                ),
                OccupancyBreakdownItem(
                    type=OccupancyType.MERCANTILE,
                    floor_range="1",
                    floor_area_sqm=1200,
                    subdivision="F",
                ),
            ],
        )

        result = classify_mixed_use(case_file)

        assert result.applies is True
        assert result.require_human_review_flag is False
        joined_clauses = " ".join(result.applicable_clauses)
        assert "HL-5" in joined_clauses
        assert "CL-4" in joined_clauses
        assert "120 minutes" in joined_clauses
        assert "Union of installations required" in joined_clauses

    def test_not_permitted_combination_forces_human_review(self):
        # Residential + Industrial-Moderate(G-2) is an "NP" cell in the
        # Group K matrix - must never be silently accepted.
        case_file = make_mixed_case_file(
            height_m=30,
            industrial_hazard_band=IndustrialHazardBand.G2_MODERATE,
            breakdown=[
                OccupancyBreakdownItem(
                    type=OccupancyType.RESIDENTIAL,
                    floor_range="1-5",
                    floor_area_sqm=1000,
                    subdivision="A-III",
                ),
                OccupancyBreakdownItem(
                    type=OccupancyType.INDUSTRIAL, floor_range="G", floor_area_sqm=1000
                ),
            ],
        )

        result = classify_mixed_use(case_file)

        assert result.require_human_review_flag is True
        assert any("NOT PERMITTED" in note for note in result.notes)
        assert any(
            "Residential" in note and "Industrial-Moderate(G-2)" in note
            for note in result.notes
        )

    def test_hazardous_component_triggers_mandatory_review(self):
        case_file = make_mixed_case_file(
            height_m=9.5,
            floors_above_ground=1,
            breakdown=[
                OccupancyBreakdownItem(
                    type=OccupancyType.STORAGE, floor_range="G", floor_area_sqm=600
                ),
                OccupancyBreakdownItem(
                    type=OccupancyType.HAZARDOUS, floor_range="1", floor_area_sqm=300
                ),
            ],
        )

        result = classify_mixed_use(case_file)

        assert result.require_human_review_flag is True
        assert any("mandatory human/expert review" in note for note in result.notes)
        # The separation rating itself should still be computed (240 min,
        # per the matrix) even though the building overall needs review.
        assert any("240 minutes" in clause for clause in result.applicable_clauses)

    def test_single_component_is_not_mixed_use(self):
        case_file = make_mixed_case_file(
            height_m=30,
            breakdown=[
                OccupancyBreakdownItem(
                    type=OccupancyType.STORAGE, floor_range="G", floor_area_sqm=600
                ),
            ],
        )

        result = classify_mixed_use(case_file)

        assert result.require_human_review_flag is True
        assert any("at least two" in note for note in result.notes)

    def test_component_missing_floor_area_routes_to_human_review(self):
        case_file = make_mixed_case_file(
            height_m=30,
            breakdown=[
                OccupancyBreakdownItem(type=OccupancyType.STORAGE, floor_range="G"),
                OccupancyBreakdownItem(
                    type=OccupancyType.MERCANTILE,
                    floor_range="1",
                    floor_area_sqm=1200,
                    subdivision="F",
                ),
            ],
        )

        result = classify_mixed_use(case_file)

        assert result.require_human_review_flag is True
        assert any("floor_area_sqm" in note for note in result.notes)

    def test_classify_routes_mixed_use_to_classify_mixed_use(self):
        from app.engine.classifier import classify

        case_file = make_mixed_case_file(
            height_m=9.5,
            floors_above_ground=1,
            breakdown=[
                OccupancyBreakdownItem(
                    type=OccupancyType.STORAGE, floor_range="G", floor_area_sqm=600
                ),
                OccupancyBreakdownItem(
                    type=OccupancyType.MERCANTILE,
                    floor_range="1",
                    floor_area_sqm=1200,
                    subdivision="F",
                ),
            ],
        )

        result = classify(case_file)

        assert result.require_human_review_flag is False
        assert "HL-5" in " ".join(result.applicable_clauses)
