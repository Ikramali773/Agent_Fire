"""Tests for typed review reasons (Phase 3).

The engine has always been able to say "a person has to look at this". The
invariant these tests defend is that it can never say so WITHOUT saying
why, nor explain a problem without actually raising the flag - which is
what routing all 15 sites through _flag_review buys.
"""

import pytest

from app.engine.classifier import classify
from app.models.case_file import (
    CaseFile,
    IndustrialHazardBand,
    OccupancyBreakdownItem,
    OccupancyType,
)
from app.models.review import ReviewReasonCode


def _codes(case_file: CaseFile) -> set[str]:
    return {reason.code.value for reason in classify(case_file).review_reasons}


# Every shape of case file worth running the invariant against. Kept as one
# list so a new classifier branch gets covered by adding one entry.
CASES = [
    pytest.param(CaseFile(session_id="s"), id="empty"),
    pytest.param(
        CaseFile(session_id="s", occupancy_type=OccupancyType.RESIDENTIAL, height_m=12.0, built_up_area_sqm=400.0),
        id="small-residential",
    ),
    pytest.param(
        CaseFile(session_id="s", occupancy_type=OccupancyType.STORAGE, height_m=30.0, built_up_area_sqm=5000.0),
        id="high-rise-storage",
    ),
    pytest.param(
        CaseFile(session_id="s", occupancy_type=OccupancyType.INSTITUTIONAL, height_m=15.0, built_up_area_sqm=900.0),
        id="institutional",
    ),
    pytest.param(
        CaseFile(session_id="s", occupancy_type=OccupancyType.HAZARDOUS, height_m=9.0, built_up_area_sqm=300.0),
        id="hazardous",
    ),
    pytest.param(
        CaseFile(
            session_id="s",
            occupancy_type=OccupancyType.INDUSTRIAL,
            industrial_hazard_band=IndustrialHazardBand.G2_MODERATE,
            height_m=18.0,
            built_up_area_sqm=2000.0,
        ),
        id="industrial",
    ),
    pytest.param(
        CaseFile(session_id="s", occupancy_type=OccupancyType.MIXED_USE, mixed_occupancy=True, height_m=30.0),
        id="mixed-no-components",
    ),
    pytest.param(
        CaseFile(
            session_id="s",
            occupancy_type=OccupancyType.MIXED_USE,
            mixed_occupancy=True,
            height_m=30.0,
            built_up_area_sqm=6000.0,
            occupancy_breakdown=[
                OccupancyBreakdownItem(type=OccupancyType.MERCANTILE, floor_range="G-2", floor_area_sqm=2000.0),
                OccupancyBreakdownItem(type=OccupancyType.RESIDENTIAL, floor_range="3-12", floor_area_sqm=4000.0),
            ],
            floors_above_ground=12,
        ),
        id="mixed-retail-residential",
    ),
    pytest.param(
        CaseFile(
            session_id="s",
            occupancy_type=OccupancyType.MIXED_USE,
            mixed_occupancy=True,
            height_m=30.0,
            occupancy_breakdown=[
                OccupancyBreakdownItem(type=OccupancyType.MIXED_USE, floor_range="G-2"),
                OccupancyBreakdownItem(type=OccupancyType.RESIDENTIAL, floor_range="3-12"),
            ],
        ),
        id="mixed-with-nested-mixed",
    ),
]


@pytest.mark.parametrize("case_file", CASES)
def test_the_flag_is_true_exactly_when_there_is_a_reason(case_file: CaseFile):
    # The whole point of _flag_review: the engine can never flag a case
    # without saying why, nor describe a blocker without flagging it.
    result = classify(case_file)

    assert result.require_human_review_flag == bool(result.review_reasons)


@pytest.mark.parametrize("case_file", CASES)
def test_every_reason_also_appears_in_the_notes(case_file: CaseFile):
    # notes stays the human-readable record the report renders; the typed
    # reasons are an index over it, not a replacement.
    result = classify(case_file)

    for reason in result.review_reasons:
        assert reason.detail in result.notes


@pytest.mark.parametrize("case_file", CASES)
def test_every_reason_carries_a_real_explanation(case_file: CaseFile):
    for reason in classify(case_file).review_reasons:
        assert reason.detail.strip(), reason.code


def test_institutional_is_flagged_as_a_mandatory_occupancy():
    case_file = CaseFile(
        session_id="s", occupancy_type=OccupancyType.INSTITUTIONAL, height_m=15.0, built_up_area_sqm=900.0
    )

    assert ReviewReasonCode.MANDATORY_OCCUPANCY.value in _codes(case_file)


def test_hazardous_is_flagged_as_a_mandatory_occupancy():
    case_file = CaseFile(
        session_id="s", occupancy_type=OccupancyType.HAZARDOUS, height_m=9.0, built_up_area_sqm=300.0
    )

    assert ReviewReasonCode.MANDATORY_OCCUPANCY.value in _codes(case_file)


def test_a_mixed_use_building_with_one_component_is_flagged_as_incomplete():
    case_file = CaseFile(
        session_id="s",
        occupancy_type=OccupancyType.MIXED_USE,
        mixed_occupancy=True,
        height_m=30.0,
        occupancy_breakdown=[OccupancyBreakdownItem(type=OccupancyType.RESIDENTIAL, floor_range="G-12")],
    )

    assert ReviewReasonCode.INCOMPLETE_MIXED_BREAKDOWN.value in _codes(case_file)


def test_a_mixed_use_component_that_is_itself_mixed_use_is_flagged():
    case_file = CaseFile(
        session_id="s",
        occupancy_type=OccupancyType.MIXED_USE,
        mixed_occupancy=True,
        height_m=30.0,
        occupancy_breakdown=[
            OccupancyBreakdownItem(type=OccupancyType.MIXED_USE, floor_range="G-2"),
            OccupancyBreakdownItem(type=OccupancyType.RESIDENTIAL, floor_range="3-12"),
        ],
    )

    assert ReviewReasonCode.INVALID_MIXED_COMPONENT.value in _codes(case_file)


def test_a_mixed_component_with_no_area_is_flagged():
    case_file = CaseFile(
        session_id="s",
        occupancy_type=OccupancyType.MIXED_USE,
        mixed_occupancy=True,
        height_m=30.0,
        occupancy_breakdown=[
            OccupancyBreakdownItem(type=OccupancyType.MERCANTILE, floor_range="G-2"),
            OccupancyBreakdownItem(type=OccupancyType.RESIDENTIAL, floor_range="3-12", floor_area_sqm=4000.0),
        ],
    )

    assert ReviewReasonCode.MISSING_COMPONENT_AREA.value in _codes(case_file)


def test_a_mixed_use_building_with_a_hazardous_component_is_mandatory_review():
    case_file = CaseFile(
        session_id="s",
        occupancy_type=OccupancyType.MIXED_USE,
        mixed_occupancy=True,
        height_m=20.0,
        occupancy_breakdown=[
            OccupancyBreakdownItem(type=OccupancyType.HAZARDOUS, floor_range="G", floor_area_sqm=500.0),
            OccupancyBreakdownItem(type=OccupancyType.BUSINESS, floor_range="1-5", floor_area_sqm=3000.0),
        ],
    )

    assert ReviewReasonCode.MANDATORY_OCCUPANCY.value in _codes(case_file)


def test_a_clean_case_carries_no_review_reasons_at_all():
    # The negative case matters as much as the positives: a flag on
    # everything is the same as a flag on nothing.
    case_file = CaseFile(
        session_id="s",
        occupancy_type=OccupancyType.RESIDENTIAL,
        height_m=12.0,
        built_up_area_sqm=400.0,
        floors_above_ground=4,
    )

    result = classify(case_file)

    assert result.review_reasons == []
    assert result.require_human_review_flag is False


def test_reasons_are_serialized_for_the_api():
    result = classify(
        CaseFile(session_id="s", occupancy_type=OccupancyType.HAZARDOUS, height_m=9.0, built_up_area_sqm=300.0)
    )

    dumped = result.model_dump(mode="json")

    assert dumped["review_reasons"][0]["code"] == "mandatory_occupancy"
    assert isinstance(dumped["review_reasons"][0]["detail"], str)


class TestFlaggingBugsFoundByTheInvariant:
    """Two pre-existing bugs the flag/reason invariant above exposed.

    Both were the same shape: a path out of _classify_single_occupancy that
    returned before the human-review flag could be set.
    """

    def test_a_small_institutional_building_is_still_flagged(self):
        # Below Part F's applicability threshold, so the old code returned
        # at "if not applies" - before the mandatory-occupancy check, which
        # sat near the end of the function. A hospital the code declined to
        # classify came back looking like a clean, automated "doesn't
        # apply", which is the worst possible answer to get wrong.
        case_file = CaseFile(
            session_id="s",
            occupancy_type=OccupancyType.INSTITUTIONAL,
            height_m=4.0,
            built_up_area_sqm=100.0,
        )

        result = classify(case_file)

        assert result.applies is False
        assert result.require_human_review_flag is True
        assert ReviewReasonCode.MANDATORY_OCCUPANCY.value in {r.code.value for r in result.review_reasons}

    def test_a_small_hazardous_building_is_still_flagged(self):
        case_file = CaseFile(
            session_id="s", occupancy_type=OccupancyType.HAZARDOUS, height_m=3.0, built_up_area_sqm=50.0
        )

        assert classify(case_file).require_human_review_flag is True

    def test_a_small_ordinary_building_is_not_flagged_by_that_fix(self):
        # The fix must not turn "below threshold" into a review flag for
        # everyone - only for the two mandatory occupancies.
        case_file = CaseFile(
            session_id="s", occupancy_type=OccupancyType.BUSINESS, height_m=4.0, built_up_area_sqm=100.0
        )

        result = classify(case_file)

        assert result.applies is False
        assert result.require_human_review_flag is False

    def test_an_undecidable_applicability_check_is_flagged(self):
        # Industrial with no hazard band: check_applicability raises. The
        # old code appended the note and returned UNFLAGGED, while the
        # identical failure one step later (the Table 7 lookup) did flag -
        # so the same blocker reached the user two different ways depending
        # on which line it happened to hit.
        case_file = CaseFile(
            session_id="s",
            occupancy_type=OccupancyType.INDUSTRIAL,
            industrial_hazard_band=None,
            height_m=20.0,
            built_up_area_sqm=3000.0,
        )

        result = classify(case_file)

        assert result.require_human_review_flag is True
        assert ReviewReasonCode.CLASSIFICATION_ERROR.value in {r.code.value for r in result.review_reasons}
